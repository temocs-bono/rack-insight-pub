"""Tests for 1.3.0: snapshot pipeline, event engine, alert engine, history."""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from collectors.base import CollectorResult
from collectors.manager import CollectionOutcome
from collectors.errors import ERROR_AUTH_FAILED, ERROR_HOST_UNREACHABLE


@pytest_asyncio.fixture()
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/v130.db")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/0")
    import config as app_config

    app_config.get_settings.cache_clear()
    import importlib

    import database.session as session_mod
    importlib.reload(session_mod)
    import database as db_pkg
    importlib.reload(db_pkg)
    import main as app_main
    importlib.reload(app_main)
    from database.migrations import run_migrations

    await run_migrations()
    await app_main._bootstrap_admin()
    async with AsyncClient(
        transport=ASGITransport(app=app_main.app), base_url="http://test"
    ) as c:
        token = (
            await c.post(
                "/api/auth/login", json={"username": "admin", "password": "admin123!"}
            )
        ).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    await session_mod.engine.dispose()
    app_config.get_settings.cache_clear()


class FakeManager:
    """Deterministic replacement for CollectorManager.

    ``queue`` holds one spec per upcoming collection:
    {"fail": True, "error_code": ...} or
    {"firmwares": [...], "memories": [...], "sensors": [...]}.
    """

    queue: list[dict] = []
    _clock = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)

    def __init__(self) -> None:  # pipeline instantiates it fresh each cycle
        pass

    async def collect_device(self, db, device):
        from models import DeviceStatus, Firmware, Memory, Sensor, Snapshot

        spec = FakeManager.queue.pop(0)
        if spec.get("fail"):
            result = CollectorResult(
                collector_name="redfish",
                success=False,
                error="collection failed",
                error_code=spec.get("error_code", ERROR_HOST_UNREACHABLE),
                duration_ms=5,
            )
            return CollectionOutcome(
                snapshot=None, results=[result], status=DeviceStatus.OFFLINE, system={}
            )

        # Strictly increasing collected_at so snapshot ordering is deterministic.
        FakeManager._clock += timedelta(minutes=5)
        snapshot = Snapshot(
            device_id=device.id,
            collected_at=FakeManager._clock,
            collector_version="test",
            redfish_success=True,
            duration_ms=5,
        )
        db.add(snapshot)
        await db.flush()
        for firmware in spec.get("firmwares", []):
            db.add(Firmware(snapshot_id=snapshot.id, **firmware))
        for memory in spec.get("memories", []):
            db.add(Memory(snapshot_id=snapshot.id, **memory))
        for sensor in spec.get("sensors", []):
            db.add(Sensor(snapshot_id=snapshot.id, **sensor))
        result = CollectorResult(collector_name="redfish", success=True, duration_ms=5)
        return CollectionOutcome(
            snapshot=snapshot, results=[result], status=DeviceStatus.ONLINE, system={}
        )


@pytest_asyncio.fixture()
async def device_id(client, monkeypatch) -> str:
    import services.snapshot_service as snapshot_service

    monkeypatch.setattr(snapshot_service, "CollectorManager", FakeManager)
    FakeManager.queue = []
    FakeManager._clock = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)

    cluster = (await client.post("/api/clusters", json={"name": "ops-c1"})).json()
    rack = (
        await client.post("/api/racks", json={"cluster_id": cluster["id"], "name": "R1"})
    ).json()
    device = (
        await client.post(
            "/api/devices",
            json={"rack_id": rack["id"], "hostname": "srv-1", "device_type": "SERVER"},
        )
    ).json()
    return device["id"]


async def _refresh(client: AsyncClient, device_id: str, spec: dict) -> int:
    FakeManager.queue.append(spec)
    response = await client.post(f"/api/devices/{device_id}/refresh")
    return response.status_code


BASELINE = {
    "firmwares": [{"component": "BIOS", "version": "2.10"}],
    "memories": [{"slot": "DIMM1", "capacity_gb": 256}],
    "sensors": [{"type": "temperature", "name": "CPU Temp", "value": "45", "status": "ok"}],
}


@pytest.mark.asyncio
async def test_first_collection_creates_no_change_alerts(client, device_id) -> None:
    assert await _refresh(client, device_id, BASELINE) == 200
    alerts = (await client.get("/api/alerts")).json()
    assert alerts["total"] == 0


