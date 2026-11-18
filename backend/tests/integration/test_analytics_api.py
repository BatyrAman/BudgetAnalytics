"""Engine-based analytics endpoints. Every expected number is hand-checked
in the comments below (Asia/Almaty = UTC+5 in 2025)."""

from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.transaction import TransactionRepository
from app.services.finance import KZT, monthly_summaries, year_period
from tests.integration.helpers import API, bearer, category, create, register, tx

ALMATY = {"tz": "Asia/Almaty"}
MARCH = {"date_from": "2025-03-01", "date_to": "2025-03-31", **ALMATY}


@pytest.fixture
async def data(client: httpx.AsyncClient) -> dict[str, object]:
    alice = bearer(await register(client, "alice@example.com"))
    bob = bearer(await register(client, "bob@example.com"))
    work = await category(client, alice, "Работа")
    food = await category(client, alice, "Еда")
    rent = await category(client, alice, "Аренда")
    moves = await category(client, alice, "Переводы")
    for cat, amount, kind, when, extra in [
        # February: income 400 000, expenses 300 000
        (work, "400000", "income", "2025-02-05T10:00:00+05:00", {}),
        (rent, "300000", "expense", "2025-02-10T10:00:00+05:00", {}),
        # March: income 600 000; expenses 260 000 − refund 5 000 = 255 000
        (work, "500000", "income", "2025-03-05T10:00:00+05:00", {}),
        (work, "100000", "income", "2025-03-31T23:30:00+05:00", {}),  # last local minute of March
        (food, "60000", "expense", "2025-03-10T10:00:00+05:00", {}),
        (food, "5000", "refund", "2025-03-12T10:00:00+05:00", {}),
        (
            rent,
            "200000",
            "expense",
            "2025-03-01T00:00:00+05:00",
            {},
        ),  # first local instant of March
        (moves, "100000", "transfer_out", "2025-03-20T10:00:00+05:00", {}),  # excluded
        (food, "70", "expense", "2025-03-15T10:00:00+05:00", {"currency": "USD"}),  # other currency
        # April
        (food, "999", "expense", "2025-04-01T00:00:00+05:00", {}),
    ]:
        await tx(client, alice, cat, amount, kind, when, **extra)
    return {"alice": alice, "bob": bob, "food": food, "rent": rent}


