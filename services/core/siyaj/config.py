"""Runtime configuration, read from environment variables only."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    # Health checks must answer quickly so orchestrators don't hang on a dead dependency.
    health_timeout_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> "Settings":
        # KeyError on a missing variable is intentional: refuse to start half-configured.
        return cls(
            database_url=os.environ["DATABASE_URL"],
            redis_url=os.environ["REDIS_URL"],
        )
