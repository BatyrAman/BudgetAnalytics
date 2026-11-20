"""Stable machine-readable ``code`` of every business rule (BACKEND_GAPS G-10).

Each test asserts the HTTP status (unchanged), the exact ``code`` and the
English ``detail`` (unchanged), so the frontend can map codes to Russian texts.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_refresh_token
from app.models.user import User
from tests.integration.helpers import API, bearer, category, create, register, register_full

WHEN = "2025-03-10T12:00:00Z"


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "alice@example.com"))


def assert_error(
    response: httpx.Response, status: int, code: str, detail: str | None = None
) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["code"] == code, body
    if detail is not None:
        assert body["detail"] == detail


async def _bank_id(client: httpx.AsyncClient, headers: dict[str, str]) -> int:
    banks = (await client.get(f"{API}/banks", headers=headers)).json()
    return int(banks[0]["id"])


async def _system_category_id(client: httpx.AsyncClient, headers: dict[str, str]) -> int:
    categories = (await client.get(f"{API}/categories", headers=headers)).json()
    return next(c["id"] for c in categories if c["is_system"])


# ---------------------------------------------------------------- auth
async def test_me_returns_default_currency_code(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    response = await client.get(f"{API}/auth/me", headers=alice)
    assert response.status_code == 200
    assert response.json()["default_currency_code"] == "KZT"


async def test_login_errors(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await register(client, "bob@example.com", "Correct-pass-1")
    wrong = await client.post(
        f"{API}/auth/login", json={"email": "bob@example.com", "password": "Wrong-pass-1"}
    )
    assert_error(wrong, 401, "invalid_credentials", "Incorrect email or password")

    await db_session.execute(
        update(User).where(User.email == "bob@example.com").values(is_active=False)
    )
    await db_session.commit()
    inactive = await client.post(
        f"{API}/auth/login", json={"email": "bob@example.com", "password": "Correct-pass-1"}
    )
    assert_error(inactive, 403, "inactive_user", "Inactive user")


async def test_inactive_user_with_valid_token(
    client: httpx.AsyncClient, alice: dict[str, str], db_session: AsyncSession
) -> None:
    await db_session.execute(
        update(User).where(User.email == "alice@example.com").values(is_active=False)
    )
    await db_session.commit()
    assert_error(await client.get(f"{API}/auth/me", headers=alice), 403, "inactive_user")


async def test_register_duplicate_email(client: httpx.AsyncClient) -> None:
    await register(client, "dup@example.com")
    response = await client.post(
        f"{API}/auth/register",
        json={"full_name": "Other", "email": "dup@example.com", "password": "Another-pass-1"},
    )
    assert_error(response, 409, "email_taken", "User with this email already exists")


async def test_change_password_wrong_old_password(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    response = await client.post(
        f"{API}/auth/change-password",
        headers=alice,
        json={"old_password": "not-the-password", "new_password": "Brand-new-pass-1"},
    )
    assert_error(response, 400, "wrong_password", "Old password is incorrect")


async def test_access_token_codes(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    missing = await client.get(f"{API}/auth/me")
    assert_error(missing, 401, "unauthorized", "Could not validate credentials")
    assert missing.headers["WWW-Authenticate"] == "Bearer"

    garbage = await client.get(f"{API}/auth/me", headers=bearer("not-a-jwt"))
    assert_error(garbage, 401, "invalid_token", "Could not validate credentials")
    assert garbage.headers["WWW-Authenticate"] == "Bearer"

    expired_token = jwt.encode(
        {"sub": "1", "ver": 0, "type": "access", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )
    expired = await client.get(f"{API}/auth/me", headers=bearer(expired_token))
    assert_error(expired, 401, "token_expired", "Could not validate credentials")

    # A token invalidated by logout-all (version bump) is rejected as invalid.
    assert (await client.post(f"{API}/auth/logout-all", headers=alice)).status_code == 204
    assert_error(await client.get(f"{API}/auth/me", headers=alice), 401, "invalid_token")


async def test_refresh_token_codes(client: httpx.AsyncClient) -> None:
    tokens = await register_full(client, "carol@example.com")
    rotated = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    reused = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert_error(reused, 401, "invalid_token", "Invalid or expired refresh token")

    expired = create_refresh_token({"sub": "1", "jti": "x", "fam": "y"}, expires_days=-1)
    response = await client.post(f"{API}/auth/refresh", json={"refresh_token": expired})
    assert_error(response, 401, "token_expired", "Invalid or expired refresh token")


# ---------------------------------------------------------------- categories
async def test_category_codes(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    assert_error(
        await client.get(f"{API}/categories/999999", headers=alice),
        404,
        "category_not_found",
        "Category not found",
    )
    system_id = await _system_category_id(client, alice)
    assert_error(
        await client.patch(f"{API}/categories/{system_id}", headers=alice, json={"name": "New"}),
        403,
        "system_category_readonly",
        "System categories are read-only",
    )

    groceries = await create(client, "/categories", alice, {"name": "Groceries", "kind": "expense"})
    assert_error(
        await client.post(f"{API}/categories", headers=alice, json={"name": "Groceries"}),
        409,
        "category_exists",
        "Category already exists",
    )

    await create(
        client,
        "/transactions",
        alice,
        {
            "amount": "100.00",
            "transaction_type": "expense",
            "transaction_date": WHEN,
            "category_id": groceries["id"],
        },
    )
    assert_error(
        await client.patch(
            f"{API}/categories/{groceries['id']}", headers=alice, json={"kind": "income"}
        ),
        409,
        "category_kind_conflict",
    )
    assert_error(
        await client.delete(f"{API}/categories/{groceries['id']}", headers=alice),
        409,
        "category_in_use",
    )


# ---------------------------------------------------------------- transactions
async def test_transaction_codes(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    salary = await create(client, "/categories", alice, {"name": "Salary", "kind": "income"})
    food = await category(client, alice, "Food")
    base: dict[str, Any] = {
        "amount": "100.00",
        "transaction_type": "expense",
        "transaction_date": WHEN,
        "category_id": food,
    }

    async def post(**overrides: Any) -> httpx.Response:
        return await client.post(f"{API}/transactions", headers=alice, json={**base, **overrides})

    assert_error(await post(category_id=999999), 400, "category_not_found", "Category not found")
    assert_error(await post(category_id=salary["id"]), 400, "category_kind_mismatch")
    assert_error(await post(bank_id=999999), 400, "bank_not_found", "Bank not found")
    assert_error(await post(account_id=999999), 400, "account_not_found", "Account not found")
    assert_error(await post(currency="XYZ"), 400, "unknown_currency", "Unknown currency")

    account = await create(
        client, "/accounts", alice, {"name": "Card", "account_type": "card", "currency": "KZT"}
    )
    assert_error(
        await post(account_id=account["id"], currency="USD"),
        400,
        "currency_mismatch",
        "Currency must match the account's currency",
    )
    assert_error(
        await client.get(f"{API}/transactions/999999", headers=alice),
        404,
        "transaction_not_found",
        "Transaction not found",
    )
    assert_error(
        await client.get(
            f"{API}/transactions",
            headers=alice,
            params={"start_date": "2025-03-10T00:00:00Z", "end_date": "2025-03-01T00:00:00Z"},
        ),
        422,
        "invalid_date_range",
        "end_date must not be before start_date",
    )
    assert_error(
        await client.get(
            f"{API}/transactions", headers=alice, params={"min_amount": "10", "max_amount": "5"}
        ),
        422,
        "invalid_amount_range",
    )


# ---------------------------------------------------------------- accounts
async def test_account_codes(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    assert_error(
        await client.get(f"{API}/accounts/999999", headers=alice),
        404,
        "account_not_found",
        "Account not found",
    )
    assert_error(
        await client.post(
            f"{API}/accounts",
            headers=alice,
            json={"name": "A", "account_type": "card", "bank_id": 999999},
        ),
        422,
        "bank_not_found",
        "Bank not found",
    )
    assert_error(
        await client.post(
            f"{API}/accounts",
            headers=alice,
            json={"name": "A", "account_type": "card", "currency": "XYZ"},
        ),
        422,
        "unknown_currency",
        "Unknown currency",
    )
    account = await create(client, "/accounts", alice, {"name": "Main", "account_type": "card"})
    # Duplicate name: caught by the database unique constraint.
    assert_error(
        await client.post(
            f"{API}/accounts", headers=alice, json={"name": "Main", "account_type": "cash"}
        ),
        409,
        "account_name_taken",
        "The request conflicts with an existing record",
    )
    food = await category(client, alice, "Food")
    await create(
        client,
        "/transactions",
        alice,
        {
            "amount": "100.00",
            "transaction_type": "expense",
            "transaction_date": WHEN,
            "category_id": food,
            "account_id": account["id"],
        },
    )
    assert_error(
        await client.delete(f"{API}/accounts/{account['id']}", headers=alice),
        409,
        "account_has_transactions",
        "Account has transactions; archive it instead of deleting",
    )


# ---------------------------------------------------------------- budgets
async def test_budget_codes(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    salary = await create(client, "/categories", alice, {"name": "Salary", "kind": "income"})
    body = {"title": "Food", "monthly_limit": "1000.00"}
    assert_error(
        await client.post(f"{API}/budgets", headers=alice, json={**body, "category_id": 999999}),
        400,
        "category_not_found",
    )
    assert_error(
        await client.post(
            f"{API}/budgets", headers=alice, json={**body, "category_id": salary["id"]}
        ),
        400,
        "budget_income_category",
    )
    assert_error(
        await client.post(f"{API}/budgets", headers=alice, json={**body, "currency": "XYZ"}),
        400,
        "unknown_currency",
    )
    assert_error(
        await client.get(f"{API}/budgets/999999", headers=alice),
        404,
        "budget_not_found",
        "Budget not found",
    )
    assert_error(
        await client.get(f"{API}/budgets/999999/utilization", headers=alice),
        404,
        "budget_not_found",
        "Budget not found",
    )
    assert_error(
        await client.get(f"{API}/budgets/utilization", headers=alice, params={"tz": "Mars/Base"}),
        422,
        "unknown_timezone",
        "Unknown time zone",
    )
    assert_error(
        await client.get(f"{API}/budgets/utilization", headers=alice, params={"month": "2025-13"}),
        422,
        "invalid_month",
        "month must be YYYY-MM",
    )


# ---------------------------------------------------------------- deposits and goals
async def test_deposit_codes(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    bank_id = await _bank_id(client, alice)
    body = {
        "bank_id": bank_id,
        "principal": "100000.00",
        "interest_rate": "14",
        "start_date": "2025-01-01",
        "end_date": "2026-01-01",
    }
    assert_error(
        await client.post(f"{API}/deposits", headers=alice, json={**body, "bank_id": 999999}),
        400,
        "bank_not_found",
    )
    assert_error(
        await client.post(f"{API}/deposits", headers=alice, json={**body, "currency": "XYZ"}),
        400,
        "unknown_currency",
    )
    deposit = await create(client, "/deposits", alice, body)
    assert_error(
        await client.patch(
            f"{API}/deposits/{deposit['id']}", headers=alice, json={"end_date": "2024-12-31"}
        ),
        422,
        "invalid_date_range",
        "end_date must be after start_date",
    )
    assert_error(
        await client.get(f"{API}/deposits/999999", headers=alice),
        404,
        "deposit_not_found",
        "Deposit not found",
    )


async def test_goal_codes(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    assert_error(
        await client.get(f"{API}/goals/999999", headers=alice),
        404,
        "goal_not_found",
        "Goal not found",
    )
    body = {"name": "Car", "target_amount": "1000000.00"}
    assert_error(
        await client.post(f"{API}/goals", headers=alice, json={**body, "currency": "XYZ"}),
        400,
        "unknown_currency",
    )
    await create(client, "/goals", alice, body)
    assert_error(
        await client.post(f"{API}/goals", headers=alice, json=body),
        409,
        "goal_name_taken",
        "The request conflicts with an existing record",
    )


async def test_pydantic_errors_keep_validation_error(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    response = await client.post(f"{API}/goals", headers=alice, json={"name": "X"})
    assert_error(response, 422, "validation_error")
    assert isinstance(response.json()["detail"], list)
