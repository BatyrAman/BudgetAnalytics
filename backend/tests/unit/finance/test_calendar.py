from datetime import date

from app.services.finance.calendar import add_months, count_payment_dates, months_between, next_payment_date


def test_month_end_is_clamped_and_anchor_day_restored():
    start = date(2025, 1, 31)
    assert add_months(start, 1) == date(2025, 2, 28)
    assert add_months(start, 2) == date(2025, 3, 31)
    assert add_months(start, 3) == date(2025, 4, 30)


def test_leap_year_february():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)


def test_year_rollover_and_negative_offsets():
    assert add_months(date(2025, 12, 15), 1) == date(2026, 1, 15)
    assert add_months(date(2025, 1, 15), -1) == date(2024, 12, 15)


def test_next_payment_date():
    assert next_payment_date(date(2025, 2, 10), 15) == date(2025, 2, 15)
    assert next_payment_date(date(2025, 2, 15), 15) == date(2025, 2, 15)
    assert next_payment_date(date(2025, 2, 16), 15) == date(2025, 3, 15)
    # день 31 в феврале → последний день месяца
    assert next_payment_date(date(2025, 2, 1), 31) == date(2025, 2, 28)


def test_months_between():
    assert months_between(date(2025, 1, 15), date(2025, 7, 15)) == 6
    assert months_between(date(2025, 1, 15), date(2025, 7, 14)) == 5
    assert months_between(date(2025, 1, 31), date(2025, 2, 28)) == 1
    assert months_between(date(2025, 7, 1), date(2025, 1, 1)) == 0


def test_count_payment_dates():
    # старт 23.09.2026, платежи 10-го числа, окончание 10.09.2028 → 24 платежа
    assert count_payment_dates(date(2026, 9, 23), date(2028, 9, 10), 10) == 24
    assert count_payment_dates(date(2026, 9, 10), date(2026, 9, 10), 10) == 1
    assert count_payment_dates(date(2026, 9, 11), date(2026, 9, 30), 10) == 0
    assert count_payment_dates(date(2025, 1, 1), date(2025, 3, 31), 31) == 3
