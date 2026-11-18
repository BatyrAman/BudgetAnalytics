# syntax=docker/dockerfile:1
# Production image. Safe by default: ENVIRONMENT=production, so a missing
# variable can never silently enable development behaviour (docs, weak keys,
# in-memory rate limits). docker-compose.yml overrides it for local work.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production \
    WEB_CONCURRENCY=2 \
    FORWARDED_ALLOW_IPS=127.0.0.1

WORKDIR /app

# Dependencies first (cached layer). Hash-checked install from the lock file.
# Slow or flaky links to PyPI: longer read timeout and more retries per file,
# and a BuildKit cache mount so wheels already downloaded by a failed build are
# reused by the next one. The cache is not part of the image layer.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes --timeout 120 --retries 10 -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Workers come from WEB_CONCURRENCY; trusted proxies from FORWARDED_ALLOW_IPS
# (uvicorn reads both). Access logs are written by the app (structured).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--no-access-log", "--proxy-headers", "--no-server-header"]
