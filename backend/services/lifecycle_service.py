"""Lifecycle / data-retention management (F5).

Admin-configurable retention per category with automatic cleanup. Current
inventory is always preserved: the latest snapshot per device is never deleted
regardless of age, so live inventory stays available.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    Alert,
    AlertSettings,
    CollectorRun,
    DeviceHistory,
    DiscoveredDevice,
    DiscoveryStatus,
    RetentionPolicy,
    Snapshot,
)
from models.operations import ALERT_RESOLVED
from models.retention import (
    CATEGORY_COLLECTOR_RUNS,
    CATEGORY_DISCOVERY,
    CATEGORY_HISTORY,
    CATEGORY_RESOLVED_ALERTS,
    CATEGORY_SNAPSHOTS,
    DEFAULT_RETENTION_DAYS,
    RETENTION_CATEGORIES,
)
from schemas.lifecycle import CleanupResult
from utils.logging import get_logger

logger = get_logger(__name__)


async def ensure_default_policies(db: AsyncSession) -> None:
    """Seed retention rows (disabled by default) on first start."""
    existing = set(
        (await db.execute(select(RetentionPolicy.category))).scalars().all()
    )
    created = False
    for category in RETENTION_CATEGORIES:
        if category not in existing:
            db.add(
                RetentionPolicy(
                    category=category,
                    retention_days=DEFAULT_RETENTION_DAYS[category],
                    enabled=False,
                )
            )
            created = True
    if created:
        await db.commit()


async def list_policies(db: AsyncSession) -> list[RetentionPolicy]:
    await ensure_default_policies(db)
    return list(
        (await db.execute(select(RetentionPolicy).order_by(RetentionPolicy.category)))
        .scalars().all()
    )


async def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


async def _cleanup_collector_runs(db: AsyncSession, days: int) -> int:
    result = await db.execute(
        delete(CollectorRun).where(CollectorRun.created_at < await _cutoff(days))
    )
    return result.rowcount or 0


async def _cleanup_snapshots(db: AsyncSession, days: int) -> int:
    """Delete old snapshots but keep each device's most recent one (current
    inventory must always remain available). Dialect-portable."""
    cutoff = await _cutoff(days)
    # Newest snapshot id(s) per device — never deleted regardless of age.
    newest = (
        select(Snapshot.device_id, func.max(Snapshot.collected_at).label("mx"))
        .group_by(Snapshot.device_id)
        .subquery()
    )
    keep_ids = set(
        (
            await db.execute(
                select(Snapshot.id).join(
                    newest,
                    and_(
                        Snapshot.device_id == newest.c.device_id,
                        Snapshot.collected_at == newest.c.mx,
                    ),
                )
            )
        ).scalars().all()
    )
    old = (
        (await db.execute(select(Snapshot.id).where(Snapshot.collected_at < cutoff)))
        .scalars().all()
    )
    to_delete = [sid for sid in old if sid not in keep_ids]
    if not to_delete:
        return 0
    result = await db.execute(delete(Snapshot).where(Snapshot.id.in_(to_delete)))
    return result.rowcount or 0


async def _cleanup_discovery(db: AsyncSession, days: int) -> int:
    cutoff = await _cutoff(days)
    result = await db.execute(
        delete(DiscoveredDevice).where(
            DiscoveredDevice.updated_at < cutoff,
            DiscoveredDevice.status != DiscoveryStatus.IMPORTED,
        )
    )
    return result.rowcount or 0


async def _cleanup_resolved_alerts(db: AsyncSession, days: int) -> int:
    """Only RESOLVED alerts are ever cleaned up; ACTIVE alerts are kept."""
    result = await db.execute(
        delete(Alert).where(
            Alert.status == ALERT_RESOLVED, Alert.created_at < await _cutoff(days)
        )
    )
    return result.rowcount or 0


async def _cleanup_history(db: AsyncSession, days: int) -> int:
    """Device history is permanent by default (policy ships disabled);
    deleting old entries is an explicit administrator opt-in."""
    result = await db.execute(
        delete(DeviceHistory).where(DeviceHistory.created_at < await _cutoff(days))
    )
    return result.rowcount or 0


_CLEANERS = {
    CATEGORY_COLLECTOR_RUNS: _cleanup_collector_runs,
    CATEGORY_SNAPSHOTS: _cleanup_snapshots,
    CATEGORY_DISCOVERY: _cleanup_discovery,
    CATEGORY_RESOLVED_ALERTS: _cleanup_resolved_alerts,
    CATEGORY_HISTORY: _cleanup_history,
}


async def get_alert_settings(db: AsyncSession) -> AlertSettings:
    """Singleton alert thresholds; created with defaults on first access."""
    settings = (await db.execute(select(AlertSettings))).scalars().first()
    if settings is None:
        settings = AlertSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def run_cleanup(db: AsyncSession) -> CleanupResult:
    """Apply every enabled retention policy. Returns per-category deletion counts."""
    await ensure_default_policies(db)
    policies = await list_policies(db)
    deleted: dict[str, int] = {}
    for policy in policies:
        if not policy.enabled:
            deleted[policy.category] = 0
            continue
        cleaner = _CLEANERS.get(policy.category)
        if cleaner is None:
            continue
        count = await cleaner(db, policy.retention_days)
        deleted[policy.category] = count
    await db.commit()
    total = sum(deleted.values())
    if total:
        logger.info("Retention cleanup removed %d rows: %s", total, deleted)
    return CleanupResult(deleted=deleted, total=total)
