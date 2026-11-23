"""T4: deposit term bounds on /deposits and legacy /investments.

Legacy rows that break a bound (stored before validation existed) are
simulated by changing a valid row in the database directly: they must be
served with ``data_issue`` and no estimate, excluded from aggregates and
never deleted.
"""

from datetime import date
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from tests.integration.helpers import API, bearer, create, register

LEGACY = {"amount": "1000000.00", "interest_rate": "14.00"}
NEW = {"principal": "1000000.00", "interest_rate": "14.00"}


@pytest.fixture
async def bank_id(db_session: AsyncSession) -> int:
    bank = Bank(name="Term Bounds Bank")
    db_session.add(bank)
    await db_session.commit()
    return bank.id


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "alice@example.com"))


@pytest.fixture
async def bob(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "bob@example.com"))


async def _legacy(
    client: httpx.AsyncClient, headers: dict[str, str], bank_id: int, start: str, end: str
) -> dict[str, Any]:
    return await create(
        client,
        "/investments",
        headers,
        {**LEGACY, "bank_id": bank_id, "start_date": start, "end_date": end},
    )


async def _corrupt(db: AsyncSession, deposit_id: int, start: date, end: date) -> None:
    """Simulate a row stored by the legacy API before T4."""

    await db.execute(
        text("UPDATE deposits SET start_date = :s, end_date = :e WHERE id = :id"),
        {"s": start, "e": end, "id": deposit_id},
    )
    await db.commit()


async def _dates(db: AsyncSession, deposit_id: int) -> tuple[date, date] | None:
    row = (
        await db.execute(
            text("SELECT start_date, end_date FROM deposits WHERE id = :id"), {"id": deposit_id}
        )
    ).one_or_none()
    return None if row is None else (row[0], row[1])


