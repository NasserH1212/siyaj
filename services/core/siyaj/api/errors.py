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

from siyaj.api.correlation import HEADER, get_correlation_id

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


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
        # Set explicitly so the 500 path (outside the correlation middleware) has it too.
        headers={**(headers or {}), HEADER: cid},
    )


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        return await _unexpected_error(request, exc)
    # Keep framework headers such as Allow on 405; drop exc.detail on purpose.
    return problem_response(request, exc.status_code, headers=exc.headers)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    return problem_response(request, HTTPStatus.UNPROCESSABLE_ENTITY)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Type only: the message or traceback may contain request data.
    logger.error(
        "unhandled exception",
        extra={"error_type": type(exc).__name__, "correlation_id": get_correlation_id(request)},
    )
    return problem_response(request, HTTPStatus.INTERNAL_SERVER_ERROR)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unexpected_error)
