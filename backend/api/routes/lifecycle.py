"""Lifecycle / retention + alert-threshold settings endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from database import get_db
from models import RetentionPolicy
from schemas.lifecycle import CleanupResult, RetentionPolicyResponse, RetentionPolicyUpdate
from schemas.operations import AlertSettingsResponse, AlertSettingsUpdate
from services.lifecycle_service import get_alert_settings, list_policies, run_cleanup
from sqlalchemy import select
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/lifecycle",
    tags=["lifecycle"],
    dependencies=[Depends(RequirePermission("lifecycle.view"))],
)


@router.get("/policies", response_model=list[RetentionPolicyResponse])
async def get_policies(db: AsyncSession = Depends(get_db)) -> list[RetentionPolicy]:
    return await list_policies(db)


@router.patch(
    "/policies/{category}",
    response_model=RetentionPolicyResponse,
    dependencies=[Depends(RequirePermission("lifecycle.manage"))],
)
async def update_policy(
    category: str, payload: RetentionPolicyUpdate, db: AsyncSession = Depends(get_db)
) -> RetentionPolicy:
    await list_policies(db)  # ensure defaults exist
    policy = (
        await db.execute(select(RetentionPolicy).where(RetentionPolicy.category == category))
    ).scalar_one_or_none()
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Retention category not found"
        )
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, key, value)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/alert-settings", response_model=AlertSettingsResponse)
async def read_alert_settings(db: AsyncSession = Depends(get_db)) -> AlertSettingsResponse:
    settings = await get_alert_settings(db)
    return AlertSettingsResponse(
        consecutive_failures_threshold=settings.consecutive_failures_threshold
    )


@router.patch(
    "/alert-settings",
    response_model=AlertSettingsResponse,
    dependencies=[Depends(RequirePermission("lifecycle.manage"))],
)
async def update_alert_settings(
    payload: AlertSettingsUpdate, db: AsyncSession = Depends(get_db)
) -> AlertSettingsResponse:
    """Configure how many consecutive failed collections / sensor breaches are
    required before a state alert fires (default 3)."""
    settings = await get_alert_settings(db)
    settings.consecutive_failures_threshold = payload.consecutive_failures_threshold
    await db.commit()
    await db.refresh(settings)
    return AlertSettingsResponse(
        consecutive_failures_threshold=settings.consecutive_failures_threshold
    )


@router.post(
    "/cleanup", response_model=CleanupResult,
    dependencies=[Depends(RequirePermission("lifecycle.manage"))],
)
async def cleanup(db: AsyncSession = Depends(get_db)) -> CleanupResult:
    try:
        return await run_cleanup(db)
    except Exception as exc:
        await db.rollback()
        logger.exception("Retention cleanup failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cleanup failed"
        ) from exc
