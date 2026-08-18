"""Alert category split + event subject (1.3.1).

Revision ID: 0011
Revises: 0010

Additive maintainability patch for the Alert Engine:

- ``events.subject`` — the Event Engine now records what changed explicitly, so
  the Alert Engine no longer parses JSON details to find it.
- ``alerts.event_type`` — alerts keep *what happened* (event type) separate from
  their operational *category*. Existing rows stored the event type in
  ``category``; we copy it into ``event_type`` and reclassify ``category`` to the
  operational domain.

No table is created or dropped; no existing column is removed.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen snapshot of the event-type -> operational-domain mapping at 1.3.1.
# (Kept inline so the migration never depends on evolving application code.)
_DOMAIN_BY_EVENT_TYPE = {
    "HardwareChanged": "Hardware",
    "FirmwareChanged": "Firmware",
    "DeviceOffline": "Connectivity",
    "DeviceRecovered": "Connectivity",
    "NetworkReachabilityChanged": "Connectivity",
    "CollectorFailed": "Collector",
    "CredentialFailed": "Credential",
    "SensorThresholdExceeded": "Health",
    "SensorRecovered": "Health",
}


def upgrade() -> None:
    op.add_column("events", sa.Column("subject", sa.String(255), nullable=True))
    op.add_column("alerts", sa.Column("event_type", sa.String(64), nullable=True))
    op.create_index("ix_alerts_event_type", "alerts", ["event_type"])

    if context.is_offline_mode():
        return

    bind = op.get_bind()
    # Existing alerts stored the event type in `category`; preserve it.
    bind.execute(
        sa.text("UPDATE alerts SET event_type = category WHERE event_type IS NULL")
    )
    # Reclassify `category` from event type to operational domain.
    for event_type, domain in _DOMAIN_BY_EVENT_TYPE.items():
        bind.execute(
            sa.text("UPDATE alerts SET category = :domain WHERE event_type = :et"),
            {"domain": domain, "et": event_type},
        )


def downgrade() -> None:
    if not context.is_offline_mode():
        # Restore the pre-1.3.1 convention where category held the event type.
        op.get_bind().execute(
            sa.text("UPDATE alerts SET category = event_type WHERE event_type IS NOT NULL")
        )
    op.drop_index("ix_alerts_event_type", table_name="alerts")
    op.drop_column("alerts", "event_type")
    op.drop_column("events", "subject")
