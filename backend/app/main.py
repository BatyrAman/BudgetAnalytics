"""Application factory.

Run: ``uvicorn app.main:app --no-access-log`` (access logs come from
RequestContextMiddleware). The schema is managed only by Alembic
(``alembic upgrade head``); tables are never created at startup.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api.health import router as health_router
from app.core.config import Settings, settings
from app.core.database import engine
from app.core.errors import ErrorResponse, register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    REQUEST_ID_HEADER,
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.rate_limit import close_rate_limiter

logger = logging.getLogger("budget")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "application startup",
        extra={"fields": {"environment": settings.ENVIRONMENT, "version": settings.VERSION}},
    )
    try:
        yield
    finally:
        from app.api.advisor import close_llm_client

        await close_llm_client()
        await close_rate_limiter()
        await engine.dispose()
        logger.info("application shutdown")


def create_app(app_settings: Settings = settings) -> FastAPI:
    configure_logging(app_settings)

    docs = app_settings.docs_enabled
    app = FastAPI(
        title=app_settings.APP_NAME,
        version=app_settings.VERSION,
        description="Budget Analytics API",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
        responses={
            401: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )

    register_exception_handlers(app)

    # Bearer-token auth does not use cookies, so credentials are not allowed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        # Readable by browser JS: request id for support, Retry-After for 429 back-off.
        expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
    )
    app.add_middleware(
        BodySizeLimitMiddleware,
        default_limit=app_settings.MAX_REQUEST_BYTES,
        upload_limit=app_settings.IMPORT_MAX_FILE_BYTES + 256 * 1024,  # multipart overhead
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=app_settings.is_production)
    # Added last → outermost: request id is set before CORS and routing.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health_router)
    app.include_router(api_router, prefix=app_settings.API_PREFIX)

    @app.get("/", tags=["Root"], include_in_schema=False)
    async def root() -> dict[str, str]:
        body = {"message": "Welcome to Budget Analytics API", "version": app_settings.VERSION}
        if docs:
            body |= {"docs": "/docs", "redoc": "/redoc"}
        return body

    return app


app = create_app()
