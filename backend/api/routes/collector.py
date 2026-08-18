"""Collector management endpoints (admin only): per-device status + run logs.
"Collect Now" reuses POST /devices/{id}/refresh."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from database import get_db
from models import CollectorRun, Device, Firmware, Sensor, Storage
from schemas.collector import CollectorDeviceStatus, CollectorRunResponse
from services.health_service import compute_health
from services.inventory_service import get_latest_snapshot
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/collector",
    tags=["collector"],
    dependencies=[Depends(RequirePermission("collector.view"))],
)

RECENT_LOGS_LIMIT: int = 50


@router.get("/status", response_model=list[CollectorDeviceStatus])
async def collector_status(db: AsyncSession = Depends(get_db)) -> list[CollectorDeviceStatus]:
    try:
        devices = (
            (await db.execute(select(Device).order_by(Device.hostname))).scalars().all()
        )
        entries: list[CollectorDeviceStatus] = []
        for device in devices:
            entry = CollectorDeviceStatus(
                device_id=device.id,
                hostname=device.hostname,
                display_name=device.display_name,
                device_type=device.device_type,
                status=device.status,
                rack_name=device.rack.name if device.rack else None,
                cluster_name=(
                    device.rack.cluster.name if device.rack and device.rack.cluster else None
                ),
            )

            snapshot = await get_latest_snapshot(db, device.id)
            if snapshot is not None:
                entry.last_snapshot_at = snapshot.collected_at
                sensors = (
                    (await db.execute(select(Sensor).where(Sensor.snapshot_id == snapshot.id)))
                    .scalars().all()
                )
                storages = (
                    (
                        await db.execute(
                            select(Storage).where(Storage.snapshot_id == snapshot.id)
                        )
                    )
                    .scalars().all()
                )
                firmwares = (
                    (
                        await db.execute(
                            select(Firmware).where(Firmware.snapshot_id == snapshot.id)
                        )
                    )
                    .scalars().all()
                )
                health = compute_health(
                    device.status, snapshot, list(sensors), list(storages), list(firmwares)
                )
                entry.health_score = health.score
                entry.health_label = health.label

            last_success = (
                await db.execute(
                    select(CollectorRun)
                    .where(CollectorRun.device_id == device.id, CollectorRun.success.is_(True))
                    .order_by(CollectorRun.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last_success is not None:
                entry.last_success_at = last_success.created_at

            last_failure = (
                await db.execute(
                    select(CollectorRun)
                    .where(
                        CollectorRun.device_id == device.id, CollectorRun.success.is_(False)
                    )
                    .order_by(CollectorRun.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if last_failure is not None:
                entry.last_failure_at = last_failure.created_at
                entry.last_error = last_failure.message
                entry.last_error_code = last_failure.error_code
                entry.last_error_readable = last_failure.readable_message

            entries.append(entry)
        return entries
    except Exception as exc:
        logger.exception("Collector status failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Collector status failed"
        ) from exc


@router.get("/devices/{device_id}/logs", response_model=list[CollectorRunResponse])
async def collector_logs(
    device_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=RECENT_LOGS_LIMIT, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[CollectorRun]:
    """Recent runs, newest first. Server-side pagination via page/page_size
    (defaults preserve the original behavior)."""
    result = await db.execute(
        select(CollectorRun)
        .where(CollectorRun.device_id == device_id)
        .order_by(CollectorRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all())
