"""RFC 7807 error responses and correlation IDs. No real network or dependencies."""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from siyaj.api.correlation import HEADER
from siyaj.api.health import HealthChecks, get_health_checks
from siyaj.main import create_app

CANARY_DETAIL = "synthetic-canary-9f2c"


class _OkProbe:
    async def check(self) -> None:
        return None


def _app() -> FastAPI:
    app = create_app()
    checks = HealthChecks(db=_OkProbe(), redis=_OkProbe(), timeout_seconds=1.0)
    app.dependency_overrides[get_health_checks] = lambda: checks

    # Test-only routes; production exposes no such endpoints.
    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError(CANARY_DETAIL)

    @app.get("/_test/typed")
    async def typed(n: int) -> dict[str, int]:
        return {"n": n}

    return app


def _client() -> TestClient:
    # Return the 500 response instead of re-raising inside the test.
    return TestClient(_app(), raise_server_exceptions=False)


def _assert_problem(resp: Response, status: int, title: str) -> dict[str, object]:
    assert resp.status_code == status
    assert resp.headers["content-type"] == "application/problem+json"
    body: dict[str, object] = resp.json()
    assert body == {
        "type": "about:blank",
        "title": title,
        "status": status,
        "correlation_id": body["correlation_id"],
    }
    assert resp.headers[HEADER] == body["correlation_id"]
    uuid.UUID(str(body["correlation_id"]))
    assert "Traceback" not in resp.text
    return body


def test_404_is_problem_json() -> None:
    _assert_problem(_client().get("/does-not-exist"), 404, "Not Found")


def test_405_is_problem_json_and_keeps_allow_header() -> None:
    resp = _client().post("/health")
    _assert_problem(resp, 405, "Method Not Allowed")
    assert "GET" in resp.headers["allow"]


def test_validation_error_is_problem_json_without_echoing_input() -> None:
    resp = _client().get("/_test/typed", params={"n": CANARY_DETAIL})
    _assert_problem(resp, 422, "Unprocessable Entity")
    assert CANARY_DETAIL not in resp.text


def test_unexpected_error_is_problem_json_without_message() -> None:
    resp = _client().get("/_test/boom")
    _assert_problem(resp, 500, "Internal Server Error")
    assert CANARY_DETAIL not in resp.text
    assert "RuntimeError" not in resp.text


def test_valid_incoming_correlation_id_is_echoed() -> None:
    cid = str(uuid.uuid4())
    resp = _client().get("/does-not-exist", headers={HEADER: cid})
    assert resp.headers[HEADER] == cid
    assert resp.json()["correlation_id"] == cid


def test_valid_correlation_id_echoed_on_500() -> None:
    cid = str(uuid.uuid4())
    resp = _client().get("/_test/boom", headers={HEADER: cid})
    assert resp.headers[HEADER] == cid
    assert resp.json()["correlation_id"] == cid


def test_invalid_incoming_correlation_ids_are_replaced() -> None:
    client = _client()
    good = uuid.uuid4()
    for bad in (
        "not-a-uuid",
        "CANARY-TEST-123",
        "1" * 500,
        good.hex,  # valid UUID, but not canonical form
        "{" + str(good) + "}",
        f"urn:uuid:{good}",
    ):
        resp = client.get("/does-not-exist", headers={HEADER: bad})
        returned = resp.headers[HEADER]
        assert returned != bad
        assert str(uuid.UUID(returned)) == returned


def test_uppercase_uuid_is_accepted_in_canonical_lowercase() -> None:
    cid = str(uuid.uuid4())
    resp = _client().get("/does-not-exist", headers={HEADER: cid.upper()})
    assert resp.headers[HEADER] == cid


def test_health_bodies_unchanged_and_carry_correlation_header() -> None:
    resp = _client().get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok", "redis": "ok"}
    uuid.UUID(resp.headers[HEADER])
