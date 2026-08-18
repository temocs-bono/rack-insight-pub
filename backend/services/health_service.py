"""Health Score (0-100) per specification:

Online(+30), Collector Success(+20), Power OK(+10), Fan OK(+10),
Storage OK(+10), Firmware OK(+10), Sensor OK(+10).
95-100 Healthy / 80-94 Warning / 0-79 Critical.

1.3.0 adds the Device Health detail (sensor groups, storage/memory/network
health, health timeline). Health is separate from inventory and from alerts:
sensor fluctuations only ever affect Health, never hardware-change alerts.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Device, DeviceStatus, Firmware, Memory, NIC, Sensor, Snapshot, Storage
from schemas.operations import (
    DeviceHealthResponse,
    HealthTimelinePoint,
    SensorSummary,
)

SCORE_ONLINE: int = 30
SCORE_COLLECTOR_SUCCESS: int = 20
SCORE_POWER_OK: int = 10
SCORE_FAN_OK: int = 10
SCORE_STORAGE_OK: int = 10
SCORE_FIRMWARE_OK: int = 10
SCORE_SENSOR_OK: int = 10

HEALTHY_MIN: int = 95
WARNING_MIN: int = 80

_OK_VALUES = {"ok", "healthy", "good", "normal", "enabled", None, ""}


@dataclass
class HealthScore:
    score: int
    label: str


def _all_ok(statuses: list[str | None]) -> bool:
    return all((status or "").lower() in _OK_VALUES for status in statuses)


def compute_health(
    status: DeviceStatus,
    snapshot: Snapshot | None,
    sensors: list[Sensor],
    storages: list[Storage],
    firmwares: list[Firmware],
) -> HealthScore:
    score = 0
    if status == DeviceStatus.ONLINE:
        score += SCORE_ONLINE
    if snapshot is not None and (
        snapshot.redfish_success or snapshot.ssh_success or snapshot.virsh_success
    ):
        score += SCORE_COLLECTOR_SUCCESS

    power_sensors = [s.status for s in sensors if (s.type or "").lower() == "power"]
    fan_sensors = [s.status for s in sensors if (s.type or "").lower() == "fan"]
    other_sensors = [
        s.status for s in sensors if (s.type or "").lower() not in ("power", "fan")
    ]

    if _all_ok(power_sensors):
        score += SCORE_POWER_OK
    if _all_ok(fan_sensors):
        score += SCORE_FAN_OK
    if _all_ok([s.health for s in storages]):
        score += SCORE_STORAGE_OK
    if _all_ok([f.health for f in firmwares]):
        score += SCORE_FIRMWARE_OK
    if _all_ok(other_sensors):
        score += SCORE_SENSOR_OK

    if score >= HEALTHY_MIN:
        label = "Healthy"
    elif score >= WARNING_MIN:
        label = "Warning"
    else:
        label = "Critical"
    return HealthScore(score=score, label=label)


# --------------------------------------------------------------------------- #
# Device Health detail (1.3.0)
# --------------------------------------------------------------------------- #
LABEL_HEALTHY = "Healthy"
LABEL_WARNING = "Warning"
LABEL_CRITICAL = "Critical"
LABEL_UNKNOWN = "Unknown"

TIMELINE_LIMIT = 10

_SENSOR_GROUPS = ("temperature", "power", "fan", "other")


def _sensor_group(sensor: Sensor) -> str:
    kind = f"{sensor.type or ''} {sensor.name or ''}".lower()
    if "temp" in kind or "thermal" in kind:
        return "temperature"
    if "power" in kind or "watt" in kind or "psu" in kind:
        return "power"
    if "fan" in kind:
        return "fan"
    return "other"


def _statuses_label(statuses: list[str | None], total: int) -> str:
    if total == 0:
        return LABEL_UNKNOWN
    breached = [s for s in statuses if (s or "").lower() not in _OK_VALUES]
    if not breached:
        return LABEL_HEALTHY
    if any("crit" in (s or "").lower() or "fail" in (s or "").lower() for s in breached):
        return LABEL_CRITICAL
    return LABEL_WARNING


async def _snapshot_health(
    db: AsyncSession, device_status: DeviceStatus, snapshot: Snapshot
) -> HealthScore:
    sensors = (
        (await db.execute(select(Sensor).where(Sensor.snapshot_id == snapshot.id)))
        .scalars().all()
    )
    storages = (
        (await db.execute(select(Storage).where(Storage.snapshot_id == snapshot.id)))
        .scalars().all()
    )
    firmwares = (
        (await db.execute(select(Firmware).where(Firmware.snapshot_id == snapshot.id)))
        .scalars().all()
    )
    return compute_health(
        device_status, snapshot, list(sensors), list(storages), list(firmwares)
    )


async def get_device_health(db: AsyncSession, device: Device) -> DeviceHealthResponse:
    """Full health view for the Health tab: overall label/score, per-group
    sensor summary, storage/memory/network health, and a timeline across the
    most recent snapshots."""
    from services.event_engine import is_sensor_breached  # avoid import cycle

    snapshots = list(
        (
            await db.execute(
                select(Snapshot)
                .where(
                    Snapshot.device_id == device.id,
                    (
                        Snapshot.redfish_success.is_(True)
                        | Snapshot.ssh_success.is_(True)
                        | Snapshot.virsh_success.is_(True)
                    ),
                )
                .order_by(Snapshot.collected_at.desc())
                .limit(TIMELINE_LIMIT)
            )
        ).scalars().all()
    )

    if not snapshots:
        return DeviceHealthResponse(
            overall_label=LABEL_UNKNOWN,
            overall_score=None,
            status=device.status.value,
            last_collected_at=None,
            sensor_groups=[],
            storage_label=LABEL_UNKNOWN,
            memory_label=LABEL_UNKNOWN,
            network_label=LABEL_UNKNOWN,
            timeline=[],
        )

    latest = snapshots[0]
    sensors = (
        (await db.execute(select(Sensor).where(Sensor.snapshot_id == latest.id)))
        .scalars().all()
    )
    storages = (
        (await db.execute(select(Storage).where(Storage.snapshot_id == latest.id)))
        .scalars().all()
    )
    memories = (
        (await db.execute(select(Memory).where(Memory.snapshot_id == latest.id)))
        .scalars().all()
    )
    nics = (
        (await db.execute(select(NIC).where(NIC.snapshot_id == latest.id)))
        .scalars().all()
    )
    firmwares = (
        (await db.execute(select(Firmware).where(Firmware.snapshot_id == latest.id)))
        .scalars().all()
    )

    groups: list[SensorSummary] = []
    for group in _SENSOR_GROUPS:
        members = [s for s in sensors if _sensor_group(s) == group]
        if not members:
            continue
        breached = [s for s in members if is_sensor_breached(s)]
        if not breached:
            label = LABEL_HEALTHY
        elif any("crit" in (s.status or "").lower() for s in breached):
            label = LABEL_CRITICAL
        else:
            label = LABEL_WARNING
        groups.append(
            SensorSummary(
                group=group,
                total=len(members),
                ok=len(members) - len(breached),
                breached=len(breached),
                label=label,
            )
        )

    storage_statuses = [s.health for s in storages]
    for storage in storages:
        storage_statuses.extend(d.health for d in storage.disks)
    # NIC link health: an explicitly down link is a warning, unknown is fine.
    nic_statuses = [
        n.link_status
        for n in nics
        if (n.link_status or "").lower() not in ("", "unknown")
    ]

    overall = compute_health(
        device.status, latest, list(sensors), list(storages), list(firmwares)
    )
    timeline = [
        HealthTimelinePoint(
            collected_at=snap.collected_at,
            **vars(await _snapshot_health(db, device.status, snap)),
        )
        for snap in reversed(snapshots)  # oldest -> newest for charting
    ]

    return DeviceHealthResponse(
        overall_label=overall.label,
        overall_score=overall.score,
        status=device.status.value,
        last_collected_at=latest.collected_at,
        sensor_groups=groups,
        storage_label=_statuses_label(storage_statuses, len(storage_statuses)),
        memory_label=_statuses_label([m.status for m in memories], len(memories)),
        network_label=_statuses_label(
            [("ok" if (s or "").lower() in ("up", "ok", "linkup", "connected") else s)
             for s in nic_statuses],
            len(nic_statuses),
        ),
        timeline=timeline,
    )
