# API → UI Mapping

> Источник: OpenAPI, сгенерированный из `backend/app/main.py` (коммит `e746e35`), с проверкой поведения по коду сервисов. Префикс всех путей — `/api/v1`. Deprecated-эндпоинты (28 операций, `ENABLE_LEGACY_API`) во frontend **не используются**.
> Поле со звёздочкой (`*`) обязательно. «Расчёт: BE» — значение считает backend, frontend только форматирует.

## 0. Общие соглашения

### 0.1 Аутентификация и сессия
| Аспект | Поведение | Источник |
|---|---|---|
| Схема | `Authorization: Bearer <access_token>` | `api/deps.py` `oauth2_scheme` |
| Access-токен | 30 мин по умолчанию (`ACCESS_TOKEN_EXPIRE_MINUTES`) | `core/config.py:57` |
| Refresh-токен | 7 дней (`REFRESH_TOKEN_EXPIRE_DAYS`), **одноразовый**: `POST /auth/refresh` возвращает новую пару, старый refresh становится недействительным; повторное использование старого → 401 и отзыв семейства токенов | `api/auth.py`, `services/auth.py` |
| Хранение | Решение frontend-архитектуры. Backend использует Bearer, cookie не поддерживает (`allow_credentials=False`) | `main.py` CORS |
| Выход | `POST /auth/logout` (по refresh, идемпотентно); уже выданный access живёт до истечения срока | `api/auth.py` |
| CORS (dev) | Разрешён только `http://localhost:3000`; доступные заголовки: `X-Request-ID`, `Retry-After` | `.env`, `main.py` |

### 0.2 Формат ошибок
Все ошибки: `{ "detail": string | [ {loc, msg, type} ], "code": string, "request_id": string | null }` (`core/errors.py` `ErrorResponse`).

| HTTP | `code` | Когда | Что делает UI |
|---|---|---|---|
| 400 | `bad_request` | Бизнес-правило сервиса (неподходящая категория, чужой счёт, неизвестная валюта…) | Текст рядом с полем или в баннере формы. `detail` на **английском** → словарь русских сообщений по известным строкам (**G-10**) |
| 401 | `unauthorized` | Нет или истёк токен; неверный логин | refresh → повтор; иначе — экран входа |
| 403 | `forbidden` | Правка системной категории; неактивный пользователь при входе | Сообщение |
| 404 | `not_found` | Нет записи **или чужая запись** | «Не найдено» |
| 409 | `conflict` | Дубликат имени; удаление используемой сущности; повторный commit импорта | Сообщение и альтернативное действие |
| 413 | `payload_too_large` / `file_too_large` | Тело запроса или файл больше лимита | «Файл больше 5 МБ» |
| 415 | `unsupported_media_type` / `unsupported_format` | Тип файла | «Поддерживаются CSV и XLSX» |
| 422 | `validation_error` | Схема (Pydantic): `detail[]` с `loc` (например `["body","amount"]`), `msg` на англ., `type` (`missing`, `greater_than`, `string_too_short`, `value_error` и т. п.) | Сообщение у поля по `loc[-1]` и `type` |
| 422 | коды импорта | `FileRejected` со своим машинным `code` (§9) | Русский текст по `code` |
| 429 | `too_many_requests` | Rate limit | Таймер из `Retry-After` |
| 500 | `internal_error` | Сбой | Блок ошибки + `request_id` |

**Несогласованность:** одинаковое бизнес-правило иногда отдаёт разные статусы. Например, «Bank not found» — 400 для транзакций и депозитов (`AppError`), но 422 для счетов (`DomainValidationError`, `services/accounts.py:64`). UI должен обрабатывать оба варианта (**G-10**).

#### Business error codes (G-10, backend)
Каждое бизнес-правило не-deprecated API отдаёт стабильный `code` (snake_case). HTTP-статус и английский `detail` не менялись — UI выбирает русский текст **по `code`**, а не по `detail`. Общие коды из таблицы выше (`bad_request`, `not_found`, `conflict`, `forbidden`, `unauthorized`) остаются только как запасной вариант для мест без отдельного кода.

