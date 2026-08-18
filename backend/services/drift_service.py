"""Inventory drift detection (F4).

Compares a device's two most recent successful snapshots and reports hardware
changes (added / removed / changed) per section: CPU, Memory, NIC, Storage,
Firmware (incl. BIOS), Network — covering serial numbers and firmware/BIOS
versions. Reuses the existing snapshot inventory loader.
"""
import uuid
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Snapshot
from schemas.drift import DriftChange, DriftReport
from schemas.inventory import DeviceInventoryResponse
from services.inventory_service import load_snapshot_inventory

CHANGE_ADDED = "added"
CHANGE_REMOVED = "removed"
CHANGE_CHANGED = "changed"


async def _recent_successful_snapshots(
    db: AsyncSession, device_id: uuid.UUID, limit: int = 2
) -> list[Snapshot]:
    result = await db.execute(
        select(Snapshot)
        .where(
            Snapshot.device_id == device_id,
            (
                Snapshot.redfish_success.is_(True)
                | Snapshot.ssh_success.is_(True)
                | Snapshot.virsh_success.is_(True)
            ),
        )
        .order_by(Snapshot.collected_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def _diff_section(
    section: str,
    previous: list[Any],
    current: list[Any],
    key: Callable[[Any], str],
    fields: list[str],
) -> list[DriftChange]:
    changes: list[DriftChange] = []
    prev_by_key = {key(item): item for item in previous}
    cur_by_key = {key(item): item for item in current}

    for identifier in cur_by_key.keys() - prev_by_key.keys():
        changes.append(
            DriftChange(section=section, identifier=identifier, change=CHANGE_ADDED)
        )
    for identifier in prev_by_key.keys() - cur_by_key.keys():
        changes.append(
            DriftChange(section=section, identifier=identifier, change=CHANGE_REMOVED)
        )
    for identifier in cur_by_key.keys() & prev_by_key.keys():
        before, after = prev_by_key[identifier], cur_by_key[identifier]
        for field in fields:
            old_value = getattr(before, field, None)
            new_value = getattr(after, field, None)
            if old_value != new_value:
                changes.append(
                    DriftChange(
                        section=section,
                        identifier=identifier,
                        field=field,
                        change=CHANGE_CHANGED,
                        old_value=None if old_value is None else str(old_value),
                        new_value=None if new_value is None else str(new_value),
                    )
                )
    return changes


def compute_inventory_drift(
    previous: DeviceInventoryResponse, current: DeviceInventoryResponse
) -> list[DriftChange]:
    changes: list[DriftChange] = []
    changes += _diff_section(
        "CPU", previous.cpus, current.cpus,
        key=lambda c: c.socket or c.model or (c.serial or "cpu"),
        fields=["model", "cores", "threads", "frequency", "microcode", "serial"],
    )
    changes += _diff_section(
        "Memory", previous.memories, current.memories,
        key=lambda m: m.slot or (m.serial or "dimm"),
        fields=["capacity_gb", "type", "speed", "part_number", "serial", "status"],
    )
    changes += _diff_section(
        "NIC", previous.nics, current.nics,
        key=lambda n: n.mac or n.name or "nic",
        fields=["firmware", "driver", "speed", "link_status", "model"],
    )
    changes += _diff_section(
        "Storage", previous.storages, current.storages,
        key=lambda s: s.controller or (s.serial or "storage"),
        fields=["firmware", "raid_level", "health", "model", "serial"],
    )
    changes += _diff_section(
        "Firmware", previous.firmwares, current.firmwares,
        key=lambda f: f.component or "firmware",
        fields=["version", "release_date", "health"],
    )
    changes += _diff_section(
        "Network", previous.networks, current.networks,
        key=lambda n: n.interface or (n.mac or "iface"),
        fields=["ipv4", "ipv6", "mac", "speed", "mtu"],
    )
    return changes


async def get_device_drift(db: AsyncSession, device_id: uuid.UUID) -> DriftReport:
    snapshots = await _recent_successful_snapshots(db, device_id)
    if len(snapshots) < 2:
        return DriftReport(
            has_previous=False,
            current_collected_at=snapshots[0].collected_at if snapshots else None,
            previous_collected_at=None,
            changes=[],
        )
    current_snap, previous_snap = snapshots[0], snapshots[1]
    current_inv = await load_snapshot_inventory(db, current_snap)
    previous_inv = await load_snapshot_inventory(db, previous_snap)
    return DriftReport(
        has_previous=True,
        current_collected_at=current_snap.collected_at,
        previous_collected_at=previous_snap.collected_at,
        changes=compute_inventory_drift(previous_inv, current_inv),
    )
