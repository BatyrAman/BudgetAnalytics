"""
Application-сервис калькуляторов: валидирует вход, вызывает чистые
функции finance/* и собирает ответы. Ошибки домена → 422 с кодом.
"""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainValidationError
from app.models.user import User
from app.schemas.debt import InstallmentResponse
from app.schemas.finance import (
    AffordabilityReason,
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
from app.services.finance.affordability import AffordabilityInput, AffordabilityService
from app.services.finance.deposits import calculate_deposit
from app.services.finance.emergency_fund import calculate_emergency_fund
from app.services.finance.loans import LoanSchedule, build_schedule, schedule_gesv
from app.services.finance.money import ZERO, MoneyError
from app.services.finance.mortgages import calculate_mortgage
from app.services.profile import FinancialProfile, FinancialProfileService


def _installments(schedule: LoanSchedule) -> list[InstallmentResponse]:
    return [InstallmentResponse(**asdict(i)) for i in schedule.installments]


def _domain_error(exc: MoneyError) -> DomainValidationError:
    return DomainValidationError(str(exc), code="INVALID_CALCULATION_INPUT")


class CalculatorService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def profile(self, user: User) -> FinancialProfile:
        return await FinancialProfileService(self.session).build(user)

    async def profile_summary(self, user: User) -> FinancialProfileSummary:
        return FinancialProfileSummary(**asdict(await self.profile(user)))

    def loan(self, request: LoanCalcRequest) -> LoanCalcResponse:
        try:
            schedule = build_schedule(
                request.amount,
                request.annual_rate,
                request.term_months,
                request.schedule_type,
                start_date=request.start_date,
            )
            effective = schedule_gesv(
                schedule, upfront_fees=request.upfront_fees, monthly_fee=request.monthly_fee
            )
        except MoneyError as exc:
            raise _domain_error(exc) from exc
        fees = request.upfront_fees + request.monthly_fee * schedule.term_months
        return LoanCalcResponse(
            amount=schedule.principal,
            annual_rate=request.annual_rate,
            term_months=schedule.term_months,
            schedule_type=schedule.schedule_type,
            monthly_payment=schedule.first_payment,
            last_payment=schedule.last_payment,
            total_payment=schedule.total_payment + fees,
            total_interest=schedule.total_interest,
            total_fees=fees,
            overpayment=schedule.overpayment + fees,
            effective_annual_rate=effective,
            schedule=_installments(schedule) if request.include_schedule else [],
        )

    async def mortgage(self, user: User | None, request: MortgageCalcRequest) -> MortgageCalcResponse:
        existing = ZERO
        if user is not None and self.session is not None:
            existing = (await self.profile(user)).debt_payments
        try:
            result = calculate_mortgage(
                request.price,
                request.down_payment,
                request.annual_rate,
                request.term_years,
                request.schedule_type,
                existing_debt_payments=existing,
            )
        except MoneyError as exc:
            raise _domain_error(exc) from exc
        return MortgageCalcResponse(
            price=result.price,
            down_payment=result.down_payment,
            down_payment_percent=result.down_payment_percent,
            loan_amount=result.loan_amount,
            annual_rate=result.annual_rate,
            term_months=result.term_months,
            schedule_type=result.schedule_type,
            monthly_payment=result.monthly_payment,
            max_monthly_payment=result.max_monthly_payment,
            total_payment=result.total_payment,
            total_interest=result.total_interest,
            overpayment=result.overpayment,
            required_monthly_income=result.required_monthly_income,
            existing_debt_payments=existing,
            schedule=_installments(result.schedule) if request.include_schedule else [],
        )

    def deposit(self, request: DepositCalcRequest) -> DepositCalcResponse:
        try:
            result = calculate_deposit(
                request.amount,
                request.annual_rate,
                request.term_months,
                request.capitalization,
                monthly_topup=request.monthly_topup,
            )
        except MoneyError as exc:
            raise _domain_error(exc) from exc
        data = asdict(result)
        data.pop("months")
        return DepositCalcResponse(**data)

    async def affordability(self, user: User, request: AffordabilityRequest) -> AffordabilityResponse:
        profile = await self.profile(user)
        sources: dict[str, str] = {}

        def pick(name: str, requested, fallback, fallback_source: str):
            if requested is not None:
                sources[name] = "request"
                return requested
            sources[name] = fallback_source
            return fallback

        income = pick(
            "monthly_income",
            request.monthly_income,
            profile.monthly_income if profile.monthly_income is not None else ZERO,
            profile.income_source,
        )
        mandatory = pick(
            "mandatory_expenses",
            request.mandatory_expenses,
            profile.mandatory_expenses,
            "transactions" if profile.months_of_data else "none",
        )
        existing = pick("existing_debt_payments", request.existing_debt_payments, profile.debt_payments, "debts")

        if request.loan is not None:
            try:
                schedule = build_schedule(
                    request.loan.amount,
                    request.loan.annual_rate,
                    request.loan.term_months,
                    request.loan.schedule_type,
                )
            except MoneyError as exc:
                raise _domain_error(exc) from exc
            # Для дифференцированного графика проверяем самый большой (первый) платёж.
            new_payment = max(i.payment for i in schedule.installments)
            sources["new_payment"] = "loan"
        else:
            new_payment = request.new_payment
            sources["new_payment"] = "request"

        result = AffordabilityService().assess(
            AffordabilityInput(income, mandatory, existing, new_payment)
        )
        return AffordabilityResponse(
            affordable=result.affordable,
            risk_level=result.risk_level,
            current_debt_load=result.current_debt_load,
            projected_debt_load=result.projected_debt_load,
            free_cash_flow=result.free_cash_flow,
            free_cash_flow_after=result.free_cash_flow_after,
            recommended_max_payment=result.recommended_max_payment,
            new_payment=result.new_payment,
            monthly_income=result.monthly_income,
            mandatory_expenses=result.mandatory_expenses,
            existing_debt_payments=result.existing_debt_payments,
            reasons=[AffordabilityReason(code=r.code, message=r.message) for r in result.reasons],
            sources=sources,
        )

    async def emergency_fund(self, user: User, request: EmergencyFundRequest) -> EmergencyFundResponse:
        expenses = request.monthly_mandatory_expenses
        dependents = 0
        if expenses is None or user is not None:
            profile = await self.profile(user)
            dependents = profile.dependents
            if expenses is None:
                expenses = profile.mandatory_expenses
        try:
            result = calculate_emergency_fund(
                expenses,
                request.current_savings,
                request.monthly_contribution,
                target_months=request.target_months,
                dependents=dependents,
                income_stability=request.income_stability,
            )
        except MoneyError as exc:
            raise _domain_error(exc) from exc
        return EmergencyFundResponse(**asdict(result))