| HTTP | `code` | Правило | Где возникает |
|---|---|---|---|
| 401 | `invalid_credentials` | Неверный e-mail или пароль | `POST /auth/login`, `POST /auth/token` |
| 403 | `inactive_user` | Пользователь деактивирован | Вход; любой защищённый эндпоинт (`api/deps.py`) |
| 409 | `email_taken` | E-mail уже зарегистрирован | `POST /auth/register` (и гонка по `ix_users_email`) |
| 400 | `wrong_password` | Старый пароль неверен | `POST /auth/change-password` |
| 401 | `unauthorized` | Токен не передан | Любой защищённый эндпоинт |
| 401 | `invalid_token` | Токен повреждён, неверного типа, отозван (logout-all, смена пароля) или refresh уже использован | Защищённые эндпоинты; `POST /auth/refresh` |
| 401 | `token_expired` | Срок действия access/refresh-токена истёк | Защищённые эндпоинты (→ refresh); `POST /auth/refresh` (→ экран входа) |
| 404 | `category_not_found` | Категории нет или она чужая | `/categories/{id}` |
| 400 | `category_not_found` | Категория в теле запроса не найдена | `POST/PATCH /transactions`, `POST/PATCH /budgets` |
| 400 | `category_kind_mismatch` | Тип операции не подходит виду категории | `POST/PATCH /transactions` |
| 403 | `system_category_readonly` | Системную категорию нельзя менять/удалять | `PATCH/DELETE /categories/{id}` |
| 409 | `category_exists` | Категория с таким именем уже есть | `POST/PATCH /categories` |
| 409 | `category_in_use` | Категория используется операциями или бюджетами | `DELETE /categories/{id}` |
| 409 | `category_kind_conflict` | Новый вид несовместим с существующими операциями | `PATCH /categories/{id}` (`kind`) |
| 404 | `account_not_found` | Счёта нет или он чужой | `/accounts/{id}` |
| 400 | `account_not_found` | Счёт в теле запроса не найден | `POST/PATCH /transactions`; превью импорта (`account_id`) |
| 409 | `account_has_transactions` | У счёта есть операции — только архивировать | `DELETE /accounts/{id}` |
| 409 | `account_name_taken` | Счёт с таким именем уже есть (уникальный индекс) | `POST/PATCH /accounts` |
| 400 | `currency_mismatch` | Валюта операции ≠ валюте счёта | `POST/PATCH /transactions` |
| 400 / 422 | `bank_not_found` | Банк не найден. **400** для операций и вкладов, **422** для счетов (статус сохранён) | `/transactions`, `/deposits`, `/accounts` |
| 400 / 422 | `unknown_currency` | Валюта не из справочника. **400**: операции, бюджеты, цели, вклады, `POST /deposits/calculate`; **422**: счета и параметр `currency` аналитики/обзора | см. слева |
| 404 | `budget_not_found` | Бюджета нет или он чужой | `/budgets/{id}`, `/budgets/{id}/utilization` |
| 400 | `budget_income_category` | Бюджет нельзя привязать к категории дохода | `POST/PATCH /budgets` |
| 404 | `transaction_not_found` | Операции нет или она чужая | `/transactions/{id}` |
| 404 | `deposit_not_found` | Вклада нет или он чужой | `/deposits/{id}` |
| 404 | `goal_not_found` | Цели нет или она чужая | `/goals/{id}` |
| 409 | `goal_name_taken` | Цель с таким именем уже есть (уникальный индекс) | `POST/PATCH /goals` |
| 409 | `duplicate` | Иное нарушение уникальности (запасной код для 23505) | Любой |
| 422 | `invalid_date_range` | Конец периода раньше начала | `PATCH /deposits/{id}`; `GET /transactions` (`start_date`/`end_date`); аналитика (`date_from`/`date_to`) |
| 422 | `invalid_amount_range` | `max_amount` < `min_amount` | `GET /transactions` |
| 422 | `period_too_long` | Период больше 5 лет | Аналитика с `date_from`/`date_to` |
| 422 | `invalid_month` | `month` не в формате `YYYY-MM` | `/budgets/utilization`, `/budgets/{id}/utilization`, аналитика по месяцу |
| 422 | `unknown_timezone` | `tz` — неизвестный IANA-пояс | Любой эндпоинт с `tz` |
| 404 | `import_not_found` | Импорта нет или он чужой | `/imports/{id}…` |
| 409 | `import_expired` | Превью истекло — загрузить файл заново | `POST /imports/{id}/commit` |
| 409 | `import_not_committable` | Импорт уже подтверждён/отменён/истёк | `POST /imports/{id}/commit` |
| 409 | `import_not_cancellable` | Отменить можно только превью | `DELETE /imports/{id}` |
| 413 / 415 / 422 / 400 | коды `FileRejected` | Проблемы файла выписки (без изменений, §9) | `POST /imports/{bank}/preview` |
| 429 | `too_many_requests` | Rate limit | Любой |
| 503 | `service_unavailable` | Хранилище rate limit недоступно | Любой |
| 422 | `validation_error` | Ошибка схемы Pydantic (`detail` — массив) | Любой |
| 422 | `invalid_financial_input` | Недопустимые входные данные финансового расчёта | Калькуляторы, аналитика |

