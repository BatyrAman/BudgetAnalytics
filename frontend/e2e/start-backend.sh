#!/usr/bin/env bash
# Start the FastAPI backend for end-to-end tests against a dedicated database.
#
#   E2E_DATABASE_URL=postgresql+asyncpg://user@127.0.0.1:5432/budget_e2e \
#   BACKEND_PYTHON=../backend/.venv/bin/python e2e/start-backend.sh
#
# The working directory is switched away from backend/ so that backend/.env
# (developer secrets) is never read; every setting comes from this script.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="${BACKEND_DIR:-$HERE/../../backend}"
BACKEND_PYTHON="${BACKEND_PYTHON:-$BACKEND_DIR/.venv/bin/python}"
PORT="${E2E_BACKEND_PORT:-8100}"
: "${E2E_DATABASE_URL:?set E2E_DATABASE_URL to a dedicated, disposable database}"

export ENVIRONMENT=development
export DATABASE_URL="$E2E_DATABASE_URL"
export SECRET_KEY="${E2E_SECRET_KEY:-$("$BACKEND_PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')}"
export AI_PROVIDER=none
export RATE_LIMIT_ENABLED=true
export RATE_LIMIT_BACKEND=memory
export ENABLE_LEGACY_API=false
export LOG_JSON=false
export FORWARDED_ALLOW_IPS=127.0.0.1
export PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}"

WORK="$(mktemp -d)"
cd "$WORK"
"$BACKEND_PYTHON" -m alembic -c "$BACKEND_DIR/alembic.ini" upgrade head
exec "$BACKEND_PYTHON" -m uvicorn app.main:app --app-dir "$BACKEND_DIR" \
  --host 127.0.0.1 --port "$PORT" --proxy-headers --no-access-log
