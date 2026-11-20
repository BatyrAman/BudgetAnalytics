# BudgetAnalytics — v0 Design Prototype Context

Source of truth: `docs/design/*` of the BudgetAnalytics repository (FastAPI backend, commit e746e35). This prototype is a **clickable DESIGN PROTOTYPE with demo data**, not the production frontend.

## 1. Hard rules
1. Stack: Next.js (App Router), React, TypeScript (strict), Tailwind CSS, shadcn/ui, lucide-react, Recharts, next-themes. Font: Inter.
2. **No backend in this project**: no API Routes, no Server Actions with business logic, no database, no Supabase, Neon, Upstash, no auth provider, no env secrets. All data comes from a typed in-memory mock client `lib/api/mock.ts` whose functions mirror the real REST endpoints (names in §6). Later it will be replaced by a real client for `/api/v1` of the FastAPI backend.
3. **Do not invent fields, endpoints, calculations or features.** Use only the types in §6. Features marked FUTURE or NEEDS BACKEND are drawn as visually complete but clearly labelled with the badge «Требует backend» or «Скоро» and are never presented as working.
4. **No financial math in the UI.** Totals, percentages, balances, budget usage, deposit interest and goal progress come pre-computed in the mock data, exactly like the API returns them. The UI only formats strings. Never sum amounts of different currencies.
5. UI language: **Russian only**. Locale ru-KZ. Default currency KZT (₸). Demo data must be Kazakhstan-flavoured and clearly fictional; a small «Демо-данные» label appears in the header. No real people, IINs or full card numbers (only last 4 digits).
6. Visual direction: **Corporate Fintech**, balanced density, all modules equally important. Tables and filters inspired by tradernet.kz ETF screener (clean dense tables, right-aligned tabular numbers, filter bar with active-filter chips) — but **no trading features**.
7. Light and Dark themes with identical layout. Theme toggle in the header (Светлая / Тёмная / Системная).
8. Responsive: desktop 1440, tablet 768, mobile 390. Mobile is a real mobile layout, not a scaled desktop. No horizontal page scroll.
9. Accessibility: visible focus ring, labels on all inputs, touch targets ≥ 44px on mobile, colour is never the only signal (amounts have +/− sign, statuses have text).

## 2. Design tokens (CSS variables; map to shadcn tokens in globals.css)
| Token | Light | Dark |
|---|---|---|
| background | #F4F6F8 | #0D1117 |
| surface (card, sidebar, popover) | #FFFFFF | #161B22 |
| surface-secondary (table header, inputs bg) | #F8FAFC | #1F2937 |
| surface-hover | #F1F4F7 | #1C232D |
| text-primary | #17212F | #F0F3F6 |
| text-secondary | #667085 | #9AA4B2 |
| text-tertiary (disabled only) | #98A2B3 | #6E7887 |
| text-on-brand | #FFFFFF | #0D1117 |
| border | #E5EAF0 | #303B49 |
| border-strong (inputs) | #D0D7E0 | #3D4A5A |
| brand (primary action, active nav, focus) | #176B55 | #38BFA0 |
| brand-hover | #125A47 | #4FD1B2 |
| brand-subtle (active nav bg) | #EAF4F0 | #17302B |
| positive (fills/icons) | #16865D | #3CCB91 |
| positive-subtle | #E7F5EE | #17372F |
| negative (fills/icons) | #D14B4B | #F07878 |
| negative-subtle | #FDEDED | #3A2226 |
| warning | #B7791F | #E8B45B |
| warning-subtle | #FDF4E3 | #3A301C |
| info | #4776C7 | #79A7F2 |
| info-subtle | #EBF1FB | #1D2A40 |
| text-positive (small text, AA) | #11744F | #3CCB91 |
| text-negative (small text, AA) | #C23D3D | #F07878 |
| text-warning (small text, AA) | #8F5E14 | #E8B45B |
| text-info (small text, AA) | #3E69B5 | #79A7F2 |
| chart-1 green (income / primary series) | #176B55 | #38BFA0 |
| chart-2 blue (expenses / second series) | #4776C7 | #79A7F2 |
| chart-3 amber | #D69A35 | #E8B45B |
| chart-4 violet | #7A6BD1 | #A99BF0 |
| chart-5 slate («Прочее») | #98A2B3 | #6E7887 |
| chart-grid | #EEF1F5 | #232B36 |
| skeleton | #EDF0F4 | #232B36 |

Rules: cards = surface + 1px border, **no shadow**; shadows only on overlays (modal, sheet, dropdown, toast). Radius: card 12, input/button 8, badge 6. Spacing grid 4px. Only one primary button per view area. Red means overspend/negative only — expenses as a chart series are blue, not red. Brand teal used sparingly in dark theme; no neon, no gradients, no pure black.

