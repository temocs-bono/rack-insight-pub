"""Device refresh flow (1.3.0 pipeline):
delete cache -> SnapshotService (collect -> snapshot -> events -> alerts)
-> repopulate cache -> return fresh inventory.

The collector never creates alerts; the pipeline in snapshot_service does.
"""
import uuid

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cache.redis_cache import cache_delete, cache_set, device_inventory_key
from models import Device
from schemas.inventory import DeviceInventoryResponse
from services.inventory_service import load_snapshot_inventory
from services.refresh_helpers import record_collector_run  # noqa: F401 (re-export)
from services.snapshot_service import collect_and_process
from utils.logging import get_logger

logger = get_logger(__name__)


async def refresh_device(db: AsyncSession, device_id: uuid.UUID) -> DeviceInventoryResponse:
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Device not found"
        )

    key = device_inventory_key(str(device_id))
    await cache_delete(key)

    pipeline = await collect_and_process(db, device, trigger="manual")
    await db.commit()

    if pipeline.outcome.snapshot is None:
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="All collectors failed; previous data preserved",
        )

    inventory = await load_snapshot_inventory(db, pipeline.outcome.snapshot)
    await cache_set(key, inventory.model_dump(mode="json"))
    return inventory
