"""Background scheduler: every N seconds (default 30 min) re-collect all
enabled devices so the UI stays current without user action.

Since 1.3.0 the scheduler runs the full snapshot pipeline (collect -> snapshot
-> event engine -> alert engine), and it also retries devices that are not
ONLINE — otherwise offline devices could never auto-recover (and their state
alerts could never auto-resolve) without a manual refresh."""
import asyncio

from sqlalchemy import select

from cache.redis_cache import cache_set, device_inventory_key
from config import get_settings
from database import async_session_factory
from models import Device
from services.inventory_service import load_snapshot_inventory
from services.lifecycle_service import run_cleanup
from services.snapshot_service import collect_and_process
from utils.logging import get_logger

logger = get_logger(__name__)

_task: asyncio.Task[None] | None = None


async def _collect_all_enabled() -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Device).where(Device.enabled.is_(True)))
        devices = list(result.scalars().all())
        logger.info("Scheduler run: %d enabled devices", len(devices))
        for device in devices:
            try:
                pipeline = await collect_and_process(db, device, trigger="scheduled")
                await db.commit()
                if pipeline.outcome.snapshot is not None:
                    inventory = await load_snapshot_inventory(
                        db, pipeline.outcome.snapshot
                    )
                    await cache_set(
                        device_inventory_key(str(device.id)),
                        inventory.model_dump(mode="json"),
                    )
            except Exception:
                await db.rollback()
                logger.exception("Scheduled collection failed for %s", device.hostname)


async def _run_retention_cleanup() -> None:
    async with async_session_factory() as db:
        await run_cleanup(db)


async def _loop() -> None:
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.scheduler_interval_seconds)
        try:
            await _collect_all_enabled()
        except Exception:
            logger.exception("Scheduler iteration failed")
        try:
            # Reuse the existing scheduler loop to apply enabled retention
            # policies (F5). No new scheduler is introduced.
            await _run_retention_cleanup()
        except Exception:
            logger.exception("Retention cleanup iteration failed")


def start_scheduler() -> None:
    global _task
    if get_settings().scheduler_enabled and _task is None:
        _task = asyncio.create_task(_loop())
        logger.info(
            "Background scheduler started (interval=%ds)",
            get_settings().scheduler_interval_seconds,
        )


def stop_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
        logger.info("Background scheduler stopped")