Примечания: ошибки дат в **схеме** (например `end_date <= start_date` при `POST /deposits`) остаются `validation_error` с массивом `detail`, т. к. это валидация Pydantic. Отдельного кода для `PATCH /goals` с неизвестной валютой нет — валюта цели не меняется.

### 0.3 Rate limits (`core/rate_limit.py:56-63`)
| Правило | Лимит |
|---|---|
| Вход | 20/мин на IP; 10/15 мин на аккаунт (e-mail), общий счётчик для `/login` и `/token` |
| Регистрация | 10/час на IP |
| Refresh | 60/мин на IP |
| Смена пароля | 5/час на пользователя |
| Импорт | 30/час на пользователя |
| AI-советник | 30/час на пользователя (`insights` и `ask` вместе) + дневной лимит токенов (`AI_DAILY_TOKEN_LIMIT_PER_USER` = 50 000) |
| Любой API | 600/мин на IP |

### 0.4 Типы данных
| Тип | Формат в API | Правило UI |
|---|---|---|
| Деньги | Строка Decimal с 2 знаками: `"450000.00"`; отрицательные — `"-1500.00"` (баланс долга) | Не парсить в `float` для вычислений; форматировать как строку (DESIGN_SYSTEM_SPEC §6) |
| Деньги во входе | `number | string`, > 0 (или ≥ 0), максимум 18 знаков, 2 после запятой | **Отправлять строкой** (`"1500.50"`), чтобы исключить float |
| Проценты | Строка (`"80.00"`, `"17.2271"`) или `null` | `null` → «—» с подсказкой |
| Дата-время | ISO 8601 в UTC (`2026-11-18T17:13:24.970598Z`) | Показывать в `tz` пользователя |
| Дата | `YYYY-MM-DD` | `ДД.ММ.ГГГГ` |
| Месяц | `YYYY-MM` | «ноябрь 2026» |
| Валюта | ISO 4217, 3 буквы, верхний регистр | Символ из справочника (§0.6) |

### 0.5 Пагинация и списки
| Эндпоинт | Форма ответа | Пагинация |
|---|---|---|
| `/transactions`, `/budgets`, `/deposits`, `/imports`, `/imports/{id}/rows` | `{items, total, limit, offset}` | `limit` 1–200 (по умолч. 20), `offset` ≥ 0 |
| `/accounts`, `/categories`, `/goals`, `/banks`, `/imports/banks` | Массив | Нет |

Сортировка нигде не настраивается (**G-7**). Порядок: транзакции — новые сначала; банки — по имени; остальные — порядок backend (UI не обещает сортировку).

### 0.6 Валюты и часовой пояс
- В БД 4 валюты: `KZT` (₸), `USD` ($), `EUR` (€), `RUB` (₽), у всех 2 знака после запятой (миграция `5d2fb0f83b83`). **Эндпоинта со списком валют нет** (**G-5**) — до его появления frontend держит статический список из этих 4 кодов.
- Неизвестная валюта → 400 «Unknown currency».
- `tz` — IANA-имя, по умолчанию `Asia/Almaty`; неверное → 422. Влияет на границы дня и месяца в аналитике, бюджетах, обзоре и целях.
- **Мультивалютность:** у счёта валюта фиксирована. Транзакция со счётом обязана быть в валюте счёта. Аналитика, обзор и бюджеты считают **одну** валюту за запрос (`currency`, по умолчанию валюта пользователя); суммы в других валютах **не включаются и не конвертируются**.

---

## 1. Аутентификация — `api/auth.py`

