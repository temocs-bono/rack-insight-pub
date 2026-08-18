"""SnapshotService (1.3.0): the single entry point for a collection cycle.

Pipeline:  Collector -> Inventory Snapshot -> Event Engine -> Alert Engine

The collector ONLY collects and stores the snapshot; it never creates events
or alerts. This service orchestrates the pipeline: it runs the collector,
records the run, updates device status, then hands the snapshot to the Event
Engine and its events to the Alert Engine.
"""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from collectors.manager import CollectionOutcome, CollectorManager
from models import Alert, Device, Event
from services import alert_engine, event_engine
from services.refresh_helpers import record_collector_run
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineResult:
    outcome: CollectionOutcome
    events: list[Event]
    alerts: list[Alert]


async def collect_and_process(
    db: AsyncSession, device: Device, trigger: str
) -> PipelineResult:
    """Run one full collection cycle for a device (does not commit)."""
    old_status = device.status

    # 1) Collector: collect inventory + save snapshot (nothing else).
    manager = CollectorManager()
    outcome = await manager.collect_device(db, device)
    record_collector_run(db, device, outcome, trigger=trigger)
    await db.flush()  # the run must be visible to consecutive-failure counting

    device.status = outcome.status
    if outcome.system.get("manufacturer") and not device.vendor:
        device.vendor = outcome.system["manufacturer"]
    if outcome.system.get("model") and not device.model:
        device.model = outcome.system["model"]

    # 2) Event Engine: snapshot N-1 vs N (plus state transitions).
    had_state_alert, sensor_subjects = await alert_engine.active_state_alert_context(
        db, device.id
    )
    events = await event_engine.generate_events(
        db,
        device,
        outcome,
        old_status=old_status,
        had_active_state_alert=had_state_alert,
        active_sensor_subjects=sensor_subjects,
    )

    # 3) Alert Engine: alerts + auto-resolution + immutable history.
    alerts = await alert_engine.process_events(db, device, events)

    return PipelineResult(outcome=outcome, events=events, alerts=alerts)