Typography (Inter): metric 28/34 bold; H1 24/30 bold; H2 18/24 semibold; H3 15/20 semibold; body 14/20; table/body-small 13/18; label 13/18 semibold; caption 12/16; overline 11/14 semibold uppercase +0.6 tracking. Use `tabular-nums` for all amounts; amounts right-aligned in tables. Minimum text size 12px (11px only for overline).

## 3. Formatting (lib/format.ts — string based, no float math)
- Money from API is a decimal string, e.g. "1250000.50", plus currency_code. Format: `1 250 000,50 ₸` (group separator U+00A0, decimal comma, symbol after a non-breaking space). Symbols: KZT ₸, USD $, EUR €, RUB ₽; unknown → code. In large metric cards only, hide ",00". In tables and forms always 2 decimals.
- Transaction sign is derived from transaction_type: income, refund, transfer_in → "+"; expense, transfer_out → "−" (U+2212). Income amounts use text-positive; expenses use text-primary (not red). Negative balances use text-negative.
- Percent: "80 %" in metrics, "80,00 %" in tables (non-breaking space before %). Percentage points: "+3,4 п. п.". null → "—" with a tooltip explaining why (e.g. «Нет доходов за период — норма сбережений не рассчитывается»).
- Dates: API datetimes are UTC ISO; show in Asia/Almaty. Date `18.11.2026`, datetime `18.11.2026, 22:31`, list day headers `18 ноября`, month `ноябрь 2026`, period `1–30 нояб. 2026`. 24h clock.
- Amount input: accept "," or "." as decimal separator, ignore spaces, max 2 decimals.

## 4. Navigation and shell
Sidebar (desktop 248px; tablet 72px icon rail with tooltips; mobile: bottom nav 5 items + «Ещё» sheet):
- Group «Финансы»: Обзор (/dashboard), Операции (/transactions), Счета (/accounts), Категории (/categories), Бюджеты (/budgets), Аналитика (/analytics), Депозиты (/deposits), Цели (/goals), AI-советник (/advisor)
- Bottom group: Уведомления (/notifications, badge «Скоро»), Настройки (/settings); user card (initials avatar, name, e-mail).
- Mobile bottom nav: Обзор, Операции, «+» (add operation), Аналитика, Ещё.
Header: page title (H1) + one-line description on desktop; contextual actions on the right; «Демо-данные» label; theme toggle; avatar menu (Настройки, Выйти).
Overlays: transaction details = right Sheet 480px on desktop/tablet, full screen on mobile. Forms = Dialog (S 400 / M 560 / L 720); on mobile a full-height bottom sheet with sticky action buttons. Toasts (sonner): bottom-right desktop, top on mobile.

**State preview switcher** (prototype-only, labelled «Демо: состояние»): a small floating control on every data page that switches the page between Обычное / Загрузка / Пусто / Ошибка by query param `?state=default|loading|empty|error`. Loading = skeletons shaped like content; Empty = icon + one sentence + primary action; Error = message + «Повторить» + small «Код запроса: 8ef5ec66…».

## 5. Glossary (use exactly)
Операция (not «транзакция» in UI text), Доход, Расход, Возврат, Перевод: поступление, Перевод: списание, Денежный поток (≠ баланс; caption «Не остаток на счёте»), Баланс, Норма сбережений, Использовано (budget), Номинальная ставка, ГЭСВ (по данным банка), Эффективная годовая ставка (расчёт), Накоплено (goal), Ответ по правилам (AI fallback).

