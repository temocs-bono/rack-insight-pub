"""Latest-snapshot inventory response schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _FromORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CPUResponse(_FromORM):
    id: uuid.UUID
    socket: str | None
    vendor: str | None
    model: str | None
    cores: int | None
    threads: int | None
    frequency: str | None
    cache: str | None
    microcode: str | None
    serial: str | None


class MemoryResponse(_FromORM):
    id: uuid.UUID
    slot: str | None
    vendor: str | None
    part_number: str | None
    serial: str | None
    capacity_gb: int | None
    speed: str | None
    type: str | None
    ecc: bool | None
    status: str | None


class NICResponse(_FromORM):
    id: uuid.UUID
    name: str | None
    vendor: str | None
    model: str | None
    mac: str | None
    firmware: str | None
    driver: str | None
    speed: str | None
    pci_slot: str | None
    serial: str | None
    link_status: str | None


class FirmwareResponse(_FromORM):
    id: uuid.UUID
    component: str | None
    version: str | None
    release_date: str | None
    health: str | None


class DiskResponse(_FromORM):
    id: uuid.UUID
    slot: str | None
    vendor: str | None
    model: str | None
    serial: str | None
    capacity: str | None
    firmware: str | None
    health: str | None


class StorageResponse(_FromORM):
    id: uuid.UUID
    controller: str | None
    raid_level: str | None
    vendor: str | None
    model: str | None
    serial: str | None
    capacity: str | None
    firmware: str | None
    health: str | None
    disks: list[DiskResponse] = []


class NetworkResponse(_FromORM):
    id: uuid.UUID
    interface: str | None
    ipv4: str | None
    ipv6: str | None
    gateway: str | None
    dns: str | None
    vlan: str | None
    bond: str | None
    mtu: int | None
    speed: str | None
    duplex: str | None
    mac: str | None


class VMResponse(_FromORM):
    id: uuid.UUID
    name: str | None
    uuid: str | None
    state: str | None
    vcpu: int | None
    memory: str | None
    os: str | None
    kernel: str | None
    ip: str | None


class SensorResponse(_FromORM):
    id: uuid.UUID
    type: str | None
    name: str | None
    value: str | None
    unit: str | None
    status: str | None
    upper_threshold: str | None = None
    lower_threshold: str | None = None


class SwitchInventoryResponse(_FromORM):
    id: uuid.UUID
    model: str | None
    ios_version: str | None
    serial: str | None
    uptime: str | None


class SnapshotMeta(_FromORM):
    id: uuid.UUID
    collected_at: datetime
    collector_version: str
    redfish_success: bool
    ssh_success: bool
    virsh_success: bool
    duration_ms: int


class DeviceInventoryResponse(BaseModel):
    """Everything the Device Detail page needs, from the latest snapshot."""

    snapshot: SnapshotMeta | None = None
    cpus: list[CPUResponse] = []
    memories: list[MemoryResponse] = []
    nics: list[NICResponse] = []
    firmwares: list[FirmwareResponse] = []
    storages: list[StorageResponse] = []
    networks: list[NetworkResponse] = []
    vms: list[VMResponse] = []
    sensors: list[SensorResponse] = []
    switch: SwitchInventoryResponse | None = None
