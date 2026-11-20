# Implementation Status — 2026-11-19 (Stabilization & Release QA done)

Nothing is committed. Release status: **Release Candidate for a closed pilot**; not ready for public beta.
Details and evidence: [QA_REPORT.md](QA_REPORT.md).

## Done
- **Backend:**
  - G-4 `default_currency_code` in `/auth/me`;
  - G-10 machine error codes;
  - G-6 `GET /budgets/utilization`.
  - Not changed during QA.
- **Frontend** `frontend/`: real typed API client, SWR hooks, Russian error layer, BFF session (httpOnly cookies, CSRF guard, deduplicated refresh), CSP, all 27 routes on the real API.
- **Stabilization (this stage):**
  - Vitest timeouts;
  - single `lib/timezone.ts`, `category-glyph.tsx` and `confirm-dialog.tsx`;
  - Overview currency before the profile loads;
  - build Suspense fix;
  - full reload at session boundaries;
  - proxy path validation (security fix);
  - mobile recent operations;
  - amount field suffix;
  - text contrast;
  - field names vs hints.
- **E2E:**
  - `auth.spec.ts`, `flows.spec.ts`, `password.spec.ts`, `responsive.spec.ts`;
  - `global-setup.ts` registers one shared user, which keeps runs inside the registration rate limit.

## Last check results
| Command | Result |
|---|---|
| backend `pytest` | 627 passed |
| backend `ruff check`, `ruff format --check`, `mypy app` | clean |
| `pnpm format:check` / `typecheck` / `lint` | clean, 0 warnings |
| `pnpm test` | 230 passed |
| `pnpm build` | PASS |
| `npx playwright test` | 35 passed |

## Remaining
- Public-beta blockers and known issues: QA_REPORT §12–13.
- NOT RUN: real AI provider, WebKit/Firefox, real devices, screen reader, load tests.

## Environment (session scratchpad, not in the repository)
- PostgreSQL on 127.0.0.1:55433 (`budget_test`, `budget_mig`, `budget_e2e`), Redis on 56380.
- Node 22 + pnpm: `$S/env/bin`.
- Playwright browsers: `$S/pw-browsers`.
