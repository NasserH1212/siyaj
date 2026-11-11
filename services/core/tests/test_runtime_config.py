"""Guards on how the container runs the server (no network, file inspection only)."""

import json
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CORE_DIR.parents[1]


def _uvicorn_cmd() -> list[str]:
    cmd_lines = [
        line
        for line in (CORE_DIR / "Dockerfile").read_text().splitlines()
        if line.startswith("CMD ")
    ]
    # Docker uses only the last CMD.
    cmd: list[str] = json.loads(cmd_lines[-1].removeprefix("CMD "))
    assert cmd[0] == "uvicorn"
    return cmd


def test_access_log_is_disabled() -> None:
    # Access log lines include the query string, which may carry prompt text or PII.
    cmd = _uvicorn_cmd()
    assert "--no-access-log" in cmd
    assert "--access-log" not in cmd


def test_compose_does_not_override_access_log() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text()
    assert "access-log" not in compose
    assert "access_log" not in compose
