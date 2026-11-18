"""Liveness and readiness probes (unversioned, unauthenticated)."""

import logging
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core import database
from app.core.config import settings
from app.core.rate_limit import RedisBackend, get_rate_limiter

router = APIRouter(tags=["Health"])

logger = logging.getLogger("budget.health")


class HealthResponse(BaseModel):
    status: Literal["healthy"]
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable"]
    rate_limit_store: Literal["ok", "unavailable", "not_used"] = "not_used"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness: the process is up. Does not touch dependencies."""

    return HealthResponse(status="healthy", service=settings.APP_NAME, version=settings.VERSION)


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness() -> ReadinessResponse | JSONResponse:
    """Readiness: the database answers ``SELECT 1`` and, when Redis backs the
    rate limiter, Redis answers PING. Unready instances get no traffic."""

    database_ok = True
    try:
        await database.check_database_connection()
    except Exception as exc:
        database_ok = False
        logger.warning("database not ready", extra={"fields": {"error_type": type(exc).__name__}})

    store: Literal["ok", "unavailable", "not_used"] = "not_used"
    limiter = get_rate_limiter()
    if isinstance(limiter.backend, RedisBackend):
        try:
            await limiter.backend.ping()
            store = "ok"
        except Exception as exc:
            store = "unavailable"
            logger.warning("redis not ready", extra={"fields": {"error_type": type(exc).__name__}})

    result = ReadinessResponse(
        status="ready" if database_ok and store != "unavailable" else "not_ready",
        database="ok" if database_ok else "unavailable",
        rate_limit_store=store,
    )
    if result.status != "ready":
        return JSONResponse(status_code=503, content=result.model_dump())
    return result
