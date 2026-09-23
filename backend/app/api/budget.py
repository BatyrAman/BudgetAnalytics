from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PaginationParams, get_current_active_user, get_db
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
)

router = APIRouter(prefix="/budgets", tags=["Budgets"])


def _progress(budget: Budget) -> float:
    if budget.monthly_limit <= 0:
        return 0.0
    return float(round((budget.spent / budget.monthly_limit) * 100, 2))


def _to_detail(budget: Budget) -> BudgetDetail:
    remaining = budget.monthly_limit - budget.spent
    progress = _progress(budget)

    return BudgetDetail(
        **BudgetResponse.model_validate(budget).model_dump(),
        remaining=remaining,
        progress=progress,
        is_exceeded=budget.spent > budget.monthly_limit,
    )


async def _get_owned_budget(
    db: AsyncSession,
    budget_id: int,
    user_id: int,
) -> Budget:

    budget = await db.scalar(
        select(Budget).where(
            Budget.id == budget_id,
            Budget.user_id == user_id,
        )
    )

    if budget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )

    return budget


@router.post(
    "",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_budget(
    payload: BudgetCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Budget:

    budget = Budget(
        title=payload.title,
        monthly_limit=payload.monthly_limit,
        spent=Decimal("0"),
        user_id=current_user.id,
    )

    db.add(budget)
    await db.commit()
    await db.refresh(budget)

    return budget


@router.get(
    "",
    response_model=BudgetListResponse,
)
async def list_budgets(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetListResponse:

    total = await db.scalar(
        select(func.count(Budget.id)).where(Budget.user_id == current_user.id)
    )

    result = await db.execute(
        select(Budget)
        .where(Budget.user_id == current_user.id)
        .order_by(Budget.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )

    return BudgetListResponse(items=result.scalars().all(), total=total or 0)


@router.get(
    "/statistics",
    response_model=BudgetStatistics,
)
async def get_statistics(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetStatistics:

    result = await db.execute(
        select(Budget).where(Budget.user_id == current_user.id)
    )
    budgets = result.scalars().all()

    total_budget = sum((b.monthly_limit for b in budgets), Decimal("0"))
    total_spent = sum((b.spent for b in budgets), Decimal("0"))
    remaining = total_budget - total_spent

    utilization = (
        float(round((total_spent / total_budget) * 100, 2))
        if total_budget > 0
        else 0.0
    )

    return BudgetStatistics(
        total_budget=total_budget,
        total_spent=total_spent,
        remaining=remaining,
        utilization_percent=utilization,
    )


@router.get(
    "/progress",
    response_model=list[BudgetProgress],
)
async def get_progress(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetProgress]:

    result = await db.execute(
        select(Budget).where(Budget.user_id == current_user.id)
    )
    budgets = result.scalars().all()

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


@router.get(
    "/alerts",
    response_model=list[BudgetAlert],
)
async def get_alerts(
    threshold: float = 80.0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetAlert]:
    """
    Бюджеты, использование которых превысило `threshold` % от лимита.
    """

    result = await db.execute(
        select(Budget).where(Budget.user_id == current_user.id)
    )
    budgets = result.scalars().all()

    alerts: list[BudgetAlert] = []

    for b in budgets:
        progress = _progress(b)

        if progress < threshold:
            continue

        if b.spent > b.monthly_limit:
            message = f"Бюджет «{b.title}» превышен."
        else:
            message = f"Бюджет «{b.title}» почти израсходован ({progress:.0f}%)."

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


@router.get(
    "/{budget_id}",
    response_model=BudgetDetail,
)
async def get_budget(
    budget_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetDetail:

    budget = await _get_owned_budget(db, budget_id, current_user.id)
    return _to_detail(budget)


@router.put(
    "/{budget_id}",
    response_model=BudgetResponse,
)
async def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Budget:

    budget = await _get_owned_budget(db, budget_id, current_user.id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(budget, field, value)

    db.add(budget)
    await db.commit()
    await db.refresh(budget)

    return budget


@router.delete(
    "/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_budget(
    budget_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:

    budget = await _get_owned_budget(db, budget_id, current_user.id)

    await db.delete(budget)
    await db.commit()
