"""Remove orphan rack_units (device_id NULL) that strand U positions.

Revision ID: 0007
Revises: 0006

Before 1.1.3, deleting an Installed Device left its rack_unit behind with
device_id NULL (the FK is ON DELETE SET NULL). Such orphan rows keep occupying
their U position, corrupt the rack layout and block re-placement. 1.1.3 removes
the placement in the application when a device is deleted; this migration
purges any orphans created by older versions.

Data-safe: only rows with NULL device_id (which reference no device and render
as dead slots) are removed.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if context.is_offline_mode():
        return
    op.get_bind().execute(sa.text("DELETE FROM rack_units WHERE device_id IS NULL"))


def downgrade() -> None:
    # Purged orphans cannot be reconstructed and were never valid; nothing to do.
    pass
