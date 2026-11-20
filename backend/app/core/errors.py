"""Centralized error handling.

Every error response has the same shape::

    {"detail": <str | list>, "code": "<machine_code>", "request_id": "<id>"}

``detail`` is kept for backward compatibility with FastAPI's default format,
so existing clients that read ``detail`` keep working. Internal exception
details are never returned to the client; unexpected errors are logged with a
stack trace and answered with a generic 500.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware import REQUEST_ID_HEADER

logger = logging.getLogger("budget.errors")

_CODES_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
}


class ErrorResponse(BaseModel):
    """OpenAPI description of the common error body."""

    detail: str | list[dict[str, Any]]
    code: str
    request_id: str | None = None


# ---------------------------------------------------------------- app errors
class AppError(Exception):
    """Base for errors raised by services; mapped to the common error body.

    ``message`` must be safe to show to the user (no internals, no data of
    other users). Services raise these instead of FastAPI's HTTPException so
    business logic stays independent of the web framework.
    """

    status_code = 400
    code = "bad_request"
    headers: dict[str, str] | None = None

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        # A stable, machine-readable snake_case code of the business rule
        # (documented in docs/design/API_TO_UI_MAPPING.md §0.2). The class
        # attribute is only a fallback for raise sites without a specific code.
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    """Missing OR owned by another user — the two are indistinguishable to
    the caller, so resource ids of other users cannot be probed (IDOR)."""

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "forbidden"


class DomainValidationError(AppError):
    status_code = 422
    code = "validation_error"


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthorized"
    headers = {"WWW-Authenticate": "Bearer"}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_response(
    request: Request,
    status_code: int,
    detail: Any,
    code: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    response_headers = dict(headers or {})
    if request_id:
        response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"detail": detail, "code": code, "request_id": request_id}),
        headers=response_headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _CODES_BY_STATUS.get(exc.status_code, "http_error")
    detail = exc.detail
    if detail is None:
        detail = HTTPStatus(exc.status_code).phrase
    return _error_response(
        request, exc.status_code, detail, code, headers=getattr(exc, "headers", None)
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Do not echo submitted values back ("input"/"ctx" may contain passwords or
    # non-serializable objects): keep only location, message and error type.
    errors = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return _error_response(request, 422, errors, "validation_error")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled exception",
        exc_info=exc,
        extra={
            "fields": {
                "request_id": _request_id(request),
                "method": request.method,
                "path": request.url.path,
                "error_type": type(exc).__name__,
            }
        },
    )
    return _error_response(request, 500, "Internal server error", "internal_error")


# PostgreSQL SQLSTATE -> (HTTP status, code, safe message). Values and
# constraint names are never echoed to the client (only logged).
_INTEGRITY_ERRORS = {
    "23505": (409, "duplicate", "The request conflicts with an existing record"),
    "23503": (422, "invalid_reference", "A referenced record does not exist"),
    "23514": (422, "constraint_violation", "A value violates a data constraint"),
    "23502": (422, "constraint_violation", "A required value is missing"),
}


# Unique constraint/index name -> entity-specific code for a 23505 violation
# (e.g. a race between two requests that passed the service-level check). The
# HTTP status and the generic message stay the same; unknown names keep
# ``duplicate``.
_UNIQUE_VIOLATION_CODES = {
    "uq_accounts_user_id_name": "account_name_taken",
    "uq_financial_goals_user_id_name": "goal_name_taken",
    "uq_categories_user_id_name": "category_exists",
    "uq_categories_system_name": "category_exists",
    "ix_users_email": "email_taken",
}


def _constraint_name(exc: IntegrityError) -> str | None:
    """asyncpg exposes the violated constraint on the driver exception that
    SQLAlchemy's adapter wraps (``exc.orig.__cause__``)."""

    for candidate in (getattr(exc.orig, "__cause__", None), exc.orig):
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str):
            return name
    return None


def _sqlstate(exc: IntegrityError) -> str | None:
    orig = exc.orig
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Database constraints are the last line of defense; a violation is a
    client error (or a race between two requests), not a server crash. The
    session is rolled back by ``get_db`` before this handler runs."""

    sqlstate = _sqlstate(exc)
    status_code, code, message = _INTEGRITY_ERRORS.get(
        sqlstate or "", (409, "conflict", "The request conflicts with stored data")
    )
    constraint = _constraint_name(exc)
    if sqlstate == "23505" and constraint is not None:
        code = _UNIQUE_VIOLATION_CODES.get(constraint, code)
    logger.warning(
        "integrity error",
        extra={
            "fields": {
                "request_id": _request_id(request),
                "path": request.url.path,
                "sqlstate": sqlstate,
                "constraint": constraint,
            }
        },
    )
    return _error_response(request, status_code, message, code)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(request, exc.status_code, exc.message, exc.code, headers=exc.headers)


async def finance_input_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    # FinanceInputError messages are written to be user-safe.
    return _error_response(request, 422, str(exc), "invalid_financial_input")


async def file_rejected_handler(request: Request, exc: Exception) -> JSONResponse:
    # FileRejected carries a safe message, a machine code and an HTTP status.
    return _error_response(
        request,
        getattr(exc, "status_code", 422),
        getattr(exc, "message", "Invalid file"),
        getattr(exc, "code", "invalid_file"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    from app.services.finance.money import FinanceInputError
    from app.services.imports.files import FileRejected

    app.add_exception_handler(FileRejected, file_rejected_handler)

    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(FinanceInputError, finance_input_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