## 6. Data types (mirror the real API exactly; money and percents are strings)
```ts
type TransactionType = 'income' | 'expense' | 'refund' | 'transfer_in' | 'transfer_out'
type CategoryKind = 'income' | 'expense' | 'any'
type AccountType = 'cash' | 'current' | 'card' | 'savings' | 'credit_card' | 'other'
type Capitalization = 'none' | 'monthly' | 'quarterly' | 'annually'
type Page<T> = { items: T[]; total: number; limit: number; offset: number }

// GET /auth/me
type User = { id: number; full_name: string; email: string; is_active: boolean; created_at: string; updated_at: string }
// GET /categories?kind=  (array; kind filter returns that kind AND 'any')
type Category = { id: number; name: string; color: string; icon: string; kind: CategoryKind; is_system: boolean }
// GET /accounts?include_archived=  (array)
type Account = { id: number; name: string; account_type: AccountType; currency_code: string; bank_id: number | null; last4: string | null; is_archived: boolean; opening_balance: string; opening_balance_at: string; balance: string; created_at: string; updated_at: string }
// GET /banks (array, alphabetical)
type Bank = { id: number; name: string; logo: string | null }
// GET /transactions (Page) — newest first ONLY, no sorting; filters: start_date, end_date, category_id, account_id, bank_id, transaction_type, currency, min_amount, max_amount, search (description only), limit (1–200, default 20), offset
type Transaction = { id: number; amount: string /* always positive */; currency_code: string; description: string | null; transaction_type: TransactionType; transaction_date: string; category_id: number; bank_id: number | null; account_id: number | null; created_at: string; updated_at: string }
// GET /transactions/{id}
type TransactionDetail = Transaction & { category_name: string; bank_name: string /* "—" if none */ }
// GET /budgets (Page) — metadata only. NEVER display its `spent`/`progress` fields.
type Budget = { id: number; title: string; monthly_limit: string; currency_code: string; category_id: number | null /* null = all expenses */ }
// GET /budgets/{id}/utilization?month=YYYY-MM — the ONLY source of budget usage
type BudgetUtilization = { budget_id: number; month: string; currency_code: string; limit: string; spent: string; remaining: string; utilization_percent: string; is_exceeded: boolean }
// GET /analytics/summary?date_from&date_to&currency
type Summary = { period: { date_from: string; date_to: string; timezone: string }; currency_code: string; income: string; gross_expenses: string; refunds: string; net_expenses: string; net_cash_flow: string; transfers_in: string; transfers_out: string; savings_rate: string | null; transaction_count: number }
type CategoryAmount = { category_id: number; name: string; amount: string; transaction_count: number; share_percent: string | null }
// GET /analytics/category-breakdown?kind=expense|income
type CategoryBreakdown = { period: Summary['period']; currency_code: string; kind: 'expense' | 'income'; total: string; items: CategoryAmount[] }
// GET /analytics/monthly?year= (12 months incl. empty ones)
type MonthSummary = { month: string; income: string; net_expenses: string; net_cash_flow: string; savings_rate: string | null; transaction_count: number }
type Monthly = { year: number; timezone: string; currency_code: string; months: MonthSummary[]; total: MonthSummary }
// GET /analytics/comparison?month=
type MetricChange = { current: string; previous: string; change: string; change_percent: string | null }
type Comparison = { timezone: string; currency_code: string; current: MonthSummary; previous: MonthSummary; income: MetricChange; net_expenses: MetricChange; net_cash_flow: MetricChange; savings_rate_change_pp: string | null }
// GET /dashboard/overview?currency= — CURRENT MONTH ONLY, one currency, no period picker
type Overview = { generated_at: string; timezone: string; currency_code: string; month: string; current_balance: string | null; accounts: { account_id: number; name: string; currency_code: string; balance: string }[]; monthly_income: string; monthly_expenses: string; monthly_net_cash_flow: string; budgets: { budget_id: number; title: string; limit: string; spent: string; utilization_percent: string; is_exceeded: boolean }[]; indicators: { savings_rate: string | null; expense_to_income_percent: string | null; expense_change_percent: string | null; income_change_percent: string | null; average_monthly_expenses_3m: string | null; emergency_fund_months: string | null; budgets_exceeded: number; budgets_total: number; deposits_principal: string; deposits_expected_interest: string } }
// GET /deposits (Page), POST /deposits/calculate (nothing stored)
type Maturity = { term_days: number; capitalization_periods: number; stub_days: number; interest: string; maturity_amount: string; effective_annual_rate: string | null; assumptions: string[] }
type Deposit = { id: number; bank_id: number; principal: string; currency_code: string; interest_rate: string /* nominal annual % */; effective_rate: string | null /* ГЭСВ as given by bank */; capitalization: Capitalization; start_date: string; end_date: string; maturity: Maturity }
type DepositCalculation = { principal: string; currency_code: string; interest_rate: string; capitalization: Capitalization; start_date: string; maturity_date: string; maturity: Maturity }
// GET /goals (array). saved_amount is entered manually; currency can't be changed after creation
type Goal = { id: number; name: string; currency_code: string; target_amount: string; saved_amount: string; target_date: string | null; progress_percent: string /* may exceed 100 */; remaining: string; is_reached: boolean; months_left: number | null; required_monthly_saving: string | null }
// POST /advisor/ask {question 3–500} and POST /advisor/insights — single question, NO chat history on the server
type Fact = { id: string; topic: string; label: string; value: string; unit: string; period: string | null }
type AdvisorMeta = { generated_by: 'llm' | 'rules'; fallback_reason: 'disabled' | 'limit_reached' | 'provider_error' | 'invalid_output' | null; currency_code: string; as_of: string; facts: Fact[]; disclaimers: string[] }
type AdvisorAnswer = AdvisorMeta & { answer: { answer: string; evidence: string[]; assumptions: string[]; involves_investment: boolean; needs_more_data: boolean; follow_up_question: string | null } }
type AdvisorReport = AdvisorMeta & { report: { summary: string; insights: { area: string; title: string; explanation: string; evidence: string[] }[]; recommendations: { title: string; action: string; reasoning: string; evidence: string[]; assumptions: string[]; priority: 'high' | 'medium' | 'low'; involves_investment: boolean }[]; risks: { title: string; explanation: string; severity: 'high' | 'medium' | 'low'; evidence: string[] }[]; assumptions: string[]; data_gaps: string[] } }
// Imports: GET /imports/banks, POST /imports/{bank}/preview (csv/xlsx ≤ 5 MB, ≤ 5000 rows, preview lives 24h), GET /imports/{id}/rows?status=, POST /imports/{id}/commit {exclude_rows, include_possible_duplicates}, DELETE /imports/{id}, GET /imports
type ImportBank = { code: 'kaspi' | 'halyk' | 'freedom'; name: string; formats: string[]; verified: boolean /* all false today */ }
type ImportSummary = { id: number; bank: string; file_name: string; file_format: string; file_size: number; status: 'preview' | 'committed' | 'failed' | 'cancelled' | 'expired'; account_id: number | null; total_rows: number; valid_rows: number; invalid_rows: number; duplicate_rows: number; imported_rows: number; period_start: string | null; period_end: string | null; error_message: string | null; created_at: string; expires_at: string | null }
type ImportRow = { row_number: number; status: 'valid' | 'invalid' | 'duplicate' | 'possible_duplicate' | 'imported' | 'skipped'; transaction_date: string | null; amount: string | null; currency_code: string | null; transaction_type: TransactionType | null; description: string | null; merchant: string | null; category_hint: string | null; error_message: string | null }
```
Category/transaction compatibility: income category → income, transfer_in, transfer_out; expense category → expense, refund, transfers; any → all. 16 system categories (read-only, lock icon): expense — Продукты, Кафе и рестораны, Транспорт, Жильё и коммунальные услуги, Связь и интернет, Здоровье, Одежда и обувь, Образование, Развлечения, Подарки, Платежи по кредитам, Прочие расходы; income — Зарплата, Прочие доходы; any — Переводы между своими счетами, Без категории. Category icons are lucide names: shopping-cart, utensils, car, home, wifi, heart, shirt, book, film, gift, credit-card, dots(→ellipsis), briefcase, plus, repeat, wallet.
Banks (seed): Altyn Bank, Bank CenterCredit, Bank RBK, Bereke Bank, Eurasian Bank, ForteBank, Freedom Bank, Halyk Bank, Home Credit Bank, Jusan Bank, Kaspi Bank, Nurbank, Otbasy Bank, Shinhan Bank Kazakhstan, Другой банк. logo is null → show bank initials in a circle.

