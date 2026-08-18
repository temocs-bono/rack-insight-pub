"""Unit tests for the health score policy."""
from models import DeviceStatus, Sensor, Snapshot
from services.health_service import compute_health


def _snapshot(redfish: bool = True) -> Snapshot:
    return Snapshot(
        collector_version="test",
        redfish_success=redfish,
        ssh_success=False,
        virsh_success=False,
        duration_ms=0,
    )


def test_perfect_score_is_healthy() -> None:
    health = compute_health(DeviceStatus.ONLINE, _snapshot(), [], [], [])
    assert health.score == 100
    assert health.label == "Healthy"


def test_offline_no_snapshot_is_critical() -> None:
    health = compute_health(DeviceStatus.OFFLINE, None, [], [], [])
    assert health.score < 80
    assert health.label == "Critical"


def test_failed_fan_reduces_score() -> None:
    bad_fan = Sensor(type="Fan", name="Fan 1", value="0", unit="RPM", status="Critical")
    health = compute_health(DeviceStatus.ONLINE, _snapshot(), [bad_fan], [], [])
    assert health.score == 90
    assert health.label == "Warning"
