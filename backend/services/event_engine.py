"""Event Engine (1.3.0).

The ONLY producer of Events. Compares the newest inventory snapshot against
the previous one (never live inventory, never the whole history) and detects:

- Meaningful hardware changes (CPU replaced, memory capacity changed, disk
  added/removed, NIC added/removed) -> HardwareChanged
- Firmware / BIOS / management-controller / NIC / storage firmware version
  changes -> FirmwareChanged
- State transitions (offline, recovered, collector/credential failures,
  partial reachability changes) -> state events
- Sensor threshold breaches persisting for N consecutive collections
  (configurable, lifecycle policy) -> SensorThresholdExceeded / SensorRecovered

Sensor value fluctuations (temperature, fan RPM, voltage, power draw) never
generate hardware-change events — they belong to Health only.

The collector never calls this module directly; the SnapshotService pipeline
does, right after a snapshot is stored.
"""
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collectors.errors import ERROR_AUTH_FAILED
from collectors.manager import CollectionOutcome
from models import AlertSettings, CollectorRun, Device, DeviceStatus, Event, Sensor, Snapshot
from models.operations import (
    EVENT_COLLECTOR_FAILED,
    EVENT_CREDENTIAL_FAILED,
    EVENT_DEVICE_OFFLINE,
    EVENT_DEVICE_RECOVERED,
    EVENT_FIRMWARE_CHANGED,
    EVENT_HARDWARE_CHANGED,
    EVENT_NETWORK_REACHABILITY_CHANGED,
    EVENT_SENSOR_RECOVERED,
    EVENT_SENSOR_THRESHOLD_EXCEEDED,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from schemas.inventory import DeviceInventoryResponse
from services.drift_service import _diff_section  # shared diff primitive
from services.inventory_service import load_snapshot_inventory
from utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_FAILURE_THRESHOLD = 3

# Sensor statuses treated as healthy (mirrors health_service).
_SENSOR_OK_VALUES = {"ok", "healthy", "good", "normal", "enabled", None, ""}


@dataclass
class ChangeItem:
    section: str
    identifier: str
    change: str  # added / removed / changed
    field: str | None = None
    old_value: str | None = None
    new_value: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "identifier": self.identifier,
            "change": self.change,
            "field": self.field,
            "old": self.old_value,
            "new": self.new_value,
        }


async def get_failure_threshold(db: AsyncSession) -> int:
    settings = (await db.execute(select(AlertSettings))).scalars().first()
    if settings is None:
        return DEFAULT_FAILURE_THRESHOLD
    return max(1, settings.consecutive_failures_threshold)


# --------------------------------------------------------------------------- #
# Meaningful change detection (hardware vs firmware buckets)
# --------------------------------------------------------------------------- #
def _flatten_disks(inventory: DeviceInventoryResponse) -> list[Any]:
    disks: list[Any] = []
    for storage in inventory.storages:
        disks.extend(storage.disks)
    return disks


def compute_meaningful_changes(
    previous: DeviceInventoryResponse, current: DeviceInventoryResponse
) -> tuple[list[ChangeItem], list[ChangeItem]]:
    """Return (hardware_changes, firmware_changes).

    Only replacement-grade changes are reported: CPU model/serial, memory
    capacity/DIMM swaps, disk add/remove/replace, NIC add/remove/replace.
    Firmware bucket collects version changes from the firmware inventory
    (BIOS, iLO/BMC management controller, PSU, ...) plus NIC and storage
    controller firmware fields. Sensors are intentionally never compared.
    """
    hardware: list[ChangeItem] = []
    firmware: list[ChangeItem] = []

    def convert(changes: list[Any]) -> list[ChangeItem]:
        return [
            ChangeItem(
                section=c.section,
                identifier=c.identifier,
                change=c.change,
                field=c.field,
                old_value=c.old_value,
                new_value=c.new_value,
            )
            for c in changes
        ]

    hardware += convert(
        _diff_section(
            "CPU", previous.cpus, current.cpus,
            key=lambda c: c.socket or c.model or (c.serial or "cpu"),
            fields=["model", "serial"],
        )
    )
    hardware += convert(
        _diff_section(
            "Memory", previous.memories, current.memories,
            key=lambda m: m.slot or (m.serial or "dimm"),
            fields=["capacity_gb", "part_number", "serial"],
        )
    )
    hardware += convert(
        _diff_section(
            "Disk", _flatten_disks(previous), _flatten_disks(current),
            key=lambda d: d.serial or d.slot or "disk",
            fields=["model", "capacity"],
        )
    )
    hardware += convert(
        _diff_section(
            "NIC", previous.nics, current.nics,
            key=lambda n: n.mac or n.name or "nic",
            fields=["model", "serial"],
        )
    )

    firmware += convert(
        _diff_section(
            "Firmware", previous.firmwares, current.firmwares,
            key=lambda f: f.component or "firmware",
            fields=["version"],
        )
    )
    firmware += convert(
        _diff_section(
            "NIC Firmware", previous.nics, current.nics,
            key=lambda n: n.mac or n.name or "nic",
            fields=["firmware"],
        )
    )
    firmware += convert(
        _diff_section(
            "Storage Firmware", previous.storages, current.storages,
            key=lambda s: s.controller or (s.serial or "storage"),
            fields=["firmware"],
        )
    )
    # add/remove of a NIC/disk already appears in the hardware bucket; drop
    # duplicate added/removed rows from the firmware field diffs.
    firmware = [c for c in firmware if c.change == "changed"]
    return hardware, firmware


