"""Alert Center + device history APIs (1.3.0).

Alerts are produced only by the Alert Engine; this API reads them, filters
them and lets operators resolve them. History is immutable and read-only.
"""
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from database import get_db
from models import Alert, Cluster, Device, DeviceHistory, Rack, User
from models.operations import ALERT_RESOLVED
from schemas.operations import (
    AlertPage,
    AlertResponse,
    ChangeItemResponse,
    HistoryEntryResponse,
    HistoryPage,
)
from services.alert_engine import resolve_alert_manually
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["alerts"])

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


def _parse_details(raw: str | None) -> tuple[list[ChangeItemResponse], dict[str, Any] | None]:
    """Split the stored JSON into (changes list, remaining detail keys)."""
    if not raw:
        return [], None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return [], None
    if not isinstance(data, dict):
        return [], None
    changes = [
        ChangeItemResponse(**{k: v for k, v in item.items() if k in ChangeItemResponse.model_fields})
        for item in data.get("changes", [])
        if isinstance(item, dict)
    ]
    rest = {k: v for k, v in data.items() if k != "changes"}
    return changes, rest or None


def _serialize_alert(
    alert: Alert, device: Device | None, rack: Rack | None, cluster: Cluster | None
) -> AlertResponse:
    changes, rest = _parse_details(alert.details)
    return AlertResponse(
        id=alert.id,
        device_id=alert.device_id,
        hostname=device.hostname if device else "?",
        display_name=device.display_name if device else None,
        vendor=device.vendor if device else None,
        model=device.model if device else None,
        rack_id=rack.id if rack else None,
        rack_name=rack.name if rack else None,
        cluster_id=cluster.id if cluster else None,
        cluster_name=cluster.name if cluster else None,
        event_type=alert.event_type,
        category=alert.category,
        severity=alert.severity,
        status=alert.status,
        subject=alert.subject,
        message=alert.message,
        changes=changes,
        details=rest,
        auto_resolve=alert.auto_resolve,
        created_at=alert.created_at,
        resolved_at=alert.resolved_at,
        resolved_by=alert.resolved_by,
    )


def _alert_join_query():
    return (
        select(Alert, Device, Rack, Cluster)
        .join(Device, Device.id == Alert.device_id)
        .outerjoin(Rack, Rack.id == Device.rack_id)
        .outerjoin(Cluster, Cluster.id == Rack.cluster_id)
    )


@router.get(
    "/alerts",
    response_model=AlertPage,
    dependencies=[Depends(RequirePermission("alert.view"))],
)
async def list_alerts(
    severity: str | None = None,
    alert_status: str | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None, description="Operational domain"),
    event_type: str | None = Query(default=None, description="What happened"),
    cluster_id: uuid.UUID | None = None,
    rack_id: uuid.UUID | None = None,
    vendor: str | None = None,
    model: str | None = None,
    hostname: str | None = None,
    q: str | None = Query(default=None, description="Matches message or hostname"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
) -> AlertPage:
    query = _alert_join_query()
    if severity:
        query = query.where(Alert.severity == severity.upper())
    if alert_status:
        query = query.where(Alert.status == alert_status.upper())
    if category:
        query = query.where(Alert.category == category)
    if event_type:
        query = query.where(Alert.event_type == event_type)
    if cluster_id is not None:
        query = query.where(Cluster.id == cluster_id)
    if rack_id is not None:
        query = query.where(Rack.id == rack_id)
    if vendor:
        query = query.where(Device.vendor.ilike(f"%{vendor}%"))
    if model:
        query = query.where(Device.model.ilike(f"%{model}%"))
    if hostname:
        query = query.where(
            Device.hostname.ilike(f"%{hostname}%")
            | Device.display_name.ilike(f"%{hostname}%")
        )
    if q:
        pattern = f"%{q}%"
        query = query.where(
            Alert.message.ilike(pattern) | Device.hostname.ilike(pattern)
        )
    if date_from is not None:
        query = query.where(Alert.created_at >= date_from)
    if date_to is not None:
        query = query.where(Alert.created_at <= date_to)

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            query.order_by(Alert.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return AlertPage(
        items=[_serialize_alert(a, d, r, c) for a, d, r, c in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/alerts/{alert_id}",
    response_model=AlertResponse,
    dependencies=[Depends(RequirePermission("alert.view"))],
)
async def get_alert(alert_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AlertResponse:
    row = (
        await db.execute(_alert_join_query().where(Alert.id == alert_id))
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert, device, rack, cluster = row
    return _serialize_alert(alert, device, rack, cluster)


@router.patch("/alerts/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(RequirePermission("alert.resolve")),
) -> AlertResponse:
    row = (
        await db.execute(_alert_join_query().where(Alert.id == alert_id))
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert, device, rack, cluster = row
    if alert.status == ALERT_RESOLVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Alert is already resolved"
        )
    await resolve_alert_manually(db, alert, resolved_by=actor.username)
    await db.commit()
    await db.refresh(alert)
    logger.info("Alert %s resolved by %s", alert_id, actor.username)
    return _serialize_alert(alert, device, rack, cluster)


# --------------------------------------------------------------------------- #
# Device history (immutable, read-only)
# --------------------------------------------------------------------------- #
def _serialize_history(entry: DeviceHistory, hostname: str | None) -> HistoryEntryResponse:
    changes, rest = _parse_details(entry.details)
    return HistoryEntryResponse(
        id=entry.id,
        device_id=entry.device_id,
        hostname=hostname,
        kind=entry.kind,
        title=entry.title,
        changes=changes,
        details=rest,
        created_at=entry.created_at,
    )


async def _history_page(
    db: AsyncSession,
    page: int,
    page_size: int,
    device_id: uuid.UUID | None = None,
    kind: str | None = None,
    q: str | None = None,
) -> HistoryPage:
    query = select(DeviceHistory, Device.hostname).join(
        Device, Device.id == DeviceHistory.device_id
    )
    if device_id is not None:
        query = query.where(DeviceHistory.device_id == device_id)
    if kind:
        query = query.where(DeviceHistory.kind == kind)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            DeviceHistory.title.ilike(pattern) | Device.hostname.ilike(pattern)
        )
    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            query.order_by(DeviceHistory.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return HistoryPage(
        items=[_serialize_history(entry, hostname) for entry, hostname in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/history",
    response_model=HistoryPage,
    dependencies=[Depends(RequirePermission("history.view"))],
)
async def list_history(
    device_id: uuid.UUID | None = None,
    kind: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
) -> HistoryPage:
    return await _history_page(db, page, page_size, device_id=device_id, kind=kind, q=q)


@router.get(
    "/history/device/{device_id}",
    response_model=HistoryPage,
    dependencies=[Depends(RequirePermission("history.view"))],
)
async def device_history(
    device_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
) -> HistoryPage:
    device = (
        await db.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return await _history_page(db, page, page_size, device_id=device_id)
