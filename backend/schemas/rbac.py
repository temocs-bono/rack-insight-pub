"""Access Management (RBAC) request/response schemas.

Password hashes and other secrets are never included in any response model.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.rbac import SCOPE_GLOBAL


# --- Permissions (read-only) ------------------------------------------------
class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    category: str
    description: str | None


# --- Roles ------------------------------------------------------------------
class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    permission_codes: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    permission_codes: list[str] | None = None


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    permission_codes: list[str]
    created_at: datetime
    updated_at: datetime


class RoleGroupRef(BaseModel):
    id: uuid.UUID
    name: str


class RoleDetailResponse(RoleResponse):
    """Role plus the groups it is bound to and how many users inherit it."""

    user_groups: list[RoleGroupRef]
    effective_user_count: int


# --- User groups ------------------------------------------------------------
class UserGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    member_ids: list[uuid.UUID] = Field(default_factory=list)
    role_ids: list[uuid.UUID] = Field(default_factory=list)


class UserGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    member_ids: list[uuid.UUID] | None = None
    role_ids: list[uuid.UUID] | None = None


class UserGroupResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    member_ids: list[uuid.UUID]
    member_count: int
    role_ids: list[uuid.UUID]
    role_names: list[str]
    created_at: datetime
    updated_at: datetime


# --- Role bindings ----------------------------------------------------------
class RoleBindingCreate(BaseModel):
    user_group_id: uuid.UUID
    role_id: uuid.UUID
    scope_type: str = SCOPE_GLOBAL
    scope_id: uuid.UUID | None = None


class RoleBindingResponse(BaseModel):
    id: uuid.UUID
    user_group_id: uuid.UUID
    user_group_name: str
    role_id: uuid.UUID
    role_name: str
    scope_type: str
    scope_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
