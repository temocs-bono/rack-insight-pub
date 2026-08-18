"""Collector management schemas: per-device status and run logs."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.device import DeviceStatus, DeviceType


class CollectorRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    success: bool
    duration_ms: int
    message: str | None
    trigger: str | None
    error_code: str | None = None
    readable_message: str | None = None
    created_at: datetime


class CollectorDeviceStatus(BaseModel):
    device_id: uuid.UUID
    hostname: str
    display_name: str | None
    device_type: DeviceType
    status: DeviceStatus
    rack_name: str | None = None
    cluster_name: str | None = None
    last_snapshot_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_error_readable: str | None = None
    health_score: int | None = None
    health_label: str | None = None
