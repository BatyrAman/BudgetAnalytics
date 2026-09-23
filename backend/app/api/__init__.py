from fastapi import APIRouter

from app.api import (
    analytics,
    auth,
    budget,
    dashboard,
    investment,
    transaction,
    upload,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(upload.router)
api_router.include_router(transaction.router)
api_router.include_router(budget.router)
api_router.include_router(investment.router)
api_router.include_router(dashboard.router)
api_router.include_router(analytics.router)

__all__ = ["api_router"]
