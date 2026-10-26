"""Errors as RFC 9457 problem details (`application/problem+json`), each carrying the request ID."""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.api_paths import is_api_request
from app.core.cache_control import CACHE_CONTROL_HEADER, NO_STORE
from app.core.request_id import REQUEST_ID_HEADER

PROBLEM_JSON = "application/problem+json"

logger = logging.getLogger(__name__)


def _title(status_code: int) -> str:
    """The standard reason phrase, or a generic title for codes outside the standard list."""
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Error"


def problem_response(
    request: Request,
    status_code: int,
    detail: str | None = None,
    extra: dict[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build a problem-details response. `type` stays `about:blank` until we define our own."""
    request_id = getattr(request.state, "request_id", None)
    body: dict[str, object] = {
        "type": "about:blank",
        "title": _title(status_code),
        "status": status_code,
        "instance": request.url.path,
    }
    if detail is not None:
        body["detail"] = detail
    if request_id is not None:
        body["requestId"] = request_id
    if extra:
        body.update(extra)
    response_headers = dict(headers or {})
    if request_id is not None:
        # Unhandled errors are answered outside the request-ID middleware, so set the header
        # here too.
        response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        body, status_code=status_code, media_type=PROBLEM_JSON, headers=response_headers or None
    )


class ProblemError(Exception):
    """A refusal with a code of its own, which becomes the problem's `type` (RFC 9457).

    `HTTPException` can't carry a `type`, and the assistant's routes need the web app to tell
    "conversation-outdated" from "turn-running" without parsing prose. The code is the bare
    string, such as `turn-running`. Every other route keeps using `HTTPException`.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        # More fields for the problem's body, such as the current status of the thing refused, under
        # names that are not the standard members (`status` is the HTTP status).
        self.extra = dict(extra or {})


async def _problem_error(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(ProblemError, exc)
    return problem_response(request, exc.status_code, exc.detail, {**exc.extra, "type": exc.code})


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    title = _title(exc.status_code)
    # An empty detail, or one that only repeats the title, adds nothing, so leave it out.
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail not in ("", title) else None
    return problem_response(request, exc.status_code, detail, headers=exc.headers)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)
    errors = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "The request did not pass validation.",
        {"errors": errors},
    )


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    # uvicorn logs this exception again (without the request ID) after we answer, because
    # Starlette re-raises it for the server. This copy is the one that carries the ID.
    logger.error("Unhandled error", exc_info=exc, extra={"request_id": request_id})
    # Like the request-ID header, this can't come from a middleware: this response is sent from
    # outside all of them.
    headers = {CACHE_CONTROL_HEADER: NO_STORE} if is_api_request(request.scope) else None
    return problem_response(
        request, status.HTTP_500_INTERNAL_SERVER_ERROR, "Something went wrong.", headers=headers
    )


def install_problem_handlers(app: FastAPI) -> None:
    """Route every error the API can produce through problem details."""
    app.add_exception_handler(ProblemError, _problem_error)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
