"""Rack and RackUnit (42U layout) models."""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import TimestampedModel

DEFAULT_RACK_HEIGHT_U: int = 42

if TYPE_CHECKING:
    from models.cluster import Cluster
    from models.device import Device


class Rack(TimestampedModel):
    __tablename__ = "racks"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    height: Mapped[int] = mapped_column(Integer, default=DEFAULT_RACK_HEIGHT_U, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    cluster: Mapped["Cluster"] = relationship(back_populates="racks", lazy="selectin")
    units: Mapped[list["RackUnit"]] = relationship(
        back_populates="rack", cascade="all, delete-orphan", lazy="selectin"
    )
    devices: Mapped[list["Device"]] = relationship(
        back_populates="rack", cascade="all, delete-orphan", lazy="selectin"
    )


class RackUnit(TimestampedModel):
    """Layout entry: which device occupies which U position in a rack."""

    __tablename__ = "rack_units"
    __table_args__ = (UniqueConstraint("rack_id", "u_position", name="uq_rack_u_position"),)

    rack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("racks.id", ondelete="CASCADE"), nullable=False
    )
    u_position: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("rack_device_instances.id", ondelete="SET NULL"), nullable=True
    )

    rack: Mapped["Rack"] = relationship(back_populates="units", lazy="selectin")
    device: Mapped["Device | None"] = relationship(lazy="selectin")
