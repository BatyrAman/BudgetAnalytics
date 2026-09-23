# BudgetAnalytics — backend

FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Alembic · Pydantic v2 · Python 3.12

## Быстрый старт

```bash
docker compose up -d db                 # из корня репозитория
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                    # заполнить SECRET_KEY, DATABASE_URL
alembic upgrade head                    # схема создаётся только миграциями
uvicorn app.main:app --reload           # http://127.0.0.1:8000/docs
```

Приложение не стартует, если БД недоступна или не мигрирована до head
(`STARTUP_CHECKS=true`).

## Тесты

```bash
createdb budget_test                    # или TEST_DATABASE_URL=postgresql+asyncpg://...
pytest -q                               # unit + integration + API
ruff check app tests alembic
```

Unit-тесты (`tests/unit`) не требуют БД. Интеграционные (`tests/integration`)
создают схему через `alembic upgrade head` в БД из `TEST_DATABASE_URL`.

## Фоновые задачи

```bash
python -m app.tasks.run payment_reminders   # cron / systemd timer
python -m app.tasks.run monthly_reports
python -m app.tasks.run bank_products       # BANK_PRODUCTS_FILE=/path/products.json

pip install -r requirements-worker.txt      # либо ARQ + Redis
arq app.tasks.scheduler.WorkerSettings
```

## Документация

* `../docs/audit.md` — аудит исходного кода
* `../docs/architecture.md` — слои, модули, потоки данных, безопасность, breaking changes
* `../docs/ai-architecture.md` — дизайн будущего AI Coach
