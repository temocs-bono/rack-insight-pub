"""Cluster: logical grouping of racks (e.g. one customer / one core network site)."""
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import TimestampedModel

if TYPE_CHECKING:
    from models.rack import Rack


class Cluster(TimestampedModel):
    __tablename__ = "clusters"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    racks: Mapped[list["Rack"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan", lazy="selectin"
    )
