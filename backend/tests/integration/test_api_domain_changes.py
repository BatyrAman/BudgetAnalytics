"""API behavior changed by the core-domain step: per-user categories, UTC
timestamps, database-constraint errors and import validation."""

from datetime import datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from tests.integration.helpers import bearer, register

API = "/api/v1"


@pytest.fixture
async def bank_id(db_session: AsyncSession) -> int:
    bank = Bank(name="Test Bank")
    db_session.add(bank)
    await db_session.commit()
    return bank.id


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "alice@example.com"))


@pytest.fixture
async def bob(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "bob@example.com"))


async def _category(client: httpx.AsyncClient, user: dict[str, str], name: str) -> int:
    response = await client.post(
        f"{API}/transactions/categories", headers=user, json={"name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _tx_body(category_id: int, bank_id: int, when: str, kind: str = "expense") -> dict[str, object]:
    return {
        "amount": "1500.00",
        "transaction_type": kind,
        "transaction_date": when,
        "category_id": category_id,
        "bank_id": bank_id,
    }


class TestCategoriesArePrivate:
    async def test_other_users_do_not_see_or_use_my_categories(
        self, client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str], bank_id: int
    ) -> None:
        secret = await _category(client, alice, "Долг Ивану")

        bob_list = (await client.get(f"{API}/transactions/categories", headers=bob)).json()
        assert all(c["name"] != "Долг Ивану" for c in bob_list)

        used = await client.post(
            f"{API}/transactions",
            headers=bob,
            json=_tx_body(secret, bank_id, "2025-03-01T10:00:00"),
        )
        assert used.status_code == 400
        assert used.json()["detail"] == "Category not found"

        # Bob can have his own category with the same name.
        assert await _category(client, bob, "Долг Ивану") != secret

    async def test_duplicate_own_name_conflicts(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        await _category(client, alice, "Кафе")
        again = await client.post(
            f"{API}/transactions/categories", headers=alice, json={"name": "Кафе"}
        )
        assert again.status_code == 409

    async def test_cannot_move_transaction_to_foreign_category(
        self, client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str], bank_id: int
    ) -> None:
        mine = await _category(client, alice, "Моя")
        foreign = await _category(client, bob, "Чужая")
        tx = await client.post(
            f"{API}/transactions",
            headers=alice,
            json=_tx_body(mine, bank_id, "2025-03-01T10:00:00"),
        )
        moved = await client.put(
            f"{API}/transactions/{tx.json()['id']}", headers=alice, json={"category_id": foreign}
        )
        assert moved.status_code == 400

    async def test_upload_creates_private_categories(
        self, client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str]
    ) -> None:
        csv = "date,category,description,amount\n2025-01-05,Секретная категория,x,-100\n".encode()
        response = await client.post(
            f"{API}/upload/kaspi", headers=alice, files={"file": ("s.csv", csv, "text/csv")}
        )
        assert response.status_code == 201
        alice_names = {
            c["name"]
            for c in (await client.get(f"{API}/transactions/categories", headers=alice)).json()
        }
        bob_names = {
            c["name"]
            for c in (await client.get(f"{API}/transactions/categories", headers=bob)).json()
        }
        assert "Секретная категория" in alice_names
        assert "Секретная категория" not in bob_names


class TestTimestamps:
    @pytest.mark.parametrize(
        ("sent", "stored_utc"),
        [
            ("2025-03-31T23:30:00", "2025-03-31T23:30:00+00:00"),  # naive -> UTC
            ("2025-03-31T23:30:00+05:00", "2025-03-31T18:30:00+00:00"),  # converted to UTC
            ("2025-03-31T18:30:00Z", "2025-03-31T18:30:00+00:00"),
        ],
    )
    async def test_dates_are_stored_and_returned_in_utc(
        self,
        client: httpx.AsyncClient,
        alice: dict[str, str],
        bank_id: int,
        sent: str,
        stored_utc: str,
    ) -> None:
        category = await _category(client, alice, "Прочее")
        response = await client.post(
            f"{API}/transactions", headers=alice, json=_tx_body(category, bank_id, sent)
        )
        assert response.status_code == 201, response.text
        returned = datetime.fromisoformat(
            response.json()["transaction_date"].replace("Z", "+00:00")
        )
        assert returned == datetime.fromisoformat(stored_utc)
        assert returned.utcoffset().total_seconds() == 0

    async def test_filtering_with_offset_dates(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
    ) -> None:
        category = await _category(client, alice, "Прочее")
        await client.post(
            f"{API}/transactions",
            headers=alice,
            json=_tx_body(category, bank_id, "2025-04-01T00:30:00+05:00"),  # = 2025-03-31T19:30Z
        )
        march_utc = await client.get(
            f"{API}/transactions",
            headers=alice,
            params={"start_date": "2025-03-01T00:00:00Z", "end_date": "2025-03-31T23:59:59Z"},
        )
        april_local = await client.get(
            f"{API}/transactions",
            headers=alice,
            params={
                "start_date": "2025-04-01T00:00:00+05:00",
                "end_date": "2025-04-30T23:59:59+05:00",
            },
        )
        assert march_utc.status_code == april_local.status_code == 200
        assert march_utc.json()["total"] == 1
        assert april_local.json()["total"] == 1


class TestConstraintErrorsAreClientErrors:
    async def test_null_in_required_field_is_rejected_by_validation(
        self, client: httpx.AsyncClient, alice: dict[str, str]
    ) -> None:
        budget = await client.post(
            f"{API}/budgets", headers=alice, json={"title": "Еда", "monthly_limit": "1000.00"}
        )
        response = await client.put(
            f"{API}/budgets/{budget.json()['id']}", headers=alice, json={"title": None}
        )
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"

    async def test_deposit_update_with_end_before_start_is_422(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
    ) -> None:
        deposit = await client.post(
            f"{API}/investments",
            headers=alice,
            json={
                "amount": "100000.00",
                "interest_rate": "14.00",
                "start_date": "2025-01-01",
                "end_date": "2026-01-01",
                "bank_id": bank_id,
            },
        )
        response = await client.put(
            f"{API}/investments/{deposit.json()['id']}",
            headers=alice,
            json={"end_date": "2024-12-31"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "constraint_violation"
        assert "ck_" not in response.text  # constraint names are not leaked

    async def test_amount_beyond_numeric_range_is_rejected_by_validation(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
    ) -> None:
        category = await _category(client, alice, "Прочее")
        body = _tx_body(category, bank_id, "2025-03-01T10:00:00")
        body["amount"] = "100000000000000000.00"  # 19 digits > NUMERIC(18, 2)
        response = await client.post(f"{API}/transactions", headers=alice, json=body)
        assert response.status_code == 422

    async def test_refund_can_be_created(
        self, client: httpx.AsyncClient, alice: dict[str, str], bank_id: int
    ) -> None:
        category = await _category(client, alice, "Прочее")
        response = await client.post(
            f"{API}/transactions",
            headers=alice,
            json=_tx_body(category, bank_id, "2025-03-01T10:00:00", kind="refund"),
        )
        assert response.status_code == 201
        assert response.json()["transaction_type"] == "refund"


async def test_zero_amount_in_statement_is_rejected(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    csv = b"date,category,description,amount\n2025-01-05,A,x,-100\n2025-01-06,B,y,0\n"
    response = await client.post(
        f"{API}/upload/kaspi", headers=alice, files={"file": ("s.csv", csv, "text/csv")}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Row 3: amount must not be zero"
    assert (await client.get(f"{API}/transactions", headers=alice)).json()["total"] == 0
