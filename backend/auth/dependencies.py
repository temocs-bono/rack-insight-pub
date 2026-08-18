"""FastAPI auth dependencies: current user resolution and admin guard."""
import uuid

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import TOKEN_TYPE_ACCESS, decode_token
from database import get_db
from models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)

# Short-lived cookie that authenticates plugin UI/proxy requests the browser
# makes without an Authorization header (iframe navigations, asset loads). It is
# scoped to /api/plugins and SameSite=Strict, so it never leaks elsewhere and is
# CSRF-safe. Minted by POST /api/plugins/ui-session.
PLUGIN_UI_COOKIE = "ri_plugin_ui"


async def _user_from_token(token: str, db: AsyncSession) -> User:
    try:
        payload = decode_token(token, TOKEN_TYPE_ACCESS)
        user_id = uuid.UUID(str(payload.get("sub")))
    except (pyjwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled"
        )
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return await _user_from_token(credentials.credentials, db)


async def get_current_user_flexible(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Like ``get_current_user`` but also accepts the plugin-UI cookie. Used only
    by the plugin UI / API proxy so an iframe (which cannot set an Authorization
    header) can still authenticate same-origin."""
    token = credentials.credentials if credentials else request.cookies.get(PLUGIN_UI_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return await _user_from_token(token, db)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator privileges required"
        )
    return user


def RequirePermission(permission: str):
    """Centralized authorization guard.

    Returns a FastAPI dependency that resolves the current user, checks the
    given business-action permission through the RBAC chain, and raises HTTP 403
    when it is missing. Use as ``actor: User = Depends(RequirePermission("x.y"))``
    so the authenticated user is still available to the handler.
    """

    async def _dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # Imported lazily to avoid a circular import (services -> models -> ...).
        from services.rbac_service import user_has_permission

        if not await user_has_permission(db, user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        return user

    return _dependency


def RequirePluginAccess(permission: str):
    """Like ``RequirePermission`` but authenticates via Bearer **or** the plugin
    UI cookie (``get_current_user_flexible``).

    Plugin UI/proxy requests the browser makes from inside an iframe cannot carry
    an ``Authorization`` header, so they authenticate with the short-lived
    ``ri_plugin_ui`` cookie instead. The RBAC permission check is identical.
    """

    async def _dependency(
        user: User = Depends(get_current_user_flexible),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from services.rbac_service import user_has_permission

        if not await user_has_permission(db, user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        return user

    return _dependency
