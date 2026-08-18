"""Tests for 1.2.1 Access Management (RBAC)."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from rbac_catalog import ALL_PERMISSION_CODES


@pytest_asyncio.fixture()
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/rbac.db")
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


async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_admin_me_has_all_permissions(client: AsyncClient) -> None:
    me = (await client.get("/api/auth/me")).json()
    assert set(me["permissions"]) == set(ALL_PERMISSION_CODES)
    assert any(m["permission"] == "user.view" for m in me["menus"])


@pytest.mark.asyncio
async def test_system_roles_seeded_and_readonly(client: AsyncClient) -> None:
    roles = {r["name"]: r for r in (await client.get("/api/roles")).json()}
    assert {"Administrator", "Operator", "Viewer"} <= set(roles)
    assert roles["Administrator"]["is_system"] is True
    assert set(roles["Administrator"]["permission_codes"]) == set(ALL_PERMISSION_CODES)
    # Viewer is read-only: only *.view codes.
    assert all(c.endswith(".view") for c in roles["Viewer"]["permission_codes"])

    admin_role_id = roles["Administrator"]["id"]
    resp = await client.patch(
        f"/api/roles/{admin_role_id}", json={"description": "hacked"}
    )
    assert resp.status_code == 400
    resp = await client.delete(f"/api/roles/{admin_role_id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_permission_catalog_readonly_endpoint(client: AsyncClient) -> None:
    perms = (await client.get("/api/permissions")).json()
    codes = {p["code"] for p in perms}
    assert set(ALL_PERMISSION_CODES) <= codes
    assert all("password" not in str(p).lower() for p in perms)


@pytest.mark.asyncio
async def test_viewer_user_is_denied_writes_and_limited_menus(client: AsyncClient) -> None:
    roles = {r["name"]: r for r in (await client.get("/api/roles")).json()}
    viewer_role_id = roles["Viewer"]["id"]

    # Create a Viewer group + binding, and a USER-role account in it.
    group = (
        await client.post(
            "/api/user-groups", json={"name": "Viewers", "description": "read only"}
        )
    ).json()
    binding = await client.post(
        "/api/role-bindings",
        json={"user_group_id": group["id"], "role_id": viewer_role_id},
    )
    assert binding.status_code == 201

    created = await client.post(
        "/api/users",
        json={
            "username": "vic",
            "password": "viewerpass1",
            "role": "USER",
            "group_ids": [group["id"]],
        },
    )
    assert created.status_code == 201, created.text

    # Log in as the viewer using a separate client so we don't clobber admin auth.
    import main as app_main

    async with AsyncClient(
        transport=ASGITransport(app=app_main.app), base_url="http://test"
    ) as viewer:
        token = await _login(viewer, "vic", "viewerpass1")
        viewer.headers["Authorization"] = f"Bearer {token}"

        me = (await viewer.get("/api/auth/me")).json()
        assert "dashboard.view" in me["permissions"]
        assert "cluster.create" not in me["permissions"]
        assert "user.view" not in me["permissions"]

        # Read allowed, write denied (403), access management denied (403).
        assert (await viewer.get("/api/clusters")).status_code == 200
        create_cluster = await viewer.post("/api/clusters", json={"name": "c1"})
        assert create_cluster.status_code == 403
        assert (await viewer.get("/api/users")).status_code == 403


@pytest.mark.asyncio
async def test_operator_can_operate_but_not_manage_access(client: AsyncClient) -> None:
    roles = {r["name"]: r for r in (await client.get("/api/roles")).json()}
    group = (await client.post("/api/user-groups", json={"name": "Ops"})).json()
    await client.post(
        "/api/role-bindings",
        json={"user_group_id": group["id"], "role_id": roles["Operator"]["id"]},
    )
    await client.post(
        "/api/users",
        json={
            "username": "olly",
            "password": "operatorpass1",
            "role": "USER",
            "group_ids": [group["id"]],
        },
    )

    import main as app_main

    async with AsyncClient(
        transport=ASGITransport(app=app_main.app), base_url="http://test"
    ) as op:
        token = await _login(op, "olly", "operatorpass1")
        op.headers["Authorization"] = f"Bearer {token}"
        create_cluster = await op.post("/api/clusters", json={"name": "opcluster"})
        assert create_cluster.status_code == 201, create_cluster.text
        assert (await op.get("/api/roles")).status_code == 403


@pytest.mark.asyncio
async def test_custom_role_lifecycle_and_admin_binding_protected(client: AsyncClient) -> None:
    role = await client.post(
        "/api/roles",
        json={
            "name": "Auditor",
            "description": "audit only",
            "permission_codes": ["audit.view", "dashboard.view"],
        },
    )
    assert role.status_code == 201, role.text
    role_id = role.json()["id"]
    assert set(role.json()["permission_codes"]) == {"audit.view", "dashboard.view"}

    updated = await client.patch(
        f"/api/roles/{role_id}", json={"permission_codes": ["audit.view"]}
    )
    assert set(updated.json()["permission_codes"]) == {"audit.view"}
    assert (await client.delete(f"/api/roles/{role_id}")).status_code == 204

    # The built-in Administrator binding must not be removable (lockout guard).
    bindings = (await client.get("/api/role-bindings")).json()
    admin_binding = next(
        b for b in bindings
        if b["user_group_name"] == "Administrators" and b["role_name"] == "Administrator"
    )
    assert (
        await client.delete(f"/api/role-bindings/{admin_binding['id']}")
    ).status_code == 400


@pytest.mark.asyncio
async def test_group_role_assignment_updates_bindings(client: AsyncClient) -> None:
    roles = {r["name"]: r for r in (await client.get("/api/roles")).json()}
    viewer_id = roles["Viewer"]["id"]
    operator_id = roles["Operator"]["id"]

    # Create a group WITH roles assigned via the group editor (no bindings page).
    group = (
        await client.post(
            "/api/user-groups",
            json={"name": "Team A", "role_ids": [viewer_id]},
        )
    ).json()
    assert group["role_ids"] == [viewer_id]
    assert group["role_names"] == ["Viewer"]

    # A role binding row was created internally.
    bindings = (await client.get("/api/role-bindings")).json()
    assert any(
        b["user_group_name"] == "Team A" and b["role_name"] == "Viewer" for b in bindings
    )

    # Editing the group's roles re-syncs the bindings (swap Viewer -> Operator).
    updated = (
        await client.patch(
            f"/api/user-groups/{group['id']}", json={"role_ids": [operator_id]}
        )
    ).json()
    assert updated["role_ids"] == [operator_id]
    bindings = (await client.get("/api/role-bindings")).json()
    team_bindings = [b for b in bindings if b["user_group_name"] == "Team A"]
    assert len(team_bindings) == 1 and team_bindings[0]["role_name"] == "Operator"

    # Clearing roles removes all of the group's bindings.
    cleared = (
        await client.patch(f"/api/user-groups/{group['id']}", json={"role_ids": []})
    ).json()
    assert cleared["role_ids"] == []


@pytest.mark.asyncio
async def test_admin_group_keeps_admin_binding(client: AsyncClient) -> None:
    groups = {g["name"]: g for g in (await client.get("/api/user-groups")).json()}
    admin_group = groups["Administrators"]
    # Attempt to strip all roles from the Administrators group.
    updated = (
        await client.patch(
            f"/api/user-groups/{admin_group['id']}", json={"role_ids": []}
        )
    ).json()
    # The built-in Administrator binding is preserved (lockout guard).
    assert "Administrator" in updated["role_names"]


@pytest.mark.asyncio
async def test_role_detail_reports_groups_and_user_count(client: AsyncClient) -> None:
    roles = {r["name"]: r for r in (await client.get("/api/roles")).json()}
    viewer_id = roles["Viewer"]["id"]

    group = (
        await client.post(
            "/api/user-groups", json={"name": "Readers", "role_ids": [viewer_id]}
        )
    ).json()
    for name in ("ann", "bob"):
        await client.post(
            "/api/users",
            json={
                "username": name,
                "password": "readerpass1",
                "role": "USER",
                "group_ids": [group["id"]],
            },
        )

    detail = (await client.get(f"/api/roles/{viewer_id}")).json()
    assert detail["is_system"] is True
    assert any(g["name"] == "Readers" for g in detail["user_groups"])
    assert detail["effective_user_count"] == 2
    assert "dashboard.view" in detail["permission_codes"]


@pytest.mark.asyncio
async def test_user_response_never_leaks_password(client: AsyncClient) -> None:
    users = (await client.get("/api/users")).json()
    assert users, "admin should be listed"
    for u in users:
        assert "password" not in u
        assert "password_hash" not in u
