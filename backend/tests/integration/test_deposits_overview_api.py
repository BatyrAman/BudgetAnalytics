"""Deposits (CRUD + calculator) and the dashboard overview."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from tests.integration.helpers import API, bearer, category, create, register, tx

ALMATY = ZoneInfo("Asia/Almaty")


@pytest.fixture
async def bank_id(db_session: AsyncSession) -> int:
    bank = Bank(name="Test Deposit Bank")
    db_session.add(bank)
    await db_session.commit()
    return bank.id


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "alice@example.com"))


@pytest.fixture
async def bob(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "bob@example.com"))


class TestDeposits:
    async def test_crud_and_maturity(
        self, client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str], bank_id: int
    ) -> None:
        deposit = await create(
            client,
            "/deposits",
            alice,
            {
                "bank_id": bank_id,
                "principal": "1000000.00",
                "interest_rate": "16.00",
                "effective_rate": "17.2",
                "capitalization": "monthly",
                "start_date": "2025-01-01",
                "end_date": "2026-01-01",
            },
        )
        m = deposit["maturity"]
        # 1 000 000 · ((1 + 0.16/12)^12 − 1) = 172 270.80 ; EAR = 17.2271 %
        assert (m["interest"], m["maturity_amount"], m["effective_annual_rate"]) == (
            "172270.80",
            "1172270.80",
            "17.2271",
        )
        assert (m["capitalization_periods"], m["stub_days"], m["term_days"]) == (12, 0, 365)
        assert deposit["effective_rate"] == "17.2000"  # bank's ГЭСВ stored as given, separately
        did = deposit["id"]

        simple = await client.patch(
            f"{API}/deposits/{did}", headers=alice, json={"capitalization": "none"}
        )
        assert simple.json()["maturity"]["interest"] == "160000.00"
        assert simple.json()["maturity"]["effective_annual_rate"] is None

        for method, kwargs in (
            ("get", {}),
            ("patch", {"json": {"principal": "1.00"}}),
            ("delete", {}),
        ):
            assert (
                await getattr(client, method)(f"{API}/deposits/{did}", headers=bob, **kwargs)
            ).status_code == 404
        assert (await client.get(f"{API}/deposits", headers=bob)).json()["total"] == 0

        assert (await client.delete(f"{API}/deposits/{did}", headers=alice)).status_code == 204
        assert (await client.get(f"{API}/deposits/{did}", headers=alice)).status_code == 404

    @pytest.mark.parametrize(
        "changes",
        [
            {"end_date": "2024-12-31"},  # before start
            {"principal": None},
            {"interest_rate": "100.01"},
            {"principal": "0"},
        ],
    )
    async def test_invalid_updates(
        self,
        client: httpx.AsyncClient,
        alice: dict[str, str],
        bank_id: int,
        changes: dict,  # type: ignore[type-arg]
    ) -> None:
        did = (
            await create(
                client,
                "/deposits",
                alice,
                {
                    "bank_id": bank_id,
                    "principal": "1000",
                    "interest_rate": "10",
                    "start_date": "2025-01-01",
                    "end_date": "2026-01-01",
                },
            )
        )["id"]
        assert (
            await client.patch(f"{API}/deposits/{did}", headers=alice, json=changes)
        ).status_code == 422

    async def test_calculator(self, client: httpx.AsyncClient, alice: dict[str, str]) -> None:
        quarterly = await client.post(
            f"{API}/deposits/calculate",
            headers=alice,
            json={
                "principal": "500000",
                "interest_rate": "12",
                "capitalization": "quarterly",
                "start_date": "2025-01-31",
                "end_date": "2025-08-15",
            },
        )
        # Anniversaries Apr 30, Jul 31; 500 000·1.03² = 530 450; + 15-day stub -> 33 065.92
        assert quarterly.json()["maturity"]["interest"] == "33065.92"
        by_months = await client.post(
            f"{API}/deposits/calculate",
            headers=alice,
            json={
                "principal": "1000000",
                "interest_rate": "16",
                "capitalization": "monthly",
                "start_date": "2025-01-01",
                "term_months": 12,
            },
        )
        assert by_months.json()["maturity_date"] == "2026-01-01"
        assert by_months.json()["maturity"]["interest"] == "172270.80"

    @pytest.mark.parametrize(
        "body",
        [
            {"start_date": "2025-01-01"},  # neither end_date nor term_months
            {"start_date": "2025-01-01", "end_date": "2026-01-01", "term_months": 12},  # both
            {"start_date": "2025-01-01", "end_date": "2025-01-01"},  # zero term
            {"start_date": "2025-01-01", "term_months": 12, "currency": "XYZ"},
        ],
    )
    async def test_calculator_validation(
        self, client: httpx.AsyncClient, alice: dict[str, str], body: dict
    ) -> None:  # type: ignore[type-arg]
        response = await client.post(
            f"{API}/deposits/calculate",
            headers=alice,
            json={"principal": "1000", "interest_rate": "10", **body},
        )
        assert response.status_code in (400, 422)

    async def test_legacy_investments_still_work(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
    ) -> None:
        legacy = await create(
            client,
            "/investments",
            alice,
            {
                "amount": "1000000.00",
                "interest_rate": "14.00",
                "start_date": "2025-01-01",
                "end_date": "2026-01-01",
                "bank_id": bank_id,
            },
        )
        detail = (await client.get(f"{API}/investments/{legacy['id']}", headers=alice)).json()
        assert detail["expected_profit"] == "140000.00"
        assert (
            await client.get(f"{API}/deposits/{legacy['id']}", headers=alice)
        ).status_code == 200


def _local_month_start(months_ago: int) -> datetime:
    today = datetime.now(ALMATY).date()
    index = today.year * 12 + today.month - 1 - months_ago
    return datetime.combine(
        today.replace(year=index // 12, month=index % 12 + 1, day=1), time(12), tzinfo=ALMATY
    )


class TestOverview:
    async def test_overview_numbers(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
    ) -> None:
        opening_at = (_local_month_start(4) - timedelta(days=1)).astimezone(UTC).isoformat()
        account = await create(
            client,
            "/accounts",
            alice,
            {
                "name": "Main",
                "account_type": "current",
                "opening_balance": "1000000.00",
                "opening_balance_at": opening_at,
            },
        )
        cid = await category(client, alice, "Всё")
        for months_ago in (1, 2, 3):  # 300 000 each -> 3-month average 300 000
            await tx(
                client,
                alice,
                cid,
                "300000",
                "expense",
                _local_month_start(months_ago).isoformat(),
                account_id=account["id"],
            )
        now_month = _local_month_start(0).isoformat()
        await tx(client, alice, cid, "500000", "income", now_month, account_id=account["id"])
        await tx(client, alice, cid, "100000", "expense", now_month, account_id=account["id"])
        await create(client, "/budgets", alice, {"title": "Лимит", "monthly_limit": "80000.00"})
        await create(
            client,
            "/deposits",
            alice,
            {
                "bank_id": bank_id,
                "principal": "1000000",
                "interest_rate": "14",
                "start_date": "2025-01-01",
                "end_date": "2026-01-01",
            },
        )

        body = (
            await client.get(
                f"{API}/dashboard/overview", headers=alice, params={"tz": "Asia/Almaty"}
            )
        ).json()
        # 1 000 000 − 3·300 000 + 500 000 − 100 000 = 500 000
        assert body["current_balance"] == "500000.00"
        assert (
            body["monthly_income"],
            body["monthly_expenses"],
            body["monthly_net_cash_flow"],
        ) == (
            "500000.00",
            "100000.00",
            "400000.00",
        )
        ind = body["indicators"]
        assert ind["savings_rate"] == "80.00"  # 400 000 / 500 000
        assert ind["expense_to_income_percent"] == "20.00"
        assert ind["expense_change_percent"] == "-66.67"  # 100 000 vs 300 000
        assert ind["income_change_percent"] is None  # no income last month
        assert ind["average_monthly_expenses_3m"] == "300000.00"
        assert ind["emergency_fund_months"] == "1.67"  # 500 000 / 300 000
        assert (ind["budgets_total"], ind["budgets_exceeded"]) == (1, 1)  # 100 000 > 80 000
        assert (ind["deposits_principal"], ind["deposits_expected_interest"]) == (
            "1000000.00",
            "140000.00",
        )
        assert body["budgets"][0]["utilization_percent"] == "125.00"
        assert body["notes"]

    async def test_without_accounts_balance_is_null(
        self, client: httpx.AsyncClient, bob: dict[str, str]
    ) -> None:
        body = (await client.get(f"{API}/dashboard/overview", headers=bob)).json()
        assert body["current_balance"] is None
        assert body["indicators"]["emergency_fund_months"] is None
        assert body["indicators"]["savings_rate"] is None
        assert body["monthly_income"] == "0.00"

    async def test_requires_authentication(self, client: httpx.AsyncClient) -> None:
        assert (await client.get(f"{API}/dashboard/overview")).status_code == 401
