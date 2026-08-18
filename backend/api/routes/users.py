"""User management endpoints (Access Management, permission-guarded)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from auth.security import hash_password
from database import get_db
from models import User, UserGroup, UserGroupMember
from models.user import STATUS_ACTIVE, STATUS_DISABLED
from schemas.user import UserCreate, UserResponse, UserUpdate
from services.audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    record_audit,
    snapshot_entity,
)
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


async def _group_ids_for(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.execute(
        select(UserGroupMember.user_group_id).where(UserGroupMember.user_id == user_id)
    )
    return list(rows.scalars().all())


def _serialize(user: User, group_ids: list[uuid.UUID]) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        display_name=user.display_name,
        email=user.email,
        status=user.status,
        enabled=user.enabled,
        last_login=user.last_login,
        group_ids=group_ids,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _validate_groups(db: AsyncSession, group_ids: list[uuid.UUID]) -> None:
    if not group_ids:
        return
    found = await db.execute(select(UserGroup.id).where(UserGroup.id.in_(group_ids)))
    if set(found.scalars().all()) != set(group_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown user group id"
        )


async def _set_memberships(
    db: AsyncSession, user_id: uuid.UUID, group_ids: list[uuid.UUID]
) -> None:
    current = set(await _group_ids_for(db, user_id))
    wanted = set(group_ids)
    for gid in wanted - current:
        db.add(UserGroupMember(user_group_id=gid, user_id=user_id))
    if current - wanted:
        stale = await db.execute(
            select(UserGroupMember).where(
                UserGroupMember.user_id == user_id,
                UserGroupMember.user_group_id.in_(current - wanted),
            )
        )
        for member in stale.scalars().all():
            await db.delete(member)


@router.get("", response_model=list[UserResponse], dependencies=[Depends(RequirePermission("user.view"))])
async def list_users(
    page: int | None = None,
    page_size: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    query = select(User).order_by(User.username)
    if page is not None and page_size is not None:
        query = query.offset((page - 1) * page_size).limit(page_size)
    users = list((await db.execute(query)).scalars().all())
    if not users:
        return []

    # Batch-load memberships to avoid N+1.
    memberships = await db.execute(
        select(UserGroupMember.user_id, UserGroupMember.user_group_id).where(
            UserGroupMember.user_id.in_([u.id for u in users])
        )
    )
    by_user: dict[uuid.UUID, list[uuid.UUID]] = {}
    for user_id, group_id in memberships.all():
        by_user.setdefault(user_id, []).append(group_id)
    return [_serialize(u, by_user.get(u.id, [])) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("user.create")),
) -> UserResponse:
    try:
        existing = await db.execute(select(User).where(User.username == payload.username))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Username already exists"
            )
        await _validate_groups(db, payload.group_ids)
        enabled = payload.status != STATUS_DISABLED
        user = User(
            username=payload.username,
            password_hash=hash_password(payload.password),
            role=payload.role,
            display_name=payload.display_name,
            email=payload.email,
            status=STATUS_ACTIVE if enabled else STATUS_DISABLED,
            enabled=enabled,
        )
        db.add(user)
        await db.flush()
        await _set_memberships(db, user.id, payload.group_ids)
        record_audit(
            db, actor, ACTION_CREATE, "user", user.username, user.id,
            new_value=snapshot_entity(user),
        )
        await db.commit()
        await db.refresh(user)
        logger.info("User %s created", user.username)
        return _serialize(user, await _group_ids_for(db, user.id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("User creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User creation failed"
        ) from exc


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("user.update")),
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    old = snapshot_entity(user)
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.email is not None:
        user.email = payload.email
    # status and enabled are kept consistent (status is the display field).
    if payload.status is not None:
        user.status = payload.status
        user.enabled = payload.status != STATUS_DISABLED
    if payload.enabled is not None:
        user.enabled = payload.enabled
        user.status = STATUS_ACTIVE if payload.enabled else STATUS_DISABLED
    if payload.group_ids is not None:
        await _validate_groups(db, payload.group_ids)
        await _set_memberships(db, user.id, payload.group_ids)
    record_audit(
        db, actor, ACTION_UPDATE, "user", user.username, user.id,
        old_value=old, new_value=snapshot_entity(user),
    )
    await db.commit()
    await db.refresh(user)
    return _serialize(user, await _group_ids_for(db, user.id))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("user.delete")),
) -> None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account"
        )
    record_audit(
        db, actor, ACTION_DELETE, "user", user.username, user.id,
        old_value=snapshot_entity(user),
    )
    await db.delete(user)
    await db.commit()
