"""Dashboard endpoints: inventory summary + operations (alerts/health)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.alerts import _alert_join_query, _serialize_alert, _serialize_history
from auth.dependencies import RequirePermission
from database import get_db
from models import Alert, Device, DeviceHistory, DeviceStatus
from models.operations import (
    ALERT_ACTIVE,
    HISTORY_FIRMWARE_CHANGE,
    HISTORY_HARDWARE_CHANGE,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from schemas.dashboard import DashboardSummary
from schemas.operations import DashboardAlerts, DashboardHealth
from services.summary_service import dashboard_summary
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(RequirePermission("dashboard.view"))],
)

LATEST_ALERTS_LIMIT = 10
RECENT_CHANGES_LIMIT = 5


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(db: AsyncSession = Depends(get_db)) -> DashboardSummary:
    try:
        return await dashboard_summary(db)
    except Exception as exc:
        logger.exception("Dashboard summary failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard summary failed",
        ) from exc


async def _active_count(db: AsyncSession, severity: str) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Alert)
            .where(Alert.status == ALERT_ACTIVE, Alert.severity == severity)
        )
    ).scalar_one()


async def _recent_history(db: AsyncSession, kind: str) -> list:
    rows = (
        await db.execute(
            select(DeviceHistory, Device.hostname)
            .join(Device, Device.id == DeviceHistory.device_id)
            .where(DeviceHistory.kind == kind)
            .order_by(DeviceHistory.created_at.desc())
            .limit(RECENT_CHANGES_LIMIT)
        )
    ).all()
    return [_serialize_history(entry, hostname) for entry, hostname in rows]


@router.get("/alerts", response_model=DashboardAlerts)
async def dashboard_alerts(db: AsyncSession = Depends(get_db)) -> DashboardAlerts:
    """Operations overview: active alert counts, latest alerts, critical
    devices, and recent hardware/firmware changes."""
    try:
        offline = (
            await db.execute(
                select(func.count())
                .select_from(Device)
                .where(Device.status == DeviceStatus.OFFLINE)
            )
        ).scalar_one()

        # Healthy = ONLINE with no active WARNING/CRITICAL alert.
        troubled = (
            select(Alert.device_id)
            .where(
                Alert.status == ALERT_ACTIVE,
                Alert.severity.in_((SEVERITY_WARNING, SEVERITY_CRITICAL)),
            )
            .distinct()
        )
        healthy = (
            await db.execute(
                select(func.count())
                .select_from(Device)
                .where(
                    Device.status == DeviceStatus.ONLINE,
                    Device.id.not_in(troubled),
                )
            )
        ).scalar_one()

        latest_rows = (
            await db.execute(
                _alert_join_query()
                .order_by(Alert.created_at.desc())
                .limit(LATEST_ALERTS_LIMIT)
            )
        ).all()
        critical_rows = (
            await db.execute(
                _alert_join_query()
                .where(
                    Alert.status == ALERT_ACTIVE,
                    Alert.severity == SEVERITY_CRITICAL,
                )
                .order_by(Alert.created_at.desc())
                .limit(LATEST_ALERTS_LIMIT)
            )
        ).all()

        return DashboardAlerts(
            active_critical=await _active_count(db, SEVERITY_CRITICAL),
            active_warning=await _active_count(db, SEVERITY_WARNING),
            active_info=await _active_count(db, SEVERITY_INFO),
            offline_devices=offline,
            healthy_devices=healthy,
            latest_alerts=[_serialize_alert(a, d, r, c) for a, d, r, c in latest_rows],
            critical_devices=[
                _serialize_alert(a, d, r, c) for a, d, r, c in critical_rows
            ],
            recent_hardware_changes=await _recent_history(db, HISTORY_HARDWARE_CHANGE),
            recent_firmware_changes=await _recent_history(db, HISTORY_FIRMWARE_CHANGE),
        )
    except Exception as exc:
        logger.exception("Dashboard alerts failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard alerts failed",
        ) from exc


@router.get("/health", response_model=DashboardHealth)
async def dashboard_health(db: AsyncSession = Depends(get_db)) -> DashboardHealth:
    """Fleet health buckets: Healthy / Warning / Critical / Unknown / Offline."""
    try:
        devices = (await db.execute(select(Device.id, Device.status))).all()
        critical_ids = set(
            (
                await db.execute(
                    select(Alert.device_id)
                    .where(
                        Alert.status == ALERT_ACTIVE,
                        Alert.severity == SEVERITY_CRITICAL,
                    )
                    .distinct()
                )
            ).scalars().all()
        )
        warning_ids = set(
            (
                await db.execute(
                    select(Alert.device_id)
                    .where(
                        Alert.status == ALERT_ACTIVE,
                        Alert.severity == SEVERITY_WARNING,
                    )
                    .distinct()
                )
            ).scalars().all()
        )

        buckets = {"healthy": 0, "warning": 0, "critical": 0, "unknown": 0, "offline": 0}
        for device_id, device_status in devices:
            if device_status == DeviceStatus.OFFLINE:
                buckets["offline"] += 1
            elif device_id in critical_ids:
                buckets["critical"] += 1
            elif device_id in warning_ids or device_status == DeviceStatus.WARNING:
                buckets["warning"] += 1
            elif device_status == DeviceStatus.UNKNOWN:
                buckets["unknown"] += 1
            else:
                buckets["healthy"] += 1

        return DashboardHealth(total=len(devices), **buckets)
    except Exception as exc:
        logger.exception("Dashboard health failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard health failed",
        ) from exc
