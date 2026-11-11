"""RFC 7807 problem+json error responses (AGENTS.md rule 8).

Bodies carry only the standard HTTP reason phrase: exception messages and validation
details can echo request content (prompts, PII) and are never returned to clients.
"""

import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from siyaj.api.correlation import HEADER, get_correlation_id

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"

# The method is client-chosen text; anything outside the standard set is logged as OTHER.
_KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


def problem_response(
    request: Request, status: int, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    cid = get_correlation_id(request)
    return JSONResponse(
        status_code=status,
        content={
            # "about:blank" means the title is just the HTTP status phrase (RFC 7807 §4.2).
            "type": "about:blank",
            "title": HTTPStatus(status).phrase,
            "status": status,
            "correlation_id": cid,
        },
        media_type=PROBLEM_JSON,
        headers={**(headers or {}), HEADER: cid},
    )


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    # Registration guarantees the type; the check only narrows it for mypy.
    status = (
        exc.status_code
        if isinstance(exc, StarletteHTTPException)
        else HTTPStatus.INTERNAL_SERVER_ERROR
    )
    headers = exc.headers if isinstance(exc, StarletteHTTPException) else None
    # Keep framework headers such as Allow on 405; drop exc.detail on purpose.
    return problem_response(request, status, headers=headers)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    return problem_response(request, HTTPStatus.UNPROCESSABLE_ENTITY)


def _route_template(scope: Scope) -> str:
    # The router writes the matched route into scope; its template (e.g. /items/{id})
    # is safe to log, whereas the raw path or query string may hold prompt text or PII.
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) else "<unmatched>"


class UnhandledErrorMiddleware:
    """Turns unhandled exceptions into an RFC 7807 500 and swallows them.

    Starlette's ServerErrorMiddleware re-raises after its handler runs, so Uvicorn
    would log the full traceback and message through uvicorn.error. Catching here,
    inside it, keeps exceptions from ever reaching that path (AGENTS.md rule 1).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        # Deliberately broad: anything escaping here would be logged with its message.
        except Exception as exc:  # noqa: BLE001
            request = Request(scope)
            method = scope.get("method", "")
            # One line, fixed fields only: no message, traceback, URL, headers or body.
            logger.error(
                "unhandled exception error_type=%s correlation_id=%s method=%s route=%s",
                type(exc).__name__,
                get_correlation_id(request),
                method if method in _KNOWN_METHODS else "OTHER",
                _route_template(scope),
            )
            if response_started:
                # Headers already sent; a second response would be a protocol error.
                return
            response = problem_response(request, HTTPStatus.INTERNAL_SERVER_ERROR)
            await response(scope, receive, send)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    # Unhandled exceptions are handled by UnhandledErrorMiddleware, not an
    # Exception handler: Starlette re-raises after such handlers, which is the leak.
    app.add_middleware(UnhandledErrorMiddleware)
