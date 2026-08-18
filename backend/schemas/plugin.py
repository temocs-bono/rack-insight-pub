"""Plugin contract & API schemas (Plugin Architecture Foundation).

``PluginManifest`` is the standard contract a plugin returns from
``GET /plugin/manifest``. It accepts camelCase (the on-the-wire convention in
the spec, e.g. ``displayName``, ``apiVersion``, ``healthEndpoint``) and, thanks
to ``populate_by_name``, snake_case too — so plugin authors can use either.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


def _camel(field_name: str) -> str:
    head, *tail = field_name.split("_")
    return head + "".join(word.capitalize() for word in tail)


class PluginUi(BaseModel):
    """UI metadata: how the Core embeds the plugin's own frontend.

    Only ``iframe`` is supported (deliberately no Module Federation / runtime
    bundle injection). ``path`` is the plugin's UI entrypoint, which the Core
    serves same-origin via ``/api/plugins/{name}/ui/``.
    """

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="ignore")

    type: str = "iframe"
    path: str = "/ui/"
    title: str | None = None


class PluginManifest(BaseModel):
    """The contract a plugin advertises. Forward-compatible: unknown fields are
    ignored so newer plugins never break an older Core."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="ignore")

    name: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    version: str = Field(default="0.0.0", max_length=32)
    api_version: str = Field(default="v1", max_length=16)
    description: str | None = None
    health_endpoint: str = "/healthz"
    ready_endpoint: str = "/readyz"
    manifest_endpoint: str = "/plugin/manifest"
    # Optional embedded frontend (iframe). Absent -> the plugin is backend-only.
    ui: PluginUi | None = None
    # Reserved for future dynamic extension (not consumed by this patch).
    routes: list[dict] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    menus: list[dict] = Field(default_factory=list)


# --- Core API request/response ------------------------------------------------
class PluginCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True


class PluginUpdate(BaseModel):
    endpoint: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


class PluginResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    display_name: str
    description: str | None
    version: str | None
    api_version: str
    endpoint: str
    enabled: bool
    managed_by_config: bool
    status: str
    last_health_check: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    failure_reason: str | None
    # Parsed from the cached manifest (None if the plugin exposes no UI).
    ui: PluginUi | None = None
    created_at: datetime
    updated_at: datetime


class PluginInventoryServer(BaseModel):
    """A read-only view of one Core inventory server, exposed to plugins through
    the Core proxy so a plugin never replicates the inventory in its own DB.

    Serialized camelCase to match the rest of the plugin-facing contract
    (manifest, job responses)."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)

    id: uuid.UUID
    hostname: str
    display_name: str | None = None
    management_ip: str | None = None
    device_type: str
    vendor: str | None = None
    model: str | None = None
    status: str
    rack: str | None = None
    cluster: str | None = None


class PluginUiSession(BaseModel):
    """Result of minting the short-lived plugin-UI cookie."""

    expires_in: int
