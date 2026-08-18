"""Integration tests for Device Templates + instances (P5/P3/P2)."""
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture()
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/tpl.db")
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


async def _rack(client: AsyncClient) -> str:
    cid = (await client.post("/api/clusters", json={"name": "C"})).json()["id"]
    return (await client.post("/api/racks", json={"cluster_id": cid, "name": "R"})).json()["id"]


@pytest.mark.asyncio
async def test_template_shared_by_instances(client: AsyncClient) -> None:
    rid = await _rack(client)
    tid = (
        await client.post(
            "/api/device-templates",
            json={"name": "HPE DL320", "vendor": "HPE", "model": "DL320"},
        )
    ).json()["id"]

    # vendor/model inherited from the template
    d1 = await client.post(
        "/api/devices",
        json={"rack_id": rid, "template_id": tid, "hostname": "a", "management_ip": "10.0.0.1"},
    )
    assert d1.status_code == 201
    assert d1.json()["vendor"] == "HPE"
    assert d1.json()["template_id"] == tid

    # a second instance shares the same template but keeps independent identity
    d2 = await client.post(
        "/api/devices",
        json={"rack_id": rid, "template_id": tid, "hostname": "b", "management_ip": "10.0.0.2"},
    )
    assert d2.json()["template_id"] == tid
    assert d2.json()["management_ip"] != d1.json()["management_ip"]

    summary = (await client.get("/api/device-templates")).json()
    assert summary[0]["instance_count"] == 2

    # cannot delete a template still in use
    assert (await client.delete(f"/api/device-templates/{tid}")).status_code == 409


@pytest.mark.asyncio
async def test_bulk_device_creation(client: AsyncClient) -> None:
    rid = await _rack(client)
    result = await client.post(
        "/api/devices/bulk",
        json={"rack_id": rid, "quantity": 3, "hostname_prefix": "DL320", "pad_width": 2},
    )
    assert result.status_code == 201
    assert [d["hostname"] for d in result.json()["created"]] == [
        "DL320-01",
        "DL320-02",
        "DL320-03",
    ]
    # duplicates are skipped, not errored
    rerun = await client.post(
        "/api/devices/bulk",
        json={"rack_id": rid, "quantity": 4, "hostname_prefix": "DL320", "pad_width": 2},
    )
    assert [d["hostname"] for d in rerun.json()["created"]] == ["DL320-04"]
    assert set(rerun.json()["skipped"]) == {"DL320-01", "DL320-02", "DL320-03"}


@pytest.mark.asyncio
async def test_bulk_wizard_items_with_per_row_values(client: AsyncClient) -> None:
    rid = await _rack(client)
    cred = (
        await client.post(
            "/api/credentials",
            json={"name": "ilo-default", "credential_type": "REDFISH", "username": "u",
                  "password": "p"},
        )
    ).json()["id"]

    # Reviewed provisioning table: per-row hostname / IPs / credential / U.
    result = await client.post(
        "/api/devices/bulk",
        json={
            "rack_id": rid,
            "redfish_credential_id": cred,  # default credential for all rows
            "items": [
                {"hostname": "worker-1", "management_ip": "10.10.1.100",
                 "ilo_ip": "10.20.1.100", "u_position": 1},
                {"hostname": "worker-2", "management_ip": "10.10.1.101",
                 "ilo_ip": "10.20.1.101", "u_position": 2},
                {"hostname": "worker-3", "management_ip": "10.10.1.102",
                 "ilo_ip": "10.20.1.102"},
            ],
        },
    )
    assert result.status_code == 201
    created = result.json()["created"]
    assert [d["hostname"] for d in created] == ["worker-1", "worker-2", "worker-3"]
    # per-row IPs preserved, default credential applied to every row
    assert created[0]["management_ip"] == "10.10.1.100"
    assert created[1]["ilo_ip"] == "10.20.1.101"
    assert all(d["redfish_credential_id"] == cred for d in created)

    # rows with a U position were placed; the third (no U) is unplaced
    layout = (await client.get(f"/api/racks/{rid}/layout")).json()
    assert sorted(u["u_position"] for u in layout["units"]) == [1, 2]


@pytest.mark.asyncio
async def test_bulk_wizard_placement_conflict_rolls_back(client: AsyncClient) -> None:
    rid = await _rack(client)
    result = await client.post(
        "/api/devices/bulk",
        json={
            "rack_id": rid,
            "items": [
                {"hostname": "a", "u_position": 5, "height": 2},
                {"hostname": "b", "u_position": 6},  # overlaps a (5-6)
            ],
        },
    )
    assert result.status_code == 201
    body = result.json()
    assert body["created"] == []
    assert any(e["hostname"] == "b" for e in body["errors"])
    # nothing was committed
    assert (await client.get(f"/api/devices?rack_id={rid}")).json() == []


@pytest.mark.asyncio
async def test_delete_device_removes_placement(client: AsyncClient) -> None:
    """Regression (1.1.3): deleting a placed device must not orphan its
    rack_unit, and the freed U must be reusable immediately."""
    rid = await _rack(client)
    a = (
        await client.post("/api/devices", json={"rack_id": rid, "hostname": "a", "u_position": 10})
    ).json()["id"]
    b = (
        await client.post("/api/devices", json={"rack_id": rid, "hostname": "b", "u_position": 20})
    ).json()["id"]

    assert (await client.delete(f"/api/devices/{a}")).status_code == 204
    layout = (await client.get(f"/api/racks/{rid}/layout")).json()
    # no orphan (device is None) units remain
    assert all(u["device"] is not None for u in layout["units"])
    assert [u["u_position"] for u in layout["units"]] == [20]

    # the freed U10 can be reused
    assert (
        await client.put(f"/api/devices/{b}/position", json={"u_position": 10})
    ).status_code == 200