## 7. Demo data (consistent! totals must match the parts)
User «Айгерим Демо», demo@example.kz. Accounts: «Kaspi Gold» card KZT ••4417 balance "485320.75"; «Halyk депозитный» savings KZT "1200000.00"; «Наличные» cash KZT "38500.00"; «USD карта» card USD ••9021 "1250.00" (shows why currencies are not summed); one archived account «Старая карта». Overview (KZT, ноябрь 2026): current_balance "1723820.75" (= 485320.75 + 1200000 + 38500), monthly_income "650000.00", monthly_expenses "412870.40", monthly_net_cash_flow "237129.60", savings_rate "36.48". Monthly 2026: plausible values; every month's net_cash_flow = income − net_expenses. ~40 realistic transactions (Magnum, Small, Glovo, Yandex Go, Kaspi переводы, коммунальные услуги, зарплата ТОО «Демо»). Budgets: Продукты 150 000 ₸ (used 118 400 → 78,93 %), Кафе 60 000 ₸ (used 71 250 → 118,75 %, exceeded), Транспорт 40 000 ₸ (used 21 900 → 54,75 %), «Все расходы» 500 000 ₸. Deposit: Halyk Bank 1 000 000 ₸, 16 % nominal, ГЭСВ 17,2 %, monthly capitalization, 01.01.2026–01.01.2027 → interest "172270.80", maturity "1172270.80", EAR "17.2271". Goals: «Подушка безопасности» 1 200 000 / 300 000 → 25,00 %, 12 months, 75 000 ₸/мес; «Отпуск в Турции» 900 000 / 960 000 → 106,67 %, reached; «Ноутбук» 600 000 / 150 000, no date.