class TestNewApiWrites:
    async def test_create_accepts_600_months(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
    ) -> None:
        body = await create(
            client,
            "/deposits",
            alice,
            {**NEW, "bank_id": bank_id, "start_date": "2025-01-01", "end_date": "2075-01-01"},
        )
        assert body["data_issue"] is None
        assert body["maturity"]["term_days"] == (date(2075, 1, 1) - date(2025, 1, 1)).days

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            ("2025-01-01", "2075-01-02"),
            ("1899-12-31", "1900-06-01"),
            ("2025-01-01", "2201-01-01"),
            ("0001-01-01", "9999-12-31"),
        ],
    )
    async def test_create_rejects(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int, start: str, end: str
    ) -> None:
        response = await client.post(
            f"{API}/deposits",
            headers=alice,
            json={**NEW, "bank_id": bank_id, "start_date": start, "end_date": end},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"
        assert (await client.get(f"{API}/deposits", headers=alice)).json()["total"] == 0

    async def test_patch_term_too_long_is_coded_and_not_stored(
        self,
        client: httpx.AsyncClient,
        alice: dict[str, str],
        bank_id: int,
        db_session: AsyncSession,
    ) -> None:
        body = await create(
            client,
            "/deposits",
            alice,
            {**NEW, "bank_id": bank_id, "start_date": "2025-01-01", "end_date": "2026-01-01"},
        )
        response = await client.patch(
            f"{API}/deposits/{body['id']}", headers=alice, json={"end_date": "2075-01-02"}
        )
        assert response.status_code == 422
        assert response.json()["code"] == "term_too_long"
        assert await _dates(db_session, body["id"]) == (date(2025, 1, 1), date(2026, 1, 1))

        out_of_range = await client.patch(
            f"{API}/deposits/{body['id']}", headers=alice, json={"start_date": "1899-12-31"}
        )
        assert out_of_range.status_code == 422
        assert out_of_range.json()["code"] == "validation_error"

    async def test_calculator_rejects_maturity_after_max_date(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        response = await client.post(
            f"{API}/deposits/calculate",
            headers=alice,
            json={
                "principal": "1000",
                "interest_rate": "10",
                "start_date": "2200-01-01",
                "term_months": 600,
            },
        )
        assert response.status_code == 422
        ok = await client.post(
            f"{API}/deposits/calculate",
            headers=alice,
            json={
                "principal": "1000",
                "interest_rate": "10",
                "start_date": "2025-01-01",
                "term_months": 600,
            },
        )
        assert ok.status_code == 200
        assert ok.json()["maturity_date"] == "2075-01-01"


class TestLegacyWrites:
    async def test_post_accepts_600_months(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
    ) -> None:
        body = await _legacy(client, alice, bank_id, "2025-01-01", "2075-01-01")
        detail = (await client.get(f"{API}/investments/{body['id']}", headers=alice)).json()
        assert detail["data_issue"] is None
        assert detail["expected_profit"] is not None

    @pytest.mark.parametrize(
        ("start", "end", "code"),
        [
            ("2025-01-01", "2025-01-01", "invalid_date_range"),
            ("2025-02-01", "2025-01-01", "invalid_date_range"),
            ("2025-01-01", "2075-01-02", "term_too_long"),
            ("1899-12-31", "1900-06-01", "date_out_of_range"),
            ("2025-01-01", "9999-12-31", "date_out_of_range"),
        ],
    )
    async def test_post_rejects(
        self,
        client: httpx.AsyncClient,
        alice: dict[str, str],
        bank_id: int,
        start: str,
        end: str,
        code: str,
    ) -> None:
        response = await client.post(
            f"{API}/investments",
            headers=alice,
            json={**LEGACY, "bank_id": bank_id, "start_date": start, "end_date": end},
        )
        assert response.status_code == 422
        assert response.json()["code"] == code
        assert (await client.get(f"{API}/investments", headers=alice)).json()["total"] == 0

    @pytest.mark.parametrize(
        ("change", "code"),
        [
            ({"end_date": "2075-01-02"}, "term_too_long"),
            ({"end_date": "9999-12-31"}, "date_out_of_range"),
            ({"start_date": "2026-06-01"}, "invalid_date_range"),
            ({"start_date": "1800-01-01", "end_date": "1801-01-01"}, "date_out_of_range"),
        ],
    )
    async def test_put_rejects_and_keeps_stored_dates(
        self,
        client: httpx.AsyncClient,
        alice: dict[str, str],
        bank_id: int,
        db_session: AsyncSession,
        change: dict[str, str],
        code: str,
    ) -> None:
        body = await _legacy(client, alice, bank_id, "2025-01-01", "2026-01-01")
        response = await client.put(f"{API}/investments/{body['id']}", headers=alice, json=change)
        assert response.status_code == 422
        assert response.json()["code"] == code
        assert await _dates(db_session, body["id"]) == (date(2025, 1, 1), date(2026, 1, 1))

    async def test_put_valid_change_and_idempotent_repeat(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
    ) -> None:
        body = await _legacy(client, alice, bank_id, "2025-01-01", "2026-01-01")
        for _ in range(2):
            response = await client.put(
                f"{API}/investments/{body['id']}", headers=alice, json={"end_date": "2075-01-01"}
            )
            assert response.status_code == 200
            assert response.json()["end_date"] == "2075-01-01"

    async def test_put_on_foreign_deposit_is_404_before_validation(
        self, client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str], bank_id: int
    ) -> None:
        body = await _legacy(client, alice, bank_id, "2025-01-01", "2026-01-01")
        response = await client.put(
            f"{API}/investments/{body['id']}", headers=bob, json={"end_date": "9999-12-31"}
        )
        assert response.status_code == 404

    async def test_unauthenticated(self, client: httpx.AsyncClient, bank_id: int) -> None:
        response = await client.post(
            f"{API}/investments",
            json={
                **LEGACY,
                "bank_id": bank_id,
                "start_date": "2025-01-01",
                "end_date": "9999-12-31",
            },
        )
        assert response.status_code == 401


class TestLegacyRowsWithDataIssue:
    @pytest.fixture
    async def rows(
        self,
        client: httpx.AsyncClient,
        alice: dict[str, str],
        bank_id: int,
        db_session: AsyncSession,
    ) -> dict[str, int]:
        good = await _legacy(client, alice, bank_id, "2025-01-01", "2026-01-01")
        long_ = await _legacy(client, alice, bank_id, "2025-01-01", "2026-01-01")
        extreme = await _legacy(client, alice, bank_id, "2025-01-01", "2026-01-01")
        await _corrupt(db_session, long_["id"], date(2025, 1, 1), date(2100, 1, 1))
        await _corrupt(db_session, extreme["id"], date(2025, 1, 1), date(9999, 12, 31))
        return {"good": good["id"], "long": long_["id"], "extreme": extreme["id"]}

    async def test_new_api_reports_issue_without_estimate(
        self, client: httpx.AsyncClient, alice: dict[str, str], rows: dict[str, int]
    ) -> None:
        listing = (await client.get(f"{API}/deposits", headers=alice)).json()
        by_id = {item["id"]: item for item in listing["items"]}
        assert listing["total"] == 3  # nothing deleted or hidden
        assert by_id[rows["good"]]["data_issue"] is None
        assert by_id[rows["good"]]["maturity"]["interest"] == "140000.00"
        assert by_id[rows["long"]]["data_issue"] == "term_too_long"
        assert by_id[rows["long"]]["maturity"] is None
        detail = await client.get(f"{API}/deposits/{rows['extreme']}", headers=alice)
        assert detail.status_code == 200
        assert detail.json()["data_issue"] == "date_out_of_range"
        assert detail.json()["maturity"] is None

    async def test_legacy_detail_and_forecast(
        self, client: httpx.AsyncClient, alice: dict[str, str], rows: dict[str, int]
    ) -> None:
        for key, code in (("long", "term_too_long"), ("extreme", "date_out_of_range")):
            detail = await client.get(f"{API}/investments/{rows[key]}", headers=alice)
            assert detail.status_code == 200
            body = detail.json()
            assert body["data_issue"] == code
            assert body["expected_profit"] is None
            assert body["expected_amount"] is None
            assert body["duration_days"] is None
            forecast = (
                await client.get(f"{API}/investments/{rows[key]}/forecast", headers=alice)
            ).json()
            assert forecast["data_issue"] == code
            assert forecast["expected_profit"] is None
            assert forecast["expected_amount"] is None
        good = (await client.get(f"{API}/investments/{rows['good']}", headers=alice)).json()
        assert good["data_issue"] is None
        assert good["expected_profit"] == "140000.00"

    async def test_excluded_from_aggregates(
        self, client: httpx.AsyncClient, alice: dict[str, str], rows: dict[str, int]
    ) -> None:
        stats = (await client.get(f"{API}/investments/statistics", headers=alice)).json()
        assert stats["total_deposits"] == 1
        assert stats["total_amount"] == "1000000.00"
        assert stats["total_expected_profit"] == "140000.00"

        chart = (await client.get(f"{API}/investments/chart", headers=alice)).json()
        assert [item["amount"] for item in chart] == ["1000000.00"]

        overview = (await client.get(f"{API}/dashboard/overview", headers=alice)).json()
        assert overview["indicators"]["deposits_principal"] == "1000000.00"
        assert overview["indicators"]["deposits_expected_interest"] == "140000.00"

        dashboard = (await client.get(f"{API}/dashboard", headers=alice)).json()
        assert [d["expected_profit"] for d in dashboard["deposits"]] == ["140000.00"]

        listing = (await client.get(f"{API}/investments", headers=alice)).json()
        assert listing["total"] == 3

    async def test_advisor_facts_skip_invalid_rows(
        self, client: httpx.AsyncClient, alice: dict[str, str], rows: dict[str, int]
    ) -> None:
        response = await client.post(f"{API}/advisor/insights", headers=alice)
        assert response.status_code == 200, response.text
        labels = [f["label"] for f in response.json()["facts"]]
        assert any(label.startswith("Вклад 1:") for label in labels)
        assert not any(label.startswith("Вклад 2:") for label in labels)

    async def test_edit_without_dates_allowed_and_fix_clears_issue(
        self, client: httpx.AsyncClient, alice: dict[str, str], rows: dict[str, int]
    ) -> None:
        rate = await client.put(
            f"{API}/investments/{rows['long']}", headers=alice, json={"interest_rate": "12.00"}
        )
        assert rate.status_code == 200
        fixed = await client.patch(
            f"{API}/deposits/{rows['long']}", headers=alice, json={"end_date": "2026-01-01"}
        )
        assert fixed.status_code == 200
        assert fixed.json()["data_issue"] is None
        assert fixed.json()["maturity"]["interest"] == "120000.00"

    async def test_patch_only_start_date_is_checked_with_stored_end(
        self,
        client: httpx.AsyncClient,
        alice: dict[str, str],
        rows: dict[str, int],
        db_session: AsyncSession,
    ) -> None:
        # Stored: 2025-01-01 → 2100-01-01 (term_too_long).
        still_long = await client.patch(
            f"{API}/deposits/{rows['long']}", headers=alice, json={"start_date": "2049-12-31"}
        )
        assert still_long.status_code == 422
        assert still_long.json()["code"] == "term_too_long"
        assert await _dates(db_session, rows["long"]) == (date(2025, 1, 1), date(2100, 1, 1))

        # 2050-01-01 + 600 months = 2100-01-01: exactly the maximum, now valid.
        fixed = await client.patch(
            f"{API}/deposits/{rows['long']}", headers=alice, json={"start_date": "2050-01-01"}
        )
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["data_issue"] is None
        assert fixed.json()["maturity"] is not None
        assert fixed.json()["end_date"] == "2100-01-01"

        # Stored end 9999-12-31 stays out of range whatever the new start.
        extreme = await client.patch(
            f"{API}/deposits/{rows['extreme']}", headers=alice, json={"start_date": "2026-01-01"}
        )
        assert extreme.status_code == 422
        assert extreme.json()["code"] == "date_out_of_range"
        assert await _dates(db_session, rows["extreme"]) == (date(2025, 1, 1), date(9999, 12, 31))

        # Same rule on the legacy PUT.
        legacy = await client.put(
            f"{API}/investments/{rows['extreme']}", headers=alice, json={"start_date": "2026-01-01"}
        )
        assert legacy.status_code == 422
        assert legacy.json()["code"] == "date_out_of_range"

    async def test_not_visible_to_other_users(
        self, client: httpx.AsyncClient, bob: dict[str, str], rows: dict[str, int]
    ) -> None:
        assert (
            await client.get(f"{API}/investments/{rows['long']}", headers=bob)
        ).status_code == 404
        assert (await client.get(f"{API}/deposits/{rows['long']}", headers=bob)).status_code == 404


class TestSqlClauseMatchesPython:
    @pytest.mark.parametrize(
        ("start", "end", "counted"),
        [
            (date(2024, 2, 29), date(2074, 2, 28), True),  # leap start, clamped 600 months
            (date(2024, 2, 29), date(2074, 3, 1), False),
            (date(2025, 1, 31), date(2075, 1, 31), True),
            (date(2025, 1, 1), date(2075, 1, 2), False),
            (date(1900, 1, 1), date(1900, 1, 2), True),
            (date(1899, 12, 31), date(1900, 1, 2), False),
            (date(2200, 12, 30), date(2200, 12, 31), True),
        ],
    )
    async def test_chart_filter(
        self,
        client: httpx.AsyncClient,
        alice: dict[str, str],
        bank_id: int,
        db_session: AsyncSession,
        start: date,
        end: date,
        counted: bool,
    ) -> None:
        body = await _legacy(client, alice, bank_id, "2025-01-01", "2026-01-01")
        await _corrupt(db_session, body["id"], start, end)
        chart = (await client.get(f"{API}/investments/chart", headers=alice)).json()
        stats = (await client.get(f"{API}/investments/statistics", headers=alice)).json()
        assert bool(chart) is counted
        assert stats["total_deposits"] == (1 if counted else 0)
