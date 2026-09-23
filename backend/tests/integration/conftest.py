from __future__ import annotations

import itertools
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal, engine

BACKEND = Path(__file__).resolve().parents[2]
_counter = itertools.count(1)


def _alembic_config(connection) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    return config


@pytest_asyncio.fixture(scope="session", autouse=True)
async def database():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - нет PostgreSQL
        pytest.skip(f"PostgreSQL is not available: {type(exc).__name__}")

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(lambda sync_conn: command.upgrade(_alembic_config(sync_conn), "head"))
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_database(database):
    yield
    # Пользовательские данные удаляются каскадом от users;
    # справочники (банки, системные категории) из миграций остаются.
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users"))
        await conn.execute(text("DELETE FROM categories WHERE user_id IS NOT NULL"))
    from app.core.rate_limit import limiter

    limiter.reset()


@pytest_asyncio.fixture
async def session():
    async with SessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


API = settings.API_PREFIX


class UserCtx:
    def __init__(self, client: AsyncClient, email: str, password: str, token: str, user_id: int):
        self.client = client
        self.email = email
        self.password = password
        self.token = token
        self.id = user_id

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def get(self, path: str, **kw):
        return await self.client.get(API + path, headers=self.headers, **kw)

    async def post(self, path: str, **kw):
        return await self.client.post(API + path, headers=self.headers, **kw)

    async def put(self, path: str, **kw):
        return await self.client.put(API + path, headers=self.headers, **kw)

    async def delete(self, path: str, **kw):
        return await self.client.delete(API + path, headers=self.headers, **kw)


async def register(client: AsyncClient, name: str | None = None) -> UserCtx:
    n = next(_counter)
    email = f"user{n}@example.com"
    password = "Str0ng-password!"
    response = await client.post(
        f"{API}/auth/register",
        json={"full_name": name or f"User {n}", "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    return UserCtx(client, email, password, token, me.json()["id"])


@pytest_asyncio.fixture
async def alice(client) -> UserCtx:
    return await register(client, "Alice")


@pytest_asyncio.fixture
async def bob(client) -> UserCtx:
    return await register(client, "Bob")


@pytest_asyncio.fixture
async def kaspi_id(session) -> int:
    return await session.scalar(text("SELECT id FROM banks WHERE name = 'Kaspi Bank'"))


@pytest_asyncio.fixture
async def halyk_id(session) -> int:
    return await session.scalar(text("SELECT id FROM banks WHERE name = 'Halyk Bank'"))


async def system_category(session, name: str, kind: str = "expense") -> int:
    return await session.scalar(
        text("SELECT id FROM categories WHERE user_id IS NULL AND name = :n AND kind = :k"),
        {"n": name, "k": kind},
    )
