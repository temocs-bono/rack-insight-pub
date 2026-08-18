"""User management schemas. Password hashes are never exposed."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.user import STATUS_ACTIVE, UserRole


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.USER
    display_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    status: str = STATUS_ACTIVE
    group_ids: list[uuid.UUID] = Field(default_factory=list)


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: UserRole | None = None
    display_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    status: str | None = None
    enabled: bool | None = None
    group_ids: list[uuid.UUID] | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: UserRole
    display_name: str | None
    email: str | None
    status: str
    enabled: bool
    last_login: datetime | None
    group_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
