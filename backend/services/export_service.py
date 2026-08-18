"""Inventory export: JSON / CSV (zip of one CSV per section) / Excel (.xlsx).

Scope: a single device, a rack, a cluster, or the entire inventory.
Reuses the existing latest-snapshot inventory reads (Redis-cached).
"""
import csv
import io
import json
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Cluster, Device, Rack
from schemas.inventory import DeviceInventoryResponse
from services.inventory_service import get_device_inventory

EXPORT_SCOPES = ("device", "rack", "cluster", "all")
EXPORT_FORMATS = ("json", "csv", "xlsx")

SECTION_COLUMNS: dict[str, list[str]] = {
    # Template (hardware model) fields first, then Rack Instance (deployment)
    # fields — clearly separated per the 1.1.1 device-model split.
    "Devices": [
        "template", "vendor", "model", "cpu", "memory",
        "hostname", "display_name", "device_type", "status",
        "management_ip", "ilo_ip", "orientation", "asset_tag",
        "cluster", "rack", "last_collected",
    ],
    "CPU": [
        "device", "socket", "vendor", "model", "cores", "threads",
        "frequency", "microcode", "serial",
    ],
    "Memory": [
        "device", "slot", "capacity_gb", "type", "speed", "vendor",
        "part_number", "serial", "ecc", "status",
    ],
    "NIC": [
        "device", "name", "mac", "firmware", "driver", "speed",
        "pci_slot", "link_status",
    ],
    "Storage": [
        "device", "controller", "raid_level", "controller_model", "controller_serial",
        "controller_firmware", "controller_health", "disk_slot", "disk_model",
        "disk_serial", "disk_capacity", "disk_firmware", "disk_health",
    ],
    "Firmware": ["device", "component", "version", "release_date", "health"],
    "Network": [
        "device", "interface", "ipv4", "ipv6", "mac", "speed", "mtu",
        "gateway", "bond", "vlan",
    ],
    "VM": ["device", "name", "state", "vcpu", "memory", "os", "kernel", "ip"],
    "Sensor": [
        "device", "type", "name", "value", "unit", "status",
        "upper_threshold", "lower_threshold",
    ],
}

Row = dict[str, Any]


@dataclass
class ExportPayload:
    filename: str
    media_type: str
    content: bytes


async def _resolve_devices(
    db: AsyncSession, scope: str, target_id: uuid.UUID | None
) -> list[Device]:
    if scope == "all":
        result = await db.execute(select(Device).order_by(Device.hostname))
        return list(result.scalars().all())
    if target_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"target_id is required for scope '{scope}'",
        )
    if scope == "device":
        result = await db.execute(select(Device).where(Device.id == target_id))
        devices = list(result.scalars().all())
    elif scope == "rack":
        result = await db.execute(
            select(Device).where(Device.rack_id == target_id).order_by(Device.hostname)
        )
        devices = list(result.scalars().all())
    elif scope == "cluster":
        rack_ids = (
            (await db.execute(select(Rack.id).where(Rack.cluster_id == target_id)))
            .scalars().all()
        )
        if not rack_ids:
            return []
        result = await db.execute(
            select(Device).where(Device.rack_id.in_(rack_ids)).order_by(Device.hostname)
        )
        devices = list(result.scalars().all())
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown scope '{scope}'",
        )
    if scope == "device" and not devices:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return devices


def _device_row(device: Device, inventory: DeviceInventoryResponse) -> Row:
    template = device.template
    return {
        # Device Template (hardware model) fields
        "template": template.name if template else None,
        "vendor": device.vendor or (template.vendor if template else None),
        "model": device.model or (template.model if template else None),
        "cpu": template.cpu if template else None,
        "memory": template.memory if template else None,
        # Rack Device Instance (deployment) fields
        "hostname": device.hostname,
        "display_name": device.display_name,
        "device_type": device.device_type.value,
        "status": device.status.value,
        "management_ip": device.management_ip,
        "ilo_ip": device.ilo_ip,
        "orientation": device.orientation.value,
        "asset_tag": device.asset_tag,
        "cluster": device.rack.cluster.name if device.rack and device.rack.cluster else None,
        "rack": device.rack.name if device.rack else None,
        "last_collected": (
            inventory.snapshot.collected_at.isoformat() if inventory.snapshot else None
        ),
    }