| UI | Метод и путь | Запрос | Ответ | Ошибки |
|---|---|---|---|---|
| A-2 Регистрация | `POST /auth/register` | `full_name*` (1–255), `email*`, `password*` (8–128) | 201 `{access_token, refresh_token, token_type}` | 409 e-mail занят, 422, 429 |
| A-1 Вход | `POST /auth/login` | `email*`, `password*` (≤ 1024) | 200 пара токенов | 401 «Incorrect email or password», 403 «Inactive user», 429 |
| (Swagger) | `POST /auth/token` | form: `username`, `password` | как `/login` | — во frontend не используется |
| Обновление сессии | `POST /auth/refresh` | `refresh_token*` | 200 новая пара | 401 |
| Выход | `POST /auth/logout` | `refresh_token*` | 204 | — |
| S-3 Выйти везде | `POST /auth/logout-all` | — | 204 | 401 |
| S-3 Смена пароля | `POST /auth/change-password` | `old_password*`, `new_password*` (8–128) | 200 `{message}`; **все сессии завершены** | 400 неверный старый пароль, 429 |
| S-1 Профиль | `GET /auth/me` | — | `{id, full_name, email, is_active, created_at, updated_at}` | 401 |
| A-3/A-4 | — | — | — | 🟧 нет эндпоинтов (**G-1**) |

E-mail хранится в нижнем регистре; при входе регистр не важен.

## 2. Категории — `api/categories.py`, `services/categories.py`

| UI | Метод и путь | Детали |
|---|---|---|
| C-1, T-3 | `GET /categories?kind=income\|expense` | Массив `{id, name, color, icon, kind, is_system}`; системные и свои; с `kind` — категории этого вида **и** `any` |
| C-2 | `POST /categories` | `name*` (2–100), `color` (`^#[0-9A-Fa-f]{6}$`, по умолч. `#3B82F6`), `icon` (`^[a-z0-9-]+$`, по умолч. `wallet`), `kind` (по умолч. `any`) → 201. 409, если имя уже видно пользователю (включая системные) |
| C-2 | `GET /categories/{id}` | Одна категория (своя или системная); чужая → 404. Для открытия формы редактирования по прямой ссылке |
| C-2 | `PATCH /categories/{id}` | Частичное обновление; системная → 403; смена `kind`, несовместимая с операциями → 409 |
| C-1 | `DELETE /categories/{id}` | 204; используется в операциях или бюджетах → 409; системная → 403 |

**Правило совместимости** (`models/enums.py::category_allows`):
| Вид категории | Разрешённые типы транзакций |
|---|---|
| `income` | `income`, `transfer_in`, `transfer_out` |
| `expense` | `expense`, `refund`, `transfer_in`, `transfer_out` |
| `any` | все |

Системные категории (16): доходные — «Зарплата», «Прочие доходы»; `any` — «Переводы между своими счетами», «Без категории»; остальные 12 — расходные (миграция `a1c3e5f7b9d2`).

## 3. Счета и банки — `api/accounts.py`, `api/banks.py`

| UI | Метод и путь | Детали |
|---|---|---|
| AC-1 | `GET /accounts?include_archived=false` | Массив `AccountResponse`: `id, name, account_type, currency_code, bank_id, last4, is_archived, opening_balance, opening_balance_at, balance` |
| AC-1 | `POST /accounts` | `name*` (1–100), `account_type*` (`cash, current, card, savings, credit_card, other`), `currency` (по умолч. валюта пользователя, потом **не меняется**), `bank_id`, `last4` (`^[0-9]{4}$`), `opening_balance` (может быть < 0), `opening_balance_at` (по умолч. сейчас) |
| AC-2 | `GET/PATCH/DELETE /accounts/{id}` | PATCH без валюты; `is_archived`; DELETE только без операций (иначе 409 «archive it instead») |
| Формы | `GET /banks` | `[{id, name, logo}]` по алфавиту; 15 засеянных + созданные импортом; `logo` = `null` у засеянных (**G-20**) |

**Баланс (Расчёт: BE)** — `services/finance/indicators.py:46-107`: `balance = opening_balance + Σ(income, refund, transfer_in) − Σ(expense, transfer_out)` по операциям, привязанным к счёту и датированным не раньше `opening_balance_at`. Операции до этой даты не учитываются.

## 4. Транзакции — `api/transaction.py`, `services/transactions.py`, `repositories/transaction.py`

