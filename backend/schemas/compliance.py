"""Firmware compliance schemas (F6)."""
import uuid

from pydantic import BaseModel


class DeviceComponentStatus(BaseModel):
    device_id: uuid.UUID
    hostname: str
    version: str | None
    compliant: bool


class ComponentCompliance(BaseModel):
    component: str
    expected_version: str | None
    compliant: bool
    devices: list[DeviceComponentStatus]


class TemplateComplianceReport(BaseModel):
    template_id: uuid.UUID
    device_count: int
    compliant: bool
    components: list[ComponentCompliance]
