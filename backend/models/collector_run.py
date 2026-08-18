"""CollectorRun: audit log of every collection attempt (manual or scheduled),
successful or not. Powers the Collector Management screen."""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.base import TimestampedModel


class CollectorRun(TimestampedModel):
    __tablename__ = "collector_runs"

    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rack_device_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("snapshots.id", ondelete="SET NULL"), nullable=True
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Categorized failure diagnosis (F2): stable code + operator-readable text.
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    readable_message: Mapped[str | None] = mapped_column(Text, nullable=True)
