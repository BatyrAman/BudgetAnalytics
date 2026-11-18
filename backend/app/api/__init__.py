from fastapi import APIRouter, Depends

from app.api import (
    accounts,
    advisor,
    analytics,
    analytics_legacy,
    auth,
    banks,
    budget,
    categories,
    dashboard,
    deposits,
    goals,
    imports,
    investment,
    overview,
    transaction,
    upload,
)
from app.api.deps import limit_api_per_ip
from app.core.config import settings

# Every API request counts towards the per-IP limit.
api_router = APIRouter(dependencies=[Depends(limit_api_per_ip)])

api_router.include_router(auth.router)
api_router.include_router(categories.router)
api_router.include_router(accounts.router)
api_router.include_router(banks.router)
api_router.include_router(goals.router)
api_router.include_router(transaction.router)
api_router.include_router(budget.router)
api_router.include_router(deposits.router)
api_router.include_router(analytics.router)
api_router.include_router(overview.router)
api_router.include_router(advisor.router)
api_router.include_router(imports.router)
if settings.legacy_api_enabled:
    api_router.include_router(upload.router)
# Deprecated, kept for existing clients (see each module's header); disabled by
# default in production (ENABLE_LEGACY_API) — the legacy advisor gives
# investment suggestions without disclaimers.
if settings.legacy_api_enabled:
    api_router.include_router(analytics_legacy.router)
    api_router.include_router(dashboard.router)
    api_router.include_router(investment.router)

__all__ = ["api_router"]
