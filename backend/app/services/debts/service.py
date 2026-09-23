from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models.debt import Debt, DebtPayment
from app.models.enums import DebtPaymentStatus, DebtScheduleType, TransactionType
from app.models.user import User
from app.repositories.banks import BankRepository
from app.repositories.debts import DebtPaymentRepository, DebtRepository
from app.repositories.transactions import TransactionRepository
from app.schemas.debt import (
    DebtCreate,
    DebtPaymentCreate,
    DebtResponse,
    DebtScheduleResponse,
    DebtSummary,
    DebtTypeTotal,
    DebtUpdate,
    InstallmentResponse,
    PayoffItem,
    PrepaymentRequest,
    PrepaymentResponse,
    StrategyOutcome,
    StrategyRequest,
    StrategyResponse,
    TimelinePoint,
    UpcomingPayment,
)
from app.services.debts.projection import initial_payment, project, schedule_anchor, to_strategy_input
from app.services.finance.affordability import AffordabilityPolicy, RiskLevel
from app.services.finance.calendar import add_months, count_payment_dates, next_payment_date
from app.services.finance.debt_strategy import Strategy, compare_strategies, simulate
from app.services.finance.loans import (
    LoanError,
    PrepaymentMode,
    ScheduleType,
    apply_prepayment,
    monthly_rate,
)
from app.services.finance.money import ZERO, percent, percent_or_zero, quantize_money
from app.services.profile import FinancialProfileService


def nearest_due_date(paid_at: date, payment_day: int) -> date:
    """Плановая дата платежа, ближайшая к фактической дате оплаты."""

    upcoming = next_payment_date(paid_at, payment_day)
    previous = add_months(upcoming, -1, payment_day)
    return previous if (paid_at - previous) < (upcoming - paid_at) else upcoming