@pytest.mark.asyncio
async def test_firmware_change_creates_manual_resolve_alert(client, device_id) -> None:
    await _refresh(client, device_id, BASELINE)
    await _refresh(
        client, device_id,
        {**BASELINE, "firmwares": [{"component": "BIOS", "version": "2.30"}]},
    )

    alerts = (await client.get("/api/alerts")).json()
    assert alerts["total"] == 1
    alert = alerts["items"][0]
    # event_type = what happened; category = operational domain (1.3.1).
    assert alert["event_type"] == "FirmwareChanged"
    assert alert["category"] == "Firmware"
    assert alert["subject"] == "BIOS"
    assert alert["severity"] == "INFO"
    assert alert["status"] == "ACTIVE"
    assert alert["auto_resolve"] is False
    change = alert["changes"][0]
    assert (change["old"], change["new"]) == ("2.10", "2.30")

    # Filtering by operational category (domain) works.
    assert (await client.get("/api/alerts?category=Firmware")).json()["total"] == 1
    assert (await client.get("/api/alerts?category=Hardware")).json()["total"] == 0

    # Firmware alerts survive further normal collections (manual resolve only).
    await _refresh(
        client, device_id,
        {**BASELINE, "firmwares": [{"component": "BIOS", "version": "2.30"}]},
    )
    still = (await client.get(f"/api/alerts/{alert['id']}")).json()
    assert still["status"] == "ACTIVE"

    resolved = await client.patch(f"/api/alerts/{alert['id']}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolved_by"] == "admin"
    # Double-resolve is rejected.
    assert (await client.patch(f"/api/alerts/{alert['id']}/resolve")).status_code == 409

    # History: firmware change + manual resolve are permanent records.
    history = (await client.get(f"/api/history/device/{device_id}")).json()
    kinds = [h["kind"] for h in history["items"]]
    assert "firmware_change" in kinds
    assert "manual_resolve" in kinds


@pytest.mark.asyncio
async def test_memory_change_creates_hardware_alert(client, device_id) -> None:
    await _refresh(client, device_id, BASELINE)
    await _refresh(
        client, device_id,
        {**BASELINE, "memories": [{"slot": "DIMM1", "capacity_gb": 512}]},
    )
    alerts = (await client.get("/api/alerts?event_type=HardwareChanged")).json()
    assert alerts["total"] == 1
    alert = alerts["items"][0]
    assert alert["event_type"] == "HardwareChanged"
    assert alert["category"] == "Hardware"
    assert alert["subject"] == "Memory"
    assert alert["severity"] == "WARNING"
    assert alert["changes"][0]["section"] == "Memory"
    assert (alert["changes"][0]["old"], alert["changes"][0]["new"]) == ("256", "512")
    # Category (domain) groups the underlying event type.
    assert (await client.get("/api/alerts?category=Hardware")).json()["total"] == 1


