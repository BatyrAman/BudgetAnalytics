"""T4: deposit term bounds (1900-01-01..2200-12-31, at most 600 months).

Covers the finance engine, the request schemas of /deposits and the adapter
that marks stored legacy deposits with a ``data_issue``.
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.errors import DomainValidationError
from app.models.deposit import Deposit
from app.models.enums import Capitalization as C
from app.schemas import deposit as legacy
from app.schemas.deposits import DepositCalculationRequest, DepositCreate, DepositUpdate
from app.services.deposits import (
    deposit_data_issue,
    valid_deposits,
    valid_maturity_of,
    validate_deposit_term,
)
from app.services.finance import FinanceInputError, deposit_maturity
from app.services.finance.deposit import (
    DATE_OUT_OF_RANGE,
    MAX_DEPOSIT_DATE,
    MAX_DEPOSIT_TERM_MONTHS,
    MIN_DEPOSIT_DATE,
    TERM_NOT_POSITIVE,
    TERM_TOO_LONG,
    add_months,
    deposit_term_issue,
)

P = Decimal("1000000.00")
R = Decimal("14.00")


class TestTermIssue:
    def test_constants_match_the_agreed_policy(self) -> None:
        assert MIN_DEPOSIT_DATE == date(1900, 1, 1)
        assert MAX_DEPOSIT_DATE == date(2200, 12, 31)
        assert MAX_DEPOSIT_TERM_MONTHS == 600

    @pytest.mark.parametrize(
        ("start", "end", "expected"),
        [
            (date(2025, 1, 1), date(2026, 1, 1), None),
            (date(2025, 1, 1), date(2025, 1, 2), None),  # one day
            (date(2025, 1, 1), date(2075, 1, 1), None),  # exactly 600 months
            (date(2025, 1, 1), date(2075, 1, 2), TERM_TOO_LONG),  # one day more
            (date(2024, 2, 29), date(2074, 2, 28), None),  # leap start, clamped
            (date(2024, 2, 29), date(2074, 3, 1), TERM_TOO_LONG),
            (date(2025, 1, 31), date(2075, 1, 31), None),
            (date(2025, 1, 1), date(2025, 1, 1), TERM_NOT_POSITIVE),
            (date(2025, 2, 1), date(2025, 1, 1), TERM_NOT_POSITIVE),
            (MIN_DEPOSIT_DATE, date(1900, 1, 2), None),  # lower boundary
            (date(1899, 12, 31), date(1900, 6, 1), DATE_OUT_OF_RANGE),
            (date(2200, 1, 1), MAX_DEPOSIT_DATE, None),  # upper boundary
            (date(2200, 1, 1), date(2201, 1, 1), DATE_OUT_OF_RANGE),
            (date(1, 1, 1), date(9999, 12, 31), DATE_OUT_OF_RANGE),  # extremes
            # Range is checked before the term so add_months never overflows.
            (date(9999, 12, 31), date(9999, 12, 31), DATE_OUT_OF_RANGE),
        ],
    )
    def test_issue(self, start: date, end: date, expected: str | None) -> None:
        assert deposit_term_issue(start, end) == expected

    def test_issue_codes_are_stable(self) -> None:
        assert {TERM_NOT_POSITIVE, DATE_OUT_OF_RANGE, TERM_TOO_LONG} == {
            "invalid_date_range",
            "date_out_of_range",
            "term_too_long",
        }


class TestEngineEnforcesBounds:
    @pytest.mark.parametrize(
        ("start", "end", "match"),
        [
            (date(2025, 1, 1), date(2075, 1, 2), "600 months"),
            (date(1, 1, 1), date(2025, 1, 1), "between"),
            (date(2025, 1, 1), date(9999, 12, 31), "between"),
        ],
    )
    def test_rejects(self, start: date, end: date, match: str) -> None:
        with pytest.raises(FinanceInputError, match=match):
            deposit_maturity(P, R, start, end, C.MONTHLY)

    @pytest.mark.parametrize("cap", list(C))
    def test_maximum_term_is_computed(self, cap: C) -> None:
        start = date(2025, 1, 31)
        end = add_months(start, MAX_DEPOSIT_TERM_MONTHS)
        result = deposit_maturity(P, R, start, end, cap)
        assert result.maturity_date == end
        assert result.interest > 0
        if cap is C.MONTHLY:
            assert result.capitalization_periods == 600
            assert result.stub_days == 0

    def test_latest_allowed_dates(self) -> None:
        result = deposit_maturity(P, R, date(2200, 12, 30), MAX_DEPOSIT_DATE)
        assert result.term_days == 1


def _deposit(start: date, end: date) -> Deposit:
    return Deposit(
        id=1,
        user_id=1,
        bank_id=1,
        amount=P,
        currency_code="KZT",
        interest_rate=R,
        capitalization=C.NONE,
        start_date=start,
        end_date=end,
    )


class TestStoredDeposits:
    def test_valid_deposit_has_estimate(self) -> None:
        deposit = _deposit(date(2025, 1, 1), date(2026, 1, 1))
        assert deposit_data_issue(deposit) is None
        maturity = valid_maturity_of(deposit)
        assert maturity is not None
        assert maturity.interest == Decimal("140000.00")

    @pytest.mark.parametrize(
        ("start", "end", "code"),
        [
            (date(2025, 1, 1), date(2100, 1, 1), TERM_TOO_LONG),
            (date(1800, 1, 1), date(1801, 1, 1), DATE_OUT_OF_RANGE),
            (date(2025, 1, 1), date(9999, 12, 31), DATE_OUT_OF_RANGE),
            (date(2025, 1, 1), date(2025, 1, 1), TERM_NOT_POSITIVE),
        ],
    )
    def test_invalid_deposit_gets_issue_not_estimate(
        self, start: date, end: date, code: str
    ) -> None:
        deposit = _deposit(start, end)
        assert deposit_data_issue(deposit) == code
        assert valid_maturity_of(deposit) is None  # never raises

    def test_valid_deposits_drops_only_invalid_rows(self) -> None:
        good = _deposit(date(2025, 1, 1), date(2026, 1, 1))
        bad = _deposit(date(2025, 1, 1), date(2200, 1, 1))
        assert valid_deposits([good, bad, good]) == [good, good]
        assert valid_deposits([]) == []

    def test_validate_deposit_term_raises_coded_422(self) -> None:
        validate_deposit_term(date(2025, 1, 1), date(2026, 1, 1))
        with pytest.raises(DomainValidationError) as exc:
            validate_deposit_term(date(2025, 1, 1), date(2100, 1, 1))
        assert exc.value.status_code == 422
        assert exc.value.code == TERM_TOO_LONG
        assert "600 months" in exc.value.message


_BASE = {"bank_id": 1, "principal": "1000", "interest_rate": "10"}


class TestDepositSchemas:
    def test_create_accepts_maximum_term(self) -> None:
        DepositCreate(**_BASE, start_date="2025-01-01", end_date="2075-01-01")

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            ("2025-01-01", "2075-01-02"),
            ("1899-12-31", "1900-02-01"),
            ("2025-01-01", "2201-01-01"),
            ("0001-01-01", "9999-12-31"),
            ("2025-01-01", "2025-01-01"),
        ],
    )
    def test_create_rejects(self, start: str, end: str) -> None:
        with pytest.raises(ValidationError):
            DepositCreate(**_BASE, start_date=start, end_date=end)

    def test_update_bounds_each_date(self) -> None:
        DepositUpdate(end_date="2200-12-31")
        with pytest.raises(ValidationError):
            DepositUpdate(end_date="2201-01-01")
        with pytest.raises(ValidationError):
            DepositUpdate(start_date="1899-12-31")

    def test_calculator_term_months_cannot_pass_max_date(self) -> None:
        ok = DepositCalculationRequest(
            principal="1000", interest_rate="10", start_date="2150-12-31", term_months=600
        )
        assert ok.maturity_date == date(2200, 12, 31)
        with pytest.raises(ValidationError):
            DepositCalculationRequest(
                principal="1000", interest_rate="10", start_date="2200-01-01", term_months=600
            )

    @pytest.mark.parametrize(
        "body",
        [
            {"start_date": "2025-01-01", "end_date": "2075-01-02"},
            {"start_date": "2025-01-01", "end_date": "9999-12-31"},
            {"start_date": "0001-01-01", "term_months": 12},
            {"start_date": "2025-01-01", "term_months": 601},
        ],
    )
    def test_calculator_rejects(self, body: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            DepositCalculationRequest(principal="1000", interest_rate="10", **body)


class TestLegacySchemas:
    def test_response_still_serializes_stored_out_of_range_rows(self) -> None:
        # Bounds live on the write path; reading a legacy row must not 500.
        detail = legacy.DepositDetail(
            id=1,
            user_id=1,
            bank_id=1,
            amount=P,
            interest_rate=R,
            start_date=date(2025, 1, 1),
            end_date=date(9999, 12, 31),
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
            bank_name="Bank",
            duration_days=None,
            expected_profit=None,
            expected_amount=None,
            is_active=True,
            data_issue="date_out_of_range",
        )
        dumped = detail.model_dump()
        assert dumped["expected_profit"] is None
        assert dumped["data_issue"] == "date_out_of_range"

    def test_data_issue_rejects_unknown_codes(self) -> None:
        with pytest.raises(ValidationError):
            legacy.DepositForecast(
                deposit_id=1,
                maturity_date=date(2025, 1, 1),
                expected_profit=None,
                expected_amount=None,
                data_issue="secret details",
            )