class DebtService:
    def __init__(self, session: AsyncSession, today: date | None = None) -> None:
        self.session = session
        self.repo = DebtRepository(session)
        self.payments = DebtPaymentRepository(session)
        self.banks = BankRepository(session)
        self.transactions = TransactionRepository(session)
        self.today = today or date.today()

    # ------------------------------------------------------------------ CRUD

    async def _get_owned(self, debt_id: int, user_id: int) -> Debt:
        debt = await self.repo.get_owned(debt_id, user_id)
        if debt is None:
            raise NotFoundError("Debt not found", code="DEBT_NOT_FOUND")
        return debt

    async def _responses(self, user_id: int, debts: list[Debt]) -> list[DebtResponse]:
        interest_paid = await self.repo.interest_paid(user_id, [d.id for d in debts])
        return [self._response(d, Decimal(interest_paid.get(d.id) or 0)) for d in debts]

    def _response(self, debt: Debt, interest_paid: Decimal) -> DebtResponse:
        schedule = project(debt, self.today) if debt.is_active else None
        amortizing = debt.balance == 0 or schedule is not None
        remaining_interest = schedule.total_interest if schedule else (ZERO if debt.balance == 0 else None)
        return DebtResponse(
            id=debt.id,
            name=debt.name,
            debt_type=debt.debt_type,
            bank_id=debt.bank_id,
            principal=debt.principal,
            balance=debt.balance,
            annual_rate=debt.annual_rate,
            gesv=debt.gesv,
            monthly_payment=debt.monthly_payment,
            payment_day=debt.payment_day,
            start_date=debt.start_date,
            end_date=debt.end_date,
            schedule_type=debt.schedule_type,
            currency=debt.currency,
            is_active=debt.is_active,
            closed_at=debt.closed_at,
            created_at=debt.created_at,
            paid_percent=max(percent_or_zero(debt.principal - debt.balance, debt.principal), ZERO),
            interest_paid=interest_paid,
            projected_months_left=schedule.term_months if schedule else (0 if debt.balance == 0 else None),
            projected_payoff_date=schedule.payoff_date if schedule else None,
            projected_remaining_interest=remaining_interest,
            projected_total_overpayment=(
                interest_paid + remaining_interest if remaining_interest is not None else None
            ),
            is_amortizing=amortizing,
        )

    async def list(self, user_id: int, include_closed: bool = False) -> list[DebtResponse]:
        conditions = [] if include_closed else [Debt.is_active.is_(True)]
        debts = await self.repo.list_owned(user_id, *conditions, order_by=(Debt.annual_rate.desc(), Debt.id))
        return await self._responses(user_id, debts)

    async def get(self, debt_id: int, user_id: int) -> DebtResponse:
        return (await self._responses(user_id, [await self._get_owned(debt_id, user_id)]))[0]

    async def create(self, user_id: int, payload: DebtCreate) -> DebtResponse:
        if payload.bank_id is not None and await self.banks.get(payload.bank_id) is None:
            raise AppError("Bank not found", code="BANK_NOT_FOUND")

        balance = payload.balance if payload.balance is not None else payload.principal
        end_date = payload.end_date
        if end_date is None and payload.term_months is not None:
            end_date = add_months(payload.start_date, payload.term_months, payload.payment_day)

        monthly_payment = payload.monthly_payment
        if monthly_payment is None:
            remaining = max(count_payment_dates(self.today, end_date, payload.payment_day), 1)
            if balance > 0:
                try:
                    monthly_payment = initial_payment(balance, payload.annual_rate, payload.schedule_type, remaining)
                except LoanError as exc:
                    raise AppError(str(exc), code="INVALID_DEBT_PARAMETERS") from exc
            else:
                monthly_payment = ZERO

        debt = self.repo.add(
            Debt(
                user_id=user_id,
                bank_id=payload.bank_id,
                name=payload.name,
                debt_type=payload.debt_type,
                principal=payload.principal,
                balance=balance,
                annual_rate=payload.annual_rate,
                gesv=payload.gesv,
                monthly_payment=monthly_payment,
                payment_day=payload.payment_day,
                start_date=payload.start_date,
                end_date=end_date,
                schedule_type=payload.schedule_type,
                currency=settings.DEFAULT_CURRENCY,
                is_active=balance > 0,
                closed_at=None if balance > 0 else datetime.now(timezone.utc),
            )
        )
        await self.session.commit()
        await self.session.refresh(debt)
        return (await self._responses(user_id, [debt]))[0]

    async def update(self, debt_id: int, user_id: int, payload: DebtUpdate) -> DebtResponse:
        debt = await self._get_owned(debt_id, user_id)
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None or k in ("gesv", "end_date", "bank_id")}
        if updates.get("bank_id") is not None and await self.banks.get(updates["bank_id"]) is None:
            raise AppError("Bank not found", code="BANK_NOT_FOUND")
        if updates.get("end_date") is not None and updates["end_date"] <= debt.start_date:
            raise AppError("end_date must be after start_date", code="INVALID_DATE_RANGE")
        for field, value in updates.items():
            setattr(debt, field, value)
        self._sync_closed(debt)
        await self.session.commit()
        await self.session.refresh(debt)
        return (await self._responses(user_id, [debt]))[0]

    @staticmethod
    def _sync_closed(debt: Debt) -> None:
        if debt.balance == 0 and debt.is_active:
            debt.is_active = False
        if not debt.is_active and debt.closed_at is None:
            debt.closed_at = datetime.now(timezone.utc)
        if debt.is_active:
            debt.closed_at = None

    async def delete(self, debt_id: int, user_id: int) -> None:
        debt = await self._get_owned(debt_id, user_id)
        await self.repo.delete(debt)
        await self.session.commit()

    # ------------------------------------------------------------- analytics

    async def summary(self, user: User) -> DebtSummary:
        debts = await self.repo.list_active(user.id)
        profile = await FinancialProfileService(self.session, self.today).build(user)
        total_payment = sum((d.monthly_payment for d in debts), ZERO)

        debt_load = percent(total_payment, profile.monthly_income) if profile.monthly_income else None
        level = None
        if debt_load is not None:
            policy = AffordabilityPolicy()
            ratio = debt_load / 100
            level = (
                RiskLevel.LOW if ratio <= policy.comfortable_dti
                else RiskLevel.MODERATE if ratio <= policy.max_dti
                else RiskLevel.HIGH if ratio < policy.critical_dti
                else RiskLevel.CRITICAL
            )

        freedom = simulate(
            [to_strategy_input(d) for d in debts],
            ZERO,
            None,
            start_date=self.today,
            rollover=False,
        ) if debts else None

        by_type: dict = defaultdict(lambda: [0, ZERO])
        for d in debts:
            by_type[d.debt_type][0] += 1
            by_type[d.debt_type][1] += d.balance

        upcoming = await self.calendar(user.id, 45)
        next_payment = next((p for p in upcoming if not p.is_paid), None)

        return DebtSummary(
            currency=settings.DEFAULT_CURRENCY,
            active_debts=len(debts),
            total_balance=sum((d.balance for d in debts), ZERO),
            total_monthly_payment=total_payment,
            monthly_income=profile.monthly_income,
            income_source=profile.income_source,
            debt_load=debt_load,
            debt_load_level=level,
            debt_free_date=freedom.payoff_date if freedom and freedom.feasible else None,
            months_to_debt_free=(freedom.months if freedom and freedom.feasible else (0 if not debts else None)),
            total_remaining_interest=(freedom.total_interest if freedom and freedom.feasible else (ZERO if not debts else None)),
            payments_cover_interest=freedom.feasible if freedom else True,
            by_type=[
                DebtTypeTotal(debt_type=t, count=count, balance=balance)
                for t, (count, balance) in sorted(by_type.items(), key=lambda kv: kv[0].value)
            ],
            next_payment=next_payment,
        )

    async def calendar(self, user_id: int, days: int) -> list[UpcomingPayment]:
        debts = await self.repo.list_active(user_id)
        horizon = self.today + timedelta(days=days)
        paid = await self.payments.paid_due_dates(user_id, self.today - timedelta(days=31), horizon)

        items: list[UpcomingPayment] = []
        for debt in debts:
            balance = debt.balance
            r = monthly_rate(debt.annual_rate)
            due = next_payment_date(self.today, debt.payment_day)
            step = 0
            while due <= horizon and balance > 0:
                interest = quantize_money(balance * r)
                amount = min(debt.monthly_payment, balance + interest)
                if amount <= 0:
                    break
                items.append(
                    UpcomingPayment(
                        debt_id=debt.id,
                        name=debt.name,
                        debt_type=debt.debt_type,
                        due_date=due,
                        amount=amount,
                        days_left=(due - self.today).days,
                        is_paid=(debt.id, due) in paid,
                    )
                )
                balance = max(balance + interest - amount, ZERO)
                step += 1
                due = add_months(next_payment_date(self.today, debt.payment_day), step, debt.payment_day)
        return sorted(items, key=lambda i: (i.due_date, i.debt_id))

    async def strategy(self, user_id: int, request: StrategyRequest) -> StrategyResponse:
        debts = await self.repo.list_active(user_id)
        if not debts:
            raise AppError("No active debts to simulate", code="NO_ACTIVE_DEBTS", status_code=422)

        inputs = [to_strategy_input(d) for d in debts]
        comparison = compare_strategies(inputs, request.extra_payment, start_date=self.today)
        chosen = comparison.results[request.strategy]

        def outcome(result, strategy: Strategy | None) -> StrategyOutcome:
            return StrategyOutcome(
                strategy=strategy,
                feasible=result.feasible,
                months=result.months,
                payoff_date=result.payoff_date,
                total_interest=result.total_interest,
                total_paid=result.total_paid,
                interest_saved_vs_minimum=(
                    comparison.interest_saved(strategy)
                    if strategy is not None and comparison.baseline.feasible and result.feasible
                    else None
                ),
                extra_cost_vs_recommended=(
                    comparison.cost_vs_recommended(strategy) if strategy is not None else None
                ),
            )

        return StrategyResponse(
            strategy=request.strategy,
            extra_payment=chosen.extra_payment,
            monthly_budget=chosen.monthly_budget,
            feasible=chosen.feasible,
            reason=chosen.reason,
            months=chosen.months,
            payoff_date=chosen.payoff_date,
            total_interest=chosen.total_interest,
            total_paid=chosen.total_paid,
            payoff_order=[
                PayoffItem(
                    debt_id=int(p.id),
                    name=p.name,
                    month=p.month,
                    date=p.date,
                    interest_paid=p.interest_paid,
                    total_paid=p.total_paid,
                )
                for p in chosen.payoff_order
            ],
            timeline=[
                TimelinePoint(
                    month=s.month,
                    date=s.date,
                    total_balance=s.total_balance,
                    interest=s.interest,
                    payment=s.payment,
                    balances=s.balances,
                    payments=s.payments,
                )
                for s in chosen.timeline
            ]
            if request.include_timeline
            else [],
            recommended_strategy=comparison.recommended,
            minimum_payments_only=outcome(comparison.baseline, None),
            comparison=[outcome(comparison.results[s], s) for s in Strategy],
        )

    async def schedule(self, debt_id: int, user_id: int) -> DebtScheduleResponse:
        debt = await self._get_owned(debt_id, user_id)
        schedule = project(debt, self.today)
        if schedule is None:
            return DebtScheduleResponse(
                debt_id=debt.id,
                is_amortizing=debt.balance == 0,
                months=0,
                total_payment=ZERO,
                total_interest=ZERO,
                installments=[],
            )
        return DebtScheduleResponse(
            debt_id=debt.id,
            is_amortizing=True,
            months=schedule.term_months,
            total_payment=schedule.total_payment,
            total_interest=schedule.total_interest,
            installments=[
                InstallmentResponse(
                    number=i.number,
                    due_date=i.due_date,
                    payment=i.payment,
                    principal=i.principal,
                    interest=i.interest,
                    balance_after=i.balance_after,
                )
                for i in schedule.installments
            ],
        )

    async def prepayment(self, debt_id: int, user_id: int, request: PrepaymentRequest) -> PrepaymentResponse:
        debt = await self._get_owned(debt_id, user_id)
        if debt.balance <= 0:
            raise AppError("Debt is already repaid", code="DEBT_CLOSED")
        if debt.schedule_type == DebtScheduleType.REVOLVING and request.mode is PrepaymentMode.REDUCE_PAYMENT:
            raise AppError(
                "Reduce-payment mode is not available for revolving debts",
                code="PREPAYMENT_MODE_UNSUPPORTED",
            )
        baseline = project(debt, self.today)
        if baseline is None:
            raise AppError(
                "Current payment does not cover interest; prepayment projection is impossible",
                code="DEBT_NOT_AMORTIZING",
                status_code=422,
            )
        schedule_type = (
            ScheduleType.DIFFERENTIAL
            if debt.schedule_type == DebtScheduleType.DIFFERENTIAL
            else ScheduleType.ANNUITY
        )
        anchor = schedule_anchor(debt, self.today)
        try:
            result = apply_prepayment(
                debt.balance,
                debt.annual_rate,
                baseline.term_months,
                request.amount,
                request.mode,
                schedule_type,
                start_date=anchor,
                payment_day=debt.payment_day,
            )
        except LoanError as exc:
            raise AppError(str(exc), code="INVALID_PREPAYMENT") from exc

        before_end = add_months(anchor, result.term_before, debt.payment_day)
        after_end = (
            add_months(anchor, result.term_after, debt.payment_day) if result.term_after else self.today
        )
        return PrepaymentResponse(
            debt_id=debt.id,
            mode=result.mode,
            amount=result.amount,
            fully_repaid=result.fully_repaid,
            balance_before=result.balance_before,
            balance_after=result.balance_after,
            payment_before=result.payment_before,
            payment_after=result.payment_after,
            term_before=result.term_before,
            term_after=result.term_after,
            payoff_date_before=before_end,
            payoff_date_after=after_end,
            interest_before=result.interest_before,
            interest_after=result.interest_after,
            interest_saved=result.interest_saved,
            months_saved=result.months_saved,
            payment_reduced_by=result.payment_reduced_by,
        )

    # --------------------------------------------------------------- payments

    async def list_payments(self, debt_id: int, user_id: int) -> list[DebtPayment]:
        await self._get_owned(debt_id, user_id)
        return await self.payments.for_debt(user_id, debt_id)

    async def record_payment(self, debt_id: int, user_id: int, payload: DebtPaymentCreate) -> DebtPayment:
        debt = await self._get_owned(debt_id, user_id)
        if not debt.is_active or debt.balance <= 0:
            raise AppError("Debt is already repaid", code="DEBT_CLOSED")

        if payload.transaction_id is not None:
            transaction = await self.transactions.get_owned(payload.transaction_id, user_id)
            if transaction is None:
                raise AppError("Transaction not found", code="TRANSACTION_NOT_FOUND")
            if transaction.transaction_type != TransactionType.EXPENSE:
                raise AppError("Only an expense can repay a debt", code="TRANSACTION_TYPE_MISMATCH")

        interest = min(quantize_money(debt.balance * monthly_rate(debt.annual_rate)), payload.amount)
        principal = payload.amount - interest
        if principal > debt.balance:
            raise AppError(
                "Payment exceeds the outstanding balance",
                code="PAYMENT_EXCEEDS_BALANCE",
                details={"max_amount": format(debt.balance + interest, "f")},
            )

        paid_at = payload.paid_at or self.today
        payment = self.payments.add(
            DebtPayment(
                debt_id=debt.id,
                user_id=user_id,
                due_date=payload.due_date or nearest_due_date(paid_at, debt.payment_day),
                amount=payload.amount,
                principal_part=principal,
                interest_part=interest,
                paid_at=paid_at,
                status=DebtPaymentStatus.PAID,
                transaction_id=payload.transaction_id,
            )
        )
        debt.balance -= principal
        self._sync_closed(debt)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if "uq_debt_payments_transaction_id" in str(exc.orig):
                raise ConflictError(
                    "This transaction is already linked to a debt payment",
                    code="TRANSACTION_ALREADY_LINKED",
                ) from exc
            raise
        await self.session.refresh(payment)
        return payment

    async def reverse_payment(self, debt_id: int, payment_id: int, user_id: int) -> None:
        debt = await self._get_owned(debt_id, user_id)
        payment = await self.payments.get_owned(payment_id, user_id)
        if payment is None or payment.debt_id != debt.id:
            raise NotFoundError("Payment not found", code="DEBT_PAYMENT_NOT_FOUND")
        if payment.status == DebtPaymentStatus.REVERSED:
            return
        payment.status = DebtPaymentStatus.REVERSED
        debt.balance += payment.principal_part
        debt.is_active = True
        self._sync_closed(debt)
        await self.session.commit()
