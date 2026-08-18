"""Tests for 1.2.0 features: discovery, drift, compliance, lifecycle."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from services.discovery.scanner import SnmpProbeResult


class FakeScanner:
    """Deterministic scanner returning canned SNMP data for two hosts."""

    def __init__(self, reachable: dict[str, dict]):
        self._reachable = reachable

    async def probe(self, ip_address, community, timeout):
        data = self._reachable.get(ip_address)
        if data is None:
            return SnmpProbeResult(ip_address=ip_address, reachable=False)
        return SnmpProbeResult(ip_address=ip_address, reachable=True, **data)


@pytest_asyncio.fixture()
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/v120.db")
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


@pytest.mark.asyncio
async def test_discovery_scan_and_import(client: AsyncClient, monkeypatch) -> None:
    from services.discovery import service as disc

    monkeypatch.setattr(
        disc,
        "_scanner_factory",
        lambda: FakeScanner(
            {
                "10.0.0.1": {
                    "sysname": "sw1",
                    "sysdescr": "Cisco NX-OS Switch",
                    "sysobjectid": "1.3.6.1.4.1.9",
                },
                "10.0.0.2": {
                    "sysname": "srv1",
                    "sysdescr": "HPE ProLiant DL320 Linux",
                    "sysobjectid": "1.3.6.1.4.1.232",
                },
            }
        ),
    )

    scan = await client.post(
        "/api/discovery/scan", json={"targets": ["10.0.0.0/29"], "community": "public"}
    )
    assert scan.status_code == 200
    body = scan.json()
    assert body["reachable"] == 2
    by_ip = {d["ip_address"]: d for d in body["discovered"]}
    assert by_ip["10.0.0.1"]["vendor"] == "Cisco"
    assert by_ip["10.0.0.1"]["device_type_guess"] == "SWITCH"
    assert by_ip["10.0.0.2"]["vendor"] == "HPE"
    assert by_ip["10.0.0.2"]["device_type_guess"] == "SERVER"

    # discovery NEVER auto-creates devices
    assert (await client.get("/api/devices")).json() == []

    # scanning again reuses the pending rows (no duplicates)
    await client.post(
        "/api/discovery/scan", json={"targets": ["10.0.0.1"], "community": "public"}
    )
    pending = (await client.get("/api/discovery")).json()
    assert len([d for d in pending if d["ip_address"] == "10.0.0.1"]) == 1

    # import a discovered device into a rack -> creates an Installed Device
    cid = (await client.post("/api/clusters", json={"name": "C"})).json()["id"]
    rid = (await client.post("/api/racks", json={"cluster_id": cid, "name": "R"})).json()["id"]
    srv = by_ip["10.0.0.2"]
    imported = await client.post(
        "/api/discovery/import",
        json={
            "rack_id": rid,
            "items": [{"discovered_id": srv["id"], "hostname": "srv1"}],
        },
    )
    assert imported.status_code == 200
    created = imported.json()["created"]
    assert len(created) == 1
    assert created[0]["management_ip"] == "10.0.0.2"  # defaulted from discovery IP
    # discovery marked IMPORTED, no longer pending
    remaining = (await client.get("/api/discovery")).json()
    assert srv["id"] not in [d["id"] for d in remaining]


@pytest.mark.asyncio
async def test_drift_detection(client: AsyncClient) -> None:
    import uuid

    from models import CPU, Device, Firmware, Snapshot
    import database.session as session_mod

    cid = (await client.post("/api/clusters", json={"name": "C"})).json()["id"]
    rid = (await client.post("/api/racks", json={"cluster_id": cid, "name": "R"})).json()["id"]
    did = (await client.post("/api/devices", json={"rack_id": rid, "hostname": "d"})).json()["id"]

    async with session_mod.async_session_factory() as db:
        dev_id = uuid.UUID(did)
        # older successful snapshot: BIOS 1.0
        s1 = Snapshot(device_id=dev_id, collector_version="t", redfish_success=True)
        db.add(s1)
        await db.flush()
        db.add(Firmware(snapshot_id=s1.id, component="BIOS", version="1.0"))
        db.add(CPU(snapshot_id=s1.id, socket="CPU1", model="Xeon", cores=8))
        # newer successful snapshot: BIOS 1.1, more cores
        import datetime as _dt
        s2 = Snapshot(
            device_id=dev_id, collector_version="t", redfish_success=True,
            collected_at=_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=1),
        )
        db.add(s2)
        await db.flush()
        db.add(Firmware(snapshot_id=s2.id, component="BIOS", version="1.1"))
        db.add(CPU(snapshot_id=s2.id, socket="CPU1", model="Xeon", cores=16))
        await db.commit()

    drift = (await client.get(f"/api/devices/{did}/drift")).json()
    assert drift["has_previous"] is True
    changes = {(c["section"], c["field"]): c for c in drift["changes"]}
    assert changes[("Firmware", "version")]["old_value"] == "1.0"
    assert changes[("Firmware", "version")]["new_value"] == "1.1"
    assert changes[("CPU", "cores")]["new_value"] == "16"


@pytest.mark.asyncio
async def test_firmware_compliance(client: AsyncClient) -> None:
    import uuid

    from models import Firmware, Snapshot
    import database.session as session_mod

    tid = (
        await client.post("/api/device-templates", json={"name": "DL320", "vendor": "HPE"})
    ).json()["id"]
    cid = (await client.post("/api/clusters", json={"name": "C"})).json()["id"]
    rid = (await client.post("/api/racks", json={"cluster_id": cid, "name": "R"})).json()["id"]
    d1 = (
        await client.post(
            "/api/devices", json={"rack_id": rid, "hostname": "a", "template_id": tid}
        )
    ).json()["id"]
    d2 = (
        await client.post(
            "/api/devices", json={"rack_id": rid, "hostname": "b", "template_id": tid}
        )
    ).json()["id"]

    async with session_mod.async_session_factory() as db:
        for did, version in ((d1, "2.60"), (d2, "2.50")):
            snap = Snapshot(device_id=uuid.UUID(did), collector_version="t", redfish_success=True)
            db.add(snap)
            await db.flush()
            db.add(Firmware(snapshot_id=snap.id, component="BIOS", version=version))
        await db.commit()

    report = (await client.get(f"/api/device-templates/{tid}/compliance")).json()
    assert report["device_count"] == 2
    assert report["compliant"] is False  # BIOS versions differ
    bios = next(c for c in report["components"] if c["component"] == "BIOS")
    mismatched = [d for d in bios["devices"] if not d["compliant"]]
    assert len(mismatched) == 1


@pytest.mark.asyncio
async def test_lifecycle_policies_and_cleanup(client: AsyncClient) -> None:
    policies = (await client.get("/api/lifecycle/policies")).json()
    categories = {p["category"] for p in policies}
    assert {"collector_runs", "snapshots", "discovery"} <= categories
    assert all(p["enabled"] is False for p in policies)  # disabled by default

    # enable + configure a policy
    updated = await client.patch(
        "/api/lifecycle/policies/collector_runs",
        json={"enabled": True, "retention_days": 30},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is True

    # manual cleanup runs and reports per-category counts
    result = (await client.post("/api/lifecycle/cleanup")).json()
    assert "collector_runs" in result["deleted"]
    assert result["total"] == 0  # nothing old enough yet
