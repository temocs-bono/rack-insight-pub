"""Collector error classification.

Maps raw collector exceptions to stable error codes plus operator-readable
messages, so the UI can say "Authentication failed" instead of dumping a
stack trace.
"""
import socket
import ssl
from dataclasses import dataclass

import asyncssh
import httpx

ERROR_AUTH_FAILED = "AUTH_FAILED"
ERROR_CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
ERROR_HOST_UNREACHABLE = "HOST_UNREACHABLE"
ERROR_SSL = "SSL_ERROR"
ERROR_DNS = "DNS_FAILURE"
ERROR_HTTP = "HTTP_ERROR"
ERROR_REDFISH_SCHEMA = "REDFISH_SCHEMA_ERROR"
ERROR_SSH = "SSH_ERROR"
ERROR_INTERNAL = "COLLECTOR_EXCEPTION"

READABLE_MESSAGES: dict[str, str] = {
    ERROR_AUTH_FAILED: "Authentication failed — check the configured credentials",
    ERROR_CONNECTION_TIMEOUT: "Connection timed out — host did not respond in time",
    ERROR_HOST_UNREACHABLE: "Host unreachable — connection refused or no route to host",
    ERROR_SSL: "SSL certificate error while connecting",
    ERROR_DNS: "DNS failure — hostname could not be resolved",
    ERROR_HTTP: "HTTP error returned by the management endpoint",
    ERROR_REDFISH_SCHEMA: "Redfish schema error — endpoint responded without expected data",
    ERROR_SSH: "SSH error while running collection commands",
    ERROR_INTERNAL: "Internal collector exception",
}


class RedfishSchemaError(RuntimeError):
    """Raised when a Redfish endpoint answers but lacks the expected schema."""


@dataclass
class ClassifiedError:
    code: str
    readable_message: str
    detail: str


def _has_cause(exc: BaseException, exc_type: type[BaseException]) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, exc_type):
            return True
        current = current.__cause__ or current.__context__
    return False


def classify_error(exc: BaseException) -> ClassifiedError:
    """Map a collector exception to a stable error code."""
    code = ERROR_INTERNAL

    if isinstance(exc, RedfishSchemaError):
        code = ERROR_REDFISH_SCHEMA
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        code = ERROR_AUTH_FAILED if status in (401, 403) else ERROR_HTTP
    elif isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)):
        code = ERROR_CONNECTION_TIMEOUT
    elif isinstance(exc, (asyncssh.PermissionDenied,)):
        code = ERROR_AUTH_FAILED
    elif isinstance(exc, asyncssh.Error):
        code = ERROR_SSH
    elif isinstance(exc, TimeoutError):
        code = ERROR_CONNECTION_TIMEOUT
    elif _has_cause(exc, socket.gaierror):
        code = ERROR_DNS
    elif _has_cause(exc, ssl.SSLError):
        code = ERROR_SSL
    elif _has_cause(exc, ConnectionRefusedError) or isinstance(exc, httpx.ConnectError):
        # httpx.ConnectError wraps DNS/SSL causes too, checked above first.
        code = ERROR_HOST_UNREACHABLE
    elif isinstance(exc, (ConnectionError, OSError)):
        code = ERROR_HOST_UNREACHABLE
    elif isinstance(exc, httpx.HTTPError):
        code = ERROR_HTTP

    return ClassifiedError(
        code=code,
        readable_message=READABLE_MESSAGES[code],
        detail=f"{type(exc).__name__}: {exc}",
    )
