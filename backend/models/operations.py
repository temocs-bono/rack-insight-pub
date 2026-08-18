"""Operations models (1.3.0): events, alerts, device history, alert settings.

Pipeline:  Collector -> Inventory Snapshot -> Event Engine -> Alert Engine -> UI

The collector only stores snapshots (the existing ``snapshots`` table + its
per-section inventory tables ARE the inventory snapshot store — one immutable
snapshot per successful collection). The Event Engine compares snapshot N-1 vs
snapshot N and generates Events; the Alert Engine turns Events into Alerts and
manages their lifecycle. Device history is an immutable, permanent record.

Event types are plain strings from ``EVENT_*`` below so future types can be
added without a migration.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.base import TimestampedModel

# --- Event types (extensible: add a constant, no schema change needed) -------
EVENT_HARDWARE_CHANGED = "HardwareChanged"
EVENT_FIRMWARE_CHANGED = "FirmwareChanged"
EVENT_DEVICE_OFFLINE = "DeviceOffline"
EVENT_DEVICE_RECOVERED = "DeviceRecovered"
EVENT_SENSOR_THRESHOLD_EXCEEDED = "SensorThresholdExceeded"
EVENT_SENSOR_RECOVERED = "SensorRecovered"
EVENT_COLLECTOR_FAILED = "CollectorFailed"
EVENT_CREDENTIAL_FAILED = "CredentialFailed"
EVENT_NETWORK_REACHABILITY_CHANGED = "NetworkReachabilityChanged"

# --- Alert severities / statuses ---------------------------------------------
SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"

ALERT_ACTIVE = "ACTIVE"
ALERT_RESOLVED = "RESOLVED"

# --- Alert categories (operational domain, distinct from event type) ---------
# Event Type = what happened; Alert Category = the operational domain the UI
# groups/filters by. The mapping lives in services.alert_policy.
CATEGORY_HARDWARE = "Hardware"
CATEGORY_FIRMWARE = "Firmware"
CATEGORY_CONNECTIVITY = "Connectivity"
CATEGORY_COLLECTOR = "Collector"
CATEGORY_CREDENTIAL = "Credential"
CATEGORY_HEALTH = "Health"
CATEGORY_OTHER = "Other"

# Event types whose alerts resolve automatically when the next collection shows
# normal state. Hardware/Firmware alerts stay ACTIVE until manually resolved.
# (These are event types, not the operational categories above.)
AUTO_RESOLVE_EVENT_TYPES = frozenset(
    {
        EVENT_DEVICE_OFFLINE,
        EVENT_SENSOR_THRESHOLD_EXCEEDED,
        EVENT_COLLECTOR_FAILED,
        EVENT_CREDENTIAL_FAILED,
        EVENT_NETWORK_REACHABILITY_CHANGED,
    }
)
# Backwards-compatible alias (the pre-1.3.1 name).
AUTO_RESOLVE_CATEGORIES = AUTO_RESOLVE_EVENT_TYPES

# --- Device history kinds -----------------------------------------------------
HISTORY_FIRMWARE_CHANGE = "firmware_change"
HISTORY_HARDWARE_CHANGE = "hardware_change"
HISTORY_COLLECTOR_FAILURE = "collector_failure"
HISTORY_MANUAL_RESOLVE = "manual_resolve"
HISTORY_DEVICE_RECOVERED = "device_recovered"


class Event(TimestampedModel):
    """One detected occurrence, produced only by the Event Engine."""

    __tablename__ = "events"

    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rack_device_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    # What actually changed (sensor name, DIMM slot, firmware component, NIC…),
    # set by the Event Engine. The Alert Engine reuses it verbatim and never
    # re-derives it from the JSON details.
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Snapshot N (and N-1) that produced this event; SET NULL keeps the event
    # meaningful even after snapshot retention removes old snapshots.
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    previous_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("snapshots.id", ondelete="SET NULL"), nullable=True
    )
    # JSON list of change items: [{section, identifier, field, old, new}, ...]
    details: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alert(TimestampedModel):
    """Alert lifecycle record. One Event creates one Alert."""

    __tablename__ = "alerts"

    event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rack_device_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # What happened (mirrors Event.event_type), kept alongside the operational
    # category so the lifecycle logic keys off the event type while the UI
    # filters by category.
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Operational domain the UI groups by (Hardware, Firmware, Connectivity…),
    # determined by AlertPolicy — no longer equal to event_type.
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=ALERT_ACTIVE, nullable=False, index=True
    )
    # Optional dedupe subject within a category (e.g. sensor name / section).
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_resolve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DeviceHistory(TimestampedModel):
    """Immutable, permanent device change history. Never updated, never
    deleted except by an explicitly enabled retention policy."""

    __tablename__ = "device_history"

    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rack_device_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )


class AlertSettings(TimestampedModel):
    """Singleton operational thresholds (extend with columns as needed)."""

    __tablename__ = "alert_settings"

    # State alerts (offline / collector failed / sensor breach) fire only after
    # this many consecutive occurrences — avoids alerting on a single blip.
    consecutive_failures_threshold: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False
    )
