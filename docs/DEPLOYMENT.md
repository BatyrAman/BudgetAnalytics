# Развёртывание BudgetAnalytics API

> **Статус: не готово к публичному запуску.** Конфигурация подготовлена для
> закрытого staging-окружения. Блокеры перечислены в
> [SECURITY_REVIEW.md](SECURITY_REVIEW.md#блокеры-продакшн-запуска). Ничего не
> разворачивается и не публикуется без явного решения владельца проекта.

## 1. Архитектура

```
Интернет ──TLS──▶ reverse proxy (Caddy/nginx, на хосте)
                     │  127.0.0.1:8000
                     ▼
               api (uvicorn, N воркеров, read-only контейнер)
                │                         │
         PostgreSQL 16 (без портов)   Redis 7 (без портов, пароль)
```

* `migrate` — одноразовый контейнер `alembic upgrade head`; `api` стартует только
  после его успешного завершения.
* `/health` — liveness (процесс жив); `/health/ready` — readiness (PostgreSQL
  `SELECT 1` и Redis `PING`). Балансировщик/оркестратор направляет трафик только
  на ready-экземпляры.
* Redis хранит только счётчики rate limiting (без персональных данных; ключи
  содержат SHA-256 от e-mail, а не сам e-mail) и не требует бэкапа.

## 2. Секреты

Секреты — **файлы** в `backend/secrets/` (каталог в `.gitignore`, права `600`),
монтируются в `/run/secrets/` и читаются настройками приложения (один файл на
настройку). Переменные окружения имеют приоритет над файлами.

| Файл | Содержимое |
|---|---|
| `SECRET_KEY` | ≥ 32 случайных символов: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `POSTGRES_PASSWORD` | случайный пароль БД |
| `DATABASE_URL` | `postgresql+asyncpg://budget:<пароль>@db:5432/budget` |
| `REDIS_PASSWORD` | случайный пароль Redis |
| `REDIS_URL` | `redis://:<пароль>@redis:6379/0` |
| `OPENAI_API_KEY` | ключ, если `AI_PROVIDER=openai`; иначе пустой файл |

```bash
cd backend && mkdir -p secrets && chmod 700 secrets
python -c "import secrets; print(secrets.token_urlsafe(48))" > secrets/SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))" > secrets/POSTGRES_PASSWORD
python -c "import secrets; print(secrets.token_urlsafe(32))" > secrets/REDIS_PASSWORD
printf 'postgresql+asyncpg://budget:%s@db:5432/budget' "$(cat secrets/POSTGRES_PASSWORD)" > secrets/DATABASE_URL
printf 'redis://:%s@redis:6379/0' "$(cat secrets/REDIS_PASSWORD)" > secrets/REDIS_URL
: > secrets/OPENAI_API_KEY
chmod 600 secrets/*
```

Ротация `SECRET_KEY` делает недействительными все токены (пользователи входят
заново). Ротация паролей БД/Redis: изменить пароль в сервисе → обновить оба файла →
перезапустить `api`.

## 3. Обязательные настройки окружения (production)

Приложение **отказывается стартовать** в `ENVIRONMENT=production`, если: ключ
короче 32 символов или заглушка; `DEBUG`/`DB_ECHO` включены; `LOG_LEVEL=DEBUG`;
CORS содержит `*` или не-HTTPS origin; rate limiting выключен или не на Redis;
`AI_PROVIDER=openai` без ключа; лимиты стоимости AI без цен.

Docker-образ по умолчанию `ENVIRONMENT=production` (небезопасная конфигурация не
может включиться из-за забытой переменной).

| Переменная | Пример | Назначение |
|---|---|---|
| `CORS_ORIGINS` | `["https://app.example.kz"]` | Только HTTPS-origin фронтенда |
| `FORWARDED_ALLOW_IPS` | `172.18.0.1` | IP reverse proxy, которому доверяем `X-Forwarded-For` |
| `WEB_CONCURRENCY` | `2` | Число воркеров uvicorn |
| `AI_PROVIDER` | `none` | `openai` только после юридического согласования |
| `APP_VERSION` | `2026.11.18-1` | Тег образа (нужен для отката) |

Устаревшие эндпоинты (`/analytics` legacy, `/dashboard`, `/investments`, `/upload`)
в production выключены (`ENABLE_LEGACY_API`).

## 4. Первое развёртывание (staging)

```bash
cd backend
export APP_VERSION=2026.11.18-1 CORS_ORIGINS='["https://staging.example.kz"]' FORWARDED_ALLOW_IPS=172.18.0.1
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d db redis
docker compose -f docker-compose.prod.yml run --rm migrate
docker compose -f docker-compose.prod.yml up -d api
curl -fsS http://127.0.0.1:8000/health/ready
```

Reverse proxy (пример Caddy): `api.example.kz { reverse_proxy 127.0.0.1:8000 }` —
TLS, HTTP→HTTPS, ограничение размера тела запроса 6 МБ.

## 5. Обновление (новая версия)

1. CI зелёный на коммите релиза (lint, типы, тесты, аудит зависимостей, сборка образа).
2. **Бэкап перед миграцией** (раздел 7).
3. Миграции пишутся совместимыми со старой версией кода (expand → deploy → contract):
   сначала добавить, потом удалить в следующем релизе.
4. ```bash
   export APP_VERSION=<новый тег>
   docker compose -f docker-compose.prod.yml build
   docker compose -f docker-compose.prod.yml run --rm migrate
   docker compose -f docker-compose.prod.yml up -d api
   curl -fsS http://127.0.0.1:8000/health/ready
   ```
5. Проверить логи (`level=ERROR`, доля 5xx) 15 минут.

## 6. Откат (rollback)

**Только код (миграций в релизе не было):**
```bash
export APP_VERSION=<предыдущий тег>
docker compose -f docker-compose.prod.yml up -d api
```

**Код + миграции:**
1. Узнать ревизию предыдущего релиза: `alembic history` / заметки релиза.
2. Откат схемы **старым** кодом миграций не делается — использовать текущий образ:
   ```bash
   docker compose -f docker-compose.prod.yml run --rm migrate alembic downgrade <ревизия>
   export APP_VERSION=<предыдущий тег>
   docker compose -f docker-compose.prod.yml up -d api
   ```
3. Миграции проекта откатываются с проверкой данных: если данные нельзя выразить
   старой схемой (например, транзакции в USD или типы refund/transfer), downgrade
   **остановится с понятным сообщением** и ничего не изменит. Тогда — восстановление
   из бэкапа (раздел 7) или исправление вперёд (fix forward).

**Восстановление из бэкапа (последнее средство):** раздел 7.3.

## 7. Резервное копирование

### 7.1 Стратегия
* **Предпочтительно:** управляемый PostgreSQL с PITR (WAL-архивирование,
  восстановление на момент времени) и шифрованием at-rest.
* **Self-hosted:** ежедневный `scripts/backup.sh` — `pg_dump` в custom-формате,
  потоково шифруется `age` (без незашифрованного файла на диске), SHA-256 рядом.
  Скрипт отказывается писать незашифрованный бэкап.
* Хранение вне хоста (объектное хранилище в другом месте), неизменяемость
  (object lock), ротация: 7 ежедневных, 4 еженедельных, 12 ежемесячных.
* Закрытый ключ `age` хранится отдельно от бэкапов (офлайн/в менеджере секретов).
* RPO ≤ 24 ч (без PITR), RTO ≤ 2 ч. **Учения по восстановлению — ежемесячно.**

### 7.2 Бэкап
```bash
docker compose -f docker-compose.prod.yml exec -T db sh -c 'pg_dump -U budget -Fc budget' \
  | age -r <публичный-ключ-age> > budget-$(date -u +%Y%m%dT%H%M%SZ).dump.age
# или на хосте с клиентом PostgreSQL:
PGHOST=... PGUSER=budget PGPASSWORD=... PGDATABASE=budget \
AGE_RECIPIENT=age1... BACKUP_DIR=/var/backups/budget scripts/backup.sh
```

### 7.3 Восстановление
```bash
createdb budget_restore
AGE_IDENTITY=/secure/age-key.txt scripts/restore.sh budget-<время>.dump.age budget_restore
# Проверить данные и alembic_version, затем переключить DATABASE_URL на budget_restore
# и перезапустить api. Скрипт откажется восстанавливать в непустую БД.
```

## 8. Наблюдаемость

* Логи — JSON в stdout, по строке на запрос (`request_id`, метод, путь, статус,
  длительность; без query string, IP, тел запросов, токенов). Ротация json-file
  драйвера: 5 × 20 МБ.
* `X-Request-ID` в каждом ответе; ошибки 500 логируются с тем же `request_id`.
* **Не реализовано (блокер):** сбор логов, метрики, алерты (5xx, latency, readiness,
  заполнение диска, неудачные бэкапы).
