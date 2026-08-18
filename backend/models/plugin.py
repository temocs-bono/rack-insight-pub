"""Plugin registry model (Plugin Architecture Foundation).

A Plugin is an independent backend service (its own container) that the Core
registers, monitors, and proxies to. The Core never runs plugin code in-process
— it only talks HTTP to the plugin's endpoint.

Two kinds of data live on this row (kept deliberately separate):

- **Configuration** (declared, stable): ``name``, ``endpoint``, ``enabled`` and
  the manifest-derived metadata. Config-declared plugins are seeded from the
  ``PLUGINS_CONFIG`` configuration at startup (``managed_by_config = True``).
- **Runtime state** (observed, changes over time): ``status``,
  ``last_health_check``, ``last_success_at``, ``last_failure_at``,
  ``failure_reason`` — updated by the health monitor.

A plugin being UNHEALTHY (or absent) never affects Core availability.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import TimestampedModel

# Runtime status values.
PLUGIN_STATUS_HEALTHY = "HEALTHY"
PLUGIN_STATUS_UNHEALTHY = "UNHEALTHY"
PLUGIN_STATUS_UNKNOWN = "UNKNOWN"
PLUGIN_STATUS_DISABLED = "DISABLED"

# The Core's supported plugin contract version. Plugins advertise their own
# api_version; a mismatch is surfaced but never crashes the Core.
SUPPORTED_API_VERSION = "v1"


class Plugin(TimestampedModel):
    __tablename__ = "plugins"

    # --- Configuration --------------------------------------------------------
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    api_version: Mapped[str] = mapped_column(
        String(16), default=SUPPORTED_API_VERSION, nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Declared in PLUGINS_CONFIG (True) vs registered at runtime via the API
    # (False). Config-managed plugins are re-seeded on every start.
    managed_by_config: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Cached manifest JSON (routes / permissions / menus) for future extension.
    manifest: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Runtime state --------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(16), default=PLUGIN_STATUS_UNKNOWN, nullable=False, index=True
    )
    last_health_check: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
