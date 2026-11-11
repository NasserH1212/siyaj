"""Unit tests for GET /health. Fakes only: no real network, database, or Redis."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from siyaj.api.health import HealthChecks, PostgresProbe, RedisProbe, get_health_checks
from siyaj.main import create_app


class OkProbe:
    async def check(self) -> None:
        return None


class FailingProbe:
    async def check(self) -> None:
        raise ConnectionError("synthetic failure: postgres://user:secret@db-host:5432")


class HangingProbe:
    async def check(self) -> None:
        await asyncio.sleep(10)


def _client(db: Any, redis: Any, timeout: float = 2.0) -> TestClient:
    app = create_app()
    checks = HealthChecks(db=db, redis=redis, timeout_seconds=timeout)
    app.dependency_overrides[get_health_checks] = lambda: checks
    # Not used as a context manager, so the lifespan (real connections) never runs.
    return TestClient(app)


def test_health_ok_when_both_dependencies_healthy() -> None:
    resp = _client(OkProbe(), OkProbe()).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok", "redis": "ok"}


def test_health_503_when_redis_unreachable() -> None:
    resp = _client(OkProbe(), FailingProbe()).get("/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "error", "db": "ok", "redis": "error"}


def test_health_503_when_db_unreachable() -> None:
    resp = _client(FailingProbe(), OkProbe()).get("/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "error", "db": "error", "redis": "ok"}


def test_health_503_when_dependency_times_out() -> None:
    resp = _client(OkProbe(), HangingProbe(), timeout=0.05).get("/health")
    assert resp.status_code == 503
    assert resp.json()["redis"] == "error"


def test_health_response_leaks_no_error_details() -> None:
    resp = _client(FailingProbe(), FailingProbe()).get("/health")
    body = resp.text
    for leaked in ("secret", "db-host", "5432", "ConnectionError", "Traceback"):
        assert leaked not in body


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_and_schema_are_not_exposed(path: str) -> None:
    assert _client(OkProbe(), OkProbe()).get(path).status_code == 404


class _FakeRedis:
    def __init__(self, reply: bool) -> None:
        self._reply = reply

    async def ping(self) -> bool:
        return self._reply


class _FakeEngine:
    def connect(self) -> Any:
        raise ConnectionRefusedError("synthetic")


def test_redis_probe_passes_on_pong() -> None:
    asyncio.run(RedisProbe(_FakeRedis(True)).check())  # type: ignore[arg-type]


def test_redis_probe_raises_on_falsy_reply() -> None:
    with pytest.raises(RuntimeError):
        asyncio.run(RedisProbe(_FakeRedis(False)).check())  # type: ignore[arg-type]


def test_postgres_probe_propagates_connection_failure() -> None:
    with pytest.raises(ConnectionRefusedError):
        asyncio.run(PostgresProbe(_FakeEngine()).check())  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Guarantees tests can't silently pick up a developer's real connection strings.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