async def _get(
    client: httpx.AsyncClient, path: str, headers: dict[str, str], **params: object
) -> dict:  # type: ignore[type-arg]
    response = await client.get(f"{API}/analytics/{path}", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_summary(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    body = await _get(client, "summary", data["alice"], **MARCH)
    assert body["currency_code"] == "KZT"
    assert body["income"] == "600000.00"
    assert body["gross_expenses"] == "260000.00"
    assert body["refunds"] == "5000.00"
    assert body["net_expenses"] == "255000.00"
    assert body["net_cash_flow"] == "345000.00"  # 600 000 − 255 000
    assert body["transfers_out"] == "100000.00"
    assert body["savings_rate"] == "57.50"  # 345 000 / 600 000
    assert body["transaction_count"] == 6  # USD row excluded
    assert body["period"] == {
        "date_from": "2025-03-01",
        "date_to": "2025-03-31",
        "timezone": "Asia/Almaty",
    }


async def test_time_zone_changes_month_boundaries(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    # In UTC: the rent at 2025-03-01T00:00+05:00 (= Feb 28 19:00Z) moves to February,
    # and the 999 expense at 2025-04-01T00:00+05:00 (= Mar 31 19:00Z) moves INTO March:
    # 60 000 − 5 000 + 999 = 55 999.
    body = await _get(
        client, "summary", data["alice"], date_from="2025-03-01", date_to="2025-03-31", tz="UTC"
    )
    assert body["net_expenses"] == "55999.00"
    assert body["income"] == "600000.00"  # Mar 31 23:30+05 = 18:30Z is still March in UTC


async def test_currency_is_never_mixed(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    body = await _get(client, "summary", data["alice"], currency="USD", **MARCH)
    assert body["net_expenses"] == "70.00" and body["income"] == "0.00"
    assert body["savings_rate"] is None  # no income -> undefined, not 0


async def test_income_and_expenses_by_category(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    income = await _get(client, "income", data["alice"], **MARCH)
    assert income["total"] == "600000.00"
    assert [(c["name"], c["amount"], c["share_percent"]) for c in income["by_category"]] == [
        ("Работа", "600000.00", "100.00")
    ]

    expenses = await _get(client, "expenses", data["alice"], **MARCH)
    assert (expenses["gross_expenses"], expenses["refunds"], expenses["net_expenses"]) == (
        "260000.00",
        "5000.00",
        "255000.00",
    )
    # Аренда 200 000 / 255 000 = 78.43 %; Еда (60 000 − 5 000) / 255 000 = 21.57 %;
    # the transfer category has no net expense and is omitted.
    assert [
        (c["name"], c["amount"], c["share_percent"], c["transaction_count"])
        for c in expenses["by_category"]
    ] == [
        ("Аренда", "200000.00", "78.43", 1),
        ("Еда", "55000.00", "21.57", 2),
    ]


async def test_category_breakdown_kind(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    body = await _get(client, "category-breakdown", data["alice"], kind="income", **MARCH)
    assert body["kind"] == "income" and body["total"] == "600000.00"
    bad = await client.get(
        f"{API}/analytics/category-breakdown", headers=data["alice"], params={"kind": "x"}
    )
    assert bad.status_code == 422


async def test_savings_rate(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    body = await _get(client, "savings-rate", data["alice"], **MARCH)
    assert body["savings_rate"] == "57.50"
    assert body["expense_to_income_percent"] == "42.50"  # 255 000 / 600 000


async def test_monthly(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    body = await _get(client, "monthly", data["alice"], year=2025, **ALMATY)
    months = {m["month"]: m for m in body["months"]}
    assert len(months) == 12
    assert months["2025-02"]["net_cash_flow"] == "100000.00"
    assert months["2025-02"]["savings_rate"] == "25.00"
    assert months["2025-03"]["net_expenses"] == "255000.00"
    assert months["2025-04"]["net_expenses"] == "999.00"
    assert months["2025-05"]["transaction_count"] == 0  # empty months present
    assert body["total"]["income"] == "1000000.00"
    assert body["total"]["net_expenses"] == "555999.00"  # 300 000 + 255 000 + 999


async def test_comparison(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    body = await _get(client, "comparison", data["alice"], month="2025-03", **ALMATY)
    assert body["income"] == {
        "current": "600000.00",
        "previous": "400000.00",
        "change": "200000.00",
        "change_percent": "50.00",
    }
    assert body["net_expenses"]["change"] == "-45000.00"
    assert body["net_expenses"]["change_percent"] == "-15.00"  # 255 000 vs 300 000
    assert body["net_cash_flow"]["change_percent"] == "245.00"  # 345 000 vs 100 000
    assert body["savings_rate_change_pp"] == "32.50"  # 57.50 − 25.00

    january = await _get(client, "comparison", data["alice"], month="2025-02", **ALMATY)
    assert january["income"]["change_percent"] is None  # previous month (January) had no income


async def test_users_see_only_their_data(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    body = await _get(client, "summary", data["bob"], **MARCH)
    assert body["income"] == body["net_expenses"] == "0.00"
    assert (await _get(client, "expenses", data["bob"], **MARCH))["by_category"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "2025-03-31", "date_to": "2025-03-01"},
        {"date_from": "2015-01-01", "date_to": "2025-01-01"},  # more than 5 years
        {"tz": "Mars/Olympus"},
        {"currency": "XYZ"},
        {"currency": "usd"},
    ],
)
async def test_invalid_parameters(client: httpx.AsyncClient, data: dict, params: dict) -> None:  # type: ignore[type-arg]
    response = await client.get(f"{API}/analytics/summary", headers=data["alice"], params=params)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "summary",
        "income",
        "expenses",
        "savings-rate",
        "category-breakdown",
        "comparison",
        "monthly?year=2025",
    ],
)
async def test_authentication_required(client: httpx.AsyncClient, path: str) -> None:
    assert (await client.get(f"{API}/analytics/{path}")).status_code == 401


@pytest.mark.parametrize("tz", ["Asia/Almaty", "UTC", "America/New_York"])
async def test_sql_month_grouping_matches_engine_boundaries(
    client: httpx.AsyncClient, db_session: AsyncSession, tz: str
) -> None:
    """SQL GROUP BY local month must agree with the engine's Python periods,
    including Almaty's 2024-03-01 switch from UTC+6 to UTC+5 and US DST."""

    headers = bearer(await register(client, "tz@example.com"))
    cid = await category(client, headers, "TZ")
    for when in [
        "2024-02-29T17:59:00Z",  # Almaty (+6): Feb 29 23:59
        "2024-02-29T18:00:00Z",  # Almaty (+6): Mar 1 00:00
        "2024-03-10T06:59:00Z",  # New York DST switch morning
        "2024-03-31T18:59:00Z",  # Almaty (+5): Mar 31 23:59
        "2024-03-31T19:00:00Z",  # Almaty (+5): Apr 1 00:00
        "2024-11-01T03:59:00Z",  # New York (−4): Oct 31 23:59
        "2024-11-01T04:00:00Z",  # New York (−4): Nov 1 00:00
    ]:
        await tx(client, headers, cid, "100", "expense", when)

    api = await _get(client, "monthly", headers, year=2024, tz=tz)
    from_api = {m["month"]: (m["net_expenses"], m["transaction_count"]) for m in api["months"]}

    zone = ZoneInfo(tz)
    period = year_period(2024, zone)
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    items = await TransactionRepository(db_session).cashflow_items(
        me["id"], period.start, period.end
    )
    engine = {
        m.period.label: (str(m.totals.net_expenses), m.totals.transaction_count)
        for m in monthly_summaries(items, 2024, KZT, zone)
    }
    assert from_api == engine
    assert sum(count for _, count in from_api.values()) == 7


async def test_budgets_api_with_utilization(client: httpx.AsyncClient, data: dict) -> None:  # type: ignore[type-arg]
    alice, bob = data["alice"], data["bob"]
    food = await create(
        client,
        "/budgets",
        alice,
        {"title": "Еда", "monthly_limit": "50000.00", "category_id": data["food"]},
    )
    everything = await create(
        client, "/budgets", alice, {"title": "Всё", "monthly_limit": "300000.00"}
    )
    assert food["currency_code"] == "KZT" and food["category_id"] == data["food"]

    util = (
        await client.get(
            f"{API}/budgets/{food['id']}/utilization",
            headers=alice,
            params={"month": "2025-03", **ALMATY},
        )
    ).json()
    # Еда: 60 000 − 5 000 = 55 000 of 50 000 -> 110 %, over by 5 000 (USD row excluded)
    assert (util["spent"], util["utilization_percent"], util["remaining"], util["is_exceeded"]) == (
        "55000.00",
        "110.00",
        "-5000.00",
        True,
    )
    util_all = (
        await client.get(
            f"{API}/budgets/{everything['id']}/utilization",
            headers=alice,
            params={"month": "2025-03", **ALMATY},
        )
    ).json()
    assert (util_all["spent"], util_all["utilization_percent"]) == ("255000.00", "85.00")

    assert (
        await client.get(f"{API}/budgets/{food['id']}/utilization", headers=bob)
    ).status_code == 404
    patched = await client.patch(
        f"{API}/budgets/{food['id']}", headers=alice, json={"monthly_limit": "60000.00"}
    )
    assert patched.status_code == 200 and patched.json()["monthly_limit"] == "60000.00"
    bad_month = await client.get(
        f"{API}/budgets/{food['id']}/utilization", headers=alice, params={"month": "2025-13"}
    )
    assert bad_month.status_code == 422
    foreign = await category(client, bob, "Чужая")
    assert (
        await client.patch(
            f"{API}/budgets/{food['id']}", headers=alice, json={"category_id": foreign}
        )
    ).status_code == 400
    listed = (await client.get(f"{API}/budgets", headers=alice)).json()
    assert (listed["total"], listed["limit"], listed["offset"]) == (2, 20, 0)
