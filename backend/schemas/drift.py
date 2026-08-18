"""Drift detection schemas (F4)."""
from datetime import datetime

from pydantic import BaseModel


class DriftChange(BaseModel):
    section: str
    identifier: str
    change: str  # added / removed / changed
    field: str | None = None
    old_value: str | None = None
    new_value: str | None = None


class DriftReport(BaseModel):
    has_previous: bool
    current_collected_at: datetime | None
    previous_collected_at: datetime | None
    changes: list[DriftChange]
