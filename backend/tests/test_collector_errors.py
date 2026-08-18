"""Unit tests for collector error classification (F2)."""
import socket
import ssl

import asyncssh
import httpx

from collectors.errors import (
    ERROR_AUTH_FAILED,
    ERROR_CONNECTION_TIMEOUT,
    ERROR_DNS,
    ERROR_HOST_UNREACHABLE,
    ERROR_HTTP,
    ERROR_INTERNAL,
    ERROR_REDFISH_SCHEMA,
    ERROR_SSH,
    ERROR_SSL,
    RedfishSchemaError,
    classify_error,
)


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example/redfish/v1")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("error", request=request, response=response)


def test_auth_failures() -> None:
    assert classify_error(_http_status_error(401)).code == ERROR_AUTH_FAILED
    assert classify_error(_http_status_error(403)).code == ERROR_AUTH_FAILED
    assert classify_error(asyncssh.PermissionDenied("denied")).code == ERROR_AUTH_FAILED


def test_http_error() -> None:
    assert classify_error(_http_status_error(500)).code == ERROR_HTTP


def test_timeouts() -> None:
    assert classify_error(httpx.ConnectTimeout("timed out")).code == ERROR_CONNECTION_TIMEOUT
    assert classify_error(TimeoutError()).code == ERROR_CONNECTION_TIMEOUT


def test_dns_failure() -> None:
    exc = httpx.ConnectError("resolve failed")
    exc.__cause__ = socket.gaierror(-2, "Name or service not known")
    assert classify_error(exc).code == ERROR_DNS


def test_ssl_error() -> None:
    exc = httpx.ConnectError("ssl failed")
    exc.__cause__ = ssl.SSLError("bad cert")
    assert classify_error(exc).code == ERROR_SSL


def test_host_unreachable() -> None:
    exc = httpx.ConnectError("refused")
    exc.__cause__ = ConnectionRefusedError()
    assert classify_error(exc).code == ERROR_HOST_UNREACHABLE
    assert classify_error(ConnectionRefusedError()).code == ERROR_HOST_UNREACHABLE


def test_ssh_and_redfish_and_fallback() -> None:
    assert classify_error(asyncssh.ConnectionLost("lost")).code == ERROR_SSH
    assert classify_error(RedfishSchemaError("no system")).code == ERROR_REDFISH_SCHEMA
    classified = classify_error(ValueError("boom"))
    assert classified.code == ERROR_INTERNAL
    assert classified.readable_message
    assert "ValueError" in classified.detail