@pytest.mark.asyncio
async def test_offline_alert_after_threshold_and_auto_recovery(client, device_id) -> None:
    await _refresh(client, device_id, BASELINE)

    # Failure 1 -> CollectorFailed WARNING (below offline threshold of 3).
    assert await _refresh(client, device_id, {"fail": True}) == 502
    alerts = (await client.get("/api/alerts?status=ACTIVE")).json()
    assert [a["event_type"] for a in alerts["items"]] == ["CollectorFailed"]

    # Failure 2 -> deduplicated, still a single active alert.
    await _refresh(client, device_id, {"fail": True})
    alerts = (await client.get("/api/alerts?status=ACTIVE")).json()
    assert alerts["total"] == 1

    # Failure 3 -> DeviceOffline CRITICAL; CollectorFailed is superseded.
    await _refresh(client, device_id, {"fail": True})
    active = (await client.get("/api/alerts?status=ACTIVE")).json()
    assert [a["event_type"] for a in active["items"]] == ["DeviceOffline"]
    assert active["items"][0]["severity"] == "CRITICAL"

    # Next successful collection -> automatic resolution + recovery record.
    await _refresh(client, device_id, BASELINE)
    active = (await client.get("/api/alerts?status=ACTIVE")).json()
    assert active["total"] == 0
    offline = (await client.get("/api/alerts?event_type=DeviceOffline")).json()
    assert offline["items"][0]["status"] == "RESOLVED"
    assert offline["items"][0]["resolved_by"] == "system"
    recovered = (await client.get("/api/alerts?event_type=DeviceRecovered")).json()
    assert recovered["total"] == 1
    assert recovered["items"][0]["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_credential_failure_alerts_immediately(client, device_id) -> None:
    await _refresh(client, device_id, BASELINE)
    await _refresh(client, device_id, {"fail": True, "error_code": ERROR_AUTH_FAILED})
    active = (await client.get("/api/alerts?status=ACTIVE")).json()
    assert [a["event_type"] for a in active["items"]] == ["CredentialFailed"]


@pytest.mark.asyncio
async def test_sensor_threshold_lifecycle(client, device_id) -> None:
    # Sensor alerts fire only after N consecutive breached collections.
    patched = await client.patch(
        "/api/lifecycle/alert-settings", json={"consecutive_failures_threshold": 2}
    )
    assert patched.status_code == 200

    breached = {
        **BASELINE,
        "sensors": [
            {"type": "temperature", "name": "CPU Temp", "value": "99", "status": "critical"}
        ],
    }
    await _refresh(client, device_id, BASELINE)
    await _refresh(client, device_id, breached)  # 1st breach: no alert yet
    assert (await client.get("/api/alerts?event_type=SensorThresholdExceeded")).json()[
        "total"
    ] == 0

    await _refresh(client, device_id, breached)  # 2nd consecutive breach: alert
    sensor_alerts = (
        await client.get("/api/alerts?event_type=SensorThresholdExceeded")
    ).json()
    assert sensor_alerts["total"] == 1
    assert sensor_alerts["items"][0]["severity"] == "CRITICAL"
    assert sensor_alerts["items"][0]["subject"] == "CPU Temp"

    await _refresh(client, device_id, BASELINE)  # back to normal: auto-resolve
    sensor_alerts = (
        await client.get("/api/alerts?event_type=SensorThresholdExceeded")
    ).json()
    assert sensor_alerts["items"][0]["status"] == "RESOLVED"
    recovered = (await client.get("/api/alerts?event_type=SensorRecovered")).json()
    assert recovered["total"] == 1


@pytest.mark.asyncio
async def test_alert_filters_and_dashboard(client, device_id) -> None:
    await _refresh(client, device_id, BASELINE)
    await _refresh(
        client, device_id,
        {**BASELINE, "firmwares": [{"component": "BIOS", "version": "3.0"}]},
    )

    by_hostname = (await client.get("/api/alerts?hostname=srv-1")).json()
    assert by_hostname["total"] == 1
    assert by_hostname["items"][0]["cluster_name"] == "ops-c1"
    assert by_hostname["items"][0]["rack_name"] == "R1"
    assert (await client.get("/api/alerts?hostname=nope")).json()["total"] == 0
    assert (await client.get("/api/alerts?severity=CRITICAL")).json()["total"] == 0

    dash = (await client.get("/api/dashboard/alerts")).json()
    assert dash["active_info"] == 1
    assert len(dash["latest_alerts"]) == 1
    assert len(dash["recent_firmware_changes"]) == 1

    health = (await client.get("/api/dashboard/health")).json()
    assert health["total"] == 1

    device_health = (await client.get(f"/api/devices/{device_id}/health")).json()
    assert device_health["overall_label"] in ("Healthy", "Warning", "Critical")
    assert device_health["sensor_groups"][0]["group"] == "temperature"
    assert len(device_health["timeline"]) == 2


@pytest.mark.asyncio
async def test_history_is_readonly_and_retention_categories_exist(client, device_id) -> None:
    # No write/delete endpoints exist for history.
    assert (await client.delete("/api/history")).status_code == 405
    assert (await client.post("/api/history", json={})).status_code == 405

    policies = {p["category"]: p for p in (await client.get("/api/lifecycle/policies")).json()}
    assert "resolved_alerts" in policies
    assert "history" in policies
    # History retention ships disabled => permanent by default.
    assert policies["history"]["enabled"] is False
