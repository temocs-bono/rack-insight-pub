"""Alert Engine (1.3.0, slimmed in 1.3.1).

Orchestrates the alert lifecycle — it no longer owns the business rules. For
each event it:

    persist events
      -> resolve existing alerts if required (recovery / escalation)
      -> deduplicate active state alerts
      -> ask AlertPolicy for category / severity / auto-resolve
      -> build the Alert with AlertBuilder
      -> persist the Alert
      -> record the immutable history entry

Behaviour is unchanged from 1.3.0: one event -> one alert; recovery events
create already-resolved INFO alerts; Hardware/Firmware alerts require a manual
resolve; state alerts auto-resolve; active state alerts are deduplicated;
history is immutable.

Category mapping and severity/auto-resolve rules live in ``alert_policy``;
Alert construction lives in ``alert_builder``; the subject lives on the Event
(set by the Event Engine). This module keeps only the orchestration and the
database reads/writes.
"""
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Alert, Device, Event
from models.operations import (
    ALERT_ACTIVE,
    ALERT_RESOLVED,
    EVENT_COLLECTOR_FAILED,
    EVENT_DEVICE_OFFLINE,
    EVENT_DEVICE_RECOVERED,
    EVENT_SENSOR_RECOVERED,
    EVENT_SENSOR_THRESHOLD_EXCEEDED,
    HISTORY_COLLECTOR_FAILURE,
    HISTORY_DEVICE_RECOVERED,
    HISTORY_FIRMWARE_CHANGE,
    HISTORY_HARDWARE_CHANGE,
    HISTORY_MANUAL_RESOLVE,
    EVENT_CREDENTIAL_FAILED,
    EVENT_FIRMWARE_CHANGED,
    EVENT_HARDWARE_CHANGED,
    EVENT_NETWORK_REACHABILITY_CHANGED,
)
from services.alert_builder import AlertBuilder
from services.alert_policy import AlertPolicy
from services.history_service import record_history
from utils.logging import get_logger

logger = get_logger(__name__)

# Event types a DeviceRecovered event resolves (state alerts).
_STATE_EVENT_TYPES = (
    EVENT_DEVICE_OFFLINE,
    EVENT_COLLECTOR_FAILED,
    EVENT_CREDENTIAL_FAILED,
    EVENT_NETWORK_REACHABILITY_CHANGED,
)

_HISTORY_KIND_BY_EVENT = {
    EVENT_HARDWARE_CHANGED: HISTORY_HARDWARE_CHANGE,
    EVENT_FIRMWARE_CHANGED: HISTORY_FIRMWARE_CHANGE,
    EVENT_COLLECTOR_FAILED: HISTORY_COLLECTOR_FAILURE,
    EVENT_DEVICE_OFFLINE: HISTORY_COLLECTOR_FAILURE,
    EVENT_CREDENTIAL_FAILED: HISTORY_COLLECTOR_FAILURE,
    EVENT_DEVICE_RECOVERED: HISTORY_DEVICE_RECOVERED,
}

_RECOVERY_EVENT_TYPES = (EVENT_DEVICE_RECOVERED, EVENT_SENSOR_RECOVERED)


async def _active_alerts(
    db: AsyncSession, device_id: uuid.UUID, event_types: tuple[str, ...] | None = None
) -> list[Alert]:
    """Active alerts for a device, optionally restricted to given event types.

    Alert lifecycle keys off the event type (what happened), not the
    operational category (which the UI filters by)."""
    query = select(Alert).where(
        Alert.device_id == device_id, Alert.status == ALERT_ACTIVE
    )
    if event_types:
        query = query.where(Alert.event_type.in_(event_types))
    return list((await db.execute(query)).scalars().all())


async def active_state_alert_context(
    db: AsyncSession, device_id: uuid.UUID
) -> tuple[bool, set[str]]:
    """(has active offline/collector/credential alert, active sensor subjects).

    Supplied to the Event Engine so it can emit recovery events without
    knowing how alerts are stored.
    """
    state = await _active_alerts(db, device_id, _STATE_EVENT_TYPES)
    sensors = await _active_alerts(db, device_id, (EVENT_SENSOR_THRESHOLD_EXCEEDED,))
    return bool(state), {a.subject for a in sensors if a.subject}


def _resolve(alert: Alert, resolved_by: str | None) -> None:
    alert.status = ALERT_RESOLVED
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = resolved_by


async def _resolve_counterparts(db: AsyncSession, device: Device, event: Event) -> None:
    """Recovery/escalation: close the active alerts a new event supersedes."""
    if event.event_type == EVENT_DEVICE_RECOVERED:
        for alert in await _active_alerts(db, device.id, _STATE_EVENT_TYPES):
            _resolve(alert, "system")
    elif event.event_type == EVENT_SENSOR_RECOVERED:
        for alert in await _active_alerts(
            db, device.id, (EVENT_SENSOR_THRESHOLD_EXCEEDED,)
        ):
            if event.subject is None or alert.subject == event.subject:
                _resolve(alert, "system")
    elif event.event_type == EVENT_DEVICE_OFFLINE:
        # Escalation: offline supersedes plain collector-failure alerts.
        for alert in await _active_alerts(db, device.id, (EVENT_COLLECTOR_FAILED,)):
            _resolve(alert, "system")


async def _is_duplicate_active(
    db: AsyncSession, device: Device, event: Event
) -> bool:
    """True if an identical active state alert already exists (same event type
    and subject), so a persisting condition doesn't re-alert every collection."""
    for alert in await _active_alerts(db, device.id, (event.event_type,)):
        if alert.subject == event.subject:
            return True
    return False


def _record_history_for(db: AsyncSession, device: Device, event: Event) -> None:
    kind = _HISTORY_KIND_BY_EVENT.get(event.event_type)
    if kind is None:
        return
    details = None
    if event.details:
        try:
            details = json.loads(event.details)
        except (ValueError, TypeError):
            details = None
    record_history(
        db, device.id, kind, event.message, details=details, event_id=event.id
    )


async def process_events(
    db: AsyncSession, device: Device, events: list[Event]
) -> list[Alert]:
    """Persist events, create/resolve alerts, and append history entries.

    Rows are added to the caller's session; the caller commits.
    """
    for event in events:
        db.add(event)
    await db.flush()  # events need ids for alert/history FKs

    created: list[Alert] = []
    for event in events:
        await _resolve_counterparts(db, device, event)

        policy = AlertPolicy.from_event(event)

        # Deduplicate active state alerts (the auto-resolving ones).
        if policy.auto_resolve and await _is_duplicate_active(db, device, event):
            continue

        alert = AlertBuilder.build(event, device, policy)
        # Recovery events create an already-resolved INFO alert so the timeline
        # stays complete without leaving noise active.
        if event.event_type in _RECOVERY_EVENT_TYPES:
            _resolve(alert, "system")
        db.add(alert)
        created.append(alert)

        _record_history_for(db, device, event)

    if created:
        await db.flush()
        logger.info(
            "Alert engine: %d alert(s) for device %s", len(created), device.hostname
        )
    return created


async def resolve_alert_manually(
    db: AsyncSession, alert: Alert, resolved_by: str
) -> Alert:
    """Administrator resolve (hardware/firmware alerts, or forcing a state
    alert closed). Recorded in the device history."""
    _resolve(alert, resolved_by)
    record_history(
        db,
        alert.device_id,
        HISTORY_MANUAL_RESOLVE,
        f"Alert resolved by {resolved_by}: {alert.message}",
        details={
            "alert_id": str(alert.id),
            "category": alert.category,
            "event_type": alert.event_type,
        },
        event_id=alert.event_id,
    )
    return alert
