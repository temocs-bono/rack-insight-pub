"""Plugin health monitor (Plugin Architecture Foundation).

A dedicated, lightweight background task that periodically probes every
registered plugin and updates its runtime status. It runs on its own short
interval (independent of the collector scheduler) and is fully isolated: any
failure is logged and swallowed, so a misbehaving plugin never affects Core.
"""
import asyncio

from config import get_settings
from database import async_session_factory
from services.plugin_registry import refresh_all_health
from utils.logging import get_logger

logger = get_logger(__name__)

_task: asyncio.Task[None] | None = None


async def _loop() -> None:
    interval = get_settings().plugin_health_interval_seconds
    while True:
        try:
            async with async_session_factory() as db:
                await refresh_all_health(db)
        except Exception:
            logger.exception("Plugin health monitor iteration failed")
        await asyncio.sleep(interval)


def start_plugin_monitor() -> None:
    global _task
    settings = get_settings()
    if settings.plugin_health_enabled and _task is None:
        _task = asyncio.create_task(_loop())
        logger.info(
            "Plugin health monitor started (interval=%ds)",
            settings.plugin_health_interval_seconds,
        )


def stop_plugin_monitor() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
        logger.info("Plugin health monitor stopped")
