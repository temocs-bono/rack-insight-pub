"""Plugin HTTP client (Plugin Architecture Foundation).

Thin, timeout-bounded HTTP access to a plugin's endpoint. Every call has an
explicit timeout so a slow or dead plugin can never make a Core request (or the
health monitor) hang. Failures are returned as values / typed exceptions, never
left to propagate as unhandled errors into Core request handling.
"""
from dataclasses import dataclass

import httpx

from config import get_settings
from schemas.plugin import PluginManifest
from utils.logging import get_logger

logger = get_logger(__name__)

MANIFEST_PATH = "/plugin/manifest"


class PluginUnavailable(RuntimeError):
    """The plugin could not be reached or answered incorrectly."""


def _timeout() -> float:
    return float(get_settings().plugin_request_timeout_seconds)


def _base(endpoint: str) -> str:
    return endpoint.rstrip("/")


def _make_client() -> httpx.AsyncClient:
    """Single place clients are created — tests swap this to route to an
    in-process ASGI plugin, so no real socket is required."""
    return httpx.AsyncClient(timeout=_timeout())


async def fetch_manifest(endpoint: str) -> PluginManifest:
    """Fetch and validate a plugin's manifest. Raises PluginUnavailable on any
    transport error, non-2xx, or malformed manifest."""
    url = f"{_base(endpoint)}{MANIFEST_PATH}"
    try:
        async with _make_client() as client:
            response = await client.get(url)
            response.raise_for_status()
            return PluginManifest.model_validate(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        raise PluginUnavailable(f"manifest fetch failed: {exc}") from exc


async def check_health(endpoint: str, health_path: str = "/healthz") -> None:
    """Probe a plugin health endpoint. Returns None on success; raises
    PluginUnavailable on any failure (timeout, refused, non-2xx)."""
    path = health_path if health_path.startswith("/") else f"/{health_path}"
    url = f"{_base(endpoint)}{path}"
    try:
        async with _make_client() as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PluginUnavailable(f"health check failed: {exc}") from exc


@dataclass
class ProxyResult:
    status_code: int
    content: bytes
    media_type: str


async def proxy_request(
    method: str,
    endpoint: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: object | None = None,
    headers: dict | None = None,
) -> ProxyResult:
    """Forward a minimal REST request (GET/POST) to the plugin and return its
    response verbatim. Raises PluginUnavailable if the plugin cannot be reached
    (so the caller can answer 503 without leaking a stack trace)."""
    normalized = path if path.startswith("/") else f"/{path}"
    url = f"{_base(endpoint)}{normalized}"
    try:
        async with _make_client() as client:
            response = await client.request(
                method.upper(), url, params=params, json=json_body, headers=headers
            )
        return ProxyResult(
            status_code=response.status_code,
            content=response.content,
            media_type=response.headers.get("content-type", "application/json"),
        )
    except httpx.HTTPError as exc:
        raise PluginUnavailable(f"proxy request failed: {exc}") from exc
