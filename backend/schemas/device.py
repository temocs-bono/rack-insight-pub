"""Device schemas. Credentials are write-only: never returned by the API."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.device import DeviceOrientation, DeviceStatus, DeviceType

VALID_COLLECTOR_TYPES = {"REDFISH", "SSH", "CISCO"}


class DeviceCreate(BaseModel):
    rack_id: uuid.UUID
    # Optional shared hardware model. When set, vendor/model are inherited
    # from the template if not provided explicitly.
    template_id: uuid.UUID | None = None
    hostname: str = Field(min_length=1, max_length=255)
    display_name: str | None = None
    device_type: DeviceType = DeviceType.SERVER
    vendor: str | None = None
    model: str | None = None
    management_ip: str | None = None
    ilo_ip: str | None = None
    ilo_port: int = Field(default=443, ge=1, le=65535)
    ilo_use_https: bool = True
    ilo_username: str | None = None
    ilo_password: str | None = None
    ssh_username: str | None = None
    ssh_password: str | None = None
    snmp_community: str | None = None
    orientation: DeviceOrientation = DeviceOrientation.FRONT
    collector_types: list[str] = Field(default_factory=list)
    redfish_credential_id: uuid.UUID | None = None
    ssh_credential_id: uuid.UUID | None = None
    snmp_credential_id: uuid.UUID | None = None
    asset_tag: str | None = None
    serial_override: str | None = None
    description: str | None = None
    u_position: int | None = Field(default=None, ge=1)
    height: int = Field(default=1, ge=1)


MAX_BULK_DEVICES = 100


class DeviceBulkItem(BaseModel):
    """One reviewed row from the provisioning wizard (1.1.2).

    Every field is an already-resolved value the administrator confirmed in
    the editable table; per-row values override the bulk defaults.
    """

    hostname: str = Field(min_length=1, max_length=255)
    management_ip: str | None = None
    ilo_ip: str | None = None
    redfish_credential_id: uuid.UUID | None = None
    ssh_credential_id: uuid.UUID | None = None
    snmp_credential_id: uuid.UUID | None = None
    u_position: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)


class DeviceBulkCreate(BaseModel):
    """Install multiple servers at once.

    Two mutually compatible modes:
    - `items`: explicit per-row list from the provisioning wizard (1.1.2).
      Top-level template/device_type/vendor/model/orientation/collector_types
      and credential ids act as defaults; each item may override.
    - otherwise (1.1.1 behavior): hostnames are provided explicitly via
      `hostnames`, or generated from `hostname_prefix` + sequential number.
    """

    rack_id: uuid.UUID
    template_id: uuid.UUID | None = None
    device_type: DeviceType = DeviceType.SERVER
    items: list[DeviceBulkItem] | None = None
    quantity: int | None = Field(default=None, ge=1, le=MAX_BULK_DEVICES)
    hostname_prefix: str | None = Field(default=None, max_length=200)
    hostnames: list[str] | None = None
    start_index: int = Field(default=1, ge=0)
    pad_width: int = Field(default=2, ge=1, le=6)
    vendor: str | None = None
    model: str | None = None
    orientation: DeviceOrientation = DeviceOrientation.FRONT
    collector_types: list[str] = Field(default_factory=list)
    redfish_credential_id: uuid.UUID | None = None
    ssh_credential_id: uuid.UUID | None = None
    snmp_credential_id: uuid.UUID | None = None


class DeviceBulkCreateError(BaseModel):
    hostname: str
    error: str


class DeviceBulkCreateResult(BaseModel):
    created: list["DeviceResponse"]
    skipped: list[str]
    errors: list[DeviceBulkCreateError]


class DeviceUpdate(BaseModel):
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = None
    device_type: DeviceType | None = None
    template_id: uuid.UUID | None = None
    vendor: str | None = None
    model: str | None = None
    management_ip: str | None = None
    ilo_ip: str | None = None
    ilo_port: int | None = Field(default=None, ge=1, le=65535)
    ilo_use_https: bool | None = None
    ilo_username: str | None = None
    ilo_password: str | None = None
    ssh_username: str | None = None
    ssh_password: str | None = None
    snmp_community: str | None = None
    orientation: DeviceOrientation | None = None
    collector_types: list[str] | None = None
    redfish_credential_id: uuid.UUID | None = None
    ssh_credential_id: uuid.UUID | None = None
    snmp_credential_id: uuid.UUID | None = None
    asset_tag: str | None = None
    serial_override: str | None = None
    description: str | None = None
    enabled: bool | None = None
    rack_id: uuid.UUID | None = None


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rack_id: uuid.UUID
    template_id: uuid.UUID | None
    hostname: str
    display_name: str | None
    device_type: DeviceType
    vendor: str | None
    model: str | None
    management_ip: str | None
    ilo_ip: str | None
    ilo_port: int
    ilo_use_https: bool
    ilo_username: str | None
    ssh_username: str | None
    status: DeviceStatus
    enabled: bool
    orientation: DeviceOrientation
    collector_types: str | None
    redfish_credential_id: uuid.UUID | None
    ssh_credential_id: uuid.UUID | None
    snmp_credential_id: uuid.UUID | None
    asset_tag: str | None = None
    serial_override: str | None = None
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class DeviceDetailResponse(DeviceResponse):
    health_score: int | None = None
    health_label: str | None = None
    last_refresh: datetime | None = None
    serial: str | None = None


class DevicePositionUpdate(BaseModel):
    """Assign/move a device to a U position (U selection / drag & drop).

    `rack_id` optionally moves the device into a different rack (assign to
    rack); omitted keeps it in its current rack.
    """

    u_position: int = Field(ge=1)
    height: int | None = Field(default=None, ge=1)
    rack_id: uuid.UUID | None = None


class DeviceSearchResult(DeviceResponse):
    rack_name: str | None = None
    cluster_name: str | None = None
    cluster_id: uuid.UUID | None = None


class DeviceSearchPage(BaseModel):
    """Server-side paginated search response (F5/F9)."""

    items: list[DeviceSearchResult]
    total: int
    page: int
    page_size: int
