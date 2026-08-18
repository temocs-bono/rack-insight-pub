"""AlertPolicy (1.3.1).

Maps an Event to its alert behaviour — the operational **category**, the alert
**severity**, and whether the alert **auto-resolves**. This is the one place
that owns those rules, so the Alert Engine can stay a thin orchestrator.

AlertPolicy is pure: it never touches the database, never creates or resolves
alerts, and never writes history. It only reads the Event it is given.

Severity currently mirrors the event's severity; future rules (e.g. escalate
FirmwareChanged to WARNING, or CollectorFailed to CRITICAL after N failures)
belong in ``_resolve_severity`` without changing any caller.
"""
from dataclasses import dataclass

from models import Event
from models.operations import (
    AUTO_RESOLVE_EVENT_TYPES,
    CATEGORY_COLLECTOR,
    CATEGORY_CONNECTIVITY,
    CATEGORY_CREDENTIAL,
    CATEGORY_FIRMWARE,
    CATEGORY_HARDWARE,
    CATEGORY_HEALTH,
    CATEGORY_OTHER,
    EVENT_COLLECTOR_FAILED,
    EVENT_CREDENTIAL_FAILED,
    EVENT_DEVICE_OFFLINE,
    EVENT_DEVICE_RECOVERED,
    EVENT_FIRMWARE_CHANGED,
    EVENT_HARDWARE_CHANGED,
    EVENT_NETWORK_REACHABILITY_CHANGED,
    EVENT_SENSOR_RECOVERED,
    EVENT_SENSOR_THRESHOLD_EXCEEDED,
)

# Event type (what happened) -> operational category (domain the UI groups by).
_CATEGORY_BY_EVENT_TYPE = {
    EVENT_HARDWARE_CHANGED: CATEGORY_HARDWARE,
    EVENT_FIRMWARE_CHANGED: CATEGORY_FIRMWARE,
    EVENT_DEVICE_OFFLINE: CATEGORY_CONNECTIVITY,
    EVENT_DEVICE_RECOVERED: CATEGORY_CONNECTIVITY,
    EVENT_NETWORK_REACHABILITY_CHANGED: CATEGORY_CONNECTIVITY,
    EVENT_COLLECTOR_FAILED: CATEGORY_COLLECTOR,
    EVENT_CREDENTIAL_FAILED: CATEGORY_CREDENTIAL,
    EVENT_SENSOR_THRESHOLD_EXCEEDED: CATEGORY_HEALTH,
    EVENT_SENSOR_RECOVERED: CATEGORY_HEALTH,
}


def _resolve_severity(event: Event) -> str:
    """Severity for the alert. Currently the event's own severity; future
    per-event-type rules go here."""
    return event.severity


@dataclass(frozen=True)
class AlertPolicy:
    category: str
    severity: str
    auto_resolve: bool

    @classmethod
    def from_event(cls, event: Event) -> "AlertPolicy":
        return cls(
            category=_CATEGORY_BY_EVENT_TYPE.get(event.event_type, CATEGORY_OTHER),
            severity=_resolve_severity(event),
            auto_resolve=event.event_type in AUTO_RESOLVE_EVENT_TYPES,
        )
