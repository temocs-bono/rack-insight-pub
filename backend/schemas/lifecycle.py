"""Lifecycle / retention schemas (F5)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RetentionPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    retention_days: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class RetentionPolicyUpdate(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    enabled: bool | None = None


class CleanupResult(BaseModel):
    deleted: dict[str, int]
    total: int
