# Локальный запуск всего стека в Docker Compose

`compose.yaml` в корне репозитория запускает весь продукт: frontend (Next.js) → API (FastAPI) → PostgreSQL и Redis.
Используются существующие `backend/Dockerfile` и `frontend/Dockerfile`.

Это конфигурация для локальной разработки и демонстрации. Production разворачивается через `backend/docker-compose.prod.yml` (секреты-файлы, read-only контейнеры): см. [DEPLOYMENT.md](DEPLOYMENT.md).

## Сервисы

| Сервис | Образ | Доступ с хоста | Назначение |
|---|---|---|---|
| `frontend` | `frontend/Dockerfile` | `http://localhost:3000` | UI и BFF: сессия в httpOnly cookies, прокси `/api/v1/*` → `http://api:8000` |
| `api` | `backend/Dockerfile` | `http://127.0.0.1:8000` (`/docs`, `/health`) | FastAPI |
| `migrate` | `backend/Dockerfile` | — | `alembic upgrade head`, запускается до `api` и завершается |
| `db` | `postgres:16-alpine` | не опубликован | данные в томе `budgetanalytics_pgdata` |
| `redis` | `redis:7-alpine` | не опубликован | общие счётчики rate limiting, без сохранения на диск |

Порядок запуска: `db` healthy → `migrate` завершился успешно → `redis` healthy → `api` healthy (`/health/ready` проверяет БД и Redis) → `frontend`.

Все сервисы работают в сети `app`. API доверяет `X-Forwarded-For` только от frontend (фиксированный адрес `FRONTEND_IPV4`), поэтому лимиты по IP видят реальный адрес браузера.

## Первый запуск

```bash
cp .env.example .env
```

В `.env` задайте `POSTGRES_PASSWORD`, `REDIS_PASSWORD` и `SECRET_KEY`. Пароли подставляются в URL, поэтому используйте только буквы, цифры, `-` и `_`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Запуск:

```bash
docker compose up -d --build
```

Откройте `http://localhost:3000`. Используйте именно `localhost`, а не IP-адрес: cookies сессии помечены `Secure`, и по `http` браузеры принимают их только для `localhost`.

## Обязательные переменные

| Переменная | Назначение |
|---|---|
| `POSTGRES_PASSWORD` | Пароль PostgreSQL (применяется только при создании тома) |
| `REDIS_PASSWORD` | Пароль Redis |
| `SECRET_KEY` | Ключ подписи JWT, не меньше 32 случайных символов |

Необязательные переменные (значения по умолчанию указаны в `.env.example`): `POSTGRES_USER`, `POSTGRES_DB`, `ENVIRONMENT`, `LOG_LEVEL`, `LOG_JSON`, `AI_PROVIDER`, `OPENAI_API_KEY`, `FRONTEND_HOST_PORT`, `API_HOST_PORT`, `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, `COMPOSE_SUBNET`, `FRONTEND_IPV4`.

## Повседневные команды

```bash
docker compose ps                         # состояние и health
docker compose logs -f                    # все логи
docker compose logs -f api frontend       # логи отдельных сервисов
docker compose restart api                # перезапуск одного сервиса
docker compose up -d --build frontend     # пересобрать и перезапустить frontend
docker compose stop                       # остановить, не удаляя контейнеры
docker compose down                       # остановить и удалить контейнеры; том с данными сохраняется
```

> Не используйте `docker compose down -v` и `docker volume rm`: это удаляет базу данных.

## Миграции

Миграции применяются автоматически сервисом `migrate` при каждом `up`.

```bash
docker compose logs migrate                                   # результат последнего запуска
docker compose run --rm migrate alembic current               # текущая ревизия БД
docker compose run --rm migrate alembic heads                 # последняя ревизия в коде
docker compose run --rm migrate alembic history --verbose     # история
docker compose run --rm migrate                               # применить вручную (upgrade head)
```

## Проверка работоспособности

```bash
curl -fsS http://127.0.0.1:8000/health                                   # liveness API
curl -fsS http://127.0.0.1:8000/health/ready                             # БД и Redis
curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:3000/login   # frontend → 200
docker compose exec db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose exec redis redis-cli ping                                 # PONG (пароль из REDISCLI_AUTH)
```

## Доступ к PostgreSQL и Redis с хоста

По умолчанию порты закрыты. Для pytest, psql или GUI-клиентов подключите дополнительный файл; порты будут привязаны только к `127.0.0.1`:

```bash
docker compose -f compose.yaml -f compose.dev-ports.yaml up -d
```

Строка подключения для тестов на хосте:

```
TEST_DATABASE_URL=postgresql+asyncpg://budget:<password>@localhost:5432/budget_test
```

Базу `budget_test` нужно создать отдельно: тесты очищают таблицы.

## Совместимость с `backend/docker-compose.yml`

Прежний сценарий из `backend/` (PostgreSQL в Docker, API на хосте) работает как раньше.

Оба файла используют проект `budgetanalytics` и том `pgdata`, поэтому данные общие. Контейнеры `db`, `migrate` и `api` у них тоже одни и те же: запускайте одновременно только один стек. При переключении между ними Compose пересоздаёт контейнеры; том с данными сохраняется.

## Устранение неполадок

| Симптом | Причина и решение |
|---|---|
| `set POSTGRES_PASSWORD in .env` (или `SECRET_KEY`, `REDIS_PASSWORD`) | Нет `.env` или в нём нет переменной: `cp .env.example .env` и заполните значения |
| `migrate` завершается с ошибкой аутентификации | Том создан с другим паролем. PostgreSQL применяет `POSTGRES_PASSWORD` только при создании тома: укажите в `.env` исходный пароль |
| `Pool overlaps with other one on this address space` | Подсеть `172.31.250.0/24` занята: измените `COMPOSE_SUBNET` и `FRONTEND_IPV4` (вместе) |
| `port is already allocated` | Порт занят: измените `FRONTEND_HOST_PORT` / `API_HOST_PORT` (или `POSTGRES_HOST_PORT` / `REDIS_HOST_PORT`) |
| После входа снова открывается страница входа | Страница открыта не по `localhost`, и браузер отбрасывает `Secure` cookies. Откройте `http://localhost:3000` |
| `api` в состоянии `unhealthy` | `docker compose logs api`; `curl http://127.0.0.1:8000/health/ready` покажет, что недоступно: `database` или `rate_limit_store` |
| `frontend` отвечает 502/500 на `/api/v1/*` | API недоступен из сети compose: `docker compose ps api`, `docker compose logs frontend` |
| Ошибка при установке `pnpm` в сборке frontend | Версия `PNPM_VERSION` в `frontend/Dockerfile` должна совпадать с `packageManager` в `frontend/package.json` |
| `429 Слишком много попыток` | Сработал rate limit. Счётчики в Redis сбрасываются через `docker compose restart redis` |
| Docker в WSL: `docker: command not found` | Включите Docker Desktop → Settings → Resources → WSL integration для вашего дистрибутива |
