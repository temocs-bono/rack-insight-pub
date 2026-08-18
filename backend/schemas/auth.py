"""Auth request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, Field

from models.user import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: str
    username: str
    role: UserRole
    display_name: str | None = None
    email: str | None = None
    last_login: datetime | None
    # Effective permission codes resolved through User Groups -> Roles.
    permissions: list[str] = []
    # Menu key -> required permission, so the frontend sidebar stays in sync.
    menus: list[dict[str, str]] = []
