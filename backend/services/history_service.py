"""HistoryService (1.3.0): immutable, permanent device change history.

History is NOT alerts: it records what happened (firmware upgrades, hardware
replacements, collector failures, manual resolves) and is never updated. The
only deletion path is the explicitly enabled ``history`` retention policy.
"""
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import DeviceHistory


def record_history(
    db: AsyncSession,
    device_id: uuid.UUID,
    kind: str,
    title: str,
    details: list[dict[str, Any]] | dict[str, Any] | None = None,
    event_id: uuid.UUID | None = None,
) -> DeviceHistory:
    """Append one immutable history entry to the caller's session."""
    entry = DeviceHistory(
        device_id=device_id,
        kind=kind,
        title=title,
        details=json.dumps(details, ensure_ascii=False) if details else None,
        event_id=event_id,
    )
    db.add(entry)
    return entry
