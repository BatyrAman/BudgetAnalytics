from datetime import date
from decimal import Decimal

import pytest

from app.services.finance.loans import (
    LoanError,
    NonAmortizingLoanError,
    PrepaymentMode,
    ScheduleType,
    annuity_payment,
    apply_prepayment,
    build_schedule,
    effective_annual_rate,
    months_to_payoff,
    schedule_gesv,
    schedule_with_fixed_payment,
)

D = Decimal


def _assert_consistent(schedule, principal):
    assert sum(i.principal for i in schedule.installments) == D(principal)
    assert schedule.installments[-1].balance_after == 0
    for inst in schedule.installments:
        assert inst.payment == inst.principal + inst.interest
        assert inst.principal >= 0 and inst.interest >= 0
    assert schedule.total_payment == D(principal) + schedule.total_interest


class TestAnnuity:
    def test_reference_payment(self):
        # 1 000 000 ₸, 12% годовых, 12 мес. → 88 848.79 ₸ (эталон)
        assert annuity_payment(1_000_000, 12, 12) == D("88848.79")

    def test_schedule_is_consistent(self):
        schedule = build_schedule(1_000_000, 12, 12)
        _assert_consistent(schedule, 1_000_000)
        assert schedule.term_months == 12
        assert schedule.first_payment == D("88848.79")
        # последний платёж отличается максимум на несколько тиынов
        assert abs(schedule.last_payment - D("88848.79")) <= D("0.10")
        # округление процентов помесячно до тиына: детерминированное значение
        assert schedule.total_interest == D("66185.45")
        assert abs(schedule.total_interest - (12 * D("88848.79") - 1_000_000)) <= D("0.12")
        assert schedule.overpayment == schedule.total_interest

    def test_zero_rate(self):
        schedule = build_schedule(100_000, 0, 3)
        assert [i.payment for i in schedule.installments] == [
            D("33333.33"),
            D("33333.33"),
            D("33333.34"),
        ]
        assert schedule.total_interest == 0
        _assert_consistent(schedule, 100_000)

    @pytest.mark.parametrize("term", [0, -1, 601])
    def test_invalid_term(self, term):
        with pytest.raises(LoanError):
            annuity_payment(100_000, 10, term)

    @pytest.mark.parametrize("principal", [0, -5])
    def test_invalid_principal(self, principal):
        with pytest.raises(LoanError):
            build_schedule(principal, 10, 12)

    def test_negative_rate(self):
        with pytest.raises(LoanError):
            build_schedule(100_000, -1, 12)

    def test_very_large_amount(self):
        schedule = build_schedule(D("999999999999.99"), 25, 360)
        _assert_consistent(schedule, D("999999999999.99"))

    def test_one_month_term(self):
        schedule = build_schedule(10_000, 12, 1)
        assert schedule.installments[0].payment == D("10100.00")

    def test_remaining_balance(self):
        schedule = build_schedule(1_000_000, 12, 12)
        assert schedule.balance_after(0) == D("1000000.00")
        assert schedule.balance_after(12) == 0
        assert schedule.balance_after(99) == 0
        assert schedule.balance_after(6) == schedule.installments[5].balance_after


class TestDifferential:
    def test_reference_interest(self):
        # тело 100 000/мес, проценты 1% от остатка: 0.01*100000*(12+...+1)
        schedule = build_schedule(1_200_000, 12, 12, ScheduleType.DIFFERENTIAL)
        assert schedule.total_interest == D("78000.00")
        assert schedule.installments[0].payment == D("112000.00")
        assert schedule.installments[-1].payment == D("101000.00")
        _assert_consistent(schedule, 1_200_000)

    def test_payments_decrease(self):
        schedule = build_schedule(500_000, 20, 24, ScheduleType.DIFFERENTIAL)
        payments = [i.payment for i in schedule.installments]
        assert payments == sorted(payments, reverse=True)
        _assert_consistent(schedule, 500_000)

    def test_indivisible_principal(self):
        schedule = build_schedule(100_000, 10, 3, ScheduleType.DIFFERENTIAL)
        assert [i.principal for i in schedule.installments] == [
            D("33333.33"),
            D("33333.33"),
            D("33333.34"),
        ]

    def test_cheaper_than_annuity(self):
        annuity = build_schedule(1_000_000, 18, 36)
        diff = build_schedule(1_000_000, 18, 36, ScheduleType.DIFFERENTIAL)
        assert diff.total_interest < annuity.total_interest


