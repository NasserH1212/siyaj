"""Unhandled exceptions must not leak messages, URLs or tracebacks into logs (rule 1)."""

import logging
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from siyaj.api.correlation import HEADER
from siyaj.api.health import HealthChecks, get_health_checks
from siyaj.main import create_app

CANARY = "CANARY-ERR-7781"
PATH_CANARY = "CANARY-PATH-4410"
QUERY_CANARY = "CANARY-QUERY-5520"
LOGGERS = ("", "uvicorn", "uvicorn.error", "siyaj")


class SyntheticLeakError(Exception):
    pass


def _app_with_raising_routes() -> FastAPI:
    app = create_app()

    # Test-only routes: production must never expose an endpoint that raises on purpose.
    @app.get("/_test/raise")
    async def raise_plain() -> None:
        raise SyntheticLeakError(f"prompt text {CANARY}")

    @app.get("/_test/items/{item_id}")
    async def raise_with_param(item_id: str) -> None:
        raise SyntheticLeakError(f"{CANARY} {item_id}")

    @app.get("/_test/stream")
    async def raise_mid_stream() -> StreamingResponse:
        async def body() -> AsyncIterator[bytes]:
            yield b"partial"
            raise SyntheticLeakError(CANARY)

        return StreamingResponse(body())

    return app


@pytest.fixture
def capture_all(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    for name in LOGGERS:
        caplog.set_level(logging.DEBUG, logger=name)
    return caplog


# The TestClient is an httpx client and logs its own outgoing request URL. That is the
# test harness talking, not the server, so only those client-side records are excluded.
_TEST_CLIENT_LOGGERS = ("httpx", "httpcore")


def _server_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name.split(".")[0] not in _TEST_CLIENT_LOGGERS]


def _assert_no_leak(caplog: pytest.LogCaptureFixture, *canaries: str) -> None:
    records = _server_records(caplog)
    assert any(r.name.startswith("siyaj") for r in records), "expected the siyaj error line"
    for record in records:
        assert record.exc_info is None, f"traceback attached by {record.name}"
        assert record.exc_text is None
        for canary in canaries:
            assert canary not in record.getMessage()
            assert canary not in repr(record.args)


def test_unhandled_exception_is_not_leaked(capture_all: pytest.LogCaptureFixture) -> None:
    client = TestClient(_app_with_raising_routes(), raise_server_exceptions=False)

    resp = client.get("/_test/raise")

    assert resp.status_code == 500
    assert resp.headers["content-type"] == "application/problem+json"
    assert CANARY not in resp.text
    _assert_no_leak(capture_all, CANARY)

    cid = resp.json()["correlation_id"]
    assert resp.headers[HEADER] == cid
    error_lines = [r for r in capture_all.records if r.levelno == logging.ERROR]
    assert len(error_lines) == 1
    line = error_lines[0].getMessage()
    assert cid in line
    assert "SyntheticLeakError" in line
    assert "method=GET" in line
    assert "route=/_test/raise" in line


def test_log_uses_route_template_not_raw_path_or_query(
    capture_all: pytest.LogCaptureFixture,
) -> None:
    client = TestClient(_app_with_raising_routes(), raise_server_exceptions=False)

    resp = client.get(f"/_test/items/{PATH_CANARY}", params={"q": QUERY_CANARY})

    assert resp.status_code == 500
    _assert_no_leak(capture_all, CANARY, PATH_CANARY, QUERY_CANARY)
    assert any(
        "route=/_test/items/{item_id}" in r.getMessage() for r in _server_records(capture_all)
    )


def test_exception_never_reaches_server_error_middleware(
    capture_all: pytest.LogCaptureFixture,
) -> None:
    # With raise_server_exceptions=True, TestClient re-raises whatever escapes
    # ServerErrorMiddleware; reaching the assert proves nothing escaped.
    client = TestClient(_app_with_raising_routes(), raise_server_exceptions=True)

    resp = client.get("/_test/raise")

    assert resp.status_code == 500
    _assert_no_leak(capture_all, CANARY)


def test_valid_incoming_correlation_id_is_logged(capture_all: pytest.LogCaptureFixture) -> None:
    cid = str(uuid.uuid4())
    client = TestClient(_app_with_raising_routes(), raise_server_exceptions=False)

    resp = client.get("/_test/raise", headers={HEADER: cid})

    assert resp.json()["correlation_id"] == cid
    assert any(f"correlation_id={cid}" in r.getMessage() for r in _server_records(capture_all))


def test_exception_after_response_started_is_swallowed_without_leak(
    capture_all: pytest.LogCaptureFixture,
) -> None:
    client = TestClient(_app_with_raising_routes(), raise_server_exceptions=True)

    resp = client.get("/_test/stream")

    # Headers were already sent, so the status can't change; nothing may leak or escape.
    assert resp.status_code == 200
    _assert_no_leak(capture_all, CANARY)
    assert any("SyntheticLeakError" in r.getMessage() for r in _server_records(capture_all))


class _OkProbe:
    async def check(self) -> None:
        return None


def test_production_app_has_no_test_routes() -> None:
    # Checked by behaviour, not by walking app.routes: included routers are wrapped
    # objects without a .path, which would make a route-list check pass vacuously.
    app = create_app()
    checks = HealthChecks(db=_OkProbe(), redis=_OkProbe(), timeout_seconds=1.0)
    app.dependency_overrides[get_health_checks] = lambda: checks
    client = TestClient(app, raise_server_exceptions=True)

    assert client.get("/health").status_code == 200  # control: real routes are reachable
    for path in ("/_test/raise", "/_test/items/x", "/_test/stream"):
        assert client.get(path).status_code == 404
