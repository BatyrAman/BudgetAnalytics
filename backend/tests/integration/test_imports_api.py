"""Statement import API on SYNTHETIC fixtures (tests/import_fixtures.py)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.statement_import import StatementImport, StatementImportRow
from app.models.transaction import Transaction
from tests import import_fixtures as fx
from tests.integration.helpers import API, bearer, create, register

CSV = "text/csv"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
async def alice(client: httpx.AsyncClient) -> dict[str, str]:
    return bearer(await register(client, "alice@example.com"))


async def preview(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    content: bytes,
    name: str = "statement.csv",
    bank: str = "kaspi",
    mime: str = CSV,
    **data: object,
) -> httpx.Response:
    return await client.post(
        f"{API}/imports/{bank}/preview",
        headers=headers,
        files={"file": (name, content, mime)},
        data={k: str(v) for k, v in data.items()},
    )


async def commit(
    client: httpx.AsyncClient, headers: dict[str, str], import_id: int, **body: object
) -> httpx.Response:
    return await client.post(f"{API}/imports/{import_id}/commit", headers=headers, json=body)


async def test_preview_then_commit(
    client: httpx.AsyncClient, alice: dict[str, str], db_session: AsyncSession
) -> None:
    response = await preview(client, alice, fx.csv_bytes())
    assert response.status_code == 201, response.text
    body = response.json()
    summary = body["import"]
    assert (
        summary["status"],
        summary["total_rows"],
        summary["valid_rows"],
        summary["invalid_rows"],
    ) == ("preview", 6, 6, 0)
    assert (summary["period_start"], summary["period_end"]) == ("2025-03-01", "2025-03-06")
    assert body["verified_parser"] is False
    assert [r["transaction_type"] for r in body["rows"]] == [
        "income",
        "expense",
        "expense",
        "expense",
        "refund",
        "transfer_out",
    ]
    # Nothing is saved before commit.
    assert (await client.get(f"{API}/transactions", headers=alice)).json()["total"] == 0

    committed = await commit(client, alice, summary["id"])
    assert committed.status_code == 200, committed.text
    assert (committed.json()["imported"], committed.json()["import"]["status"]) == (6, "committed")

    txs = (await client.get(f"{API}/transactions", headers=alice, params={"limit": 50})).json()[
        "items"
    ]
    assert len(txs) == 6
    stored = list(await db_session.scalars(select(Transaction).order_by(Transaction.id)))
    assert all(t.import_hash and t.import_id == summary["id"] for t in stored)
    assert stored[1].merchant == "MAGNUM CASH&CARRY ALMATY"
    assert all("4400430012345678" not in (t.description or "") for t in stored)

    # Committing twice is refused.
    again = await commit(client, alice, summary["id"])
    assert again.status_code == 409
    assert again.json()["code"] == "import_not_committable"
    cancel = await client.delete(f"{API}/imports/{summary['id']}", headers=alice)
    assert cancel.status_code == 409
    assert cancel.json()["code"] == "import_not_cancellable"


async def test_identical_rows_in_one_file_are_both_imported(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    body = (await preview(client, alice, fx.csv_bytes())).json()
    coffee = [r for r in body["rows"] if r["description"] and "Coffee Boom" in r["description"]]
    assert len(coffee) == 2 and all(r["status"] == "valid" for r in coffee)


async def test_reimport_of_the_same_file_is_all_duplicates(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    first = (await preview(client, alice, fx.csv_bytes())).json()["import"]["id"]
    await commit(client, alice, first)
    second = (await preview(client, alice, fx.csv_bytes())).json()
    assert second["import"]["duplicate_rows"] == 6
    assert {r["status"] for r in second["rows"]} == {"duplicate"}
    result = (await commit(client, alice, second["import"]["id"])).json()
    assert result["imported"] == 0
    assert (await client.get(f"{API}/transactions", headers=alice)).json()["total"] == 6


async def test_overlapping_statement_imports_only_new_rows(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    await commit(
        client,
        alice,
        (await preview(client, alice, fx.csv_bytes(fx.ROWS[:4]))).json()["import"]["id"],
    )
    overlap = (await preview(client, alice, fx.csv_bytes(fx.ROWS[2:]))).json()
    # Rows 3-4 (the two identical coffees) were imported already; 5-6 are new.
    assert [r["status"] for r in overlap["rows"]] == ["duplicate", "duplicate", "valid", "valid"]
    assert (await commit(client, alice, overlap["import"]["id"])).json()["imported"] == 2
    assert (await client.get(f"{API}/transactions", headers=alice)).json()["total"] == 6


async def test_possible_duplicate_of_manual_entry(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    cat = (await create(client, "/categories", alice, {"name": "Ручная"}))["id"]
    await create(
        client,
        "/transactions",
        alice,
        {
            "amount": "12500.50",
            "transaction_type": "expense",
            "category_id": cat,
            "transaction_date": "2025-03-02T08:00:00Z",  # same Almaty day as the statement row
        },
    )
    body = (await preview(client, alice, fx.csv_bytes())).json()
    flagged = [r for r in body["rows"] if r["status"] == "possible_duplicate"]
    assert [r["amount"] for r in flagged] == ["12500.50"]

    result = (await commit(client, alice, body["import"]["id"])).json()
    assert (result["imported"], result["skipped"]) == (5, 1)  # skipped by default


async def test_include_possible_duplicates_and_exclude_rows(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    cat = (await create(client, "/categories", alice, {"name": "Ручная"}))["id"]
    await create(
        client,
        "/transactions",
        alice,
        {
            "amount": "12500.50",
            "transaction_type": "expense",
            "category_id": cat,
            "transaction_date": "2025-03-02T08:00:00Z",
        },
    )
    body = (await preview(client, alice, fx.csv_bytes())).json()
    result = await commit(
        client, alice, body["import"]["id"], include_possible_duplicates=True, exclude_rows=[11]
    )
    assert (result.json()["imported"], result.json()["skipped"]) == (
        5,
        1,
    )  # row 11 (transfer) excluded
    rows = (
        await client.get(
            f"{API}/imports/{body['import']['id']}/rows",
            headers=alice,
            params={"status": "skipped"},
        )
    ).json()
    assert [r["row_number"] for r in rows["items"]] == [11]


async def test_invalid_rows_are_reported_and_never_imported(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    rows = [
        ["01.03.2025", "-100,00", "KZT", "Покупка", "ok"],
        ["31.02.2025", "-100,00", "KZT", "Покупка", "bad date"],
        ["02.03.2025", "-5", "JPY", "Покупка", "unsupported currency"],
    ]
    body = (await preview(client, alice, fx.csv_bytes(rows))).json()
    by_row = {r["row_number"]: (r["status"], r["error_code"]) for r in body["rows"]}
    assert by_row == {
        6: ("valid", None),
        7: ("invalid", "invalid_date"),
        8: ("invalid", "unknown_currency"),
    }
    assert (await commit(client, alice, body["import"]["id"])).json()["imported"] == 1


async def test_xlsx_import_into_account(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    account = await create(
        client,
        "/accounts",
        alice,
        {
            "name": "Kaspi Gold",
            "account_type": "card",
            "opening_balance_at": "2025-01-01T00:00:00Z",
        },
    )
    body = (
        await preview(
            client, alice, fx.xlsx_bytes(), "march.xlsx", mime=XLSX, account_id=account["id"]
        )
    ).json()
    assert body["import"]["file_format"] == "xlsx" and body["import"]["account_id"] == account["id"]
    await commit(client, alice, body["import"]["id"])
    # 0 + 350 000 − 12 500.50 − 999.99 = 336 499.51
    assert (await client.get(f"{API}/accounts/{account['id']}", headers=alice)).json()[
        "balance"
    ] == "336499.51"


async def test_currency_must_match_account(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    usd = await create(
        client, "/accounts", alice, {"name": "USD", "account_type": "card", "currency": "USD"}
    )
    body = (await preview(client, alice, fx.csv_bytes(), account_id=usd["id"])).json()
    assert {r["error_code"] for r in body["rows"]} == {"currency_mismatch"}


@pytest.mark.parametrize(
    ("name", "content", "status", "code"),
    [
        ("s.csv", b"%PDF-1.7 fake", 415, "format_mismatch"),
        ("s.pdf", b"%PDF-1.7 fake", 415, "pdf_not_supported"),
        ("s.docx", b"whatever", 415, "unsupported_format"),
        ("s.xlsx", None, 422, "malicious_file"),
        ("s.csv", b"date;comment\n01.03.2025;x\n", 422, "missing_columns"),
        ("s.csv", b"", 422, "empty_file"),
    ],
)
async def test_failures_are_rejected_and_recorded(
    client: httpx.AsyncClient,
    alice: dict[str, str],
    name: str,
    content: bytes | None,
    status: int,
    code: str,
) -> None:
    response = await preview(
        client, alice, content if content is not None else fx.xlsx_with_macro(), name
    )
    assert response.status_code == status and response.json()["code"] == code
    history = (await client.get(f"{API}/imports", headers=alice)).json()
    assert history["total"] == 1
    failed = history["items"][0]
    assert (failed["status"], failed["error_code"]) == ("failed", code)
    assert failed["error_message"] and "Traceback" not in failed["error_message"]


async def test_file_size_limit(
    client: httpx.AsyncClient, alice: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "IMPORT_MAX_FILE_BYTES", 2048)
    response = await preview(client, alice, b"a" * 5000)
    assert response.status_code == 413 and response.json()["code"] == "file_too_large"


async def test_unknown_bank(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    response = await preview(client, alice, fx.csv_bytes(), bank="monobank")
    assert response.status_code == 400 and response.json()["code"] == "unsupported_bank"


async def test_cancel_deletes_preview_rows(
    client: httpx.AsyncClient, alice: dict[str, str], db_session: AsyncSession
) -> None:
    import_id = (await preview(client, alice, fx.csv_bytes())).json()["import"]["id"]
    assert (await client.delete(f"{API}/imports/{import_id}", headers=alice)).status_code == 204
    remaining = await db_session.scalar(
        select(StatementImportRow.id).where(StatementImportRow.import_id == import_id)
    )
    assert remaining is None
    assert (await client.get(f"{API}/imports/{import_id}", headers=alice)).json()[
        "status"
    ] == "cancelled"
    refused = await commit(client, alice, import_id)
    assert refused.status_code == 409
    assert refused.json()["code"] == "import_not_committable"


async def test_expired_preview_cannot_be_committed(
    client: httpx.AsyncClient, alice: dict[str, str], db_session: AsyncSession
) -> None:
    import_id = (await preview(client, alice, fx.csv_bytes())).json()["import"]["id"]
    await db_session.execute(
        update(StatementImport)
        .where(StatementImport.id == import_id)
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()
    expired = await commit(client, alice, import_id)
    assert expired.status_code == 409
    assert expired.json()["code"] == "import_expired"
    assert (await client.get(f"{API}/imports/{import_id}", headers=alice)).json()[
        "status"
    ] == "expired"


async def test_other_users_imports_are_not_accessible(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    bob = bearer(await register(client, "bob@example.com"))
    import_id = (await preview(client, alice, fx.csv_bytes())).json()["import"]["id"]
    missing = await client.get(f"{API}/imports/{import_id}", headers=bob)
    assert missing.status_code == 404
    assert missing.json()["code"] == "import_not_found"
    assert (await client.get(f"{API}/imports/{import_id}/rows", headers=bob)).status_code == 404
    assert (await commit(client, bob, import_id)).status_code == 404
    assert (await client.delete(f"{API}/imports/{import_id}", headers=bob)).status_code == 404
    assert (await client.get(f"{API}/imports", headers=bob)).json()["total"] == 0
    alice_account = await create(client, "/accounts", alice, {"name": "A", "account_type": "card"})
    foreign = await preview(client, bob, fx.csv_bytes(), account_id=alice_account["id"])
    assert foreign.status_code == 400 and foreign.json()["code"] == "account_not_found"


async def test_banks_endpoint_and_auth(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    banks = (await client.get(f"{API}/imports/banks", headers=alice)).json()
    assert {b["code"] for b in banks} == {"kaspi", "halyk", "freedom"}
    assert all(b["verified"] is False and b["formats"] == ["csv", "xlsx"] for b in banks)
    assert (
        await client.post(f"{API}/imports/kaspi/preview", files={"file": ("s.csv", b"x", CSV)})
    ).status_code == 401
    assert (await client.get(f"{API}/imports")).status_code == 401