class TestDueDates:
    def test_month_end_payment_day(self):
        schedule = build_schedule(90_000, 0, 3, start_date=date(2024, 1, 31))
        assert [i.due_date for i in schedule.installments] == [
            date(2024, 2, 29),
            date(2024, 3, 31),
            date(2024, 4, 30),
        ]
        assert schedule.payoff_date == date(2024, 4, 30)


class TestFixedPayment:
    def test_months_to_payoff(self):
        assert months_to_payoff(100_000, 0, 30_000) == 4

    def test_payment_bigger_than_balance(self):
        schedule = schedule_with_fixed_payment(10_000, 12, 50_000)
        assert schedule.term_months == 1
        assert schedule.installments[0].payment == D("10100.00")

    def test_payment_not_covering_interest(self):
        with pytest.raises(NonAmortizingLoanError):
            schedule_with_fixed_payment(1_000_000, 24, 20_000)  # проценты 20 000


class TestPrepayment:
    def test_shorten_term(self):
        result = apply_prepayment(1_000_000, 12, 12, 300_000, PrepaymentMode.SHORTEN_TERM)
        assert result.payment_after == result.payment_before == D("88848.79")
        assert result.term_after < result.term_before
        assert result.interest_saved > 0
        assert result.balance_after == D("700000.00")

    def test_reduce_payment(self):
        result = apply_prepayment(1_000_000, 12, 12, 300_000, PrepaymentMode.REDUCE_PAYMENT)
        assert result.term_after == 12
        assert result.payment_after == annuity_payment(700_000, 12, 12)
        assert result.payment_reduced_by > 0
        assert result.interest_saved > 0

    def test_shorten_term_saves_more_than_reduce_payment(self):
        term = apply_prepayment(2_000_000, 20, 36, 500_000, PrepaymentMode.SHORTEN_TERM)
        pay = apply_prepayment(2_000_000, 20, 36, 500_000, PrepaymentMode.REDUCE_PAYMENT)
        assert term.interest_saved > pay.interest_saved

    def test_prepayment_greater_than_balance_closes_loan(self):
        result = apply_prepayment(100_000, 12, 12, 250_000)
        assert result.fully_repaid
        assert result.amount == D("100000.00")
        assert result.interest_after == 0
        assert result.term_after == 0

    def test_differential_shorten_term(self):
        result = apply_prepayment(
            1_200_000, 12, 12, 300_000, PrepaymentMode.SHORTEN_TERM, ScheduleType.DIFFERENTIAL
        )
        assert result.term_after == 9
        assert result.schedule_after.installments[0].principal == D("100000.00")

    def test_invalid_amount(self):
        with pytest.raises(LoanError):
            apply_prepayment(100_000, 12, 12, 0)


class TestEffectiveRate:
    def test_zero_rate_zero_fees(self):
        schedule = build_schedule(120_000, 0, 12)
        assert schedule_gesv(schedule) == D("0.00")

    def test_nominal_12_percent(self):
        schedule = build_schedule(1_000_000, 12, 12)
        assert schedule_gesv(schedule) == D("12.68")

    def test_fees_increase_effective_rate(self):
        schedule = build_schedule(1_000_000, 12, 12)
        with_fee = schedule_gesv(schedule, upfront_fees=20_000)
        with_monthly = schedule_gesv(schedule, monthly_fee=1_000)
        assert with_fee > D("12.68")
        assert with_monthly > D("12.68")

    def test_zero_percent_installment_with_fee_is_not_free(self):
        schedule = build_schedule(300_000, 0, 12)
        assert schedule_gesv(schedule, upfront_fees=15_000) > D("9")

    def test_invalid_inputs(self):
        with pytest.raises(LoanError):
            effective_annual_rate(1000, [], upfront_fees=0)
        with pytest.raises(LoanError):
            effective_annual_rate(1000, [D("100")], upfront_fees=1000)
