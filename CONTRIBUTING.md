# Contributing to BudgetAnalytics

Thank you for your interest.

> **Before you contribute:** the project has **no license yet** (see [docs/legal/LICENSING_DECISION.md](docs/legal/LICENSING_DECISION.md)). Until one is approved, outside contributions can only be accepted on terms agreed in writing with the repository owner. Please open an issue to discuss before writing code.

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Report security problems privately as described in [SECURITY.md](SECURITY.md), never in public issues.

## Development setup

The quickest way to run the whole stack is Docker Compose; see [README → Quick start](README.md#7-quick-start-with-docker):

```bash
cp .env.example .env    # set POSTGRES_PASSWORD, REDIS_PASSWORD, SECRET_KEY
docker compose up -d --build
```

To run the backend or frontend without Docker, see [README → Development without Docker](README.md#9-development-without-docker). You need Python 3.12+, Node.js 22+ and pnpm 12.21.0.

## Workflow

1. Create a branch from `main`, for example `feature/budget-export` or `fix/import-dates`.
2. Make **one small, focused change**. Follow the engineering rules in [CLAUDE.md](CLAUDE.md):
   - money uses `Decimal` on the backend and strings on the frontend, never floats;
   - business logic belongs in services, not route handlers;
   - every query is scoped to the authenticated user;
   - the frontend never recalculates financial values.
3. Add or update tests: valid and invalid input, unauthenticated access, another user's data, empty data, boundary values.
4. Run the checks (below) and make sure they pass.
5. Open a pull request. Describe what changed and why, the checks you ran, and any migration or configuration impact.
6. A maintainer reviews it. Address the comments in new commits.

## Required checks

Backend (from `backend/`, virtual environment active):

```bash
ruff check .
ruff format --check app tests
mypy
pytest -q
```

Integration tests need a disposable test database; see [README → Testing](README.md#10-testing-and-code-quality).

Frontend (from `frontend/`):

```bash
pnpm format:check
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the backend checks on every pull request. The frontend checks must currently be run locally.

## Database changes

- Change the schema only through an Alembic migration in `backend/alembic/versions/`.
- CI checks that migrations upgrade, match the models (`alembic check`), downgrade and upgrade again.

## Rules for data and secrets

- Never commit `.env` files, credentials, API keys, tokens, database dumps or Playwright session files (`frontend/e2e/.auth/`).
- Never use real personal or financial data in code, tests, fixtures or issues. Use clearly fictitious values (for example `@example.com` addresses).
- Do not add a dependency without checking its license. Record notable licenses in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Do not copy code, icons, fonts or images from other projects unless their license allows it, and record their source in [docs/legal/ASSET_ATTRIBUTION.md](docs/legal/ASSET_ATTRIBUTION.md).
