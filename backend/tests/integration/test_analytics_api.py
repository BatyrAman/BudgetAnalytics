from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy import event

from app.core.database import engine
from app.services.analytics.overview import AnalyticsOverviewService
from app.services.analytics.periods import Period
from tests.integration.conftest import system_category

pytestmark = pytest.mark.integration


@contextmanager
def count_queries():
    statements: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)


async def add_tx(user, category_id, bank_id, amount, when, type_="expense", description="Magnum"):
    response = await user.post(
        "/transactions",
        json={
            "amount": amount,
            "transaction_type": type_,
            "transaction_date": when,
            "category_id": category_id,
            "bank_id": bank_id,
            "description": description,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def seeded(alice, session, kaspi_id):
    food = await system_category(session, "Продукты")
    subs = await system_category(session, "Подписки")
    salary = await system_category(session, "Зарплата", "income")
    await add_tx(alice, salary, kaspi_id, "500000", "2025-03-01T09:00:00", "income", "Salary")
    await add_tx(alice, food, kaspi_id, "20000", "2025-03-03T18:00:00")
    await add_tx(alice, food, kaspi_id, "30000", "2025-03-10T18:30:00")
    await add_tx(alice, subs, kaspi_id, "3990", "2025-01-05T00:00:00", description="Netflix")
    await add_tx(alice, subs, kaspi_id, "3990", "2025-02-05T00:00:00", description="Netflix")
    await add_tx(alice, subs, kaspi_id, "3990", "2025-03-05T00:00:00", description="Netflix")
    # прошлый период (февраль) для сравнения
    await add_tx(alice, food, kaspi_id, "10000", "2025-02-10T12:00:00")
    return {"food": food, "subs": subs}


async def test_overview_custom_month(alice, seeded):
    response = await alice.get("/analytics/overview", params={"date_from": "2025-03-01", "date_to": "2025-03-31"})
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["period"]["type"] == "custom"
    assert data["period"]["granularity"] == "day"
    assert data["period"]["currency"] == "KZT"

    summary = data["summary"]
    assert summary["income"] == "500000.00"
    assert summary["expense"] == "53990.00"
    assert summary["net"] == "446010.00"
    assert summary["savings_rate"] == "89.20"
    assert summary["expense_count"] == 3
    assert summary["average_daily_expense"] == "1741.61"
    assert summary["previous"]["expense"] == "13990.00"  # 31 день до 1 марта
    assert summary["income_change_percent"] is None     # в прошлом периоде дохода не было

    assert len(data["series"]) == 31
    march_3 = next(p for p in data["series"] if p["label"] == "2025-03-03")
    assert march_3["expense"] == "20000.00"
    assert data["series"][1]["expense"] == "0.00"  # пустой день — ноль, не дыра

    categories = {c["name"]: c for c in data["categories"]}
    assert categories["Продукты"]["amount"] == "50000.00"
    assert categories["Продукты"]["transaction_count"] == 2
    assert categories["Продукты"]["share_percent"] == "92.61"

    assert data["top_merchants"][0] == {"merchant": "MAGNUM", "amount": "50000.00", "transaction_count": 2}
    assert data["top_expenses"][0]["amount"] == "30000.00"

    recurring = data["recurring"]
    assert recurring[0]["merchant"] == "NETFLIX"
    assert recurring[0]["months"] == 3
    assert recurring[0]["amount"] == "3990.00"

    assert data["banks"][0]["bank_name"] == "Kaspi Bank"
    assert {w["weekday"] for w in data["weekdays"]} <= set(range(1, 8))


async def test_overview_year_period_with_injected_today(alice, seeded, session):
    overview = await AnalyticsOverviewService(session, today=date(2025, 3, 20)).overview(alice.id, Period.YEAR)
    assert [p.label for p in overview.series][-3:] == ["2025-01", "2025-02", "2025-03"]
    march = overview.series[-1]
    assert str(march.expense) == "53990.00"
    assert len(overview.series) == 12


async def test_overview_day_period_hourly(alice, seeded, session):
    overview = await AnalyticsOverviewService(session, today=date(2025, 3, 10)).overview(alice.id, Period.DAY)
    assert len(overview.series) == 24
    assert str(overview.series[18].expense) == "30000.00"


async def test_overview_validation(alice):
    bad = await alice.get("/analytics/overview", params={"period": "custom"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "INVALID_PERIOD"
    wrong = await alice.get("/analytics/overview", params={"period": "decade"})
    assert wrong.status_code == 422


async def test_overview_card_filter_and_isolation(alice, bob, kaspi_id):
    card = (await alice.post("/cards", json={"bank_id": kaspi_id, "last4": "7777"})).json()
    ok = await alice.get("/analytics/overview", params={"card_id": card["id"]})
    assert ok.status_code == 200
    foreign = await bob.get("/analytics/overview", params={"card_id": card["id"]})
    assert foreign.status_code == 404


async def test_overview_is_isolated_between_users(alice, bob, seeded):
    data = (await bob.get("/analytics/overview", params={"date_from": "2025-01-01", "date_to": "2025-12-31"})).json()
    assert data["summary"]["expense"] == "0.00"
    assert data["categories"] == [] and data["recurring"] == []


async def test_legacy_trend_single_query(alice, seeded):
    trend = (await alice.get("/analytics/trend", params={"months": 24})).json()
    assert len(trend) == 24
    with count_queries() as statements:
        await alice.get("/analytics/trend", params={"months": 24})
    # auth (1) + одна агрегирующая выборка, а не 2×24
    assert len(statements) <= 3


async def test_dashboard_query_count_does_not_grow(alice, session, kaspi_id):
    food = await system_category(session, "Продукты")
    await add_tx(alice, food, kaspi_id, "100", "2025-03-01T10:00:00")
    with count_queries() as few:
        assert (await alice.get("/dashboard")).status_code == 200
    for day in range(2, 20):
        await add_tx(alice, food, kaspi_id, "100", f"2025-03-{day:02d}T10:00:00")
    with count_queries() as many:
        dashboard = (await alice.get("/dashboard")).json()
    assert len(many) == len(few)
    assert len(dashboard["recent_transactions"]) == 10
    assert dashboard["recent_transactions"][0]["category"] == "Продукты"


async def test_legacy_endpoints_still_work(alice, seeded):
    for path in ("/analytics", "/analytics/cash-flow", "/analytics/categories", "/analytics/forecast",
                 "/analytics/savings", "/analytics/health", "/analytics/recommendations", "/analytics/banks"):
        response = await alice.get(path)
        assert response.status_code == 200, (path, response.text)
    full = (await alice.get("/analytics")).json()
    assert full["cash_flow"]["total_income"] == "500000.00"
    assert full["financial_health"]["status"] == "Отлично"
