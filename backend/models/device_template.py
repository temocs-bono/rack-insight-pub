"""DeviceTemplate: a reusable hardware model (vendor/model + nominal specs).

Many Rack Device Instances reference one template. A template holds ONLY
hardware-model information — never deployment-specific data (hostname, IPs,
credentials, rack, U position). Collected inventory stays per-instance in
snapshots; the template carries admin-declared nominal specifications.
"""
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import TimestampedModel

if TYPE_CHECKING:
    from models.device import Device


class DeviceTemplate(TimestampedModel):
    __tablename__ = "device_templates"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Nominal hardware specification (admin-declared, free text).
    cpu: Mapped[str | None] = mapped_column(String(255), nullable=True)
    memory: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    instances: Mapped[list["Device"]] = relationship(
        back_populates="template", lazy="noload"
    )
