from fastapi import APIRouter

from app.api import (
    analytics,
    auth,
    budget,
    cards,
    dashboard,
    debts,
    finance,
    investment,
    products,
    transaction,
    upload,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(upload.router)
api_router.include_router(cards.router)
api_router.include_router(transaction.router)
api_router.include_router(budget.router)
api_router.include_router(debts.router)
api_router.include_router(investment.router)
api_router.include_router(dashboard.router)
api_router.include_router(analytics.router)
api_router.include_router(finance.router)
api_router.include_router(products.router)

__all__ = ["api_router"]
