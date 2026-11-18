"""Banks reference API, financial goals, category kinds and financial edge
scenarios over HTTP. Expected values are computed by hand in the comments."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from tests import import_fixtures as fx
from tests.integration.helpers import API, bearer, category, create, register, tx

ALMATY = ZoneInfo("Asia/Almaty")
SEEDED_BANKS = {
    "Kaspi Bank",
    "Halyk Bank",
    "Freedom Bank",
    "Jusan Bank",
    "ForteBank",
    "Bank CenterCredit",
    "Home Credit Bank",
    "Eurasian Bank",
    "Bereke Bank",
    "Otbasy Bank",
    "Altyn Bank",
    "Nurbank",
    "Bank RBK",
    "Shinhan Bank Kazakhstan",
    "Другой банк",
}


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "alice@example.com"))


@pytest.fixture
async def bob(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "bob@example.com"))


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


# --------------------------------------------------------------------------- banks


class TestBanks:
    async def test_seeded_list_and_deposit_creation(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        response = await client.get(f"{API}/banks", headers=alice)
        assert response.status_code == 200, response.text
        banks = response.json()
        names = [b["name"] for b in banks]
        assert SEEDED_BANKS <= set(names)
        assert names == sorted(names)

        halyk = next(b["id"] for b in banks if b["name"] == "Halyk Bank")
        deposit = await create(
            client,
            "/deposits",
            alice,
            {
                "bank_id": halyk,
                "principal": "1000000.00",
                "interest_rate": "14.00",
                "capitalization": "annually",
                "start_date": "2025-01-01",
                "end_date": "2027-01-01",
            },
        )
        # 1 000 000 · (1.14² − 1) = 1 000 000 · 0.2996 = 299 600.00
        assert deposit["maturity"]["interest"] == "299600.00"

    async def test_requires_authentication(self, client: httpx.AsyncClient) -> None:
        assert (await client.get(f"{API}/banks")).status_code == 401

    async def test_unknown_bank_is_rejected(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        response = await client.post(
            f"{API}/deposits",
            headers=alice,
            json={
                "bank_id": 999_999,
                "principal": "1000",
                "interest_rate": "10",
                "start_date": "2025-01-01",
                "end_date": "2026-01-01",
            },
        )
        assert response.status_code in (400, 404, 422), response.text


# --------------------------------------------------------------------------- goals


class TestGoals:
    async def test_crud_and_calculations(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        today = datetime.now(ALMATY).date()
        target_date = _add_months(today, 12)  # 12 calendar months ahead
        goal = await create(
            client,
            "/goals",
            alice,
            {
                "name": "Подушка безопасности",
                "target_amount": "1200000.00",
                "saved_amount": "300000.00",
                "target_date": target_date.isoformat(),
            },
        )
        assert goal["currency_code"] == "KZT"  # user's default currency
        assert goal["progress_percent"] == "25.00"  # 300 000 / 1 200 000
        assert goal["remaining"] == "900000.00"
        assert goal["is_reached"] is False
        assert goal["months_left"] == 12
        assert goal["required_monthly_saving"] == "75000.00"  # 900 000 / 12

        listed = (await client.get(f"{API}/goals", headers=alice)).json()
        assert [g["id"] for g in listed] == [goal["id"]]

        # 1 000 000 / 3 = 333 333.333… → 333 333.33 (ROUND_HALF_UP)
        patched = await client.patch(
            f"{API}/goals/{goal['id']}",
            headers=alice,
            json={
                "target_amount": "1000000.00",
                "saved_amount": "0",
                "target_date": _add_months(today, 3).isoformat(),
            },
        )
        assert patched.status_code == 200, patched.text
        body = patched.json()
        assert (body["months_left"], body["required_monthly_saving"]) == (3, "333333.33")
        assert body["progress_percent"] == "0.00"

        # Over-saved: progress above 100 %, nothing remaining, no monthly need.
        over = await client.patch(
            f"{API}/goals/{goal['id']}", headers=alice, json={"saved_amount": "1500000.00"}
        )
        body = over.json()
        assert (body["progress_percent"], body["remaining"], body["is_reached"]) == (
            "150.00",
            "0.00",
            True,
        )
        assert body["required_monthly_saving"] is None

        # No date / past date: no month count.
        cleared = await client.patch(
            f"{API}/goals/{goal['id']}",
            headers=alice,
            json={"target_date": None, "saved_amount": "0"},
        )
        assert (cleared.json()["months_left"], cleared.json()["required_monthly_saving"]) == (
            None,
            None,
        )
        past = await client.patch(
            f"{API}/goals/{goal['id']}", headers=alice, json={"target_date": "2020-01-01"}
        )
        assert past.json()["months_left"] is None

        deleted = await client.delete(f"{API}/goals/{goal['id']}", headers=alice)
        assert deleted.status_code == 204
        assert (await client.get(f"{API}/goals/{goal['id']}", headers=alice)).status_code == 404

    async def test_other_users_goal_is_not_found(
        self, client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str]
    ) -> None:
        goal = await create(client, "/goals", alice, {"name": "Отпуск", "target_amount": "500000"})
        url = f"{API}/goals/{goal['id']}"
        assert (await client.get(url, headers=bob)).status_code == 404
        assert (await client.patch(url, headers=bob, json={"name": "X-hacked"})).status_code == 404
        assert (await client.delete(url, headers=bob)).status_code == 404
        assert (await client.get(f"{API}/goals", headers=bob)).json() == []
        assert (await client.get(url, headers=alice)).json()["name"] == "Отпуск"

    @pytest.mark.parametrize(
        "body",
        [
            {"name": "Цель", "target_amount": "0"},
            {"name": "Цель", "target_amount": "-1"},
            {"name": "Цель", "target_amount": "100.001"},
            {"name": "Цель", "target_amount": "100", "saved_amount": "-1"},
            {"name": "Цель", "target_amount": "100", "currency": "XYZ"},
            {"name": "", "target_amount": "100"},
        ],
    )
    async def test_validation(
        self, client: httpx.AsyncClient, alice: dict[str, str], body: dict
    ) -> None:  # type: ignore[type-arg]
        response = await client.post(f"{API}/goals", headers=alice, json=body)
        assert response.status_code in (400, 422), response.text

    async def test_duplicate_name_and_auth(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        await create(client, "/goals", alice, {"name": "Машина", "target_amount": "100"})
        duplicate = await client.post(
            f"{API}/goals", headers=alice, json={"name": "Машина", "target_amount": "200"}
        )
        assert duplicate.status_code == 409
        assert (await client.get(f"{API}/goals")).status_code == 401
        null_name = await client.patch(f"{API}/goals/1", headers=alice, json={"name": None})
        assert null_name.status_code in (404, 422)


# --------------------------------------------------------------------------- category kinds


async def _categories(
    client: httpx.AsyncClient, headers: dict[str, str], **params: str
) -> dict[str, dict]:  # type: ignore[type-arg]
    response = await client.get(f"{API}/categories", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return {c["name"]: c for c in response.json()}


class TestCategoryKinds:
    async def test_system_kinds_and_filter(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        everything = await _categories(client, alice)
        assert everything["Зарплата"]["kind"] == "income"
        assert everything["Прочие доходы"]["kind"] == "income"
        assert everything["Продукты"]["kind"] == "expense"
        assert everything["Без категории"]["kind"] == "any"
        assert everything["Переводы между своими счетами"]["kind"] == "any"

        own = await create(client, "/categories", alice, {"name": "Фриланс", "kind": "income"})
        assert own["kind"] == "income"
        assert (await create(client, "/categories", alice, {"name": "Разное"}))["kind"] == "any"

        income = await _categories(client, alice, kind="income")
        assert {"Зарплата", "Фриланс", "Без категории", "Разное"} <= set(income)
        assert "Продукты" not in income
        expense = await _categories(client, alice, kind="expense")
        assert "Продукты" in expense and "Зарплата" not in expense and "Фриланс" not in expense

        bad = await client.get(f"{API}/categories", headers=alice, params={"kind": "salary"})
        assert bad.status_code == 422
        invalid = await client.post(
            f"{API}/categories", headers=alice, json={"name": "Плохая", "kind": "salary"}
        )
        assert invalid.status_code == 422

    async def test_transaction_type_must_fit_category(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        cats = await _categories(client, alice)
        salary, food = cats["Зарплата"]["id"], cats["Продукты"]["id"]
        when = "2025-03-10T12:00:00+05:00"

        for category_id, kind in [(salary, "expense"), (salary, "refund"), (food, "income")]:
            response = await client.post(
                f"{API}/transactions",
                headers=alice,
                json={
                    "amount": "100",
                    "transaction_type": kind,
                    "transaction_date": when,
                    "category_id": category_id,
                },
            )
            assert response.status_code == 400, (category_id, kind, response.text)
            assert "cannot be used" in response.json()["detail"]

        await tx(client, alice, salary, "500000", "income", when)
        await tx(client, alice, food, "100", "refund", when)  # refund reduces spending
        await tx(client, alice, salary, "100", "transfer_out", when)  # transfers: any category

        expense = await tx(client, alice, food, "2000", "expense", when)
        url = f"{API}/transactions/{expense['id']}"
        changed_type = await client.patch(url, headers=alice, json={"transaction_type": "income"})
        assert changed_type.status_code == 400
        changed_cat = await client.patch(url, headers=alice, json={"category_id": salary})
        assert changed_cat.status_code == 400
        both = await client.patch(
            url, headers=alice, json={"category_id": salary, "transaction_type": "income"}
        )
        assert both.status_code == 200, both.text

    async def test_budget_rejects_income_category(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        cats = await _categories(client, alice)
        response = await client.post(
            f"{API}/budgets",
            headers=alice,
            json={
                "title": "Зарплата",
                "monthly_limit": "1000",
                "category_id": cats["Зарплата"]["id"],
            },
        )
        assert response.status_code == 400, response.text
        await create(
            client,
            "/budgets",
            alice,
            {"title": "Еда", "monthly_limit": "1000", "category_id": cats["Продукты"]["id"]},
        )

    async def test_kind_change_must_fit_existing_transactions(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        own = await category(client, alice, "Хобби")  # kind any
        await tx(client, alice, own, "1500", "expense", "2025-03-10T12:00:00+05:00")
        url = f"{API}/categories/{own}"
        conflict = await client.patch(url, headers=alice, json={"kind": "income"})
        assert conflict.status_code == 409, conflict.text
        ok = await client.patch(url, headers=alice, json={"kind": "expense"})
        assert (ok.status_code, ok.json()["kind"]) == (200, "expense")

    async def test_import_falls_back_when_hint_does_not_fit(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        content = fx.csv_bytes(
            header=[*fx.HEADER, "Категория"],
            rows=[
                ["01.03.2025", "+1 000,00 ₸", "KZT", "Пополнение", "Кэшбэк", "Продукты"],
                ["02.03.2025", "-500,00 ₸", "KZT", "Покупка", "Магазин", "Продукты"],
            ],
        )
        preview = await client.post(
            f"{API}/imports/kaspi/preview",
            headers=alice,
            files={"file": ("s.csv", content, "text/csv")},
        )
        assert preview.status_code == 201, preview.text
        import_id = preview.json()["import"]["id"]
        committed = await client.post(f"{API}/imports/{import_id}/commit", headers=alice, json={})
        assert committed.status_code == 200, committed.text

        cats = {
            c["id"]: c["name"]
            for c in (await client.get(f"{API}/categories", headers=alice)).json()
        }
        items = (await client.get(f"{API}/transactions", headers=alice)).json()["items"]
        by_type = {t["transaction_type"]: cats[t["category_id"]] for t in items}
        assert by_type == {"income": "Без категории", "expense": "Продукты"}


# --------------------------------------------------------------------------- scenarios


class TestFinancialScenarios:
    async def test_empty_month(self, client: httpx.AsyncClient, alice: dict[str, str]) -> None:
        response = await client.get(
            f"{API}/analytics/summary",
            headers=alice,
            params={"date_from": "2025-02-01", "date_to": "2025-02-28"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["income"], body["net_expenses"], body["net_cash_flow"]) == (
            "0.00",
            "0.00",
            "0.00",
        )
        assert body["transaction_count"] == 0
        assert body["savings_rate"] is None  # undefined without income, not 0 %

    async def test_leap_day_belongs_to_february(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        food = (await _categories(client, alice))["Продукты"]["id"]
        await tx(client, alice, food, "1000", "expense", "2024-02-29T23:59:00+05:00")
        await tx(client, alice, food, "7", "expense", "2024-03-01T00:00:00+05:00")
        feb = await client.get(
            f"{API}/analytics/summary",
            headers=alice,
            params={"date_from": "2024-02-01", "date_to": "2024-02-29"},
        )
        assert feb.json()["net_expenses"] == "1000.00"
        invalid = await client.get(
            f"{API}/analytics/summary",
            headers=alice,
            params={"date_from": "2025-02-01", "date_to": "2025-02-29"},  # not a leap year
        )
        assert invalid.status_code == 422

    async def test_very_large_amounts_stay_exact(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        cats = await _categories(client, alice)
        when = "2025-03-10T12:00:00+05:00"
        await tx(client, alice, cats["Зарплата"]["id"], "9999999999999999.99", "income", when)
        await tx(client, alice, cats["Продукты"]["id"], "0.01", "expense", when)
        summary = (
            await client.get(
                f"{API}/analytics/summary",
                headers=alice,
                params={"date_from": "2025-03-01", "date_to": "2025-03-31"},
            )
        ).json()
        # 9 999 999 999 999 999.99 − 0.01 = 9 999 999 999 999 999.98 (float would lose cents)
        assert summary["income"] == "9999999999999999.99"
        assert summary["net_cash_flow"] == "9999999999999999.98"
        too_big = await client.post(
            f"{API}/transactions",
            headers=alice,
            json={
                "amount": "10000000000000000.00",
                "transaction_type": "income",
                "transaction_date": when,
                "category_id": cats["Зарплата"]["id"],
            },
        )
        assert too_big.status_code == 422

    async def test_zero_budget_limit_and_zero_rate_deposit(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        zero = await client.post(
            f"{API}/budgets", headers=alice, json={"title": "Ноль", "monthly_limit": "0"}
        )
        assert zero.status_code == 422
        calc = await client.post(
            f"{API}/deposits/calculate",
            headers=alice,
            json={
                "principal": "1000000",
                "interest_rate": "0",
                "capitalization": "monthly",
                "start_date": "2025-01-01",
                "term_months": 12,
            },
        )
        assert calc.status_code == 200, calc.text
        assert calc.json()["maturity"]["interest"] == "0.00"
        assert calc.json()["maturity"]["maturity_amount"] == "1000000.00"
