# Implementation Audit — BudgetAnalytics frontend + backend gaps

> Date: 2026-11-19. Starting point: `main` at `e746e35` (backend MVP). Uncommitted: `docs/design/` only.
> Scope: the MASTER PROMPT «BudgetAnalytics Production Implementation». Decisions D-1…D-9 are approved; D-10 (Figma purchase) is deferred.

## 1. Repository and toolchain

| Area | Finding |
|---|---|
| Structure | `backend/` (FastAPI) + `docs/`. **No frontend in the repository.** |
| Backend | FastAPI, SQLAlchemy 2 async, PostgreSQL 16, Alembic (head `a1c3e5f7b9d2`), Pydantic v2. Tests: pytest, 605 passing at `e746e35`. Lint: ruff, mypy. |
| Frontend source | Only the v0 design prototype (chat `sJZGh14MJnN`, 73 files, ~10 000 lines TS/TSX). It is not in the repository and uses an in-memory mock API. |
| Node.js on host | Only Windows `node.exe` v24 via WSL interop. Linux Node 22 is installed into an isolated conda environment in the session scratchpad for builds and tests (no system-wide changes). |
| Docker | **Not available in this WSL distro now** (Docker Desktop WSL integration is off). The dev stack cannot be started by Claude; backend integration tests run against a local scratch PostgreSQL instead. |
| Figma | Plan is now Pro with a Full seat. File `spaehjXGVBqqhoqZh22o9C` has 1 page (v1 approved dashboards), token collections Light `1:2` / Dark `11:42` / Spacing `11:90`, 12 text styles, 3 effect styles, 1 component (`Navigation Item`). **There is no full app design in Figma** — screens exist only in the v0 prototype. Token values in Figma and in the prototype `globals.css` are identical. |
| Requested docs | `docs/design/NAVIGATION_SPEC.md` and `docs/design/FRONTEND_IMPLEMENTATION_PLAN.md` **do not exist**. Navigation is defined in `PRODUCT_DESIGN_BRIEF.md §5`, `SCREEN_INVENTORY.md` and `RESPONSIVE_SPEC.md`; this file contains the implementation plan. |

## 2. v0 prototype — reusable vs. must change

| Part | Status | Action |
|---|---|---|
| Next.js 16 App Router, React 19, TS strict, Tailwind 4, next-themes, Recharts, SWR, sonner | Reusable | Keep. Pin versions that actually install from the npm registry. |
| `globals.css` tokens (Light/Dark, D-1 text tokens, D-2 on-brand) | Reusable | Keep as the single token source. |
| `lib/format.ts` (string-based money/percent/date) | Reusable | Keep, add unit tests. |
| `lib/types.ts` (mirrors API) | Mostly reusable | Re-check every type against OpenAPI; add missing fields after backend changes (G-4, G-10, G-6). |
| `lib/api/mock.ts` (+ `mock-data.ts`) | **Must not be in the production path** | Replace with a real typed API client with the same function names; keep fixtures only for tests. |
| Screens (27 routes) | Reusable layouts | Wire to the real client; split components over ~400 lines. |
| `next.config.mjs` | `typescript.ignoreBuildErrors: true` | **Remove** — type errors must fail the build. |
| Demo toggles (state switcher, AI/rules, notifications example) | Prototype-only | Allowed only when `NODE_ENV !== "production"`. |
| ESLint, unit/integration/E2E tests | Missing | Add ESLint (next config), Vitest + Testing Library, Playwright. |

## 3. Backend API facts relevant to the frontend
- Auth: JSON login/register return `{access_token, refresh_token}`; refresh is single-use (rotation, reuse detection). Bearer only; CORS `allow_credentials=False`.
- 41 non-deprecated operations (full map: `docs/design/API_TO_UI_MAPPING.md`).
- Error body `{detail, code, request_id}`; **business errors have no machine codes** (`code` = `bad_request`/`conflict`) — G-10.
- `UserResponse` has **no `default_currency_code`** — G-4.
- Budget usage is available only per budget (`/budgets/{id}/utilization`); `/budgets` and `/budgets/{id}` expose `progress/remaining/is_exceeded` computed from the deprecated manual `spent` — G-6.

## 4. Technical risks
| Risk | Mitigation |
|---|---|
| Token storage (XSS) | Backend-for-frontend inside Next.js: route handlers keep access and refresh tokens in `httpOnly`, `Secure`, `SameSite=Strict` cookies and proxy `/api/v1/*` to FastAPI. Browser JS never sees tokens. No business logic in the proxy. |
| CSRF on cookie-auth proxy | `SameSite=Strict` + same-origin check (`Origin`/`Sec-Fetch-Site`) + required `X-Requested-With` header on mutating requests. |
| Refresh races | Single in-flight refresh on the server per request; client retries the original request once after a 401→refresh. |
| Large files in import upload through the proxy | Stream the multipart body with a size cap (5 MB + overhead); backend still enforces its own limits. |
| No Docker | E2E runs against a locally started FastAPI + scratch PostgreSQL + `next start`. |
| Package versions from v0 sandbox (pnpm 12, next 16.4.6) may not exist publicly | Verify with a real install; adjust to the latest published versions; record in the status doc. |

## 5. Implementation plan
| # | Stage | Files | API | Tests | Acceptance |
|---|---|---|---|---|---|
| 1 | **Backend G-4**: `default_currency_code` in `GET /auth/me` | `schemas/user.py` | `/auth/me` | API test | Field present, KZT default |
| 2 | **Backend G-10**: machine error codes for every business rule | `core/errors.py`, services | all | API tests per code | `code` is specific; `detail` unchanged |
| 3 | **Backend G-6**: `GET /budgets/utilization?month=` for all budgets in one call | `api/budget.py`, `services/budgets.py`, schemas | new endpoint | API + IDOR tests | Correct values, user-scoped, no N+1 calls from the UI |
| 4 | Frontend foundation in `frontend/` | config, `lib/api/*`, BFF route handlers, error layer | auth, proxy | unit (format, errors, client) | Build passes without `ignoreBuildErrors`; login works against FastAPI |
| 5 | Sections wired to the real API | `components/*`, `app/*` | all 41 operations | integration (Testing Library + fetch mocks at the client boundary) | No mock in production path; all states |
| 6 | Advisor, Notifications (needs backend), Settings | as specified | advisor, auth | integration + E2E | Per prompt §5–7 |
| 7 | Design System page | `app/design-system` | — | — | Components in all states, both themes |
| 8 | E2E | `frontend/e2e` | real backend | Playwright | Login, dashboard, create operation, create budget, advisor, report, theme, password change |
| 9 | Security, responsive, a11y review + release checks | docs/implementation | — | — | QA_REPORT with real command output |

Progress is tracked in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md); verification in [QA_REPORT.md](QA_REPORT.md).
