"""Audit log read API (admin only), server-side paginated."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from database import get_db
from models import AuditLog
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(RequirePermission("audit.view"))],
)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    entity_name: str | None
    old_value: str | None
    new_value: str | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=AuditLogPage)
async def list_audit_logs(
    entity_type: str | None = None,
    action: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
) -> AuditLogPage:
    try:
        query = select(AuditLog)
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
        if action:
            query = query.where(AuditLog.action == action.upper())
        total = (
            await db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        result = await db.execute(
            query.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return AuditLogPage(
            items=[AuditLogResponse.model_validate(row) for row in result.scalars().all()],
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        logger.exception("Audit log read failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Audit log read failed"
        ) from exc
