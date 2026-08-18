"""Latest-snapshot inventory reads with Redis cache in front of the DB."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cache.redis_cache import cache_get, cache_set, device_inventory_key
from models import (
    CPU,
    NIC,
    VM,
    Firmware,
    Memory,
    Network,
    Sensor,
    Snapshot,
    Storage,
    SwitchInventory,
)
from schemas.inventory import (
    CPUResponse,
    DeviceInventoryResponse,
    FirmwareResponse,
    MemoryResponse,
    NetworkResponse,
    NICResponse,
    SensorResponse,
    SnapshotMeta,
    StorageResponse,
    SwitchInventoryResponse,
    VMResponse,
)


async def get_latest_snapshot(db: AsyncSession, device_id: uuid.UUID) -> Snapshot | None:
    result = await db.execute(
        select(Snapshot)
        .where(Snapshot.device_id == device_id)
        .order_by(Snapshot.collected_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def load_snapshot_inventory(
    db: AsyncSession, snapshot: Snapshot
) -> DeviceInventoryResponse:
    cpus = (await db.execute(select(CPU).where(CPU.snapshot_id == snapshot.id))).scalars().all()
    memories = (
        (await db.execute(select(Memory).where(Memory.snapshot_id == snapshot.id)))
        .scalars().all()
    )
    nics = (await db.execute(select(NIC).where(NIC.snapshot_id == snapshot.id))).scalars().all()
    firmwares = (
        (await db.execute(select(Firmware).where(Firmware.snapshot_id == snapshot.id)))
        .scalars().all()
    )
    storages = (
        (
            await db.execute(
                select(Storage)
                .where(Storage.snapshot_id == snapshot.id)
                .options(selectinload(Storage.disks))
            )
        )
        .scalars().all()
    )
    networks = (
        (await db.execute(select(Network).where(Network.snapshot_id == snapshot.id)))
        .scalars().all()
    )
    vms = (await db.execute(select(VM).where(VM.snapshot_id == snapshot.id))).scalars().all()
    sensors = (
        (await db.execute(select(Sensor).where(Sensor.snapshot_id == snapshot.id)))
        .scalars().all()
    )
    switch = (
        (
            await db.execute(
                select(SwitchInventory).where(SwitchInventory.snapshot_id == snapshot.id)
            )
        )
        .scalars().first()
    )

    return DeviceInventoryResponse(
        snapshot=SnapshotMeta.model_validate(snapshot),
        cpus=[CPUResponse.model_validate(c) for c in cpus],
        memories=[MemoryResponse.model_validate(m) for m in memories],
        nics=[NICResponse.model_validate(n) for n in nics],
        firmwares=[FirmwareResponse.model_validate(f) for f in firmwares],
        storages=[StorageResponse.model_validate(s) for s in storages],
        networks=[NetworkResponse.model_validate(n) for n in networks],
        vms=[VMResponse.model_validate(v) for v in vms],
        sensors=[SensorResponse.model_validate(s) for s in sensors],
        switch=SwitchInventoryResponse.model_validate(switch) if switch else None,
    )


async def get_device_inventory(
    db: AsyncSession, device_id: uuid.UUID
) -> DeviceInventoryResponse:
    """Redis first, then DB; populates the cache on a miss."""
    key = device_inventory_key(str(device_id))
    cached = await cache_get(key)
    if cached is not None:
        return DeviceInventoryResponse.model_validate(cached)

    snapshot = await get_latest_snapshot(db, device_id)
    if snapshot is None:
        return DeviceInventoryResponse()

    inventory = await load_snapshot_inventory(db, snapshot)
    await cache_set(key, inventory.model_dump(mode="json"))
    return inventory
