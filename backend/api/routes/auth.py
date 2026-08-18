"""Authentication endpoints: login, token refresh, current user."""
import uuid
from datetime import datetime, timezone

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from database import get_db
from models import User
from rbac_catalog import MENU_PERMISSIONS
from schemas.auth import LoginRequest, MeResponse, RefreshRequest, TokenResponse
from services.rbac_service import get_user_permissions
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        result = await db.execute(select(User).where(User.username == payload.username))
        user = result.scalar_one_or_none()
        if user is None or not user.enabled or not verify_password(
            payload.password, user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )
        user.last_login = datetime.now(timezone.utc)
        await db.commit()
        logger.info("User %s logged in", user.username)
        return TokenResponse(
            access_token=create_access_token(str(user.id)),
            refresh_token=create_refresh_token(str(user.id)),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Login failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed"
        ) from exc


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    try:
        token_payload = decode_token(payload.refresh_token, TOKEN_TYPE_REFRESH)
        user_id = uuid.UUID(str(token_payload.get("sub")))
    except (pyjwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled"
        )
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    permissions = await get_user_permissions(db, user)
    return MeResponse(
        id=str(user.id),
        username=user.username,
        role=user.role,
        display_name=user.display_name,
        email=user.email,
        last_login=user.last_login,
        permissions=sorted(permissions),
        menus=[dict(m) for m in MENU_PERMISSIONS],
    )