@pytest.mark.asyncio
async def test_create_at_occupied_u_is_422(client: AsyncClient) -> None:
    """create_device must validate placement (meaningful 422, not 500)."""
    rid = await _rack(client)
    await client.post("/api/devices", json={"rack_id": rid, "hostname": "a", "u_position": 5})
    conflict = await client.post(
        "/api/devices", json={"rack_id": rid, "hostname": "b", "u_position": 5}
    )
    assert conflict.status_code == 422
    assert "overlap" in conflict.json()["detail"].lower()

    too_tall = await client.post(
        "/api/devices",
        json={"rack_id": rid, "hostname": "c", "u_position": 42, "height": 4},
    )
    assert too_tall.status_code == 422
    assert "exceeds" in too_tall.json()["detail"].lower()


@pytest.mark.asyncio
async def test_duplicate_hostname_in_rack_rejected(client: AsyncClient) -> None:
    rid = await _rack(client)
    assert (
        await client.post("/api/devices", json={"rack_id": rid, "hostname": "dup"})
    ).status_code == 201
    again = await client.post("/api/devices", json={"rack_id": rid, "hostname": "dup"})
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_bulk_duplicate_ip_rejected(client: AsyncClient) -> None:
    rid = await _rack(client)
    result = await client.post(
        "/api/devices/bulk",
        json={
            "rack_id": rid,
            "items": [
                {"hostname": "a", "management_ip": "10.0.0.1"},
                {"hostname": "b", "management_ip": "10.0.0.1"},  # duplicate
            ],
        },
    )
    assert result.status_code == 201
    body = result.json()
    assert body["created"] == []
    assert any("Management IP" in e["error"] for e in body["errors"])
    assert (await client.get(f"/api/devices?rack_id={rid}")).json() == []


@pytest.mark.asyncio
async def test_update_rack_change_clears_placement(client: AsyncClient) -> None:
    """Moving a device to another rack via PATCH must not strand its placement
    in the old rack (Required Fix 5)."""
    cid = (await client.post("/api/clusters", json={"name": "C"})).json()["id"]
    r1 = (await client.post("/api/racks", json={"cluster_id": cid, "name": "R1"})).json()["id"]
    r2 = (await client.post("/api/racks", json={"cluster_id": cid, "name": "R2"})).json()["id"]
    did = (
        await client.post("/api/devices", json={"rack_id": r1, "hostname": "m", "u_position": 3})
    ).json()["id"]

    assert (await client.patch(f"/api/devices/{did}", json={"rack_id": r2})).status_code == 200
    # old rack no longer shows the device; no orphan unit left behind
    assert (await client.get(f"/api/racks/{r1}/layout")).json()["units"] == []
    assert (await client.get(f"/api/racks/{r2}/layout")).json()["units"] == []


@pytest.mark.asyncio
async def test_update_invalid_template_rejected(client: AsyncClient) -> None:
    import uuid as _uuid

    rid = await _rack(client)
    did = (
        await client.post("/api/devices", json={"rack_id": rid, "hostname": "t"})
    ).json()["id"]
    bad = await client.patch(
        f"/api/devices/{did}", json={"template_id": str(_uuid.uuid4())}
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_multi_u_device_move_preserves_height(client: AsyncClient) -> None:
    rid = await _rack(client)
    did = (
        await client.post(
            "/api/devices",
            json={"rack_id": rid, "hostname": "big", "u_position": 10, "height": 2},
        )
    ).json()["id"]
    # move without specifying height keeps the 2U footprint
    assert (
        await client.put(f"/api/devices/{did}/position", json={"u_position": 20})
    ).status_code == 200
    layout = (await client.get(f"/api/racks/{rid}/layout")).json()
    unit = next(u for u in layout["units"] if u["device"]["id"] == did)
    assert unit["u_position"] == 20
    assert unit["height"] == 2
    # a device cannot be dropped into the 2U device's second U (21)
    other = (
        await client.post("/api/devices", json={"rack_id": rid, "hostname": "x"})
    ).json()["id"]
    assert (
        await client.put(f"/api/devices/{other}/position", json={"u_position": 21})
    ).status_code == 422


@pytest.mark.asyncio
async def test_assign_and_unassign(client: AsyncClient) -> None:
    rid = await _rack(client)
    did = (
        await client.post(
            "/api/devices", json={"rack_id": rid, "hostname": "srv"}
        )
    ).json()["id"]

    assert (
        await client.put(f"/api/devices/{did}/position", json={"u_position": 5})
    ).status_code == 200
    layout = (await client.get(f"/api/racks/{rid}/layout")).json()
    assert [u["u_position"] for u in layout["units"]] == [5]

    assert (await client.delete(f"/api/devices/{did}/position")).status_code == 204
    layout = (await client.get(f"/api/racks/{rid}/layout")).json()
    assert layout["units"] == []
    # the device itself still exists (uninstalled, not deleted)
    assert (await client.get(f"/api/devices/{did}")).status_code == 200
