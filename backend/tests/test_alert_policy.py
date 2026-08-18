"""Unit tests for the 1.3.1 responsibility split: AlertPolicy + AlertBuilder.

These are pure (no database): AlertPolicy maps an event to its behaviour, and
AlertBuilder only constructs an Alert model.
"""
import uuid

import pytest

from models import Alert, Device, Event
from models.operations import (
    ALERT_ACTIVE,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from services.alert_builder import AlertBuilder
from services.alert_policy import AlertPolicy


def _event(event_type: str, severity: str = SEVERITY_WARNING, subject=None) -> Event:
    return Event(
        event_type=event_type, severity=severity, subject=subject, message="msg"
    )


@pytest.mark.parametrize(
    "event_type,expected_category",
    [
        ("HardwareChanged", "Hardware"),
        ("FirmwareChanged", "Firmware"),
        ("DeviceOffline", "Connectivity"),
        ("DeviceRecovered", "Connectivity"),
        ("NetworkReachabilityChanged", "Connectivity"),
        ("CollectorFailed", "Collector"),
        ("CredentialFailed", "Credential"),
        ("SensorThresholdExceeded", "Health"),
        ("SensorRecovered", "Health"),
        ("SomethingNew", "Other"),  # unknown types fall back, never crash
    ],
)
def test_policy_maps_event_type_to_operational_category(event_type, expected_category):
    policy = AlertPolicy.from_event(_event(event_type))
    assert policy.category == expected_category


@pytest.mark.parametrize(
    "event_type,auto_resolve",
    [
        ("DeviceOffline", True),
        ("CollectorFailed", True),
        ("CredentialFailed", True),
        ("SensorThresholdExceeded", True),
        ("NetworkReachabilityChanged", True),
        ("HardwareChanged", False),  # manual resolve
        ("FirmwareChanged", False),  # manual resolve
    ],
)
def test_policy_auto_resolve_flag(event_type, auto_resolve):
    assert AlertPolicy.from_event(_event(event_type)).auto_resolve is auto_resolve


def test_policy_severity_currently_mirrors_event():
    assert AlertPolicy.from_event(_event("FirmwareChanged", SEVERITY_INFO)).severity == (
        SEVERITY_INFO
    )


def test_builder_only_constructs_active_alert():
    device = Device(hostname="srv-1")
    device.id = uuid.uuid4()
    event = _event("SensorThresholdExceeded", SEVERITY_WARNING, subject="CPU Temp")
    event.id = uuid.uuid4()
    event.details = '{"sensor": "CPU Temp"}'

    policy = AlertPolicy.from_event(event)
    alert = AlertBuilder.build(event, device, policy)

    assert isinstance(alert, Alert)
    assert alert.event_id == event.id
    assert alert.device_id == device.id
    assert alert.event_type == "SensorThresholdExceeded"
    assert alert.category == "Health"
    assert alert.severity == SEVERITY_WARNING
    assert alert.status == ALERT_ACTIVE  # builder never resolves
    assert alert.subject == "CPU Temp"  # reused from the event, not re-parsed
    assert alert.auto_resolve is True
    assert alert.resolved_at is None and alert.resolved_by is None