| UI | Метод и путь | Детали |
|---|---|---|
| T-1 | `GET /transactions` | Фильтры: `start_date`, `end_date` (date-time, включительно; без смещения = UTC), `category_id`, `account_id`, `bank_id`, `transaction_type`, `currency`, `min_amount`, `max_amount` (≥ 0), `search` (1–100, **ILIKE только по `description`**), `limit`, `offset`. Порядок: `transaction_date desc, id desc` |
| T-2 | `GET /transactions/{id}` | `TransactionDetail` = поля + `category_name` (`"—"` если нет), `bank_name` (`"—"` если нет) |
| T-3 | `POST /transactions` | `amount*` (> 0), `transaction_type*`, `transaction_date*` (date-time), `category_id*`, `description` (≤ 500), `account_id`, `bank_id`, `currency` (по умолч. валюта счёта, иначе пользователя) → 201 |
| T-3 | `PATCH /transactions/{id}` | Частичное; `PUT` — то же самое (legacy), используем `PATCH` |
| T-2 | `DELETE /transactions/{id}` | 204 |

**Типы:** `income` (Доход), `expense` (Расход), `refund` (Возврат — уменьшает расходы), `transfer_in` (Перевод: поступление), `transfer_out` (Перевод: списание). Сумма **всегда положительная**; знак в UI определяется типом 🟦: `+` для `income`, `refund`, `transfer_in`; `−` для `expense`, `transfer_out`.

**Ошибки сервиса (400):** «Category not found», «Category '<name>' (<kind>) cannot be used for a <type> transaction», «Bank not found», «Account not found», «Currency must match the account's currency», «Unknown currency».

**Особенности:**
- `start_date`/`end_date` — date-time в UTC: для «дня» в Алматы frontend передаёт границы с `+05:00` 🟦;
- транзакции в список **не включают имена** категории, счёта и банка — их подставляет frontend из справочников 🟦 (**G-7**);
- архивные счета не блокируются (**G-9**).

## 5. Бюджеты — `api/budget.py`, `services/budgets.py`, `services/financial_summary.py`

| UI | Метод и путь | Детали |
|---|---|---|
| B-1 | `GET /budgets` | Страница `BudgetResponse`: `id, title, monthly_limit, currency_code, category_id, spent (DEPRECATED)` |
| B-2 | `GET /budgets/{id}` | `BudgetDetail` с `remaining`, `progress` (float), `is_exceeded` — **из ручного `spent`, не использовать** (**G-6**) |
| B-2, B-1 | `GET /budgets/{id}/utilization?month=YYYY-MM&tz=` | `{budget_id, month, currency_code, limit, spent, remaining, utilization_percent, is_exceeded}` — **единственный правильный источник использования** |
| B-3 | `POST /budgets` | `title*` (2–100), `monthly_limit*` (> 0), `currency`, `category_id` (нет = «все расходы»); доходная категория → 400 |
| B-3 | `PATCH /budgets/{id}` | Частичное; поле `spent` (DEPRECATED) в UI не выводить |
| B-1 | `DELETE /budgets/{id}` | 204 |
| D-1, B-1 | `GET /dashboard/overview` → `budgets[]` | Использование всех бюджетов **в выбранной валюте** за текущий месяц одним запросом |

**Использование (Расчёт: BE)** — `financial_summary.py::budget_utilization`:
- `spent` = Σ`expense` − Σ`refund` за календарный месяц в `tz`, в валюте бюджета и в его категории (или по всем категориям);
- `remaining` = `limit − spent` (может быть < 0);
- `utilization_percent` = `spent / limit × 100`;
- `is_exceeded` = `spent > limit`.

## 6. Аналитика и обзор — `api/analytics.py`, `api/overview.py`, `services/financial_summary.py`, `services/overview.py`

Общие параметры: `date_from`, `date_to` (даты, включительно, **по умолчанию — текущий месяц**), `tz`, `currency`.

