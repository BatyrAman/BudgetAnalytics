import pytest

pytestmark = pytest.mark.integration

CSV = (
    "date,category,description,amount\n"
    "2025-03-01,,Magnum Cash&Carry,-12 500\n"
    "2025-03-01,,Magnum Cash&Carry,-12 500\n"      # честный повтор в той же выписке
    "2025-03-02,,Yandex Go,-1500,00\n"
    "2025-03-05,Зарплата,ТОО Ромашка зарплата,450000\n"
    "2025-03-07,Хобби,Лего магазин,-20000\n"
)


def _file(content: str, name: str = "statement.csv"):
    return {"file": (name, content.encode("utf-8"), "text/csv")}


async def test_import_is_idempotent(alice):
    first = await alice.post("/upload/kaspi", files=_file(CSV))
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["status"] == "completed"
    assert body["imported"] == 5
    assert body["skipped_duplicates"] == 0
    assert body["bank"] == "Kaspi Bank"
    assert body["total_income"] == "450000.00"
    assert body["total_expense"] == "46500.00"

    second = (await alice.post("/upload/kaspi", files=_file(CSV))).json()
    assert second["imported"] == 0
    assert second["skipped_duplicates"] == 5
    assert second["status"] == "completed"

    listed = (await alice.get("/transactions", params={"limit": 50})).json()
    assert listed["total"] == 5


async def test_same_statement_for_different_users_is_not_deduplicated(alice, bob):
    await alice.post("/upload/kaspi", files=_file(CSV))
    bob_result = (await bob.post("/upload/kaspi", files=_file(CSV))).json()
    assert bob_result["imported"] == 5


async def test_categorization_rules_and_statement_hints(alice):
    await alice.post("/upload/kaspi", files=_file(CSV))
    items = (await alice.get("/transactions", params={"limit": 50})).json()["items"]
    categories = {c["id"]: c for c in (await alice.get("/transactions/categories")).json()}
    by_merchant = {
        i["merchant"]: (categories[i["category_id"]]["name"], i["category_source"]) for i in items
    }
    assert by_merchant["MAGNUM CASH&CARRY"] == ("Продукты", "rule")
    assert by_merchant["YANDEX GO"] == ("Такси", "rule")
    assert by_merchant["ТОО РОМАШКА ЗАРПЛАТА"] == ("Зарплата", "rule")
    # неизвестная категория из выписки создаётся как пользовательская
    assert by_merchant["ЛЕГО МАГАЗИН"] == ("Хобби", "statement")
    hobby = next(c for c in categories.values() if c["name"] == "Хобби")
    assert hobby["is_system"] is False


async def test_user_memory_beats_rules(alice):
    await alice.post("/upload/kaspi", files=_file("date,description,amount\n2025-01-01,Magnum,-100\n"))
    tx = (await alice.get("/transactions")).json()["items"][0]
    hobby = (await alice.post("/transactions/categories", json={"name": "Хозтовары"})).json()
    await alice.put(f"/transactions/{tx['id']}", json={"category_id": hobby["id"]})

    await alice.post("/upload/kaspi", files=_file("date,description,amount\n2025-02-01,MAGNUM,-200\n"))
    newest = (await alice.get("/transactions")).json()["items"][0]
    assert newest["amount"] == "200.00"
    assert newest["category_id"] == hobby["id"]
    assert newest["category_source"] == "memory"


async def test_partial_import(alice):
    content = (
        "date,description,amount\n"
        "2025-03-01,Coffee,-900\n"
        "not-a-date,Broken,-100\n"
        "2025-03-02,Zero,0\n"
        "2025-03-03,Bad amount,abc\n"
    )
    body = (await alice.post("/upload/halyk", files=_file(content))).json()
    assert body["status"] == "partial"
    assert body["imported"] == 1
    assert body["failed"] == 3
    assert [e["row"] for e in body["errors"]] == [3, 4, 5]

    record = (await alice.get(f"/imports/{body['import_id']}")).json()
    assert record["status"] == "partial"
    assert record["rows_failed"] == 3


async def test_all_rows_invalid_is_failed(alice):
    body = (await alice.post("/upload/kaspi", files=_file("date,amount\nxx,1\n"))).json()
    assert body["status"] == "failed"
    assert body["imported"] == 0


async def test_missing_columns_is_400_and_logged_as_failed(alice):
    response = await alice.post("/upload/kaspi", files=_file("foo,bar\n1,2\n"))
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "STATEMENT_INVALID"
    record = (await alice.get(f"/imports/{error['details']['import_id']}")).json()
    assert record["status"] == "failed"


@pytest.mark.parametrize(
    "encoding, currency",
    [("cp1251", "тг"), ("utf-8", "₸")],
)
async def test_semicolon_russian_headers(alice, encoding, currency):
    content = (
        "Дата;Сумма;Операция;Детали\n"
        f"01.03.2025;- 1 500,00 {currency};Покупка;Starbucks\n"
        f"02.03.2025;+ 10 000,00 {currency};Пополнение;С Halyk\n"
    )
    body = (await alice.post("/upload/kaspi", files={"file": ("s.csv", content.encode(encoding), "text/csv")})).json()
    assert body["status"] == "completed", body
    assert body["imported"] == 2
    assert body["total_expense"] == "1500.00"
    assert body["total_income"] == "10000.00"


async def test_unsupported_bank_and_file_type(alice):
    unsupported = await alice.post("/upload/unknown", files=_file(CSV))
    assert unsupported.status_code == 400
    assert unsupported.json()["error"]["code"] == "UNSUPPORTED_BANK"
    wrong_type = await alice.post("/upload/kaspi", files=_file(CSV, "statement.pdf"))
    assert wrong_type.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


async def test_card_binding(alice, kaspi_id, halyk_id):
    card = (await alice.post("/cards", json={"bank_id": kaspi_id, "last4": "4321"})).json()
    ok = await alice.post("/upload/kaspi", files=_file(CSV), params={"card_id": card["id"]})
    assert ok.status_code == 201
    items = (await alice.get("/transactions", params={"card_id": card["id"]})).json()
    assert items["total"] == 5

    # тот же файл без карты — другой счёт, не дубликат
    assert (await alice.post("/upload/kaspi", files=_file(CSV))).json()["imported"] == 5

    mismatch = await alice.post("/upload/halyk", files=_file(CSV), params={"card_id": card["id"]})
    assert mismatch.json()["error"]["code"] == "CARD_BANK_MISMATCH"


async def test_file_size_limit(alice, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    big = "date,description,amount\n" + "2025-01-01,x,-1\n" * 80_000
    response = await alice.post("/upload/kaspi", files=_file(big))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
