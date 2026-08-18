"""Dashboard summaries: cluster cards, rack cards and global device counts."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cache.redis_cache import cache_get, cache_set
from models import Cluster, Device, DeviceStatus, DeviceType, Firmware, Rack, Sensor, Snapshot, Storage
from schemas.cluster import ClusterSummary
from schemas.dashboard import DashboardSummary
from schemas.rack import RackSummary
from services.health_service import compute_health
from services.inventory_service import get_latest_snapshot

DASHBOARD_SUMMARY_CACHE_KEY = "rackinsight:dashboard:summary"
DASHBOARD_SUMMARY_TTL_SECONDS = 60


async def cluster_summaries(db: AsyncSession) -> list[ClusterSummary]:
    clusters = (await db.execute(select(Cluster).order_by(Cluster.name))).scalars().all()
    summaries: list[ClusterSummary] = []
    for cluster in clusters:
        rack_ids = (
            (await db.execute(select(Rack.id).where(Rack.cluster_id == cluster.id)))
            .scalars().all()
        )
        summary = ClusterSummary.model_validate(cluster)
        summary.rack_count = len(rack_ids)
        if rack_ids:
            devices = (
                (await db.execute(select(Device).where(Device.rack_id.in_(rack_ids))))
                .scalars().all()
            )
            summary.device_count = len(devices)
            summary.server_count = sum(
                1 for d in devices if d.device_type == DeviceType.SERVER
            )
            summary.switch_count = sum(
                1 for d in devices if d.device_type == DeviceType.SWITCH
            )
            summary.online_count = sum(1 for d in devices if d.status == DeviceStatus.ONLINE)
            summary.warning_count = sum(
                1 for d in devices if d.status == DeviceStatus.WARNING
            )
            device_ids = [d.id for d in devices]
            if device_ids:
                summary.last_refresh = (
                    await db.execute(
                        select(func.max(Snapshot.collected_at)).where(
                            Snapshot.device_id.in_(device_ids)
                        )
                    )
                ).scalar_one_or_none()
        summaries.append(summary)
    return summaries


async def rack_summaries(db: AsyncSession, cluster_id: uuid.UUID) -> list[RackSummary]:
    racks = (
        (await db.execute(select(Rack).where(Rack.cluster_id == cluster_id).order_by(Rack.name)))
        .scalars().all()
    )
    summaries: list[RackSummary] = []
    for rack in racks:
        devices = (
            (await db.execute(select(Device).where(Device.rack_id == rack.id))).scalars().all()
        )
        summary = RackSummary.model_validate(rack)
        summary.device_count = len(devices)
        summary.online_count = sum(1 for d in devices if d.status == DeviceStatus.ONLINE)
        summary.offline_count = sum(1 for d in devices if d.status == DeviceStatus.OFFLINE)
        summary.warning_count = sum(1 for d in devices if d.status == DeviceStatus.WARNING)
        summaries.append(summary)
    return summaries


async def dashboard_summary(db: AsyncSession) -> DashboardSummary:
    """Global device counts by status plus health-critical devices.

    "Critical" means the latest snapshot's health score falls in the
    Critical band; cached briefly since it walks per-device health data.
    """
    cached = await cache_get(DASHBOARD_SUMMARY_CACHE_KEY)
    if cached is not None:
        return DashboardSummary.model_validate(cached)

    devices = (await db.execute(select(Device))).scalars().all()
    summary = DashboardSummary(
        total_devices=len(devices),
        online=sum(1 for d in devices if d.status == DeviceStatus.ONLINE),
        warning=sum(1 for d in devices if d.status == DeviceStatus.WARNING),
        offline=sum(1 for d in devices if d.status == DeviceStatus.OFFLINE),
        unknown=sum(1 for d in devices if d.status == DeviceStatus.UNKNOWN),
    )

    critical = 0
    for device in devices:
        snapshot = await get_latest_snapshot(db, device.id)
        if snapshot is None:
            continue
        sensors = (
            (await db.execute(select(Sensor).where(Sensor.snapshot_id == snapshot.id)))
            .scalars().all()
        )
        storages = (
            (await db.execute(select(Storage).where(Storage.snapshot_id == snapshot.id)))
            .scalars().all()
        )
        firmwares = (
            (await db.execute(select(Firmware).where(Firmware.snapshot_id == snapshot.id)))
            .scalars().all()
        )
        health = compute_health(
            device.status, snapshot, list(sensors), list(storages), list(firmwares)
        )
        if health.label == "Critical":
            critical += 1
    summary.critical = critical

    await cache_set(
        DASHBOARD_SUMMARY_CACHE_KEY,
        summary.model_dump(),
        ttl_seconds=DASHBOARD_SUMMARY_TTL_SECONDS,
    )
    return summary
