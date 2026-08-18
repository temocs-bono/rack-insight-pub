"""Inventory export endpoints (any authenticated user, read-only)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import RequirePermission
from database import get_db
from services.export_service import EXPORT_FORMATS, EXPORT_SCOPES, export_inventory
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/export",
    tags=["export"],
    dependencies=[Depends(RequirePermission("export.run"))],
)


@router.get(
    "",
    summary="Export inventory as JSON, CSV (zip) or Excel",
    response_class=Response,
)
async def export(
    scope: str = Query(description=f"One of: {', '.join(EXPORT_SCOPES)}"),
    format: str = Query(default="json", description=f"One of: {', '.join(EXPORT_FORMATS)}"),
    target_id: uuid.UUID | None = Query(
        default=None, description="Device / rack / cluster id (not needed for scope=all)"
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        payload = await export_inventory(db, scope, target_id, format)
        return Response(
            content=payload.content,
            media_type=payload.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{payload.filename}"'
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Inventory export failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Export failed"
        ) from exc
