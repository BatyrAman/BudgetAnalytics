from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ERROR_RESPONSES
from app.schemas.finance import (
    AffordabilityRequest,
    AffordabilityResponse,
    DepositCalcRequest,
    DepositCalcResponse,
    EmergencyFundRequest,
    EmergencyFundResponse,
    FinancialProfileSummary,
    LoanCalcRequest,
    LoanCalcResponse,
    MortgageCalcRequest,
    MortgageCalcResponse,
)
from app.services.calculators import CalculatorService

router = APIRouter(prefix="/finance", tags=["Finance calculators"], responses=ERROR_RESPONSES)


@router.get("/profile", response_model=FinancialProfileSummary)
async def get_financial_profile(user: CurrentUser, db: DbSession):
    """Агрегаты доходов/расходов/долгов за последние 6 полных месяцев (без ПДн)."""

    return await CalculatorService(db).profile_summary(user)


@router.post("/loan", response_model=LoanCalcResponse)
async def calculate_loan(payload: LoanCalcRequest, _: CurrentUser):
    """Платёж, переплата и эффективная ставка (аналог ГЭСВ) кредита."""

    return CalculatorService().loan(payload)


@router.post("/mortgage", response_model=MortgageCalcResponse)
async def calculate_mortgage(payload: MortgageCalcRequest, user: CurrentUser, db: DbSession):
    """Ипотека: платёж, переплата и доход, нужный с учётом текущих долгов."""

    return await CalculatorService(db).mortgage(user, payload)


@router.post("/deposit", response_model=DepositCalcResponse)
async def calculate_deposit(payload: DepositCalcRequest, _: CurrentUser):
    return CalculatorService().deposit(payload)


@router.post("/affordability", response_model=AffordabilityResponse)
async def calculate_affordability(payload: AffordabilityRequest, user: CurrentUser, db: DbSession):
    """
    Потянет ли пользователь новый платёж. Риск и лимит платежа
    определяет детерминированный AffordabilityService.
    """

    return await CalculatorService(db).affordability(user, payload)


@router.post("/emergency-fund", response_model=EmergencyFundResponse)
async def calculate_emergency_fund(payload: EmergencyFundRequest, user: CurrentUser, db: DbSession):
    return await CalculatorService(db).emergency_fund(user, payload)
