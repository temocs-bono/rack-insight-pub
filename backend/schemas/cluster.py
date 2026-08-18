"""Cluster schemas including dashboard summary."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClusterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    vendor: str | None = None
    site: str | None = None
    description: str | None = None


class ClusterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    vendor: str | None = None
    site: str | None = None
    description: str | None = None


class ClusterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    vendor: str | None
    site: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class ClusterSummary(ClusterResponse):
    """Dashboard card: counts derived from racks/devices."""

    rack_count: int = 0
    device_count: int = 0
    server_count: int = 0
    switch_count: int = 0
    online_count: int = 0
    warning_count: int = 0
    last_refresh: datetime | None = None
