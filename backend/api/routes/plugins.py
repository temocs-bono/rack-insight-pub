"""Plugin registry + proxy API (Plugin Platform).

- Registry CRUD and health-check: manage the plugins the Core knows about.
- Minimal REST proxy (GET/POST): ``/api/plugins/{name}/proxy/{path}`` forwards a
  request to the plugin's backend API after the Core has authenticated the user
  and checked the ``plugin.proxy`` permission.
- UI proxy: ``/api/plugins/{name}/ui/{path}`` serves the plugin's own frontend
  same-origin, so the browser embeds it in an iframe without ever learning the
  plugin's Kubernetes Service DNS name.
- ``/api/plugins/inventory/servers`` gives a plugin read-only access to the Core
  inventory (through the same-origin proxy) so it never replicates devices.

Plugins never handle login themselves and are never reached directly by the
browser. A plugin that is missing, disabled, or unreachable yields a clear
404/503; it never turns into a Core 500 or a hung request.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import (
    PLUGIN_UI_COOKIE,
    RequirePermission,
    RequirePluginAccess,
    get_current_user,
)
from auth.security import create_access_token
from config import get_settings
from database import get_db
from models import Device, Plugin, User
from models.plugin import PLUGIN_STATUS_DISABLED
from schemas.plugin import (
    PluginCreate,
    PluginInventoryServer,
    PluginResponse,
    PluginUiSession,
    PluginUpdate,
)
from services import plugin_client, plugin_registry
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/plugins", tags=["plugins"])


async def _get_plugin(db: AsyncSession, plugin_id: uuid.UUID) -> Plugin:
    plugin = (
        await db.execute(select(Plugin).where(Plugin.id == plugin_id))
    ).scalar_one_or_none()
    if plugin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")
    return plugin


@router.get(
    "",
    response_model=list[PluginResponse],
    dependencies=[Depends(RequirePermission("plugin.view"))],
)
async def list_plugins(db: AsyncSession = Depends(get_db)) -> list[PluginResponse]:
    plugins = await plugin_registry.list_plugins(db)
    return [plugin_registry.to_response(p) for p in plugins]


# --------------------------------------------------------------------------- #
# Plugin UI session (mint the short-lived cookie the iframe uses)
# --------------------------------------------------------------------------- #
@router.post("/ui-session", response_model=PluginUiSession)
async def create_ui_session(
    response: Response,
    actor: User = Depends(RequirePermission("plugin.view")),
) -> PluginUiSession:
    """Mint the short-lived ``ri_plugin_ui`` cookie an iframe uses to authenticate.

    The SPA calls this with its Bearer token *before* pointing an iframe at the
    plugin UI proxy. Iframe navigations and asset loads cannot carry an
    Authorization header, so the browser sends this HttpOnly cookie instead. It
    is scoped to ``/api/plugins`` and ``SameSite=Strict`` (CSRF-safe), and is a
    normal access token, so the proxy authorizes it exactly like a Bearer token.
    """
    settings = get_settings()
    max_age = settings.access_token_expire_minutes * 60
    token = create_access_token(str(actor.id))
    response.set_cookie(
        key=PLUGIN_UI_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="strict",
        # Testbed/offline runs over plain HTTP; the Ingress terminates TLS in
        # production. Kept False so the cookie works in both without config.
        secure=False,
        path="/api/plugins",
    )
    return PluginUiSession(expires_in=max_age)


# --------------------------------------------------------------------------- #
# Inventory access for plugins (read-only, reuses the Core Device inventory)
# --------------------------------------------------------------------------- #
@router.get(
    "/inventory/servers",
    response_model=list[PluginInventoryServer],
    dependencies=[Depends(RequirePluginAccess("plugin.proxy"))],
)
async def list_inventory_servers(
    db: AsyncSession = Depends(get_db),
) -> list[PluginInventoryServer]:
    """Expose the Core inventory to plugins (through the same-origin proxy) so a
    plugin never replicates devices in its own database. Credentials are never
    included — only identity/placement fields a plugin needs to target a server."""
    devices = list(
        (await db.execute(select(Device).order_by(Device.hostname))).scalars().all()
    )
    return [
        PluginInventoryServer(
            id=d.id,
            hostname=d.hostname,
            display_name=d.display_name,
            management_ip=d.management_ip,
            device_type=d.device_type.value,
            vendor=d.vendor,
            model=d.model,
            status=d.status.value,
            rack=d.rack.name if d.rack else None,
            cluster=d.rack.cluster.name if d.rack and d.rack.cluster else None,
        )
        for d in devices
    ]


@router.get(
    "/{plugin_id}",
    response_model=PluginResponse,
    dependencies=[Depends(RequirePermission("plugin.view"))],
)
async def get_plugin(
    plugin_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> PluginResponse:
    plugin = await _get_plugin(db, plugin_id)
    return plugin_registry.to_response(plugin)


@router.post("", response_model=PluginResponse, status_code=status.HTTP_201_CREATED)
async def create_plugin(
    payload: PluginCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("plugin.manage")),
) -> PluginResponse:
    if await plugin_registry.get_by_name(db, payload.name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Plugin name already exists"
        )
    plugin = await plugin_registry.register_plugin(db, actor, payload)
    return plugin_registry.to_response(plugin)


@router.patch("/{plugin_id}", response_model=PluginResponse)
async def update_plugin(
    plugin_id: uuid.UUID,
    payload: PluginUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("plugin.manage")),
) -> PluginResponse:
    plugin = await _get_plugin(db, plugin_id)
    plugin = await plugin_registry.update_plugin(db, actor, plugin, payload)
    return plugin_registry.to_response(plugin)


@router.delete("/{plugin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plugin(
    plugin_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("plugin.manage")),
) -> None:
    plugin = await _get_plugin(db, plugin_id)
    await plugin_registry.delete_plugin(db, actor, plugin)


@router.post(
    "/{plugin_id}/health-check",
    response_model=PluginResponse,
    dependencies=[Depends(RequirePermission("plugin.view"))],
)
async def health_check(
    plugin_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> PluginResponse:
    plugin = await _get_plugin(db, plugin_id)
    plugin = await plugin_registry.refresh_health(db, plugin)
    return plugin_registry.to_response(plugin)


# --------------------------------------------------------------------------- #
# Minimal REST proxy (GET / POST) — plugin backend API
# --------------------------------------------------------------------------- #
async def _resolve_enabled_plugin(db: AsyncSession, plugin_name: str) -> Plugin:
    plugin = await plugin_registry.get_by_name(db, plugin_name)
    if plugin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")
    if not plugin.enabled or plugin.status == PLUGIN_STATUS_DISABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Plugin is disabled"
        )
    return plugin


async def _proxy(
    db: AsyncSession, plugin_name: str, path: str, method: str, request: Request,
    json_body: Any = None,
) -> Response:
    plugin = await _resolve_enabled_plugin(db, plugin_name)
    try:
        result = await plugin_client.proxy_request(
            method, plugin.endpoint, path,
            params=dict(request.query_params),
            json_body=json_body,
        )
    except plugin_client.PluginUnavailable as exc:
        # Never leak the Core token to the plugin, and never 500 on a dead plugin.
        logger.info("Proxy to plugin %s failed: %s", plugin_name, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Plugin '{plugin_name}' is unavailable",
        ) from exc
    return Response(
        content=result.content,
        status_code=result.status_code,
        media_type=result.media_type,
    )


@router.get("/{plugin_name}/proxy/{path:path}")
async def proxy_get(
    plugin_name: str,
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(RequirePluginAccess("plugin.proxy")),
) -> Response:
    return await _proxy(db, plugin_name, path, "GET", request)


@router.post("/{plugin_name}/proxy/{path:path}")
async def proxy_post(
    plugin_name: str,
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(RequirePluginAccess("plugin.proxy")),
    body: Any = Body(default=None),
) -> Response:
    return await _proxy(db, plugin_name, path, "POST", request, json_body=body)


# --------------------------------------------------------------------------- #
# UI proxy — serve the plugin's own frontend same-origin (embedded as an iframe)
# --------------------------------------------------------------------------- #
async def _proxy_ui(
    db: AsyncSession, plugin_name: str, path: str, request: Request
) -> Response:
    plugin = await _resolve_enabled_plugin(db, plugin_name)
    # The plugin serves its frontend under /ui/; forward the sub-path verbatim.
    target = f"/ui/{path}" if path else "/ui/"
    try:
        result = await plugin_client.proxy_request(
            "GET", plugin.endpoint, target,
            params=dict(request.query_params),
        )
    except plugin_client.PluginUnavailable as exc:
        logger.info("UI proxy to plugin %s failed: %s", plugin_name, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Plugin '{plugin_name}' is unavailable",
        ) from exc
    # The Core, not the plugin, dictates framing: allow embedding by the Core's
    # own origin only, and drop any upstream X-Frame-Options / CSP.
    headers = {"Content-Security-Policy": "frame-ancestors 'self'"}
    return Response(
        content=result.content,
        status_code=result.status_code,
        media_type=result.media_type,
        headers=headers,
    )


@router.get("/{plugin_name}/ui", include_in_schema=False)
async def proxy_ui_root(
    plugin_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(RequirePluginAccess("plugin.proxy")),
) -> Response:
    return await _proxy_ui(db, plugin_name, "", request)


@router.get("/{plugin_name}/ui/{path:path}")
async def proxy_ui(
    plugin_name: str,
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(RequirePluginAccess("plugin.proxy")),
) -> Response:
    return await _proxy_ui(db, plugin_name, path, request)
