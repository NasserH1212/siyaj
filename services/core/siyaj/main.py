"""FastAPI application factory for Siyaj core."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from siyaj.api import health
from siyaj.api.correlation import CorrelationIdMiddleware
from siyaj.api.errors import register_error_handlers
from siyaj.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings or Settings.from_env()
        timeout = cfg.health_timeout_seconds
        engine = create_async_engine(
            cfg.database_url,
            pool_pre_ping=True,
            connect_args={"timeout": timeout},
        )
        redis_client = Redis.from_url(
            cfg.redis_url,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
        )
        app.state.health_checks = health.HealthChecks(
            db=health.PostgresProbe(engine),
            redis=health.RedisProbe(redis_client),
            timeout_seconds=timeout,
        )
        try:
            yield
        finally:
            await redis_client.aclose()
            await engine.dispose()

    # Interactive docs and the OpenAPI schema are disabled: /health must stay the only
    # unauthenticated surface until auth lands in Task 2.2.
    app = FastAPI(
        title="Siyaj core",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    register_error_handlers(app)
    # Added last so it is outermost: the ID exists before the error middleware needs it.
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health.router)
    return app


app = create_app()
