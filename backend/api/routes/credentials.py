"""Credential management endpoints (admin only). Passwords are write-only."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from database import get_db
from models import Credential, User
from schemas.credential import CredentialCreate, CredentialResponse, CredentialUpdate
from services.audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    record_audit,
    snapshot_entity,
)
from utils.crypto import encrypt_secret
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/credentials",
    tags=["credentials"],
    dependencies=[Depends(RequirePermission("credential.view"))],
)


def _to_response(credential: Credential) -> CredentialResponse:
    response = CredentialResponse.model_validate(credential)
    response.has_password = bool(credential.password_encrypted)
    return response


async def _get_credential(db: AsyncSession, credential_id: uuid.UUID) -> Credential:
    result = await db.execute(select(Credential).where(Credential.id == credential_id))
    credential = result.scalar_one_or_none()
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )
    return credential


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(db: AsyncSession = Depends(get_db)) -> list[CredentialResponse]:
    result = await db.execute(select(Credential).order_by(Credential.name))
    return [_to_response(c) for c in result.scalars().all()]


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credential(
    payload: CredentialCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("credential.create")),
) -> CredentialResponse:
    try:
        existing = await db.execute(select(Credential).where(Credential.name == payload.name))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Credential name already exists"
            )
        credential = Credential(
            name=payload.name,
            credential_type=payload.credential_type,
            username=payload.username,
            password_encrypted=encrypt_secret(payload.password),
            description=payload.description,
        )
        db.add(credential)
        await db.flush()
        record_audit(
            db, admin, ACTION_CREATE, "credential", credential.name, credential.id,
            new_value=snapshot_entity(credential),
        )
        await db.commit()
        await db.refresh(credential)
        logger.info("Credential %s created", credential.name)
        return _to_response(credential)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Credential creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Credential creation failed",
        ) from exc


@router.patch("/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: uuid.UUID,
    payload: CredentialUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("credential.update")),
) -> CredentialResponse:
    credential = await _get_credential(db, credential_id)
    old = snapshot_entity(credential)
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password:  # empty string keeps existing password
            credential.password_encrypted = encrypt_secret(password)
    for key, value in data.items():
        setattr(credential, key, value)
    record_audit(
        db, admin, ACTION_UPDATE, "credential", credential.name, credential.id,
        old_value=old, new_value=snapshot_entity(credential),
    )
    await db.commit()
    await db.refresh(credential)
    return _to_response(credential)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    credential_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("credential.delete")),
) -> None:
    credential = await _get_credential(db, credential_id)
    record_audit(
        db, admin, ACTION_DELETE, "credential", credential.name, credential.id,
        old_value=snapshot_entity(credential),
    )
    await db.delete(credential)
    await db.commit()
