"""Credential schemas. Passwords are write-only: accepted on create/update,
never included in any response."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.credential import CredentialType


class CredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    credential_type: CredentialType
    username: str | None = None
    password: str | None = Field(default=None, max_length=256)
    description: str | None = None


class CredentialUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    credential_type: CredentialType | None = None
    username: str | None = None
    password: str | None = Field(default=None, max_length=256)
    description: str | None = None


class CredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    credential_type: CredentialType
    username: str | None
    description: str | None
    has_password: bool = False
    created_at: datetime
    updated_at: datetime
