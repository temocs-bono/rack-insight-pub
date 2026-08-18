"""Plugin Registry (Plugin Architecture Foundation).

Owns plugin configuration + runtime state persistence and the health lifecycle.
Config-declared plugins (PLUGINS_CONFIG) are seeded idempotently at startup,
exactly like the RBAC and retention seeders. Registering/enabling/disabling and
health transitions are recorded in the existing audit log.

Everything here is failure-isolated: a plugin that is down, slow, or returns a
malformed manifest becomes UNHEALTHY — it never raises into Core startup or the
Core request path.
"""
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings, load_plugin_configs
from models import Plugin, User
from models.plugin import (
    PLUGIN_STATUS_DISABLED,
    PLUGIN_STATUS_HEALTHY,
    PLUGIN_STATUS_UNHEALTHY,
    PLUGIN_STATUS_UNKNOWN,
)
from schemas.plugin import PluginCreate, PluginResponse, PluginUi, PluginUpdate
from services import plugin_client
from services.audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    record_audit,
    record_system_audit,
)
from utils.logging import get_logger

logger = get_logger(__name__)

ENTITY_PLUGIN = "plugin"


def parse_ui(plugin: Plugin) -> PluginUi | None:
    """Extract the UI descriptor from the plugin's cached manifest (or None)."""
    if not plugin.manifest:
        return None
    try:
        data = json.loads(plugin.manifest)
    except (ValueError, TypeError):
        return None
    ui = data.get("ui")
    if not isinstance(ui, dict):
        return None
    try:
        return PluginUi.model_validate(ui)
    except Exception:
        return None


def to_response(plugin: Plugin) -> PluginResponse:
    """Serialize a plugin, enriching it with the parsed UI descriptor."""
    response = PluginResponse.model_validate(plugin)
    response.ui = parse_ui(plugin)
    return response


async def get_by_name(db: AsyncSession, name: str) -> Plugin | None:
    return (
        await db.execute(select(Plugin).where(Plugin.name == name))
    ).scalar_one_or_none()


async def list_plugins(db: AsyncSession) -> list[Plugin]:
    return list(
        (await db.execute(select(Plugin).order_by(Plugin.name))).scalars().all()
    )


async def _apply_manifest(db: AsyncSession, plugin: Plugin) -> None:
    """Best-effort: pull the manifest to fill version/api_version/description.
    Never raises — a plugin that is down just keeps its previous metadata."""
    try:
        manifest = await plugin_client.fetch_manifest(plugin.endpoint)
    except plugin_client.PluginUnavailable as exc:
        logger.info("Manifest unavailable for plugin %s: %s", plugin.name, exc)
        return
    plugin.version = manifest.version
    plugin.api_version = manifest.api_version
    if manifest.description and not plugin.description:
        plugin.description = manifest.description
    if manifest.display_name:
        plugin.display_name = manifest.display_name
    plugin.manifest = manifest.model_dump_json(by_alias=True)


async def seed_plugins_from_config(db: AsyncSession) -> None:
    """Upsert config-declared plugins. Idempotent; runs on every startup."""
    configs = load_plugin_configs()
    if not configs:
        return
    for cfg in configs:
        plugin = await get_by_name(db, cfg.name)
        if plugin is None:
            plugin = Plugin(
                name=cfg.name,
                display_name=cfg.display_name or cfg.name,
                endpoint=cfg.endpoint,
                enabled=cfg.enabled,
                managed_by_config=True,
                status=PLUGIN_STATUS_UNKNOWN,
            )
            db.add(plugin)
            await db.flush()
            await _apply_manifest(db, plugin)
            logger.info("Registered config plugin %s -> %s", cfg.name, cfg.endpoint)
        else:
            # Configuration wins for endpoint/enabled/config-managed flag.
            plugin.endpoint = cfg.endpoint
            plugin.enabled = cfg.enabled
            plugin.managed_by_config = True
            if cfg.display_name:
                plugin.display_name = cfg.display_name
    await db.commit()


