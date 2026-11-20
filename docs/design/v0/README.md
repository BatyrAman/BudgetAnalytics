# v0 Design Prototype

Clickable **design prototype** of BudgetAnalytics generated in v0 (Vercel) from the Task 0 design contract. This is **not** the production frontend:
- data is demo data from an in-memory mock client;
- there is no backend code;
- nothing from the prototype is merged into this repository.

| Item | Value |
|---|---|
| v0 chat (private) | https://v0.app/chat/sJZGh14MJnN |
| Preview | https://budgetanalytics-design-prototype-task-0-x08qtto2.v0.build (opens with the v0 account) |
| Context sent to v0 | [V0_CONTEXT.md](V0_CONTEXT.md), condensed from `docs/design/*` |
| Model / cost | v0-pro, 1.39 plan credits (6 steps + 1 continuation), no on-demand charges |
| Stack | Next.js 16 (App Router), TypeScript, Tailwind, shadcn/ui, Recharts, next-themes, sonner, SWR |
| Size | 73 files, ~10 000 lines of TS/TSX (without `components/ui`) |

## Generation steps
| Step | Scope | Result |
|---|---|---|
| 1 | Foundation (tokens, types, formatting, mock client), shell, `/design-system`, auth (A-1…A-4), Overview (D-1) | Done. The first message was sent with a placeholder instead of the context attachment and was stopped; step 1 was re-sent with the full context |
| 2 | Operations: list, details, create/edit, import wizard, import history (T-1…T-3, I-1, I-2) + fixes of step 1 | Done |
| 3 | Accounts, Categories (AC-1, AC-2, C-1, C-2) | Done |
| 4 | Budgets, Goals (B-1…B-3, G-1…G-3) | Done |
| 5 | Analytics, Deposits + calculator (AN-1, AN-2, DP-1…DP-3) | Done. The step hit the generation length limit; finished in a continuation message |
| 6 | AI advisor, Notifications (needs backend), Settings (AI-1, AI-2, N-1…N-3, S-1…S-3), design-system additions | Done |

v0 ran `tsc --noEmit`, `pnpm build`, `prettier` and browser checks at 390 px in both themes on every step.

## Screen → route map
| Screens | Routes |
|---|---|
| A-1…A-4 | `/login`, `/register`, `/forgot-password`, `/reset-password` (A-3/A-4 with a «требует backend» banner, submit disabled) |
| D-1 | `/dashboard` |
| T-1…T-3 | `/transactions` (list, filters, create/edit dialog), `/transactions/[id]` (details) |
| I-1, I-2 | `/transactions/import`, `/transactions/import/history` |
| AC-1, AC-2 | `/accounts`, `/accounts/[id]` |
| C-1, C-2 | `/categories` (tabs + form dialog) |
| B-1…B-3 | `/budgets`, `/budgets/[id]` (+ form dialog) |
| AN-1, AN-2 | `/analytics`, `/analytics/details` |
| DP-1…DP-3 | `/deposits`, `/deposits/[id]`, `/deposits/calculator` |
| G-1…G-3 | `/goals`, `/goals/[id]` (+ form dialog) |
| AI-1, AI-2 | `/advisor`, `/advisor/report` |
| N-1…N-3 | `/notifications` (needs backend; empty state by default, demo layout toggle) |
| S-1…S-3 | `/settings` (General / Appearance / Security) |
| Design system | `/design-system` |

States are previewed with the «Демо: состояние» switcher (`?state=default|loading|empty|error`).

## Contract audit (done by Claude on the final source, 2026-11-19)
| Check | Result |
|---|---|
| No backend code: API routes, server actions, DB SDKs, `process.env`, telemetry | ✅ none |
| Pages read data only through `lib/api/mock.ts` (swappable for the real `/api/v1` client) | ✅ no direct `mock-data` imports |
| Money formatted from decimal strings (`lib/format.ts`, no float math): `1 250 000,50 ₸` | ✅ |
| Budget usage only from `getBudgetUtilization` / `overview.budgets`; `Budget.spent/progress` never shown | ✅ |
| Account group totals from `overview.current_balance`, currencies never summed | ✅ |
| Operations table: no sortable headers («Сначала новые»), search labelled «Поиск по описанию», archived accounts excluded from pickers | ✅ |
| UI text in Russian, term «Операция» (no «транзакция») | ✅ |
| Features without backend clearly labelled (password recovery, notifications, profile edit, sessions, 2FA, account deletion, balance history, analytics by week/account) | ✅ |
| Deposit calculator demo: 1 000 000 ₸ · 16 % · monthly · 12 mo → 172 270,80 ₸ | ✅ (checked by v0 in the browser) |
| `Number()` on amounts | Only for chart geometry, progress-bar width and threshold colours — never for displayed values |

## Known limitations of the prototype
- The import preview does not parse files; it shows demo rows from the mock client.
- The deposit calculator returns pre-computed demo results (marked «Демо-расчёт») rather than calculating interest in the browser.
- The prototype was not reviewed by a human designer; accessibility contrast was specified in tokens (AA text tokens) but not audited with a tool on the rendered pages.
- The code is a design artifact. Re-using it as the production frontend requires a separate decision, a review, and replacing `lib/api/mock.ts` with a real API client.

## Decisions applied as defaults (pending product-owner approval, see `BACKEND_GAPS.md` §4)
| ID | Default applied |
|---|---|
| D-1 | AA text tokens |
| D-2 | Dark text on teal buttons |
| D-3 | Import inside Operations |
| D-4 | Notifications shown with «Скоро» / «Требует backend» |
| D-5 | Term «Операции» |
| D-6 | Kazakhstan demo data |
| D-7 | Budget warning at 80 % |
| D-8 | Hide zero cents only in metric cards |
