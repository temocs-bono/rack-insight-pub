"""DiscoveredDevice: an SNMP-discovered device awaiting administrator import.

Discovery collects identification data only and NEVER creates Installed
Devices automatically — rows sit here as PENDING until an administrator
imports them through the Discovery Import Wizard. This is retention-based
(temporary) data managed by the lifecycle service.
"""
import enum
import uuid

from sqlalchemy import Enum, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.base import TimestampedModel


class DiscoveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    IMPORTED = "IMPORTED"
    IGNORED = "IGNORED"


class DiscoveredDevice(TimestampedModel):
    __tablename__ = "discovered_devices"

    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    sysname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sysdescr: Mapped[str | None] = mapped_column(Text, nullable=True)
    sysobjectid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_type_guess: Mapped[str | None] = mapped_column(String(32), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[DiscoveryStatus] = mapped_column(
        Enum(DiscoveryStatus, name="discovery_status"),
        default=DiscoveryStatus.PENDING,
        nullable=False,
    )
    # Set once the administrator imports this discovery into an Installed Device.
    imported_device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
