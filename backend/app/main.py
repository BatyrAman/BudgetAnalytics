from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.startup import check_database

configure_logging(settings.LOG_LEVEL, settings.LOG_JSON)
logger = logging.getLogger("budget")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Схему создают только миграции (alembic upgrade head).
    # Здесь — лишь проверка инфраструктуры.
    if settings.STARTUP_CHECKS:
        await check_database(engine)

    logger.info(
        "%s %s started (env=%s)",
        settings.APP_NAME,
        settings.VERSION,
        settings.ENVIRONMENT,
    )

    yield

    await engine.dispose()
    logger.info("%s stopped", settings.APP_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        description="Budget Analytics API — deterministic financial core",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router, prefix=settings.API_PREFIX)

    @app.get("/", tags=["Root"])
    async def root():
        return {
            "message": "Welcome to Budget Analytics API",
            "docs": "/docs",
            "redoc": "/redoc",
            "version": settings.VERSION,
        }

    @app.get("/health", tags=["Health"])
    async def health():
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "version": settings.VERSION,
        }

    @app.get("/health/ready", tags=["Health"])
    async def readiness():
        """Готовность к трафику: БД доступна."""

        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ready"}

    @app.get("/home", tags=["Home"], include_in_schema=False)
    async def home():
        return {"message": "Hello World"}

    return app


app = create_app()
