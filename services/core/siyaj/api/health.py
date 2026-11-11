"""Liveness/readiness endpoint. The only unauthenticated route (auth arrives in Task 2.2)."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

ComponentStatus = Literal["ok", "error"]


class Probe(Protocol):
    async def check(self) -> None:
        """Return normally if healthy; raise on any problem."""


class PostgresProbe:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self) -> None:
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))


class RedisProbe:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def check(self) -> None:
        if not await self._client.ping():
            raise RuntimeError("redis PING returned a falsy reply")


@dataclass(frozen=True, slots=True)
class HealthChecks:
    db: Probe
    redis: Probe
    timeout_seconds: float


async def _run(name: str, probe: Probe, limit_seconds: float) -> ComponentStatus:
    try:
        async with asyncio.timeout(limit_seconds):
            await probe.check()
    # Fail closed: any failure, including timeouts and unexpected errors, means "error".
    except Exception as exc:  # noqa: BLE001
        # Only the exception type is logged: driver messages can echo DSNs or hostnames.
        logger.warning(
            "health check failed",
            extra={"component": name, "error_type": type(exc).__name__},
        )
        return "error"
    return "ok"


def get_health_checks(request: Request) -> HealthChecks:
    checks: HealthChecks = request.app.state.health_checks
    return checks


router = APIRouter()


@router.get("/health")
async def health(checks: Annotated[HealthChecks, Depends(get_health_checks)]) -> JSONResponse:
    # Run concurrently so the endpoint's worst case is one timeout, not the sum.
    db, redis = await asyncio.gather(
        _run("db", checks.db, checks.timeout_seconds),
        _run("redis", checks.redis, checks.timeout_seconds),
    )
    healthy = db == "ok" and redis == "ok"
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "error", "db": db, "redis": redis},
    )
