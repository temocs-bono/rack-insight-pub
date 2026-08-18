"""Snapshot: one collector run result. Collectors never UPDATE inventory,
they always create a new snapshot; the UI reads the latest one."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import TimestampedModel
from models.device import Device


class Snapshot(TimestampedModel):
    __tablename__ = "snapshots"

    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rack_device_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    collector_version: Mapped[str] = mapped_column(String(32), nullable=False)
    redfish_success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ssh_success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    virsh_success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    device: Mapped[Device] = relationship(back_populates="snapshots", lazy="noload")
