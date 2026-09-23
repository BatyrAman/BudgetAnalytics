from datetime import date
from decimal import Decimal

import pytest

from app.services.finance.debt_strategy import (
    DebtInput,
    DebtType,
    Strategy,
    StrategyError,
    compare_strategies,
    simulate,
)

D = Decimal
START = date(2025, 1, 15)


def debt(id, balance, rate, minimum, type=DebtType.CONSUMER_LOAN, name=None):
    return DebtInput(
        id=id,
        name=name or f"debt-{id}",
        debt_type=type,
        balance=D(balance),
        annual_rate=D(rate),
        minimum_payment=D(minimum),
    )


CARD = debt(1, 100_000, 30, 10_000, DebtType.CREDIT_CARD, "card")
LOAN = debt(2, 50_000, 10, 5_000, DebtType.CONSUMER_LOAN, "loan")


def _check_invariants(result, debts):
    principal = sum(d.balance for d in debts)
    assert result.feasible
    assert result.total_paid == principal + result.total_interest
    assert result.timeline[-1].total_balance == 0
    for snap in result.timeline[:-1]:
        # весь бюджет используется каждый месяц, кроме последнего
        assert snap.payment == result.monthly_budget
    assert result.timeline[-1].payment <= result.monthly_budget
    assert {p.id for p in result.payoff_order} == {str(d.id) for d in debts}


def test_avalanche_targets_highest_rate():
    result = simulate([CARD, LOAN], 5_000, Strategy.AVALANCHE, start_date=START)
    _check_invariants(result, [CARD, LOAN])
    first = result.timeline[0]
    assert first.payments["1"] == D("15000.00")  # 10k min + 5k extra
    assert first.payments["2"] == D("5000.00")
    assert result.payoff_order[0].id == "1"


def test_snowball_targets_smallest_balance():
    result = simulate([CARD, LOAN], 5_000, Strategy.SNOWBALL, start_date=START)
    _check_invariants(result, [CARD, LOAN])
    assert result.timeline[0].payments["2"] == D("10000.00")
    assert result.payoff_order[0].id == "2"


def test_avalanche_never_costs_more_than_snowball():
    comparison = compare_strategies([CARD, LOAN], 5_000, start_date=START)
    avalanche = comparison.results[Strategy.AVALANCHE]
    snowball = comparison.results[Strategy.SNOWBALL]
    assert avalanche.total_interest <= snowball.total_interest
    assert comparison.recommended is Strategy.AVALANCHE
    assert comparison.cost_vs_recommended(Strategy.SNOWBALL) == (
        snowball.total_interest - avalanche.total_interest
    )


def test_freed_payment_rolls_over():
    result = simulate([CARD, LOAN], 5_000, Strategy.SNOWBALL, start_date=START)
    loan_closed_month = next(p.month for p in result.payoff_order if p.id == "2")
    after = result.timeline[loan_closed_month]  # следующий месяц
    # весь бюджет (15k + 5k) теперь идёт на карту
    assert after.payments["1"] == result.monthly_budget
    assert "2" not in after.payments


def test_hybrid_pays_microloan_first_even_with_lower_rate():
    micro = debt(1, 40_000, 20, 4_000, DebtType.MICROLOAN)
    consumer = debt(2, 40_000, 35, 4_000, DebtType.CONSUMER_LOAN)
    hybrid = simulate([micro, consumer], 10_000, Strategy.HYBRID, start_date=START)
    avalanche = simulate([micro, consumer], 10_000, Strategy.AVALANCHE, start_date=START)
    assert hybrid.payoff_order[0].id == "1"
    assert avalanche.payoff_order[0].id == "2"
    _check_invariants(hybrid, [micro, consumer])


def test_extra_payment_saves_interest_vs_baseline():
    comparison = compare_strategies([CARD, LOAN], 20_000, start_date=START)
    for strategy in Strategy:
        assert comparison.interest_saved(strategy) > 0
        assert comparison.results[strategy].months < comparison.baseline.months


def test_baseline_has_no_rollover():
    baseline = compare_strategies([CARD, LOAN], 0, start_date=START).baseline
    loan_closed = next(p.month for p in baseline.payoff_order if p.id == "2")
    after = baseline.timeline[loan_closed]
    assert after.payments["1"] <= D("10000.00")


def test_zero_rate_debts():
    a = debt(1, 30_000, 0, 10_000, DebtType.PERSONAL)
    result = simulate([a], 0, Strategy.AVALANCHE, start_date=START)
    assert result.months == 3
    assert result.total_interest == 0
    assert result.payoff_date == date(2025, 4, 15)


def test_payment_greater_than_balance():
    a = debt(1, 5_000, 12, 50_000)
    result = simulate([a], 0, start_date=START)
    assert result.months == 1
    assert result.total_paid == D("5050.00")


def test_infeasible_when_payment_below_interest():
    a = debt(1, 1_000_000, 60, 10_000, DebtType.MICROLOAN)  # проценты 50 000/мес
    result = simulate([a], 0, start_date=START)
    assert not result.feasible
    assert result.reason == "PAYMENTS_DO_NOT_COVER_INTEREST"
    assert result.payoff_date is None


def test_exploding_debt_stops_early_without_overflow():
    a = debt(1, 500_000, 120, 10_000, DebtType.MICROLOAN)  # 10%/мес при платеже 2%
    result = simulate([a], 0, start_date=START)
    assert not result.feasible
    assert result.months <= 40
    baseline = compare_strategies([a], 0, start_date=START).baseline
    assert not baseline.feasible


def test_extra_makes_infeasible_feasible():
    a = debt(1, 1_000_000, 60, 10_000, DebtType.MICROLOAN)
    assert simulate([a], 100_000, start_date=START).feasible


def test_empty_debts():
    result = simulate([], 10_000, start_date=START)
    assert result.feasible and result.months == 0 and result.payoff_date is None


def test_zero_balance_debt_is_ignored():
    closed = debt(1, 0, 20, 1_000)
    open_ = debt(2, 10_000, 0, 1_000)
    result = simulate([closed, open_], 0, start_date=START)
    assert result.monthly_budget == D("1000.00")
    assert result.months == 10
