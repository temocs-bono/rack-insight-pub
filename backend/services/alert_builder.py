"""AlertBuilder (1.3.1).

Constructs an ``Alert`` model from an Event, its Device, and the AlertPolicy.
That is its only job — it never resolves, deduplicates, writes history, or
touches the database. Every alert is built ACTIVE; the Alert Engine decides
whether to immediately resolve it (e.g. recovery events).
"""
from models import Alert, Device, Event
from models.operations import ALERT_ACTIVE
from services.alert_policy import AlertPolicy


class AlertBuilder:
    @staticmethod
    def build(event: Event, device: Device, policy: AlertPolicy) -> Alert:
        return Alert(
            event_id=event.id,
            device_id=device.id,
            event_type=event.event_type,
            category=policy.category,
            severity=policy.severity,
            status=ALERT_ACTIVE,
            subject=event.subject,
            message=event.message,
            details=event.details,
            auto_resolve=policy.auto_resolve,
        )
