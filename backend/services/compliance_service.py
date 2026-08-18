"""Firmware compliance across devices sharing a Device Template (F6).

For every instance of a template, the latest firmware inventory is compared
component-by-component. The most common version per component is treated as the
expected baseline; devices differing from (or missing) it are flagged.
"""
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Device, Firmware
from schemas.compliance import (
    ComponentCompliance,
    DeviceComponentStatus,
    TemplateComplianceReport,
)
from services.inventory_service import get_latest_snapshot


async def _latest_firmware(db: AsyncSession, device_id: uuid.UUID) -> dict[str, str]:
    """Component -> version from the device's latest snapshot (empty if none)."""
    snapshot = await get_latest_snapshot(db, device_id)
    if snapshot is None:
        return {}
    rows = (
        (await db.execute(select(Firmware).where(Firmware.snapshot_id == snapshot.id)))
        .scalars().all()
    )
    versions: dict[str, str] = {}
    for row in rows:
        if row.component and row.version:
            versions[row.component] = row.version
    return versions


async def get_template_compliance(
    db: AsyncSession, template_id: uuid.UUID
) -> TemplateComplianceReport:
    devices = (
        (await db.execute(select(Device).where(Device.template_id == template_id)))
        .scalars().all()
    )
    device_versions: dict[uuid.UUID, dict[str, str]] = {}
    device_names: dict[uuid.UUID, str] = {}
    for device in devices:
        device_versions[device.id] = await _latest_firmware(db, device.id)
        device_names[device.id] = device.hostname

    # All components seen across the fleet.
    components: set[str] = set()
    for versions in device_versions.values():
        components |= versions.keys()

    component_reports: list[ComponentCompliance] = []
    compliant = True
    for component in sorted(components):
        present = [
            versions[component]
            for versions in device_versions.values()
            if component in versions
        ]
        counter = Counter(present)
        expected = counter.most_common(1)[0][0] if counter else None
        statuses: list[DeviceComponentStatus] = []
        component_ok = True
        for device_id, versions in device_versions.items():
            actual = versions.get(component)
            is_compliant = actual == expected and actual is not None
            if not is_compliant:
                component_ok = False
                compliant = False
            statuses.append(
                DeviceComponentStatus(
                    device_id=device_id,
                    hostname=device_names[device_id],
                    version=actual,
                    compliant=is_compliant,
                )
            )
        component_reports.append(
            ComponentCompliance(
                component=component,
                expected_version=expected,
                compliant=component_ok,
                devices=statuses,
            )
        )

    return TemplateComplianceReport(
        template_id=template_id,
        device_count=len(devices),
        compliant=compliant,
        components=component_reports,
    )
