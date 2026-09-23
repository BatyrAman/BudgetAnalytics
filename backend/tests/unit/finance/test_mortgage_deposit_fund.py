from datetime import date
from decimal import Decimal

import pytest

from app.services.finance.cashflow import growth_percent, monthly_average, savings_rate
from app.services.finance.deposits import (
    Capitalization,
    DayCount,
    DepositError,
    calculate_deposit,
    simple_interest,
)
from app.services.finance.emergency_fund import IncomeStability, calculate_emergency_fund
from app.services.finance.loans import LoanError, ScheduleType
from app.services.finance.money import MoneyError, quantize_money
from app.services.finance.mortgages import calculate_mortgage

D = Decimal


class TestMortgage:
    def test_basic(self):
        result = calculate_mortgage(30_000_000, 6_000_000, 18, 20)
        assert result.loan_amount == D("24000000.00")
        assert result.down_payment_percent == D("20.00")
        assert result.term_months == 240
        assert result.total_payment == result.loan_amount + result.total_interest
        # доход, при котором платёж = 40% дохода
        assert result.required_monthly_income == quantize_money(result.monthly_payment / D("0.40"))

    def test_existing_payments_raise_required_income(self):
        base = calculate_mortgage(30_000_000, 6_000_000, 18, 20)
        loaded = calculate_mortgage(30_000_000, 6_000_000, 18, 20, existing_debt_payments=100_000)
        assert loaded.required_monthly_income - base.required_monthly_income == D("250000.00")

    def test_differential_uses_first_payment_for_income(self):
        result = calculate_mortgage(20_000_000, 4_000_000, 16, 15, ScheduleType.DIFFERENTIAL)
        assert result.max_monthly_payment == result.schedule.installments[0].payment

    @pytest.mark.parametrize(
        "price, down, years",
        [(0, 0, 10), (10_000_000, 10_000_000, 10), (10_000_000, -1, 10), (10_000_000, 1, 0), (10_000_000, 1, 36)],
    )
    def test_invalid(self, price, down, years):
        with pytest.raises(LoanError):
            calculate_mortgage(price, down, 15, years)


class TestDeposit:
    def test_simple_interest_matches_legacy_formula(self):
        # старый API: amount * rate/100 * days / 365; 181 день
        assert simple_interest(1_000_000, D("14.5"), date(2025, 1, 1), date(2025, 7, 1)) == D("71904.11")

    def test_leap_year_day_count(self):
        start, end = date(2024, 1, 1), date(2025, 1, 1)  # 366 дней
        assert simple_interest(1_000_000, 10, start, end, DayCount.ACT_365) == D("100273.97")
        assert simple_interest(1_000_000, 10, start, end, DayCount.ACT_ACT) == D("100000.00")

    def test_end_before_start_gives_zero(self):
        assert simple_interest(1_000_000, 10, date(2025, 2, 1), date(2025, 1, 1)) == 0

    def test_monthly_capitalization(self):
        result = calculate_deposit(1_000_000, 12, 12, Capitalization.MONTHLY)
        # 1e6 * 1.01^12 = 1 126 825.03; помесячное округление процентов даёт .02
        assert result.final_amount == D("1126825.02")
        assert result.effective_annual_rate == D("12.68")
        assert result.total_interest == result.final_amount - result.total_contributions

    def test_no_capitalization(self):
        result = calculate_deposit(1_000_000, 12, 12, Capitalization.NONE)
        assert result.total_interest == D("120000.00")
        assert result.effective_annual_rate == D("12.00")

    def test_topups(self):
        result = calculate_deposit(100_000, 0, 6, monthly_topup=10_000)
        assert result.total_contributions == D("150000.00")
        assert result.final_amount == D("150000.00")

    def test_zero_rate(self):
        assert calculate_deposit(500_000, 0, 6).total_interest == 0

    @pytest.mark.parametrize("amount, rate, term", [(0, 10, 12), (100, -1, 12), (100, 10, 0)])
    def test_invalid(self, amount, rate, term):
        with pytest.raises(DepositError):
            calculate_deposit(amount, rate, term)


class TestEmergencyFund:
    def test_three_months_by_default(self):
        result = calculate_emergency_fund(200_000, 100_000, 50_000)
        assert result.target_months == 3
        assert result.target_amount == D("600000.00")
        assert result.gap == D("500000.00")
        assert result.months_to_goal == 10
        assert result.coverage_months == D("0.5")

    def test_six_months_with_dependents_or_variable_income(self):
        assert calculate_emergency_fund(100_000, dependents=2).target_months == 6
        assert (
            calculate_emergency_fund(100_000, income_stability=IncomeStability.VARIABLE).target_months
            == 6
        )

    def test_reached_and_no_contribution(self):
        assert calculate_emergency_fund(100_000, 400_000).is_reached
        assert calculate_emergency_fund(100_000, 0, 0).months_to_goal is None

    def test_zero_expenses(self):
        result = calculate_emergency_fund(0)
        assert result.is_reached and result.target_amount == 0

    def test_negative(self):
        with pytest.raises(MoneyError):
            calculate_emergency_fund(-1)


class TestCashflow:
    def test_savings_rate(self):
        assert savings_rate(420_000, 315_000) == D("25.00")
        assert savings_rate(0, 100) == D("0.00")
        assert savings_rate(100, 150) == D("-50.00")

    def test_growth(self):
        assert growth_percent(120, 100) == D("20.00")
        assert growth_percent(100, 0) is None

    def test_monthly_average(self):
        assert monthly_average([]) == D("0.00")
        assert monthly_average([D("100"), D("200"), D("0")]) == D("100.00")
