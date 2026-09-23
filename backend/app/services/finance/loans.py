"""
Кредитные калькуляторы: аннуитет, дифференцированный график,
переплата, остаток, досрочное погашение, ГЭСВ.

Соглашения:
* annual_rate — годовая номинальная ставка в процентах (18.5 = 18.5%).
* Месячная ставка r = annual_rate / 100 / 12.
* Проценты за месяц = остаток * r, округление до тиына.
* Последний платёж корректируется так, чтобы остаток стал ровно 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal, localcontext
from enum import StrEnum

from app.services.finance.calendar import add_months
from app.services.finance.money import (
    HUNDRED,
    ONE,
    ZERO,
    MoneyError,
    quantize_money,
    quantize_percent,
    to_decimal,
)

MAX_TERM_MONTHS = 600
TWELVE = Decimal("12")


class ScheduleType(StrEnum):
    ANNUITY = "annuity"
    DIFFERENTIAL = "differential"


class PrepaymentMode(StrEnum):
    SHORTEN_TERM = "term"
    REDUCE_PAYMENT = "payment"


class LoanError(MoneyError):
    """Некорректные параметры кредита."""


class NonAmortizingLoanError(LoanError):
    """Платёж не покрывает проценты — долг никогда не будет погашен."""


@dataclass(frozen=True, slots=True)
class Installment:
    number: int
    due_date: date | None
    payment: Decimal
    principal: Decimal
    interest: Decimal
    balance_after: Decimal


@dataclass(frozen=True, slots=True)
class LoanSchedule:
    principal: Decimal
    annual_rate: Decimal
    schedule_type: ScheduleType
    installments: tuple[Installment, ...]

    @property
    def term_months(self) -> int:
        return len(self.installments)

    @property
    def total_payment(self) -> Decimal:
        return sum((i.payment for i in self.installments), ZERO)

    @property
    def total_interest(self) -> Decimal:
        return sum((i.interest for i in self.installments), ZERO)

    @property
    def overpayment(self) -> Decimal:
        """Переплата = всё выплаченное сверх тела кредита."""

        return self.total_payment - self.principal

    @property
    def first_payment(self) -> Decimal:
        return self.installments[0].payment if self.installments else ZERO

    @property
    def last_payment(self) -> Decimal:
        return self.installments[-1].payment if self.installments else ZERO

    @property
    def payoff_date(self) -> date | None:
        return self.installments[-1].due_date if self.installments else None

    def balance_after(self, payments_made: int) -> Decimal:
        """Остаток долга после `payments_made` платежей."""

        if payments_made <= 0:
            return self.principal
        if payments_made >= len(self.installments):
            return ZERO
        return self.installments[payments_made - 1].balance_after


def monthly_rate(annual_rate: Decimal | int | str) -> Decimal:
    rate = to_decimal(annual_rate)
    if rate < 0:
        raise LoanError("Interest rate cannot be negative")
    return rate / HUNDRED / TWELVE


def _validate(principal: Decimal, term_months: int) -> None:
    if principal <= 0:
        raise LoanError("Principal must be positive")
    if term_months <= 0:
        raise LoanError("Term must be at least 1 month")
    if term_months > MAX_TERM_MONTHS:
        raise LoanError(f"Term cannot exceed {MAX_TERM_MONTHS} months")


def annuity_payment(principal, annual_rate, term_months: int) -> Decimal:
    """
    A = P * r(1+r)^n / ((1+r)^n - 1), при r = 0: A = P / n.
    Округление вверх не применяется: ROUND_HALF_UP до тиына,
    а разница закрывается последним платежом графика.
    """

    principal = to_decimal(principal)
    _validate(principal, term_months)
    r = monthly_rate(annual_rate)

    with localcontext() as ctx:
        ctx.prec = 40
        if r == 0:
            return quantize_money(principal / term_months)
        growth = (ONE + r) ** term_months
        return quantize_money(principal * r * growth / (growth - ONE))


def _due(start_date: date | None, number: int, payment_day: int | None) -> date | None:
    if start_date is None:
        return None
    return add_months(start_date, number, payment_day)


def build_schedule(
    principal,
    annual_rate,
    term_months: int,
    schedule_type: ScheduleType = ScheduleType.ANNUITY,
    *,
    start_date: date | None = None,
    payment_day: int | None = None,
) -> LoanSchedule:
    """Полный график платежей на term_months месяцев."""

    principal = quantize_money(principal)
    _validate(principal, term_months)
    r = monthly_rate(annual_rate)
    schedule_type = ScheduleType(schedule_type)

    installments: list[Installment] = []
    balance = principal

    if schedule_type is ScheduleType.ANNUITY:
        payment = annuity_payment(principal, annual_rate, term_months)
        for number in range(1, term_months + 1):
            interest = quantize_money(balance * r)
            principal_part = payment - interest
            if number == term_months or principal_part >= balance:
                principal_part = balance
            balance -= principal_part
            installments.append(
                Installment(
                    number=number,
                    due_date=_due(start_date, number, payment_day),
                    payment=principal_part + interest,
                    principal=principal_part,
                    interest=interest,
                    balance_after=balance,
                )
            )
            if balance == 0:
                break
    else:
        base_part = quantize_money(principal / term_months)
        for number in range(1, term_months + 1):
            interest = quantize_money(balance * r)
            principal_part = balance if number == term_months else min(base_part, balance)
            balance -= principal_part
            installments.append(
                Installment(
                    number=number,
                    due_date=_due(start_date, number, payment_day),
                    payment=principal_part + interest,
                    principal=principal_part,
                    interest=interest,
                    balance_after=balance,
                )
            )
            if balance == 0:
                break

    return LoanSchedule(
        principal=principal,
        annual_rate=to_decimal(annual_rate),
        schedule_type=schedule_type,
        installments=tuple(installments),
    )


def schedule_with_fixed_payment(
    balance,
    annual_rate,
    payment,
    *,
    start_date: date | None = None,
    payment_day: int | None = None,
    max_months: int = MAX_TERM_MONTHS,
) -> LoanSchedule:
    """
    График при фиксированном ежемесячном платеже (срок вычисляется).

    Используется для «уменьшить срок» и для долгов, где известен
    только текущий платёж (кредитки, рассрочки, личные долги).
    """

    balance = quantize_money(balance)
    payment = quantize_money(payment)
    if balance <= 0:
        raise LoanError("Balance must be positive")
    if payment <= 0:
        raise LoanError("Payment must be positive")

    r = monthly_rate(annual_rate)
    first_interest = quantize_money(balance * r)
    if payment <= first_interest:
        raise NonAmortizingLoanError(
            "Monthly payment does not cover accrued interest",
        )

    installments: list[Installment] = []
    remaining = balance
    number = 0
    while remaining > 0:
        number += 1
        if number > max_months:
            raise NonAmortizingLoanError(
                f"Loan is not repaid within {max_months} months"
            )
        interest = quantize_money(remaining * r)
        principal_part = min(payment - interest, remaining)
        remaining -= principal_part
        installments.append(
            Installment(
                number=number,
                due_date=_due(start_date, number, payment_day),
                payment=principal_part + interest,
                principal=principal_part,
                interest=interest,
                balance_after=remaining,
            )
        )

    return LoanSchedule(
        principal=balance,
        annual_rate=to_decimal(annual_rate),
        schedule_type=ScheduleType.ANNUITY,
        installments=tuple(installments),
    )


def months_to_payoff(balance, annual_rate, payment) -> int:
    return schedule_with_fixed_payment(balance, annual_rate, payment).term_months


@dataclass(frozen=True, slots=True)
class PrepaymentResult:
    mode: PrepaymentMode
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    payment_before: Decimal
    payment_after: Decimal
    term_before: int
    term_after: int
    interest_before: Decimal
    interest_after: Decimal
    fully_repaid: bool
    schedule_after: LoanSchedule | None = field(repr=False, default=None)

    @property
    def interest_saved(self) -> Decimal:
        return self.interest_before - self.interest_after

    @property
    def months_saved(self) -> int:
        return self.term_before - self.term_after

    @property
    def payment_reduced_by(self) -> Decimal:
        return self.payment_before - self.payment_after


def apply_prepayment(
    balance,
    annual_rate,
    remaining_term_months: int,
    amount,
    mode: PrepaymentMode = PrepaymentMode.SHORTEN_TERM,
    schedule_type: ScheduleType = ScheduleType.ANNUITY,
    *,
    start_date: date | None = None,
    payment_day: int | None = None,
) -> PrepaymentResult:
    """
    Частично-досрочное погашение суммой `amount` прямо сейчас.

    SHORTEN_TERM — платёж прежний, срок сокращается.
    REDUCE_PAYMENT — срок прежний, платёж пересчитывается.
    Если amount >= balance — долг закрывается полностью.
    """

    balance = quantize_money(balance)
    amount = quantize_money(amount)
    mode = PrepaymentMode(mode)
    schedule_type = ScheduleType(schedule_type)
    if amount <= 0:
        raise LoanError("Prepayment amount must be positive")

    before = build_schedule(
        balance,
        annual_rate,
        remaining_term_months,
        schedule_type,
        start_date=start_date,
        payment_day=payment_day,
    )

    if amount >= balance:
        return PrepaymentResult(
            mode=mode,
            amount=balance,
            balance_before=balance,
            balance_after=ZERO,
            payment_before=before.first_payment,
            payment_after=ZERO,
            term_before=before.term_months,
            term_after=0,
            interest_before=before.total_interest,
            interest_after=ZERO,
            fully_repaid=True,
            schedule_after=None,
        )

    new_balance = balance - amount

    if mode is PrepaymentMode.REDUCE_PAYMENT:
        after = build_schedule(
            new_balance,
            annual_rate,
            remaining_term_months,
            schedule_type,
            start_date=start_date,
            payment_day=payment_day,
        )
    elif schedule_type is ScheduleType.ANNUITY:
        after = schedule_with_fixed_payment(
            new_balance,
            annual_rate,
            before.first_payment,
            start_date=start_date,
            payment_day=payment_day,
        )
    else:
        # Дифференцированный: тело платежа прежнее, месяцев меньше.
        base_part = before.installments[0].principal
        months = int((new_balance / base_part).to_integral_value(rounding=ROUND_CEILING))
        after = build_schedule(
            new_balance,
            annual_rate,
            months,
            schedule_type,
            start_date=start_date,
            payment_day=payment_day,
        )

    return PrepaymentResult(
        mode=mode,
        amount=amount,
        balance_before=balance,
        balance_after=new_balance,
        payment_before=before.first_payment,
        payment_after=after.first_payment,
        term_before=before.term_months,
        term_after=after.term_months,
        interest_before=before.total_interest,
        interest_after=after.total_interest,
        fully_repaid=False,
        schedule_after=after,
    )


def effective_annual_rate(
    principal,
    payments: list[Decimal] | tuple[Decimal, ...],
    *,
    upfront_fees=ZERO,
    monthly_fee=ZERO,
) -> Decimal:
    """
    Годовая эффективная ставка (аналог ГЭСВ) в процентах.

    Находит месячную IRR потока: заёмщик получает principal - upfront_fees,
    платит payments[k] + monthly_fee в конце каждого месяца k.
    Годовая ставка = (1 + i)^12 - 1.

    Это приближение на месячных периодах; официальная формула НБРК
    считает по фактическим дням. Для сравнения предложений между
    собой (где все считаются одинаково) приближение корректно.
    """

    principal = to_decimal(principal)
    fees = to_decimal(upfront_fees)
    monthly_fee = to_decimal(monthly_fee)
    net = principal - fees
    if net <= 0:
        raise LoanError("Net amount received must be positive")
    if not payments:
        raise LoanError("Payments are required")
    flows = [to_decimal(p) + monthly_fee for p in payments]

    with localcontext() as ctx:
        ctx.prec = 40

        def npv(i: Decimal) -> Decimal:
            factor = ONE / (ONE + i)
            discount = ONE
            total = ZERO
            for flow in flows:
                discount *= factor
                total += flow * discount
            return total - net

        low, high = Decimal("-0.99"), Decimal("1")
        while npv(high) > 0:
            high *= 2
            if high > 1000:
                raise LoanError("Effective rate is out of range")

        for _ in range(200):
            mid = (low + high) / 2
            if npv(mid) > 0:
                low = mid
            else:
                high = mid
            if high - low < Decimal("1e-15"):
                break

        monthly = (low + high) / 2
        annual = ((ONE + monthly) ** 12 - ONE) * HUNDRED
        return quantize_percent(annual)


def schedule_gesv(schedule: LoanSchedule, *, upfront_fees=ZERO, monthly_fee=ZERO) -> Decimal:
    return effective_annual_rate(
        schedule.principal,
        [i.payment for i in schedule.installments],
        upfront_fees=upfront_fees,
        monthly_fee=monthly_fee,
    )
