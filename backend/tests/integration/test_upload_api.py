"""Statement upload with the *current* generic parser.

The CSV is synthetic (see tests/unit/test_parsers.py) — not a real bank format.
"""

import httpx

from tests.integration.helpers import bearer, register

API = "/api/v1"

SYNTHETIC_CSV = (
    "date,category,description,amount\n"
    "2025-01-05,Зарплата,Salary,350000.00\n"
    "2025-01-06,Продукты,Shop,-12500.50\n"
).encode()


async def test_upload_imports_rows_for_current_user_only(client: httpx.AsyncClient) -> None:
    alice = bearer(await register(client, "alice@example.com"))
    bob = bearer(await register(client, "bob@example.com"))

    response = await client.post(
        f"{API}/upload/kaspi",
        headers=alice,
        files={"file": ("statement.csv", SYNTHETIC_CSV, "text/csv")},
    )
    assert response.status_code == 201, response.text
    assert response.json() == {
        "imported": 2,
        "bank": "Kaspi Bank",
        "total_income": "350000.00",
        "total_expense": "12500.50",
    }

    assert (await client.get(f"{API}/transactions", headers=alice)).json()["total"] == 2
    assert (await client.get(f"{API}/transactions", headers=bob)).json()["total"] == 0


async def test_upload_rejects_unknown_bank_and_non_csv(client: httpx.AsyncClient) -> None:
    alice = bearer(await register(client, "alice@example.com"))
    files = {"file": ("statement.csv", SYNTHETIC_CSV, "text/csv")}

    unknown = await client.post(f"{API}/upload/unknownbank", headers=alice, files=files)
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "bad_request"

    pdf = await client.post(
        f"{API}/upload/kaspi",
        headers=alice,
        files={"file": ("statement.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert pdf.status_code == 400
