"""Discovery schemas (F1/F2)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.discovery import DiscoveryStatus


class DiscoveryScanRequest(BaseModel):
    # A mix of single IPs and CIDR blocks, e.g. ["10.0.0.5", "10.0.1.0/28"].
    targets: list[str] = Field(min_length=1)
    community: str = Field(default="public", min_length=1, max_length=128)
    timeout: float = Field(default=2.0, ge=0.2, le=10.0)


class DiscoveredDeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ip_address: str
    sysname: str | None
    sysdescr: str | None
    sysobjectid: str | None
    vendor: str | None
    device_type_guess: str | None
    serial: str | None
    status: DiscoveryStatus
    imported_device_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DiscoveryScanResult(BaseModel):
    scanned: int
    reachable: int
    discovered: list[DiscoveredDeviceResponse]


class DiscoveryImportItem(BaseModel):
    discovered_id: uuid.UUID
    hostname: str = Field(min_length=1, max_length=255)
    management_ip: str | None = None
    ilo_ip: str | None = None
    u_position: int | None = Field(default=None, ge=1)


class DiscoveryImportRequest(BaseModel):
    rack_id: uuid.UUID
    template_id: uuid.UUID | None = None
    redfish_credential_id: uuid.UUID | None = None
    ssh_credential_id: uuid.UUID | None = None
    snmp_credential_id: uuid.UUID | None = None
    items: list[DiscoveryImportItem] = Field(min_length=1)
