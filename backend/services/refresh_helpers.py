"""Shared collection-run bookkeeping (used by the snapshot pipeline)."""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from collectors.manager import CollectionOutcome
from models import CollectorRun, Device


def record_collector_run(
    db: AsyncSession, device: Device, outcome: CollectionOutcome, trigger: str
) -> None:
    """Append an audit entry for this collection attempt (success or failure)."""
    failed = [r for r in outcome.results if not r.skipped and not r.success]
    errors = [f"{r.collector_name}: {r.error}" for r in failed if r.error]
    ran = [r.collector_name for r in outcome.results if not r.skipped and r.success]
    message_parts: list[str] = []
    if ran:
        message_parts.append(f"succeeded: {', '.join(ran)}")
    if errors:
        message_parts.append("; ".join(errors))

    # Categorized diagnosis: surface the first failing collector's code.
    primary = next((r for r in failed if r.error_code), None)
    readable = None
    if primary is not None:
        readable = f"{primary.collector_name}: {primary.readable_message}"
        others = [
            f"{r.collector_name}: {r.readable_message}"
            for r in failed
            if r is not primary and r.readable_message
        ]
        if others:
            readable = "; ".join([readable, *others])

    db.add(
        CollectorRun(
            # Explicit microsecond timestamp: consecutive-failure counting
            # orders runs by created_at, and DB server defaults can have only
            # second precision (ties would make the order ambiguous).
            created_at=datetime.now(timezone.utc),
            device_id=device.id,
            success=outcome.snapshot is not None,
            duration_ms=max((r.duration_ms for r in outcome.results), default=0),
            snapshot_id=outcome.snapshot.id if outcome.snapshot is not None else None,
            message="; ".join(message_parts) or None,
            trigger=trigger,
            error_code=primary.error_code if primary is not None else None,
            readable_message=readable,
        )
    )
