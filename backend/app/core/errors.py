"""
Единый формат ошибок API.

Любая ошибка возвращается как:

    {
        "error": {
            "code": "DEBT_NOT_FOUND",
            "message": "Debt not found",
            "details": {}
        }
    }

Сервисный и доменный слои бросают AppError (или наследников);
API-слой ничего не знает о кодах статусов для бизнес-ошибок.
Внутренние исключения наружу не раскрываются.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str = Field(examples=["DEBT_NOT_FOUND"])
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "Bad request"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "Resource already exists"


class DomainValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "Invalid input"


class AuthenticationError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "Could not validate credentials"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "Forbidden"


class RateLimitError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests"


def _payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details or {})
    ).model_dump()


_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Pydantic кладёт в ошибку исходное значение ("input") — это может
    # быть пароль или сумма. Наружу отдаём только путь, тип и текст.
    return [
        {
            "loc": [str(part) for part in err.get("loc", ())],
            "type": err.get("type"),
            "msg": err.get("msg"),
        }
        for err in errors
    ]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        if isinstance(exc.detail, str):
            message = exc.detail
        else:
            message = HTTPStatus(exc.status_code).phrase
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload(
                "VALIDATION_ERROR",
                "Request validation failed",
                {"errors": _sanitize_validation_errors(exc.errors())},
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=_payload(
                "INTERNAL_ERROR",
                "Internal server error",
                {"request_id": request_id_var.get()},
            ),
        )


# Стандартные ответы для OpenAPI, чтобы клиенты видели контракт ошибок.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    404: {"model": ErrorResponse, "description": "Not found"},
    422: {"model": ErrorResponse, "description": "Validation error"},
}
