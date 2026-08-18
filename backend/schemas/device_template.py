"""Device template schemas (hardware model, no deployment data)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeviceTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    vendor: str | None = None
    model: str | None = None
    cpu: str | None = None
    memory: str | None = None
    storage: str | None = None
    firmware: str | None = None
    nic: str | None = None
    description: str | None = None


class DeviceTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    vendor: str | None = None
    model: str | None = None
    cpu: str | None = None
    memory: str | None = None
    storage: str | None = None
    firmware: str | None = None
    nic: str | None = None
    description: str | None = None


class DeviceTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    vendor: str | None
    model: str | None
    cpu: str | None
    memory: str | None
    storage: str | None
    firmware: str | None
    nic: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class DeviceTemplateSummary(DeviceTemplateResponse):
    instance_count: int = 0