| UI | Метод и путь | Ответ (все суммы — Расчёт: BE) |
|---|---|---|
| AN-1, D-1 | `GET /analytics/summary` | `period{date_from,date_to,timezone}`, `income`, `gross_expenses`, `refunds`, `net_expenses`, `net_cash_flow`, `transfers_in`, `transfers_out`, `savings_rate` (`null` при доходе 0), `transaction_count`, `note` |
| AN-2 | `GET /analytics/income` | `total`, `by_category[]{category_id,name,amount,transaction_count,share_percent}` |
| AN-2 | `GET /analytics/expenses` | `gross_expenses`, `refunds`, `net_expenses`, `by_category[]` |
| AN-2 | `GET /analytics/savings-rate` | `income`, `net_expenses`, `savings_rate`, `expense_to_income_percent` |
| D-1, AN-2 | `GET /analytics/category-breakdown?kind=expense\|income` | `total`, `items[]` (`share_percent` = `null`, если итог ≤ 0) |
| D-1, AN-1 | `GET /analytics/monthly?year=*` | 12 месяцев (пустые включены) + `total` |
| AN-1 | `GET /analytics/comparison?month=` | `current`, `previous`, `income`, `net_expenses`, `net_cash_flow` (`{current, previous, change, change_percent}`), `savings_rate_change_pp` |
| D-1 | `GET /dashboard/overview` | см. SCREEN_INVENTORY D-1; период — **только текущий месяц** |

**Формулы (BE):**
- `net_expenses = expenses − refunds`;
- `net_cash_flow = income − net_expenses`;
- `savings_rate = (income − net_expenses) / income × 100`;
- переводы исключены из дохода и расхода;
- `change_percent` = `null`, если прошлое значение 0;
- `emergency_fund_months = current_balance / average_monthly_expenses_3m` (3 последних **полных** месяца).

## 7. Депозиты — `api/deposits.py`, `services/deposit_service.py`, `services/finance/deposit.py`

| UI | Метод и путь | Детали |
|---|---|---|
| DP-3 | `POST /deposits/calculate` | `principal*` (> 0), `currency` (по умолч. **KZT**), `interest_rate*` (0–100, номинальная годовая), `capitalization` (`none`, `monthly`, `quarterly`, `annually`), `start_date*`, **ровно одно** из `end_date` или `term_months` (1–600) → `{principal, currency_code, interest_rate, capitalization, start_date, maturity_date, maturity}`; ничего не сохраняется |
| DP-1 | `GET /deposits` | Страница; каждый элемент с `maturity` |
| DP-1/2 | `POST /deposits` | `bank_id*`, `principal*`, `currency`, `interest_rate*`, `effective_rate` (ГЭСВ, 0–1000, хранится как есть, **никогда не используется как номинальная**), `capitalization`, `start_date*`, `end_date*` (> `start_date`) |
| DP-2 | `GET/PATCH/DELETE /deposits/{id}` | PATCH проверяет `end_date > start_date` (422) |

**Расчёт (BE)** — `services/finance/deposit.py`, ACT/365 Fixed:
- без капитализации: `interest = P · r · days / 365`;
- с капитализацией: проценты капитализируются в «годовщины» даты начала (ежемесячно/ежеквартально/ежегодно); оставшиеся `stub_days` — простые проценты от наращенной суммы; округление один раз, ROUND_HALF_UP до копеек;
- `effective_annual_rate` = EAR номинальной ставки при данной капитализации (`null` без капитализации).
- `maturity.assumptions[]` — на английском (**G-10**).

## 8. Финансовые цели — `api/goals.py`, `services/goals.py`

| UI | Метод и путь | Детали |
|---|---|---|
| G-1 | `GET /goals?tz=` | Массив `GoalResponse` |
| G-3 | `POST /goals` | `name*` (1–100, уникально → 409), `target_amount*` (> 0), `saved_amount` (≥ 0, по умолч. 0), `currency` (по умолч. валюта пользователя; неизвестная → 400), `target_date` |
| G-2/3 | `PATCH /goals/{id}` | `name`, `target_amount`, `saved_amount`, `target_date` (можно `null`); **валюту изменить нельзя** |
| G-2 | `DELETE /goals/{id}` | 204 |

**Производные поля (Расчёт: BE):**
- `progress_percent` = saved / target × 100 (0,01 %, может быть > 100);
- `remaining` = max(target − saved, 0);
- `is_reached` = (remaining == 0);
- `months_left` = разница календарных месяцев между сегодняшним днём в `tz` и `target_date` (`null`, если даты нет или ≤ 0);
- `required_monthly_saving` = remaining / months_left (`null`, если неприменимо).

## 9. Импорт — `api/imports.py`, `services/imports/*`

