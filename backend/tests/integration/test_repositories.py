"""Repositories, database constraints and user-level isolation (real PostgreSQL)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    AccountType,
    Bank,
    Budget,
    Category,
    Deposit,
    FinancialGoal,
    Transaction,
    TransactionType,
    User,
)
from app.repositories.account import AccountRepository
from app.repositories.budget import BudgetRepository
from app.repositories.category import CategoryRepository
from app.repositories.currency import CurrencyRepository
from app.repositories.deposit import DepositRepository
from app.repositories.goal import FinancialGoalRepository
from app.repositories.transaction import TransactionRepository


@pytest.fixture
async def users(db_session: AsyncSession) -> tuple[User, User]:
    alice = User(full_name="Alice", email="alice@example.com", hashed_password="x")
    bob = User(full_name="Bob", email="bob@example.com", hashed_password="x")
    db_session.add_all([alice, bob])
    await db_session.commit()
    return alice, bob


@pytest.fixture
async def bank(db_session: AsyncSession) -> Bank:
    bank = Bank(name="Test Bank")
    db_session.add(bank)
    await db_session.commit()
    return bank


async def _category(db: AsyncSession, name: str, user: User | None) -> Category:
    category = Category(name=name, user_id=user.id if user else None)
    db.add(category)
    await db.commit()
    return category


def _tx(
    user: User,
    category: Category,
    bank: Bank,
    amount: str,
    kind: TransactionType = TransactionType.EXPENSE,
    when: datetime = datetime(2025, 3, 10, 6, tzinfo=UTC),
    currency: str = "KZT",
    account_id: int | None = None,
) -> Transaction:
    return Transaction(
        amount=Decimal(amount),
        transaction_type=kind,
        transaction_date=when,
        currency_code=currency,
        user_id=user.id,
        category_id=category.id,
        bank_id=bank.id,
        account_id=account_id,
    )


async def _expect_integrity_error(db: AsyncSession, *objects: object) -> None:
    db.add_all(objects)
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


class TestCurrencies:
    async def test_seeded_reference_data(self, db_session: AsyncSession) -> None:
        currencies = {
            c.code: c.minor_units for c in await CurrencyRepository(db_session).list_active()
        }
        assert currencies == {"EUR": 2, "KZT": 2, "RUB": 2, "USD": 2}

    async def test_spec(self, db_session: AsyncSession) -> None:
        spec = await CurrencyRepository(db_session).get_spec("KZT")
        assert spec is not None and (spec.code, spec.minor_units) == ("KZT", 2)
        assert await CurrencyRepository(db_session).get_spec("XXX") is None


class TestAccounts:
    async def test_isolation(self, db_session: AsyncSession, users: tuple[User, User]) -> None:
        alice, bob = users
        repo = AccountRepository(db_session)
        account = Account(
            user_id=alice.id,
            name="Kaspi Gold",
            account_type=AccountType.CARD,
            currency_code="KZT",
            last4="1234",
        )
        repo.add(account)
        await db_session.commit()

        assert await repo.get_for_user(account.id, alice.id) is not None
        assert await repo.get_for_user(account.id, bob.id) is None
        assert [a.name for a in await repo.list_for_user(alice.id)] == ["Kaspi Gold"]
        assert await repo.list_for_user(bob.id) == []

    async def test_archived_accounts_are_hidden_by_default(
        self, db_session: AsyncSession, users: tuple[User, User]
    ) -> None:
        alice, _ = users
        repo = AccountRepository(db_session)
        repo.add(
            Account(
                user_id=alice.id,
                name="Old",
                account_type=AccountType.CASH,
                currency_code="KZT",
                is_archived=True,
            )
        )
        await db_session.commit()
        assert await repo.list_for_user(alice.id) == []
        assert len(await repo.list_for_user(alice.id, include_archived=True)) == 1

    async def test_name_unique_per_user_only(
        self, db_session: AsyncSession, users: tuple[User, User]
    ) -> None:
        alice, bob = users
        db_session.add_all(
            [
                Account(
                    user_id=alice.id,
                    name="Cash",
                    account_type=AccountType.CASH,
                    currency_code="KZT",
                ),
                Account(
                    user_id=bob.id, name="Cash", account_type=AccountType.CASH, currency_code="KZT"
                ),
            ]
        )
        await db_session.commit()
        await _expect_integrity_error(
            db_session,
            Account(
                user_id=alice.id, name="Cash", account_type=AccountType.CASH, currency_code="USD"
            ),
        )

    @pytest.mark.parametrize(
        "overrides",
        [
            {"last4": "12a4"},  # only 4 digits may be stored, never a full number
            {"currency_code": "XXX"},  # unknown currency
            {"name": "   "},  # blank name
        ],
    )
    async def test_constraints(
        self, db_session: AsyncSession, users: tuple[User, User], overrides: dict[str, str]
    ) -> None:
        alice, _ = users
        values = {
            "user_id": alice.id,
            "name": "Card",
            "account_type": AccountType.CARD,
            "currency_code": "KZT",
        }
        await _expect_integrity_error(db_session, Account(**{**values, **overrides}))


class TestCategories:
    async def test_visibility(self, db_session: AsyncSession, users: tuple[User, User]) -> None:
        alice, bob = users
        system = await _category(db_session, "Тестовая системная", None)
        private = await _category(db_session, "Долг Ивану", alice)
        repo = CategoryRepository(db_session)

        alice_names = {c.name for c in await repo.list_visible(alice.id)}
        bob_names = {c.name for c in await repo.list_visible(bob.id)}
        assert {"Тестовая системная", "Долг Ивану"} <= alice_names
        assert "Тестовая системная" in bob_names and "Долг Ивану" not in bob_names
        assert await repo.get_visible(private.id, bob.id) is None
        assert await repo.get_visible(system.id, bob.id) is not None

    async def test_get_or_create_own_never_touches_other_users(
        self, db_session: AsyncSession, users: tuple[User, User]
    ) -> None:
        alice, bob = users
        alices = await _category(db_session, "Такси", alice)
        repo = CategoryRepository(db_session)

        bobs = await repo.get_or_create_own("Такси", bob.id)
        await db_session.commit()
        assert bobs.id != alices.id and bobs.user_id == bob.id
        assert (await repo.get_or_create_own("Такси", bob.id)).id == bobs.id

    async def test_uniqueness_rules(
        self, db_session: AsyncSession, users: tuple[User, User]
    ) -> None:
        alice, bob = users
        await _category(db_session, "Кафе", alice)
        await _category(db_session, "Кафе", bob)  # same name, different owners: allowed
        await _category(db_session, "Связь", None)
        await _expect_integrity_error(db_session, Category(name="Кафе", user_id=alice.id))
        await _expect_integrity_error(db_session, Category(name="Связь", user_id=None))


class TestTransactions:
    async def test_cannot_reference_another_users_account(
        self, db_session: AsyncSession, users: tuple[User, User], bank: Bank
    ) -> None:
        alice, bob = users
        account = Account(
            user_id=alice.id, name="Card", account_type=AccountType.CARD, currency_code="KZT"
        )
        db_session.add(account)
        await db_session.commit()
        category = await _category(db_session, "Прочее", bob)

        # Composite FK (account_id, user_id) -> accounts(id, user_id).
        await _expect_integrity_error(
            db_session, _tx(bob, category, bank, "100", account_id=account.id)
        )

    @pytest.mark.parametrize(
        "overrides", [{"amount": "0"}, {"amount": "-5.00"}, {"currency": "ABC"}]
    )
    async def test_constraints(
        self,
        db_session: AsyncSession,
        users: tuple[User, User],
        bank: Bank,
        overrides: dict[str, str],
    ) -> None:
        alice, _ = users
        category = await _category(db_session, "Прочее", alice)
        await _expect_integrity_error(
            db_session, _tx(alice, category, bank, **{"amount": "100", **overrides})
        )

    async def test_new_transaction_types_and_timezone_roundtrip(
        self, db_session: AsyncSession, users: tuple[User, User], bank: Bank
    ) -> None:
        alice, _ = users
        category = await _category(db_session, "Прочее", alice)
        when = datetime.fromisoformat("2025-03-31T23:30:00+05:00")
        tx = _tx(alice, category, bank, "10.50", TransactionType.REFUND, when, currency="USD")
        db_session.add(tx)
        await db_session.commit()
        db_session.expunge_all()

        stored = await TransactionRepository(db_session).get_for_user(tx.id, alice.id)
        assert stored is not None
        assert stored.transaction_type is TransactionType.REFUND
        assert stored.transaction_date == when  # same instant
        assert stored.transaction_date.utcoffset().total_seconds() == 0  # returned in UTC
        assert stored.amount == Decimal("10.50") and stored.currency_code == "USD"

    async def test_cashflow_items_are_scoped_and_half_open(
        self, db_session: AsyncSession, users: tuple[User, User], bank: Bank
    ) -> None:
        alice, bob = users
        a_cat = await _category(db_session, "A", alice)
        b_cat = await _category(db_session, "B", bob)
        start = datetime(2025, 3, 1, tzinfo=UTC)
        end = datetime(2025, 4, 1, tzinfo=UTC)
        db_session.add_all(
            [
                _tx(alice, a_cat, bank, "1", when=start),  # included (start is inclusive)
                _tx(alice, a_cat, bank, "2", when=end),  # excluded (end is exclusive)
                _tx(alice, a_cat, bank, "3", currency="USD"),
                _tx(bob, b_cat, bank, "4"),  # other user
            ]
        )
        await db_session.commit()

        repo = TransactionRepository(db_session)
        items = await repo.cashflow_items(alice.id, start, end)
        assert sorted(i.amount for i in items) == [Decimal("1.00"), Decimal("3.00")]
        kzt = await repo.cashflow_items(alice.id, start, end, currency_code="KZT")
        assert [i.amount for i in kzt] == [Decimal("1.00")]
        with pytest.raises(ValueError, match="timezone-aware"):
            await repo.cashflow_items(alice.id, datetime(2025, 3, 1), end)


class TestBudgetsDepositsGoals:
    async def test_isolation(
        self, db_session: AsyncSession, users: tuple[User, User], bank: Bank
    ) -> None:
        alice, bob = users
        budget = Budget(title="Еда", monthly_limit=Decimal("100000"), user_id=alice.id)
        deposit = Deposit(
            amount=Decimal("500000"),
            interest_rate=Decimal("14"),
            start_date=date(2025, 1, 1),
            end_date=date(2026, 1, 1),
            user_id=alice.id,
            bank_id=bank.id,
        )
        goal = FinancialGoal(
            user_id=alice.id, name="Подушка", target_amount=Decimal("1500000"), currency_code="KZT"
        )
        db_session.add_all([budget, deposit, goal])
        await db_session.commit()

        for repo, obj in (
            (BudgetRepository(db_session), budget),
            (DepositRepository(db_session), deposit),
            (FinancialGoalRepository(db_session), goal),
        ):
            assert await repo.get_for_user(obj.id, alice.id) is not None
            assert await repo.get_for_user(obj.id, bob.id) is None
            assert len(await repo.list_for_user(alice.id)) == 1
            assert await repo.list_for_user(bob.id) == []

        assert deposit.capitalization.value == "none"  # default for every existing deposit
        assert goal.saved_amount == Decimal("0")

    @pytest.mark.parametrize(
        "factory",
        [
            pytest.param(
                lambda u, b: Budget(title="x", monthly_limit=Decimal("0"), user_id=u),
                id="budget-limit-0",
            ),
            pytest.param(
                lambda u, b: Budget(
                    title="x", monthly_limit=Decimal("1"), spent=Decimal("-1"), user_id=u
                ),
                id="budget-negative-spent",
            ),
            pytest.param(
                lambda u, b: Deposit(
                    amount=Decimal("1"),
                    interest_rate=Decimal("10"),
                    start_date=date(2025, 1, 2),
                    end_date=date(2025, 1, 2),
                    user_id=u,
                    bank_id=b,
                ),
                id="deposit-zero-term",
            ),
            pytest.param(
                lambda u, b: Deposit(
                    amount=Decimal("1"),
                    interest_rate=Decimal("100.01"),
                    start_date=date(2025, 1, 1),
                    end_date=date(2025, 2, 1),
                    user_id=u,
                    bank_id=b,
                ),
                id="deposit-rate-over-100",
            ),
            pytest.param(
                lambda u, b: FinancialGoal(
                    user_id=u, name="g", target_amount=Decimal("0"), currency_code="KZT"
                ),
                id="goal-target-0",
            ),
            pytest.param(
                lambda u, b: FinancialGoal(
                    user_id=u,
                    name="g",
                    target_amount=Decimal("10"),
                    saved_amount=Decimal("-1"),
                    currency_code="KZT",
                ),
                id="goal-negative-saved",
            ),
        ],
    )
    async def test_constraints(
        self,
        db_session: AsyncSession,
        users: tuple[User, User],
        bank: Bank,
        factory,  # type: ignore[no-untyped-def]
    ) -> None:
        alice, _ = users
        await _expect_integrity_error(db_session, factory(alice.id, bank.id))
