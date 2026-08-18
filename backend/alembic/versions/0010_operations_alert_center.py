"""Operations & Alert Center tables (1.3.0).

Revision ID: 0010
Revises: 0009

Additive only: events, alerts, device_history, alert_settings. No existing
inventory table is modified. The existing ``snapshots`` table (one immutable
snapshot per successful collection, with per-section inventory tables) is the
inventory snapshot store the Event Engine compares.

Indexes per the 1.3.0 performance requirements: device_id, snapshot_id,
alert status, severity (created_at ordering uses the timestamped base column;
an explicit index is added on alerts.created_at for the newest-first list).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "events",
        *_base_columns(),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("previous_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["device_id"], ["rack_device_instances.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["previous_snapshot_id"], ["snapshots.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_events_device_id", "events", ["device_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_snapshot_id", "events", ["snapshot_id"])
    op.create_index("ix_events_created_at", "events", ["created_at"])

    op.create_table(
        "alerts",
        *_base_columns(),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("auto_resolve", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["rack_device_instances.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_alerts_device_id", "alerts", ["device_id"])
    op.create_index("ix_alerts_category", "alerts", ["category"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])

    op.create_table(
        "device_history",
        *_base_columns(),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["device_id"], ["rack_device_instances.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_device_history_device_id", "device_history", ["device_id"])
    op.create_index("ix_device_history_kind", "device_history", ["kind"])
    op.create_index("ix_device_history_created_at", "device_history", ["created_at"])

    op.create_table(
        "alert_settings",
        *_base_columns(),
        sa.Column("consecutive_failures_threshold", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("alert_settings")
    op.drop_table("device_history")
    op.drop_table("alerts")
    op.drop_table("events")
