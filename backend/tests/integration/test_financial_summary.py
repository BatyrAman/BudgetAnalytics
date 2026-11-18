"""Repositories + finance engine end to end on real PostgreSQL."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bank, Budget, Category, Transaction, TransactionType, User
from app.services.finance import FinanceInputError
from app.services.financial_summary import FinancialSummaryService, NotFoundError

T = TransactionType


@pytest.fixture
async def setup(db_session: AsyncSession) -> dict[str, object]:
    alice = User(full_name="Alice", email="alice@example.com", hashed_password="x")
    bob = User(full_name="Bob", email="bob@example.com", hashed_password="x")
    bank = Bank(name="Test Bank")
    db_session.add_all([alice, bob, bank])
    await db_session.flush()
    food = Category(name="Продукты", user_id=alice.id)
    rent = Category(name="Аренда", user_id=alice.id)
    bobs = Category(name="Продукты", user_id=bob.id)
    db_session.add_all([food, rent, bobs])
    await db_session.flush()

    def tx(
        user: User, cat: Category, amount: str, kind: T, when: str, currency: str = "KZT"
    ) -> Transaction:
        return Transaction(
            amount=Decimal(amount),
            transaction_type=kind,
            transaction_date=datetime.fromisoformat(when),
            currency_code=currency,
            user_id=user.id,
            category_id=cat.id,
            bank_id=bank.id,
        )

    db_session.add_all(
        [
            tx(alice, food, "500000", T.INCOME, "2025-03-05T10:00:00+05:00"),
            tx(alice, food, "60000", T.EXPENSE, "2025-03-10T10:00:00+05:00"),
            tx(alice, food, "5000", T.REFUND, "2025-03-12T10:00:00+05:00"),
            tx(
                alice, rent, "200000", T.EXPENSE, "2025-03-01T00:00:00+05:00"
            ),  # first local instant
            tx(alice, rent, "100000", T.TRANSFER_OUT, "2025-03-20T10:00:00+05:00"),
            tx(alice, food, "70", T.EXPENSE, "2025-03-15T10:00:00+05:00", "USD"),  # other currency
            tx(alice, food, "999", T.EXPENSE, "2025-04-01T00:00:00+05:00"),  # April
            tx(bob, bobs, "777777", T.EXPENSE, "2025-03-10T10:00:00+05:00"),  # other user
        ]
    )
    budget = Budget(
        title="Еда", monthly_limit=Decimal("80000"), user_id=alice.id, category_id=food.id
    )
    total_budget = Budget(title="Все расходы", monthly_limit=Decimal("250000"), user_id=alice.id)
    db_session.add_all([budget, total_budget])
    await db_session.commit()
    return {"alice": alice, "bob": bob, "budget": budget, "total_budget": total_budget}


async def test_monthly_summary_for_one_user_and_currency(
    db_session: AsyncSession, setup: dict[str, object]
) -> None:
    alice = setup["alice"]
    months = await FinancialSummaryService(db_session).monthly_summaries(alice.id, 2025, "KZT")  # type: ignore[attr-defined]
    march, april = months[2], months[3]

    assert march.totals.income == Decimal("500000.00")
    assert march.totals.net_expenses == Decimal("255000.00")  # 60 000 + 200 000 − 5 000
    assert march.totals.net_cash_flow == Decimal("245000.00")
    assert march.totals.transfers_out == Decimal("100000.00")
    assert march.savings_rate == Decimal("49.00")  # 245 000 / 500 000
    assert april.totals.net_expenses == Decimal("999.00")
    assert months[0].totals.transaction_count == 0  # January present but empty


async def test_usd_is_summarized_separately(
    db_session: AsyncSession, setup: dict[str, object]
) -> None:
    alice = setup["alice"]
    year = await FinancialSummaryService(db_session).yearly_summary(alice.id, 2025, "USD")  # type: ignore[attr-defined]
    assert year.totals.net_expenses == Decimal("70.00")
    assert year.totals.income == Decimal("0.00")


async def test_budget_utilization_from_actual_transactions(
    db_session: AsyncSession, setup: dict[str, object]
) -> None:
    alice, budget, total = setup["alice"], setup["budget"], setup["total_budget"]
    service = FinancialSummaryService(db_session)

    food = await service.budget_utilization(alice.id, budget.id, date(2025, 3, 1))  # type: ignore[attr-defined]
    assert food.spent == Decimal("55000.00")  # 60 000 − 5 000 refund; USD row excluded
    assert food.utilization_percent == Decimal("68.75")
    assert food.is_exceeded is False

    everything = await service.budget_utilization(alice.id, total.id, date(2025, 3, 31))  # type: ignore[attr-defined]
    assert everything.spent == Decimal("255000.00")  # transfers excluded
    assert everything.utilization_percent == Decimal("102.00")
    assert everything.is_exceeded is True
    assert everything.remaining == Decimal("-5000.00")


async def test_other_users_budget_is_not_found(
    db_session: AsyncSession, setup: dict[str, object]
) -> None:
    bob, budget = setup["bob"], setup["budget"]
    with pytest.raises(NotFoundError):
        await FinancialSummaryService(db_session).budget_utilization(
            bob.id, budget.id, date(2025, 3, 1)
        )  # type: ignore[attr-defined]


async def test_unknown_currency(db_session: AsyncSession, setup: dict[str, object]) -> None:
    alice = setup["alice"]
    with pytest.raises(FinanceInputError, match="Unknown currency"):
        await FinancialSummaryService(db_session).yearly_summary(alice.id, 2025, "XYZ")  # type: ignore[attr-defined]


async def test_dates_are_compared_as_instants(
    db_session: AsyncSession, setup: dict[str, object]
) -> None:
    # 2025-03-01T00:00+05:00 == 2025-02-28T19:00Z must count in March (Almaty), not February.
    alice = setup["alice"]
    months = await FinancialSummaryService(db_session).monthly_summaries(alice.id, 2025, "KZT")  # type: ignore[attr-defined]
    assert months[1].totals.transaction_count == 0
    assert datetime(2025, 2, 28, 19, tzinfo=UTC) >= months[2].period.start
