"""Inventory entities collected per snapshot (CPU, RAM, NIC, Firmware, Storage,
Disk, Network, VM, Sensor, SwitchInventory)."""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import TimestampedModel


class SnapshotChildMixin:
    """Every inventory row belongs to exactly one snapshot."""

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class CPU(TimestampedModel, SnapshotChildMixin):
    __tablename__ = "cpus"

    socket: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cores: Mapped[int | None] = mapped_column(Integer, nullable=True)
    threads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cache: Mapped[str | None] = mapped_column(String(128), nullable=True)
    microcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Memory(TimestampedModel, SnapshotChildMixin):
    __tablename__ = "memories"

    slot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    part_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capacity_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ecc: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)


class NIC(TimestampedModel, SnapshotChildMixin):
    __tablename__ = "nics"

    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mac: Mapped[str | None] = mapped_column(String(32), nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(128), nullable=True)
    driver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    speed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pci_slot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    link_status: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Firmware(TimestampedModel, SnapshotChildMixin):
    __tablename__ = "firmwares"

    component: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    health: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Storage(TimestampedModel, SnapshotChildMixin):
    __tablename__ = "storages"

    controller: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raid_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capacity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(128), nullable=True)
    health: Mapped[str | None] = mapped_column(String(32), nullable=True)

    disks: Mapped[list["Disk"]] = relationship(
        back_populates="storage", cascade="all, delete-orphan", lazy="selectin"
    )


class Disk(TimestampedModel):
    __tablename__ = "disks"

    storage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("storages.id", ondelete="CASCADE"), nullable=False
    )
    slot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capacity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(128), nullable=True)
    health: Mapped[str | None] = mapped_column(String(32), nullable=True)

    storage: Mapped[Storage] = relationship(back_populates="disks", lazy="selectin")


class Network(TimestampedModel, SnapshotChildMixin):
    __tablename__ = "networks"

    interface: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ipv4: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ipv6: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gateway: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dns: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vlan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bond: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mtu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duplex: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mac: Mapped[str | None] = mapped_column(String(32), nullable=True)


class VM(TimestampedModel, SnapshotChildMixin):
    __tablename__ = "vms"

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vcpu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    os: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kernel: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Sensor(TimestampedModel, SnapshotChildMixin):
    __tablename__ = "sensors"

    type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Redfish thresholds when the endpoint provides them (F6).
    upper_threshold: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lower_threshold: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SwitchInventory(TimestampedModel, SnapshotChildMixin):
    __tablename__ = "switch_inventories"

    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ios_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uptime: Mapped[str | None] = mapped_column(String(128), nullable=True)