# --------------------------------------------------------------------------- #
# Sensor breach evaluation
# --------------------------------------------------------------------------- #
def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def is_sensor_breached(sensor: Sensor) -> bool:
    if (sensor.status or "").lower() not in _SENSOR_OK_VALUES:
        return True
    value = _parse_float(sensor.value)
    if value is None:
        return False
    upper = _parse_float(sensor.upper_threshold)
    lower = _parse_float(sensor.lower_threshold)
    if upper is not None and value > upper:
        return True
    if lower is not None and value < lower:
        return True
    return False


async def _sensors_for_snapshot(db: AsyncSession, snapshot_id: uuid.UUID) -> list[Sensor]:
    return list(
        (await db.execute(select(Sensor).where(Sensor.snapshot_id == snapshot_id)))
        .scalars().all()
    )


async def _previous_successful_snapshots(
    db: AsyncSession, device_id: uuid.UUID, before: Snapshot, limit: int
) -> list[Snapshot]:
    result = await db.execute(
        select(Snapshot)
        .where(
            Snapshot.device_id == device_id,
            Snapshot.id != before.id,
            Snapshot.collected_at <= before.collected_at,
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


async def _consecutive_failures(db: AsyncSession, device_id: uuid.UUID) -> int:
    """Consecutive failed collector runs, newest first (including the run
    recorded for the current collection)."""
    runs = (
        await db.execute(
            select(CollectorRun.success)
            .where(CollectorRun.device_id == device_id)
            .order_by(CollectorRun.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    count = 0
    for success in runs:
        if success:
            break
        count += 1
    return count


# --------------------------------------------------------------------------- #
# Event generation
# --------------------------------------------------------------------------- #
def _make_event(
    device: Device,
    event_type: str,
    severity: str,
    message: str,
    snapshot_id: uuid.UUID | None = None,
    previous_snapshot_id: uuid.UUID | None = None,
    changes: list[ChangeItem] | None = None,
    extra: dict[str, Any] | None = None,
    subject: str | None = None,
) -> Event:
    details: Any = None
    if changes is not None:
        details = {"changes": [c.as_dict() for c in changes]}
    if extra:
        details = {**(details or {}), **extra}
    return Event(
        device_id=device.id,
        event_type=event_type,
        severity=severity,
        # The Event Engine knows what changed, so it records the subject here
        # (the Alert Engine reuses it instead of re-parsing the JSON details).
        subject=subject,
        message=message,
        snapshot_id=snapshot_id,
        previous_snapshot_id=previous_snapshot_id,
        details=json.dumps(details, ensure_ascii=False) if details else None,
    )


async def generate_events(
    db: AsyncSession,
    device: Device,
    outcome: CollectionOutcome,
    old_status: DeviceStatus,
    had_active_state_alert: bool,
    active_sensor_subjects: set[str],
) -> list[Event]:
    """Compare snapshot N-1 vs N (or classify the failure) and emit events.

    The caller (SnapshotService) supplies alert-state context so this module
    stays independent of the Alert Engine's storage.
    """
    events: list[Event] = []
    threshold = await get_failure_threshold(db)

    if outcome.snapshot is None:
        failures = await _consecutive_failures(db, device.id)
        primary_code = next(
            (r.error_code for r in outcome.results if r.error_code), None
        )
        if primary_code == ERROR_AUTH_FAILED:
            # Credential failures never fix themselves — alert immediately.
            events.append(
                _make_event(
                    device, EVENT_CREDENTIAL_FAILED, SEVERITY_WARNING,
                    f"Authentication failed while collecting {device.hostname}",
                    extra={"consecutive_failures": failures},
                )
            )
        elif failures >= threshold:
            events.append(
                _make_event(
                    device, EVENT_DEVICE_OFFLINE, SEVERITY_CRITICAL,
                    f"{device.hostname} is offline "
                    f"({failures} consecutive failed collections)",
                    extra={"consecutive_failures": failures},
                )
            )
        else:
            events.append(
                _make_event(
                    device, EVENT_COLLECTOR_FAILED, SEVERITY_WARNING,
                    f"Collection failed for {device.hostname} "
                    f"({failures}/{threshold} before offline alert)",
                    extra={"consecutive_failures": failures, "threshold": threshold},
                )
            )
        return events

    snapshot = outcome.snapshot

    # --- Recovery -------------------------------------------------------------
    if had_active_state_alert:
        events.append(
            _make_event(
                device, EVENT_DEVICE_RECOVERED, SEVERITY_INFO,
                f"{device.hostname} recovered — collection succeeded",
                snapshot_id=snapshot.id,
            )
        )
    elif old_status != outcome.status and DeviceStatus.WARNING in (
        old_status, outcome.status
    ):
        # Partial reachability change (e.g. one management path lost/restored)
        # that is not a full offline/recovery transition.
        events.append(
            _make_event(
                device, EVENT_NETWORK_REACHABILITY_CHANGED, SEVERITY_WARNING,
                f"{device.hostname} reachability changed: "
                f"{old_status.value} -> {outcome.status.value}",
                snapshot_id=snapshot.id,
            )
        )

    # --- Snapshot N-1 vs N: hardware / firmware -------------------------------
    previous = await _previous_successful_snapshots(db, device.id, snapshot, limit=1)
    current_inv = await load_snapshot_inventory(db, snapshot)
    if previous:
        prev_snap = previous[0]
        previous_inv = await load_snapshot_inventory(db, prev_snap)
        hardware, firmware = compute_meaningful_changes(previous_inv, current_inv)

        by_section: dict[str, list[ChangeItem]] = {}
        for change in hardware:
            by_section.setdefault(change.section, []).append(change)
        for section, changes in by_section.items():
            events.append(
                _make_event(
                    device, EVENT_HARDWARE_CHANGED, SEVERITY_WARNING,
                    f"{section} changed on {device.hostname} "
                    f"({len(changes)} change{'s' if len(changes) != 1 else ''})",
                    snapshot_id=snapshot.id,
                    previous_snapshot_id=prev_snap.id,
                    changes=changes,
                    subject=section,
                )
            )
        if firmware:
            components = sorted({c.identifier for c in firmware})
            events.append(
                _make_event(
                    device, EVENT_FIRMWARE_CHANGED, SEVERITY_INFO,
                    f"Firmware changed on {device.hostname}: "
                    f"{', '.join(components[:5])}"
                    f"{'…' if len(components) > 5 else ''}",
                    snapshot_id=snapshot.id,
                    previous_snapshot_id=prev_snap.id,
                    changes=firmware,
                    subject=", ".join(components[:3]) or None,
                )
            )

    # --- Sensor lifecycle (threshold policy, never hardware alerts) ------------
    breached_now = {
        (s.name or s.type or "sensor"): s
        for s in current_inv.sensors
        if is_sensor_breached(s)
    }

    # SensorThresholdExceeded: breached in this AND the previous (threshold-1)
    # successful snapshots.
    if breached_now and threshold >= 1:
        history_snaps = await _previous_successful_snapshots(
            db, device.id, snapshot, limit=threshold - 1
        )
        persistent = set(breached_now)
        if threshold > 1:
            if len(history_snaps) < threshold - 1:
                persistent = set()  # not enough history to confirm persistence
            else:
                for snap in history_snaps:
                    sensors = await _sensors_for_snapshot(db, snap.id)
                    breached_then = {
                        (s.name or s.type or "sensor")
                        for s in sensors
                        if is_sensor_breached(s)
                    }
                    persistent &= breached_then
        for name in sorted(persistent):
            if name in active_sensor_subjects:
                continue  # alert already active; engine dedupes anyway
            sensor = breached_now[name]
            severity = (
                SEVERITY_CRITICAL
                if "crit" in (sensor.status or "").lower()
                else SEVERITY_WARNING
            )
            events.append(
                _make_event(
                    device, EVENT_SENSOR_THRESHOLD_EXCEEDED, severity,
                    f"Sensor '{name}' on {device.hostname} exceeded its threshold "
                    f"for {threshold} consecutive collections "
                    f"(value: {sensor.value or 'n/a'}{sensor.unit or ''})",
                    snapshot_id=snapshot.id,
                    subject=name,
                    extra={
                        "sensor": name,
                        "value": sensor.value,
                        "unit": sensor.unit,
                        "status": sensor.status,
                        "upper_threshold": sensor.upper_threshold,
                        "lower_threshold": sensor.lower_threshold,
                    },
                )
            )

    # SensorRecovered: an alerted sensor is no longer breached.
    for name in sorted(active_sensor_subjects - set(breached_now)):
        events.append(
            _make_event(
                device, EVENT_SENSOR_RECOVERED, SEVERITY_INFO,
                f"Sensor '{name}' on {device.hostname} returned to normal",
                snapshot_id=snapshot.id,
                subject=name,
                extra={"sensor": name},
            )
        )

    return events
