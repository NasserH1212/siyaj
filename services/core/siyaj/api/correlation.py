"""Per-request correlation IDs, echoed in the X-Correlation-ID response header."""

import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Correlation-ID"
_STATE_KEY = "correlation_id"
# Canonical UUID text is 36 chars; anything longer is rejected before parsing.
_MAX_LEN = 36


def _accept_or_generate(raw: str | None) -> str:
    # Only canonical UUIDs are trusted: the value ends up in logs and response headers,
    # so arbitrary client text (log injection, header smuggling, PII) must never pass through.
    if raw is not None and len(raw) <= _MAX_LEN:
        try:
            parsed = uuid.UUID(raw)
        except ValueError:
            pass
        else:
            if str(parsed) == raw.lower():
                return str(parsed)
    return str(uuid.uuid4())


def get_correlation_id(request: Request) -> str:
    cid = getattr(request.state, _STATE_KEY, None)
    # Fallback for paths that bypass the middleware; still never returns client input.
    return cid if isinstance(cid, str) else str(uuid.uuid4())


class CorrelationIdMiddleware:
    """Pure ASGI middleware so the ID lives in scope state, readable by the outermost
    500 handler (which runs outside user middleware and never sees this send wrapper)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cid = _accept_or_generate(Headers(scope=scope).get(HEADER))
        # Mutate in place: Request objects built later share this exact dict.
        scope.setdefault("state", {})[_STATE_KEY] = cid

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if HEADER not in headers:
                    headers[HEADER] = cid
            await send(message)

        await self.app(scope, receive, send_with_header)
