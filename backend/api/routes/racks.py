"""Rack CRUD and 42U layout read/write."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.dependencies import RequirePermission
from database import get_db
from models import Rack, RackUnit, User
from schemas.rack import (
    RackBulkCreate,
    RackBulkCreateResult,
    RackCreate,
    RackLayoutResponse,
    RackLayoutUpdate,
    RackResponse,
    RackUnitResponse,
    RackUpdate,
)
from services.audit_service import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_UPDATE,
    record_audit,
    snapshot_entity,
)
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/racks",
    tags=["racks"],
    dependencies=[Depends(RequirePermission("rack.view"))],
)


async def _get_rack(db: AsyncSession, rack_id: uuid.UUID) -> Rack:
    result = await db.execute(select(Rack).where(Rack.id == rack_id))
    rack = result.scalar_one_or_none()
    if rack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rack not found")
    return rack


@router.get("/{rack_id}", response_model=RackResponse)
async def get_rack(rack_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Rack:
    return await _get_rack(db, rack_id)


@router.get("/{rack_id}/layout", response_model=RackLayoutResponse)
async def get_rack_layout(
    rack_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> RackLayoutResponse:
    rack = await _get_rack(db, rack_id)
    result = await db.execute(
        select(RackUnit)
        .where(RackUnit.rack_id == rack_id)
        .options(selectinload(RackUnit.device))
        .order_by(RackUnit.u_position.desc())
    )
    units = list(result.scalars().all())
    return RackLayoutResponse(
        rack=RackResponse.model_validate(rack),
        units=[RackUnitResponse.model_validate(u) for u in units],
    )


@router.put(
    "/{rack_id}/layout",
    response_model=RackLayoutResponse,
    dependencies=[Depends(RequirePermission("rack.layout.edit"))],
)
async def update_rack_layout(
    rack_id: uuid.UUID, payload: RackLayoutUpdate, db: AsyncSession = Depends(get_db)
) -> RackLayoutResponse:
    rack = await _get_rack(db, rack_id)
    try:
        occupied: set[int] = set()
        for entry in payload.units:
            span = set(range(entry.u_position, entry.u_position + entry.height))
            if entry.u_position + entry.height - 1 > rack.height:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"U{entry.u_position} exceeds rack height {rack.height}U",
                )
            if span & occupied:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Overlapping units at U{entry.u_position}",
                )
            occupied |= span

        await db.execute(sa_delete(RackUnit).where(RackUnit.rack_id == rack_id))
        for entry in payload.units:
            db.add(
                RackUnit(
                    rack_id=rack_id,
                    u_position=entry.u_position,
                    height=entry.height,
                    device_id=entry.device_id,
                )
            )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("Rack layout update failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Layout update failed"
        ) from exc
    return await get_rack_layout(rack_id, db)


@router.post(
    "",
    response_model=RackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rack(
    payload: RackCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("rack.create")),
) -> Rack:
    try:
        rack = Rack(**payload.model_dump())
        db.add(rack)
        await db.flush()
        record_audit(
            db, admin, ACTION_CREATE, "rack", rack.name, rack.id,
            new_value=snapshot_entity(rack),
        )
        await db.commit()
        await db.refresh(rack)
        return rack
    except Exception as exc:
        logger.exception("Rack creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Rack creation failed"
        ) from exc


@router.post(
    "/bulk",
    response_model=RackBulkCreateResult,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_racks(
    payload: RackBulkCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("rack.create")),
) -> RackBulkCreateResult:
    """Create prefix-N racks in one call; existing names are skipped (F7)."""
    try:
        names = [
            f"{payload.prefix}-{index}"
            for index in range(payload.start_index, payload.start_index + payload.count)
        ]
        existing = set(
            (
                await db.execute(
                    select(Rack.name).where(
                        Rack.cluster_id == payload.cluster_id, Rack.name.in_(names)
                    )
                )
            )
            .scalars().all()
        )
        created: list[Rack] = []
        skipped: list[str] = []
        for name in names:
            if name in existing:
                skipped.append(name)
                continue
            rack = Rack(
                cluster_id=payload.cluster_id,
                name=name,
                height=payload.height,
                location=payload.location,
            )
            db.add(rack)
            created.append(rack)
        await db.flush()
        for rack in created:
            record_audit(
                db, admin, ACTION_CREATE, "rack", rack.name, rack.id,
                new_value=snapshot_entity(rack),
            )
        await db.commit()
        for rack in created:
            await db.refresh(rack)
        logger.info(
            "Bulk rack creation: %d created, %d skipped (prefix=%s)",
            len(created), len(skipped), payload.prefix,
        )
        return RackBulkCreateResult(
            created=[RackResponse.model_validate(rack) for rack in created],
            skipped=skipped,
        )
    except Exception as exc:
        await db.rollback()
        logger.exception("Bulk rack creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk rack creation failed",
        ) from exc


@router.patch("/{rack_id}", response_model=RackResponse)
async def update_rack(
    rack_id: uuid.UUID,
    payload: RackUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("rack.update")),
) -> Rack:
    rack = await _get_rack(db, rack_id)
    old = snapshot_entity(rack)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rack, key, value)
    record_audit(
        db, admin, ACTION_UPDATE, "rack", rack.name, rack.id,
        old_value=old, new_value=snapshot_entity(rack),
    )
    await db.commit()
    await db.refresh(rack)
    return rack


@router.delete("/{rack_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rack(
    rack_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(RequirePermission("rack.delete")),
) -> None:
    rack = await _get_rack(db, rack_id)
    record_audit(
        db, admin, ACTION_DELETE, "rack", rack.name, rack.id,
        old_value=snapshot_entity(rack),
    )
    await db.delete(rack)
    await db.commit()
