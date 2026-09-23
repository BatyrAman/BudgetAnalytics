"""
Стратегии погашения долгов с помесячной симуляцией.

Каждый месяц:
  1. начислить проценты по всем открытым долгам;
  2. внести минимальные платежи;
  3. остаток бюджета (extra + освободившиеся платежи) направить
     на долги в порядке стратегии;
  4. закрыть долги с нулевым остатком;
  5. платёж закрытого долга остаётся в бюджете и со следующего
     месяца уходит на следующий долг (rollover).

Бюджет месяца постоянен: сумма минимальных платежей всех долгов
на старте + extra_payment. Базовый сценарий «только минимальные
платежи» (baseline) не использует rollover — с ним сравнивается
экономия.

Стратегии:
  avalanche — сначала самая высокая ставка (минимум переплаты);
  snowball  — сначала самый маленький остаток (быстрые победы);
  hybrid    — сначала МФО и кредитные карты (дорогие и опасные),
              внутри и затем — по ставке, как avalanche.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.services.finance.calendar import add_months
from app.services.finance.loans import monthly_rate
from app.services.finance.money import ZERO, MoneyError, quantize_money

MAX_SIMULATION_MONTHS = 600


class DebtType(StrEnum):
    CONSUMER_LOAN = "consumer_loan"
    INSTALLMENT = "installment"
    CREDIT_CARD = "credit_card"
    MORTGAGE = "mortgage"
    AUTO_LOAN = "auto_loan"
    MICROLOAN = "microloan"
    PERSONAL = "personal"


HIGH_RISK_TYPES = frozenset({DebtType.MICROLOAN, DebtType.CREDIT_CARD})


class Strategy(StrEnum):
    AVALANCHE = "avalanche"
    SNOWBALL = "snowball"
    HYBRID = "hybrid"


class StrategyError(MoneyError):
    pass


@dataclass(frozen=True, slots=True)
class DebtInput:
    id: int | str
    name: str
    debt_type: DebtType
    balance: Decimal
    annual_rate: Decimal
    minimum_payment: Decimal


@dataclass(frozen=True, slots=True)
class MonthSnapshot:
    month: int
    date: date
    interest: Decimal
    payment: Decimal
    total_balance: Decimal
    balances: dict[str, Decimal]
    payments: dict[str, Decimal]
    closed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DebtPayoff:
    id: str
    name: str
    month: int
    date: date
    interest_paid: Decimal
    total_paid: Decimal


@dataclass(frozen=True, slots=True)
class SimulationResult:
    strategy: Strategy | None
    extra_payment: Decimal
    monthly_budget: Decimal
    feasible: bool
    months: int
    payoff_date: date | None
    total_interest: Decimal
    total_paid: Decimal
    payoff_order: tuple[DebtPayoff, ...]
    timeline: tuple[MonthSnapshot, ...] = field(repr=False)
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class StrategyComparison:
    baseline: SimulationResult
    results: dict[Strategy, SimulationResult]
    recommended: Strategy

    def interest_saved(self, strategy: Strategy) -> Decimal:
        return self.baseline.total_interest - self.results[strategy].total_interest

    def cost_vs_recommended(self, strategy: Strategy) -> Decimal:
        """Сколько тенге переплатит выбор strategy вместо рекомендованной."""

        return (
            self.results[strategy].total_interest
            - self.results[self.recommended].total_interest
        )


@dataclass(slots=True)
class _State:
    debt: DebtInput
    key: str
    balance: Decimal
    rate: Decimal
    interest_paid: Decimal = ZERO
    total_paid: Decimal = ZERO


def _priority(strategy: Strategy, state: _State) -> tuple:
    d = state.debt
    if strategy is Strategy.AVALANCHE:
        return (-d.annual_rate, state.balance, state.key)
    if strategy is Strategy.SNOWBALL:
        return (state.balance, -d.annual_rate, state.key)
    tier = 0 if d.debt_type in HIGH_RISK_TYPES else 1
    return (tier, -d.annual_rate, state.balance, state.key)


def _validate(debts: list[DebtInput], extra: Decimal) -> None:
    if extra < 0:
        raise StrategyError("extra_payment cannot be negative")
    keys = [str(d.id) for d in debts]
    if len(keys) != len(set(keys)):
        raise StrategyError("Debt ids must be unique")
    for d in debts:
        if d.balance < 0:
            raise StrategyError(f"Debt {d.id}: balance cannot be negative")
        if d.minimum_payment < 0:
            raise StrategyError(f"Debt {d.id}: minimum payment cannot be negative")
        if d.annual_rate < 0:
            raise StrategyError(f"Debt {d.id}: rate cannot be negative")


def simulate(
    debts: list[DebtInput],
    extra_payment=ZERO,
    strategy: Strategy | None = Strategy.AVALANCHE,
    *,
    start_date: date,
    rollover: bool = True,
    max_months: int = MAX_SIMULATION_MONTHS,
) -> SimulationResult:
    """
    strategy=None и rollover=False — базовый сценарий «только минимумы».
    """

    extra = quantize_money(extra_payment)
    _validate(debts, extra)
    if strategy is not None:
        strategy = Strategy(strategy)

    states = [
        _State(
            debt=d,
            key=str(d.id),
            balance=quantize_money(d.balance),
            rate=monthly_rate(d.annual_rate),
        )
        for d in debts
    ]
    minimums = {s.key: quantize_money(s.debt.minimum_payment) for s in states}
    # Уже закрытые долги не добавляют свой минимум в бюджет.
    budget = sum((minimums[s.key] for s in states if s.balance > 0), ZERO) + extra

    timeline: list[MonthSnapshot] = []
    payoffs: list[DebtPayoff] = []
    total_interest = ZERO
    total_paid = ZERO
    month = 0

    def open_states() -> list[_State]:
        return [s for s in states if s.balance > 0]

    while open_states():
        if month >= max_months:
            return SimulationResult(
                strategy=strategy,
                extra_payment=extra,
                monthly_budget=budget,
                feasible=False,
                months=month,
                payoff_date=None,
                total_interest=total_interest,
                total_paid=total_paid,
                payoff_order=tuple(payoffs),
                timeline=tuple(timeline),
                reason="PAYMENTS_DO_NOT_COVER_INTEREST",
            )

        month += 1
        current_date = add_months(start_date, month)
        active = open_states()
        month_interest = ZERO
        payments: dict[str, Decimal] = {}

        # 1. проценты
        for s in active:
            interest = quantize_money(s.balance * s.rate)
            s.balance += interest
            s.interest_paid += interest
            month_interest += interest

        # 2. минимальные платежи
        available = budget if rollover else sum((minimums[s.key] for s in active), ZERO)
        for s in active:
            pay = min(minimums[s.key], s.balance, available)
            s.balance -= pay
            available -= pay
            payments[s.key] = pay

        # 3. extra + освободившиеся платежи — по стратегии
        if rollover and strategy is not None and available > 0:
            for s in sorted(
                (s for s in active if s.balance > 0),
                key=lambda st: _priority(strategy, st),
            ):
                if available <= 0:
                    break
                pay = min(available, s.balance)
                s.balance -= pay
                available -= pay
                payments[s.key] = payments.get(s.key, ZERO) + pay

        # 4. закрытие долгов
        closed: list[str] = []
        for s in active:
            s.total_paid += payments.get(s.key, ZERO)
            if s.balance == 0:
                closed.append(s.key)
                payoffs.append(
                    DebtPayoff(
                        id=s.key,
                        name=s.debt.name,
                        month=month,
                        date=current_date,
                        interest_paid=s.interest_paid,
                        total_paid=s.total_paid,
                    )
                )

        month_payment = sum(payments.values(), ZERO)
        total_interest += month_interest
        total_paid += month_payment

        timeline.append(
            MonthSnapshot(
                month=month,
                date=current_date,
                interest=month_interest,
                payment=month_payment,
                total_balance=sum((s.balance for s in states), ZERO),
                balances={s.key: s.balance for s in states},
                payments=payments,
                closed=tuple(closed),
            )
        )

    return SimulationResult(
        strategy=strategy,
        extra_payment=extra,
        monthly_budget=budget,
        feasible=True,
        months=month,
        payoff_date=timeline[-1].date if timeline else None,
        total_interest=total_interest,
        total_paid=total_paid,
        payoff_order=tuple(payoffs),
        timeline=tuple(timeline),
    )


def compare_strategies(
    debts: list[DebtInput],
    extra_payment=ZERO,
    *,
    start_date: date,
) -> StrategyComparison:
    baseline = simulate(debts, ZERO, None, start_date=start_date, rollover=False)
    results = {
        strategy: simulate(debts, extra_payment, strategy, start_date=start_date)
        for strategy in Strategy
    }

    feasible = [s for s in Strategy if results[s].feasible]
    candidates = feasible or list(Strategy)
    # Минимальная переплата; при равенстве — раньше свобода от долгов,
    # затем порядок enum (avalanche по умолчанию).
    recommended = min(
        candidates,
        key=lambda s: (
            results[s].total_interest,
            results[s].months,
            list(Strategy).index(s),
        ),
    )
    return StrategyComparison(baseline=baseline, results=results, recommended=recommended)
