from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.enums import ProductType
from app.services.products.sources import ProductOffer
from app.tasks.bank_products import update_bank_products
from app.tasks.monthly_report import generate_monthly_reports
from app.tasks.payment_reminders import send_payment_reminders
from app.tasks.statement_import import process_statement_import

pytestmark = pytest.mark.integration


class FakeSource:
    def __init__(self, offers, name="test-source"):
        self.offers = offers
        self.name = name

    async def fetch(self):
        return self.offers


class BrokenSource:
    name = "broken"

    async def fetch(self):
        raise RuntimeError("site is down")


def offer(key, rate, **kw):
    base = dict(
        bank_name="Kaspi Bank",
        product_type=ProductType.DEPOSIT,
        external_key=key,
        name=f"Депозит {key}",
        rate_min=Decimal(rate),
        rate_max=Decimal(rate),
        source_url=f"https://example.kz/{key}",
        term_min=3,
        term_max=12,
        amount_min=Decimal("10000"),
        fetched_at=datetime.now(timezone.utc),
    )
    base.update(kw)
    return ProductOffer(**base)


@pytest.fixture(autouse=True)
async def clean_products(session):
    yield
    await session.execute(text("DELETE FROM bank_products"))
    await session.commit()


async def test_bank_products_update_is_idempotent(session, alice):
    source = FakeSource([offer("a", "14.5"), offer("b", "15.2", term_max=24)])
    await update_bank_products([source])
    await update_bank_products([source])
    assert await session.scalar(text("SELECT count(*) FROM bank_products")) == 2

    # изменились условия + один продукт исчез из выгрузки
    source.offers = [offer("a", "16.0")]
    stats = await update_bank_products([source, BrokenSource()])
    assert [s.deactivated for s in stats] == [1]

    products = (await alice.get("/products", params={"type": "deposit"})).json()
    assert len(products) == 1
    assert products[0]["rate_max"] == "16.00"
    assert products[0]["source_url"] == "https://example.kz/a"
    assert products[0]["source"] == "test-source"
    assert products[0]["is_stale"] is False
    assert products[0]["fetched_at"] and products[0]["updated_at"]


async def test_products_filtering_and_ordering(alice):
    await update_bank_products([FakeSource([
        offer("small", "13", amount_max=Decimal("100000")),
        offer("big", "15", amount_min=Decimal("1000000")),
        offer("any", "14", amount_min=None, term_min=None, term_max=None),
        offer("loan", "20", product_type=ProductType.CONSUMER_LOAN, gesv=Decimal("24.5")),
        offer("old", "18", fetched_at=datetime.now(timezone.utc) - timedelta(days=30)),
    ])])
    names = [p["name"] for p in (await alice.get("/products", params={"type": "deposit", "amount": "50000", "term": 6})).json()]
    assert names == ["Депозит old", "Депозит any", "Депозит small"]  # по убыванию ставки
    stale = (await alice.get("/products", params={"type": "deposit"})).json()
    assert next(p for p in stale if p["name"] == "Депозит old")["is_stale"] is True
    loans = (await alice.get("/products", params={"type": "consumer_loan"})).json()
    assert [p["gesv"] for p in loans] == ["24.50"]


async def test_payment_reminders_are_sent_once(alice):
    today = date.today()
    due = today + timedelta(days=3)
    await alice.post("/debts", json={
        "name": "Кредит", "debt_type": "consumer_loan", "principal": "100000", "annual_rate": "10",
        "monthly_payment": "10000", "payment_day": due.day if due.day <= 28 else 28,
        "start_date": "2025-01-01"})

    class Collect:
        def __init__(self):
            self.messages = []

        async def send_payment_reminder(self, message):
            self.messages.append(message)

    target_today = today if due.day <= 28 else date(due.year, due.month, 25)
    notifier = Collect()
    first = await send_payment_reminders(target_today, notifier)
    second = await send_payment_reminders(target_today, notifier)
    assert first == 1 and second == 0
    assert notifier.messages[0].kind == "before_3_days"


async def test_monthly_reports_are_idempotent(alice, session, kaspi_id):
    from tests.integration.conftest import system_category

    food = await system_category(session, "Продукты")
    await alice.post("/transactions", json={
        "amount": "1500", "transaction_type": "expense", "transaction_date": "2025-02-10T10:00:00",
        "category_id": food, "bank_id": kaspi_id})
    await generate_monthly_reports(date(2025, 2, 1))
    await generate_monthly_reports(date(2025, 2, 1))
    rows = (await session.execute(text(
        "SELECT data FROM monthly_reports WHERE user_id = :u"), {"u": alice.id})).all()
    assert len(rows) == 1
    assert rows[0][0]["expense"] == "1500.00"
    assert rows[0][0]["top_categories"][0]["name"] == "Продукты"


async def test_statement_import_task_is_idempotent(alice):
    content = b"date,description,amount\n2025-01-01,Coffee,-900\n"
    body = (await alice.post("/upload/kaspi", files={"file": ("s.csv", content, "text/csv")})).json()
    # импорт уже завершён — повторный запуск задачи ничего не делает
    assert (await process_statement_import(body["import_id"], content)).value == "completed"
    assert (await alice.get("/transactions")).json()["total"] == 1
    assert await process_statement_import(999_999, content) is None
