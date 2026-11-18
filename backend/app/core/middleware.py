"""ASGI middleware: request id propagation and access logging."""

import logging
import re
import time
import uuid

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

access_logger = logging.getLogger("budget.access")


class RequestContextMiddleware:
    """Assigns a request id (or accepts a safe client-supplied one), exposes it
    in ``request.state.request_id`` and the ``X-Request-ID`` response header,
    and writes one access-log line per request.

    The access log contains method, path, status and duration only — never the
    query string, headers or body.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = None
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break

        request_id = (
            incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        )
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                header_name = REQUEST_ID_HEADER.lower().encode()
                if not any(name.lower() == header_name for name, _ in headers):
                    headers.append((header_name, request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            access_logger.info(
                "request",
                extra={
                    "fields": {
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
            request_id_var.reset(token)


# ---------------------------------------------------------------- security headers
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    """Defensive headers for a JSON API that returns personal financial data.

    * ``Cache-Control: no-store`` on API responses (no caching in browsers/proxies);
    * nosniff, frame denial, no referrer, restrictive permissions;
    * a strict CSP everywhere except the interactive docs (disabled in production);
    * HSTS when ``hsts`` is enabled (production, served over HTTPS only).
    """

    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ]
                if path.startswith("/api/"):
                    extra.append((b"cache-control", b"no-store"))
                if not path.startswith(_DOCS_PATHS):
                    extra.append(
                        (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
                    )
                if self.hsts:
                    extra.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                present = {name.lower() for name, _ in headers}
                headers += [(n, v) for n, v in extra if n not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ---------------------------------------------------------------- body size
class _BodyTooLarge(HTTPException):
    """An HTTPException so FastAPI re-raises it unchanged while reading the
    body (other exceptions there become a generic 400) and the central
    handler renders the standard error body with the request id."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail="Request body is too large")


class BodySizeLimitMiddleware:
    """Rejects request bodies above a limit with 413 — by ``Content-Length``
    up front and by counting bytes as they stream in (chunked uploads).
    Statement upload paths get ``upload_limit``; everything else ``default_limit``."""

    def __init__(self, app: ASGIApp, default_limit: int, upload_limit: int) -> None:
        self.app = app
        self.default_limit = default_limit
        self.upload_limit = upload_limit

    def _limit(self, path: str) -> int:
        is_upload = (path.endswith("/preview") and "/imports/" in path) or "/upload/" in path
        return self.upload_limit if is_upload else self.default_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope.get("path", ""))
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    too_large = int(value) > limit
                except ValueError:
                    too_large = True
                if too_large:
                    await _send_413(send)
                    return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if not started:
                await _send_413(send)


async def _send_413(send: Send) -> None:
    body = b'{"detail":"Request body is too large","code":"payload_too_large","request_id":null}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