def _inventory_rows(
    hostname: str, inventory: DeviceInventoryResponse
) -> dict[str, list[Row]]:
    sections: dict[str, list[Row]] = {name: [] for name in SECTION_COLUMNS}
    for cpu in inventory.cpus:
        sections["CPU"].append({"device": hostname, **cpu.model_dump(exclude={"id"})})
    for dimm in inventory.memories:
        sections["Memory"].append({"device": hostname, **dimm.model_dump(exclude={"id"})})
    for nic in inventory.nics:
        row = nic.model_dump(exclude={"id", "vendor", "model", "serial"})
        sections["NIC"].append({"device": hostname, **row})
    for storage in inventory.storages:
        controller = {
            "device": hostname,
            "controller": storage.controller,
            "raid_level": storage.raid_level,
            "controller_model": storage.model,
            "controller_serial": storage.serial,
            "controller_firmware": storage.firmware,
            "controller_health": storage.health,
        }
        if not storage.disks:
            sections["Storage"].append(controller)
        for disk in storage.disks:
            sections["Storage"].append(
                {
                    **controller,
                    "disk_slot": disk.slot,
                    "disk_model": disk.model,
                    "disk_serial": disk.serial,
                    "disk_capacity": disk.capacity,
                    "disk_firmware": disk.firmware,
                    "disk_health": disk.health,
                }
            )
    for firmware in inventory.firmwares:
        sections["Firmware"].append(
            {"device": hostname, **firmware.model_dump(exclude={"id"})}
        )
    for network in inventory.networks:
        row = network.model_dump(exclude={"id", "dns", "duplex"})
        sections["Network"].append({"device": hostname, **row})
    for vm in inventory.vms:
        sections["VM"].append(
            {"device": hostname, **vm.model_dump(exclude={"id", "uuid"})}
        )
    for sensor in inventory.sensors:
        sections["Sensor"].append(
            {"device": hostname, **sensor.model_dump(exclude={"id"})}
        )
    return sections


async def build_export_sections(
    db: AsyncSession, scope: str, target_id: uuid.UUID | None
) -> dict[str, list[Row]]:
    """Gather every section's rows for the requested scope."""
    devices = await _resolve_devices(db, scope, target_id)
    sections: dict[str, list[Row]] = {name: [] for name in SECTION_COLUMNS}
    for device in devices:
        inventory = await get_device_inventory(db, device.id)
        sections["Devices"].append(_device_row(device, inventory))
        for name, rows in _inventory_rows(device.hostname, inventory).items():
            sections[name].extend(rows)
    return sections


def _normalize(row: Row, columns: list[str]) -> list[Any]:
    return [row.get(column) for column in columns]


def _render_json(sections: dict[str, list[Row]], scope: str) -> bytes:
    document = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "sections": sections,
    }
    return json.dumps(document, indent=2, default=str).encode("utf-8")


def _render_csv_zip(sections: dict[str, list[Row]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, rows in sections.items():
            columns = SECTION_COLUMNS[name]
            text = io.StringIO()
            writer = csv.writer(text)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(_normalize(row, columns))
            archive.writestr(f"{name.lower()}.csv", text.getvalue())
    return buffer.getvalue()


def _render_xlsx(sections: dict[str, list[Row]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sections.items():
        sheet = workbook.create_sheet(title=name)
        columns = SECTION_COLUMNS[name]
        sheet.append(columns)
        for row in rows:
            sheet.append(
                [
                    value if isinstance(value, (int, float)) or value is None else str(value)
                    for value in _normalize(row, columns)
                ]
            )
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def export_inventory(
    db: AsyncSession, scope: str, target_id: uuid.UUID | None, export_format: str
) -> ExportPayload:
    if scope not in EXPORT_SCOPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"scope must be one of {', '.join(EXPORT_SCOPES)}",
        )
    if export_format not in EXPORT_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"format must be one of {', '.join(EXPORT_FORMATS)}",
        )

    sections = await build_export_sections(db, scope, target_id)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_name = f"rack-insight-{scope}-{timestamp}"

    if export_format == "json":
        return ExportPayload(
            filename=f"{base_name}.json",
            media_type="application/json",
            content=_render_json(sections, scope),
        )
    if export_format == "csv":
        return ExportPayload(
            filename=f"{base_name}.zip",
            media_type="application/zip",
            content=_render_csv_zip(sections),
        )
    return ExportPayload(
        filename=f"{base_name}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=_render_xlsx(sections),
    )
