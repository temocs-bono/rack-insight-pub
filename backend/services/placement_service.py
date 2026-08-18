"""Shared rack-placement validation (1.1.3).

Previously the U-position / overlap / rack-height checks were duplicated across
create_device, move_device and bulk_create_devices with subtle differences —
including a `device_id != device_id` filter that silently excluded orphan
(NULL device_id) rack_units from overlap detection. This module is the single
source of truth used by every placement path.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Rack, RackUnit

# (u_position, height) pairs currently occupying a rack.
OccupiedRange = tuple[int, int]


def ranges_overlap(u_position: int, height: int, ranges: list[OccupiedRange]) -> int | None:
    """Return the anchor U of the first range that overlaps [u, u+height), else None."""
    target = range(u_position, u_position + height)
    target_set = set(target)
    for pos, span_height in ranges:
        if target_set & set(range(pos, pos + span_height)):
            return pos
    return None


async def occupied_ranges(
    db: AsyncSession, rack_id: uuid.UUID, exclude_unit_id: uuid.UUID | None = None
) -> list[OccupiedRange]:
    """Every occupied (u_position, height) in a rack, excluding one unit by id.

    Excluding by the unit's own id (not device_id) is what lets a device be
    moved onto part of its own current span, and correctly counts every other
    unit including any legacy orphans.
    """
    units = (
        (await db.execute(select(RackUnit).where(RackUnit.rack_id == rack_id)))
        .scalars().all()
    )
    return [
        (unit.u_position, unit.height)
        for unit in units
        if exclude_unit_id is None or unit.id != exclude_unit_id
    ]


def validate_within_rack(rack: Rack, u_position: int, height: int) -> None:
    if u_position + height - 1 > rack.height:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"U{u_position} (+{height}U) exceeds rack height {rack.height}U",
        )


async def validate_placement(
    db: AsyncSession,
    rack: Rack,
    u_position: int,
    height: int,
    exclude_unit_id: uuid.UUID | None = None,
) -> None:
    """Raise HTTP 422 if the placement exceeds the rack or overlaps another unit."""
    validate_within_rack(rack, u_position, height)
    conflict = ranges_overlap(
        u_position, height, await occupied_ranges(db, rack.id, exclude_unit_id)
    )
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"U{u_position} overlaps an existing unit at U{conflict}",
        )