| UI | Метод и путь | Детали |
|---|---|---|
| I-1 шаг 1 | `GET /imports/banks` | `[{code, name, formats, verified}]` — сейчас `kaspi`, `halyk`, `freedom`, все `verified=false` |
| I-1 шаг 2 | `POST /imports/{bank}/preview` | multipart: `file*` (.csv/.xlsx), `account_id` → 201 `{import: ImportSummary, rows: [первые строки], verified_parser}` |
| I-1 шаг 3 | `GET /imports/{id}/rows?status=` | Страница `ImportRowOut`: `row_number, status, transaction_date, amount, currency_code, transaction_type, type_source (keyword\|sign), description, merchant, category_hint, error_code, error_message, transaction_id` |
| I-1 шаг 4 | `POST /imports/{id}/commit` | `exclude_rows: int[]`, `include_possible_duplicates: bool` → `{import, imported, skipped}`; второй раз → 409 |
| I-1 отмена | `DELETE /imports/{id}` | 204; только для `preview`, иначе 409 |
| I-2 | `GET /imports`, `GET /imports/{id}` | История, `ImportSummary` |

**Лимиты:** файл ≤ 5 МБ (`IMPORT_MAX_FILE_BYTES`), ≤ 5000 строк, предпросмотр живёт 24 ч (`IMPORT_PREVIEW_TTL_HOURS`); XLSX без макросов и внешних ссылок.

**Коды отказа файла (`code` в ошибке):** `empty_file`, `file_too_large`, `unsupported_format`, `pdf_not_supported`, `unreadable_file`, `malformed_file`, `missing_columns`, `format_mismatch`, `too_many_rows`, `no_transactions`, `malicious_file`, `unsupported_bank`, `account_not_found`.

**Коды ошибок строк (`error_code`):** `missing_date`, `invalid_date`, `date_out_of_range`, `missing_amount`, `invalid_amount`, `zero_amount`, `invalid_currency`.

**Правила commit:**
- импортируются строки со статусом `valid` минус `exclude_rows`;
- `duplicate` не импортируются никогда; `possible_duplicate` — только с флагом;
- категория строки — по `category_hint`, а если она не подходит к типу — «Без категории» (`service.py`).

## 10. AI-советник — `api/advisor.py`, `services/ai/*`

| UI | Метод и путь | Детали |
|---|---|---|
| AI-2 | `POST /advisor/insights?tz=&currency=` | Без тела → `AdvisorReportResponse` |
| AI-1 | `POST /advisor/ask?tz=&currency=` | `question*` (3–500) → `AdvisorAnswerResponse` |

**Общие метаданные ответа:** `generated_by` (`llm`|`rules`), `fallback_reason` (`disabled`|`limit_reached`|`provider_error`|`invalid_output`|`null`), `provider`, `model`, `prompt_version`, `currency_code`, `as_of`, `facts[]{id, topic, label, value, unit, period}`, `disclaimers[]` (по-русски).

**Тексты:** ответы LLM — по-русски (`prompts.py:15`); дисклеймеры — по-русски (`financial_advisor.py:44-55`); подписи фактов (`label`) формирует backend.

**Ограничения:**
- в dev и по умолчанию `AI_PROVIDER=none` → ответы всегда из правил (`generated_by=rules`, `fallback_reason=disabled`);
- истории нет; каждый `ask` независим (**G-12**);
- числа в ответе обязаны ссылаться на `facts`: backend проверяет это защитным guard-ом (`services/ai/guard.py`).

## 11. Что считается на frontend

| Значение | Где | Правило |
|---|---|---|
| Знак суммы | Списки транзакций | По `transaction_type` (§4) — это отображение, не расчёт |
| Ширина прогресс-бара | Бюджеты, цели | min(процент из API, 100 %) — только визуально; текст показывает настоящий процент |
| Группировка по дате и валюте | Списки | Без суммирования денег |
| Подстановка имён по id | Транзакции, депозиты | Join со справочниками |
| Границы периодов для запросов | Фильтры | Даты в `tz` → `start_date`/`end_date` с явным смещением |

**Запрещено на frontend:** суммы по нескольким валютам, итоги, проценты, остатки бюджета, доход по вкладу, прогресс цели, норма сбережений — всё это есть в API или отсутствует (тогда это пробел backend, а не задача frontend).
