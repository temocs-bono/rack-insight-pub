"""Rack / rack layout schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.device import DeviceStatus, DeviceType
from models.rack import DEFAULT_RACK_HEIGHT_U


class RackCreate(BaseModel):
    cluster_id: uuid.UUID
    name: str = Field(min_length=1, max_length=128)
    location: str | None = None
    height: int = Field(default=DEFAULT_RACK_HEIGHT_U, ge=1, le=60)
    description: str | None = None


class RackUpdate(BaseModel):
    cluster_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    location: str | None = None
    height: int | None = Field(default=None, ge=1, le=60)
    description: str | None = None


class RackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cluster_id: uuid.UUID
    name: str
    location: str | None
    height: int
    description: str | None
    created_at: datetime
    updated_at: datetime


class RackSummary(RackResponse):
    device_count: int = 0
    online_count: int = 0
    offline_count: int = 0
    warning_count: int = 0


class LayoutDevice(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hostname: str
    display_name: str | None
    device_type: DeviceType
    vendor: str | None
    model: str | None
    management_ip: str | None
    ilo_ip: str | None
    status: DeviceStatus


class RackUnitEntry(BaseModel):
    u_position: int = Field(ge=1)
    height: int = Field(default=1, ge=1)
    device_id: uuid.UUID | None = None


class RackUnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    u_position: int
    height: int
    device: LayoutDevice | None


class RackLayoutResponse(BaseModel):
    rack: RackResponse
    units: list[RackUnitResponse]


class RackLayoutUpdate(BaseModel):
    """Full replacement of a rack layout (spreadsheet-style editor save)."""

    units: list[RackUnitEntry]


MAX_BULK_RACKS = 100


class RackBulkCreate(BaseModel):
    """Create <count> racks named <prefix>-<start_index>.. (F7)."""

    cluster_id: uuid.UUID
    prefix: str = Field(min_length=1, max_length=100)
    count: int = Field(ge=1, le=MAX_BULK_RACKS)
    start_index: int = Field(default=1, ge=0)
    height: int = Field(default=DEFAULT_RACK_HEIGHT_U, ge=1, le=60)
    location: str | None = None


class RackBulkCreateResult(BaseModel):
    created: list[RackResponse]
    skipped: list[str]