# --------------------------------------------------------------------------- #
# CRUD (API-driven)
# --------------------------------------------------------------------------- #
async def register_plugin(
    db: AsyncSession, actor: User, payload: PluginCreate
) -> Plugin:
    plugin = Plugin(
        name=payload.name,
        display_name=payload.display_name or payload.name,
        description=payload.description,
        endpoint=payload.endpoint,
        enabled=payload.enabled,
        managed_by_config=False,
        status=PLUGIN_STATUS_UNKNOWN,
    )
    db.add(plugin)
    await db.flush()
    await _apply_manifest(db, plugin)
    record_audit(
        db, actor, ACTION_CREATE, ENTITY_PLUGIN, plugin.name, plugin.id,
        new_value={"endpoint": plugin.endpoint, "enabled": plugin.enabled},
    )
    await db.commit()
    await db.refresh(plugin)
    return plugin


async def update_plugin(
    db: AsyncSession, actor: User, plugin: Plugin, payload: PluginUpdate
) -> Plugin:
    old = {"endpoint": plugin.endpoint, "enabled": plugin.enabled}
    data = payload.model_dump(exclude_unset=True)
    if "endpoint" in data:
        plugin.endpoint = data["endpoint"]
    if "display_name" in data and data["display_name"] is not None:
        plugin.display_name = data["display_name"]
    if "description" in data:
        plugin.description = data["description"]
    if "enabled" in data and data["enabled"] is not None:
        plugin.enabled = data["enabled"]
        if not plugin.enabled:
            plugin.status = PLUGIN_STATUS_DISABLED
        elif plugin.status == PLUGIN_STATUS_DISABLED:
            plugin.status = PLUGIN_STATUS_UNKNOWN
    record_audit(
        db, actor, ACTION_UPDATE, ENTITY_PLUGIN, plugin.name, plugin.id,
        old_value=old,
        new_value={"endpoint": plugin.endpoint, "enabled": plugin.enabled},
    )
    await db.commit()
    await db.refresh(plugin)
    return plugin


async def delete_plugin(db: AsyncSession, actor: User, plugin: Plugin) -> None:
    record_audit(
        db, actor, ACTION_DELETE, ENTITY_PLUGIN, plugin.name, plugin.id,
        old_value={"endpoint": plugin.endpoint},
    )
    await db.delete(plugin)
    await db.commit()


# --------------------------------------------------------------------------- #
# Health monitoring
# --------------------------------------------------------------------------- #
def _health_path(plugin: Plugin) -> str:
    if plugin.manifest:
        try:
            data = json.loads(plugin.manifest)
            return data.get("healthEndpoint") or data.get("health_endpoint") or "/healthz"
        except (ValueError, TypeError):
            pass
    return "/healthz"


async def refresh_health(db: AsyncSession, plugin: Plugin) -> Plugin:
    """Probe one plugin and update its runtime state. Never raises. Records a
    system audit entry when the status transitions."""
    previous = plugin.status
    now = datetime.now(timezone.utc)
    plugin.last_health_check = now

    if not plugin.enabled:
        plugin.status = PLUGIN_STATUS_DISABLED
    else:
        try:
            await plugin_client.check_health(plugin.endpoint, _health_path(plugin))
            plugin.status = PLUGIN_STATUS_HEALTHY
            plugin.last_success_at = now
            plugin.failure_reason = None
        except plugin_client.PluginUnavailable as exc:
            plugin.status = PLUGIN_STATUS_UNHEALTHY
            plugin.last_failure_at = now
            plugin.failure_reason = str(exc)

    if plugin.status != previous:
        record_system_audit(
            db, ACTION_UPDATE, ENTITY_PLUGIN, plugin.name, plugin.id,
            old_value={"status": previous},
            new_value={"status": plugin.status},
        )
        logger.info(
            "Plugin %s status %s -> %s", plugin.name, previous, plugin.status
        )
    await db.commit()
    await db.refresh(plugin)
    return plugin


async def refresh_all_health(db: AsyncSession) -> None:
    """Health-check every registered plugin, isolating per-plugin failures."""
    for plugin in await list_plugins(db):
        try:
            await refresh_health(db, plugin)
        except Exception:  # defensive: never let one plugin break the sweep
            await db.rollback()
            logger.exception("Health refresh crashed for plugin %s", plugin.name)
