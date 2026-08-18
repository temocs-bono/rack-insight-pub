"""RetentionPolicy: admin-configurable data retention per category (F5).

One row per retention category. The lifecycle service deletes rows in each
category older than `retention_days` when `enabled` is true. Current inventory
(the latest successful snapshot per device) is always preserved regardless of
policy.
"""
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import TimestampedModel

# Retention categories (operational/historical data only — never core inventory).
CATEGORY_COLLECTOR_RUNS = "collector_runs"
CATEGORY_SNAPSHOTS = "snapshots"
CATEGORY_DISCOVERY = "discovery"
CATEGORY_RESOLVED_ALERTS = "resolved_alerts"
# Device history defaults to permanent (policy disabled); enabling it is an
# explicit administrator opt-in.
CATEGORY_HISTORY = "history"

RETENTION_CATEGORIES = (
    CATEGORY_COLLECTOR_RUNS,
    CATEGORY_SNAPSHOTS,
    CATEGORY_DISCOVERY,
    CATEGORY_RESOLVED_ALERTS,
    CATEGORY_HISTORY,
)

DEFAULT_RETENTION_DAYS = {
    CATEGORY_COLLECTOR_RUNS: 90,
    CATEGORY_SNAPSHOTS: 180,
    CATEGORY_DISCOVERY: 30,
    CATEGORY_RESOLVED_ALERTS: 90,
    CATEGORY_HISTORY: 365,
}


class RetentionPolicy(TimestampedModel):
    __tablename__ = "retention_policies"

    category: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
