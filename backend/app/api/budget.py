from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    PaginationParams,
    get_current_active_user,
    get_db,
    get_timezone,
    parse_month,
)
from app.core.errors import ErrorResponse
from app.models.budget import Budget
from app.models.user import User
from app.schemas.budget import (
    BudgetAlert,
    BudgetCreate,
    BudgetDetail,
    BudgetListResponse,
    BudgetProgress,
    BudgetResponse,
    BudgetStatistics,
    BudgetUpdate,
    BudgetUtilizationResponse,
)
from app.services.budgets import BudgetService, budget_progress_percent
from app.services.finance import BudgetUtilization
from app.services.financial_summary import FinancialSummaryService

router = APIRouter(prefix="/budgets", tags=["Budgets"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
_LEGACY = (
    "DEPRECATED: based on the manually entered `spent` value. "
    "Use GET /budgets/{id}/utilization for spending computed from transactions."
)


def _progress(budget: Budget) -> float:
    return budget_progress_percent(budget.spent, budget.monthly_limit)


def _to_detail(budget: Budget) -> BudgetDetail:
    return BudgetDetail(
        **BudgetResponse.model_validate(budget).model_dump(),
        remaining=budget.monthly_limit - budget.spent,
        progress=_progress(budget),
        is_exceeded=budget.spent > budget.monthly_limit,
    )


@router.post(
    "", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED, responses=_ERRORS
)
async def create_budget(
    payload: BudgetCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Budget:
    budget = await BudgetService(db).create(payload, current_user)
    await db.commit()
    return budget


@router.get("", response_model=BudgetListResponse, responses=_ERRORS)
async def list_budgets(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetListResponse:
    total = await db.scalar(select(func.count(Budget.id)).where(Budget.user_id == current_user.id))
    rows = await db.scalars(
        select(Budget)
        .where(Budget.user_id == current_user.id)
        .order_by(Budget.created_at.desc(), Budget.id.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    return BudgetListResponse(
        items=[BudgetResponse.model_validate(b) for b in rows],
        total=total or 0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


# ---------------------------------------------------------------- legacy (manual `spent`)
async def _default_currency_budgets(db: AsyncSession, user: User) -> list[Budget]:
    rows = await db.scalars(
        select(Budget).where(
            Budget.user_id == user.id, Budget.currency_code == user.default_currency_code
        )
    )
    return list(rows)


@router.get("/statistics", response_model=BudgetStatistics, deprecated=True, description=_LEGACY)
async def get_statistics(
    current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
) -> BudgetStatistics:
    """Totals over budgets in the user's default currency only."""

    budgets = await _default_currency_budgets(db, current_user)
    total_budget = sum((b.monthly_limit for b in budgets), Decimal("0"))
    total_spent = sum((b.spent for b in budgets), Decimal("0"))
    return BudgetStatistics(
        total_budget=total_budget,
        total_spent=total_spent,
        remaining=total_budget - total_spent,
        utilization_percent=budget_progress_percent(total_spent, total_budget),
    )


@router.get("/progress", response_model=list[BudgetProgress], deprecated=True, description=_LEGACY)
async def get_progress(
    current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
) -> list[BudgetProgress]:
    budgets = await db.scalars(select(Budget).where(Budget.user_id == current_user.id))
    return [
        BudgetProgress(
            budget_id=b.id,
            title=b.title,
            monthly_limit=b.monthly_limit,
            spent=b.spent,
            remaining=b.monthly_limit - b.spent,
            progress=_progress(b),
        )
        for b in budgets
    ]


@router.get("/alerts", response_model=list[BudgetAlert], deprecated=True, description=_LEGACY)
async def get_alerts(
    threshold: Decimal = Query(default=Decimal("80"), ge=0, le=1000),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetAlert]:
    """Budgets whose usage reached ``threshold`` % of the limit."""

    alerts: list[BudgetAlert] = []
    for b in await db.scalars(select(Budget).where(Budget.user_id == current_user.id)):
        progress = _progress(b)
        if Decimal(str(progress)) < threshold:
            continue
        message = (
            f"Бюджет «{b.title}» превышен."
            if b.spent > b.monthly_limit
            else f"Бюджет «{b.title}» почти израсходован ({progress:.0f}%)."
        )
        alerts.append(
            BudgetAlert(
                title=b.title,
                spent=b.spent,
                monthly_limit=b.monthly_limit,
                progress=progress,
                message=message,
            )
        )
    return alerts


# ---------------------------------------------------------------- utilization of all budgets
def _utilization_response(
    budget_id: int, first_day: date, result: BudgetUtilization
) -> BudgetUtilizationResponse:
    return BudgetUtilizationResponse(
        budget_id=budget_id,
        month=f"{first_day:%Y-%m}",
        currency_code=result.currency_code,
        limit=result.limit,
        spent=result.spent,
        remaining=result.remaining,
        utilization_percent=result.utilization_percent,
        is_exceeded=result.is_exceeded,
    )


# Declared before ``/{budget_id}`` so "utilization" is not parsed as an id.
@router.get("/utilization", response_model=list[BudgetUtilizationResponse], responses=_ERRORS)
async def list_budget_utilization(
    month: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM; default: current month"
    ),
    tz: ZoneInfo = Depends(get_timezone),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetUtilizationResponse]:
    """Actual utilization of ALL the user's budgets (every currency) for a
    calendar month (local to ``tz``), ordered by budget id. Each item equals
    ``GET /budgets/{id}/utilization`` for the same ``month`` and ``tz``.
    Not paginated: one item per budget of the current user."""

    first_day = parse_month(month, tz)
    results = await FinancialSummaryService(db).all_budget_utilizations(
        current_user.id, first_day, tz
    )
    return [_utilization_response(budget.id, first_day, r) for budget, r in results]


# ---------------------------------------------------------------- single budget
@router.get("/{budget_id}", response_model=BudgetDetail, responses=_ERRORS)
async def get_budget(
    budget_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetDetail:
    return _to_detail(await BudgetService(db).get(budget_id, current_user.id))


@router.get("/{budget_id}/utilization", response_model=BudgetUtilizationResponse, responses=_ERRORS)
async def get_budget_utilization(
    budget_id: int,
    month: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM; default: current month"
    ),
    tz: ZoneInfo = Depends(get_timezone),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetUtilizationResponse:
    """Actual utilization for a calendar month (local to ``tz``), computed from
    transactions: expenses − refunds, in the budget's currency and category."""

    first_day = parse_month(month, tz)
    result = await FinancialSummaryService(db).budget_utilization(
        current_user.id, budget_id, first_day, tz
    )
    return _utilization_response(budget_id, first_day, result)


async def _update(budget_id: int, payload: BudgetUpdate, user: User, db: AsyncSession) -> Budget:
    budget = await BudgetService(db).update(budget_id, payload, user.id)
    await db.commit()
    return budget


@router.patch("/{budget_id}", response_model=BudgetResponse, responses=_ERRORS)
async def patch_budget(
    budget_id: int,
    payload: BudgetUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Budget:
    return await _update(budget_id, payload, current_user, db)


@router.put(
    "/{budget_id}",
    response_model=BudgetResponse,
    responses=_ERRORS,
    description="Same partial-update semantics as PATCH (kept for existing clients).",
)
async def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Budget:
    return await _update(budget_id, payload, current_user, db)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_budget(
    budget_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await BudgetService(db).delete(budget_id, current_user.id)
    await db.commit()
