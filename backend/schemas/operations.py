"""Operations & Alert Center schemas (1.3.0)."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChangeItemResponse(BaseModel):
    section: str
    identifier: str
    change: str
    field: str | None = None
    old: str | None = None
    new: str | None = None


class AlertResponse(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    hostname: str
    display_name: str | None
    vendor: str | None
    model: str | None
    rack_id: uuid.UUID | None
    rack_name: str | None
    cluster_id: uuid.UUID | None
    cluster_name: str | None
    # event_type = what happened; category = operational domain (UI filters by
    # category). See services.alert_policy.
    event_type: str
    category: str
    severity: str
    status: str
    subject: str | None
    message: str
    changes: list[ChangeItemResponse] = Field(default_factory=list)
    details: dict[str, Any] | None = None
    auto_resolve: bool
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None


class AlertPage(BaseModel):
    items: list[AlertResponse]
    total: int
    page: int
    page_size: int


class HistoryEntryResponse(BaseModel):
    id: uuid.UUID
    device_id: uuid.UUID
    hostname: str | None
    kind: str
    title: str
    changes: list[ChangeItemResponse] = Field(default_factory=list)
    details: dict[str, Any] | None = None
    created_at: datetime


class HistoryPage(BaseModel):
    items: list[HistoryEntryResponse]
    total: int
    page: int
    page_size: int


class DashboardAlerts(BaseModel):
    active_critical: int
    active_warning: int
    active_info: int
    offline_devices: int
    healthy_devices: int
    latest_alerts: list[AlertResponse]
    critical_devices: list[AlertResponse]
    recent_hardware_changes: list[HistoryEntryResponse]
    recent_firmware_changes: list[HistoryEntryResponse]


class DashboardHealth(BaseModel):
    healthy: int
    warning: int
    critical: int
    unknown: int
    offline: int
    total: int


class SensorSummary(BaseModel):
    group: str  # temperature / power / fan / other
    total: int
    ok: int
    breached: int
    label: str  # Healthy / Warning / Critical / Unknown


class HealthTimelinePoint(BaseModel):
    collected_at: datetime
    score: int
    label: str


class DeviceHealthResponse(BaseModel):
    overall_label: str  # Healthy / Warning / Critical / Unknown
    overall_score: int | None
    status: str
    last_collected_at: datetime | None
    sensor_groups: list[SensorSummary]
    storage_label: str
    memory_label: str
    network_label: str
    timeline: list[HealthTimelinePoint]


class AlertSettingsResponse(BaseModel):
    consecutive_failures_threshold: int


class AlertSettingsUpdate(BaseModel):
    consecutive_failures_threshold: int = Field(ge=1, le=100)
