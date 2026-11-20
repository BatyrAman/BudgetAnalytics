# License Audit — BudgetAnalytics

- **Date:** 2026-11-20.
- **Scope:** the repository at commit `2bbaaef`, its lock files, the installed dependencies, the Docker images used by `compose.yaml`, and the assets in `frontend/public/`.
- This is a software compliance inventory, not legal advice. It does not establish that the project is legally compliant.

## 1. Summary

| Area | Result |
|---|---|
| Project license | **None.** No `LICENSE`/`NOTICE`, no copyright or SPDX headers, no license fields. Decision draft: [LICENSING_DECISION.md](LICENSING_DECISION.md). |
| Frontend runtime dependencies | 259 packages: 209 MIT, 23 ISC, 8 Apache-2.0, 7 BSD-3-Clause, 4 BSD-2-Clause, 3 BlueOak-1.0.0, 1 0BSD, 1 `(MIT OR CC0-1.0)`, 1 `MIT AND ISC AND BSD-3-Clause`, **1 LGPL-3.0-or-later**, **1 CC-BY-4.0** |
| Frontend development dependencies | 394 packages, all permissive or weak copyleft (3 MPL-2.0); not shipped at runtime |
| Backend runtime dependencies | 45 packages: MIT, BSD-3-Clause, Apache-2.0, ISC, PSF-2.0, MIT-0, Unlicense, MIT OR Apache-2.0, **1 MPL-2.0** (`certifi`) |
| Container images | PostgreSQL License; Python PSF; Node.js MIT; OS packages under various licenses including GPL; **Redis 7.4.8: RSALv2 / SSPLv1** |
| Strong copyleft (GPL/AGPL) linked into the application | **None found** |
| Unknown or missing license declarations | None in runtime dependencies. `server-only` and `eslint-config-next` declare MIT but ship no license file in the package. |
| Assets with unclear ownership | `frontend/public/icon.svg` (appears to be the v0 / Vercel template mark) and three `.png` icons of unknown origin; see [ASSET_ATTRIBUTION.md](ASSET_ATTRIBUTION.md) |
| Code copied from identifiable external sources | None identified by search (no copied license headers, no vendored libraries). The frontend was built from a v0-generated prototype (see [LICENSING_DECISION.md §2](LICENSING_DECISION.md#2-ownership-questions-to-settle-first)). |
| Secrets or personal data in git history | None found (only `.env.example` files were ever committed) |

## 2. Method

1. **Frontend:** ran `pnpm licenses list --prod --json` and `--dev --json` against `frontend/pnpm-lock.yaml`. For all 28 direct dependencies, the version, the `license` field and the first line of the shipped `LICENSE` file were checked. Every package with a license other than MIT, ISC, BSD or 0BSD was listed and reviewed.
2. **Backend:** read the installed distribution metadata (`License-Expression`, `License`, classifiers) and the license file names for all 45 packages pinned in `backend/requirements.txt`. Non-SPDX values were resolved from the license files:
   - `pwdlib` → MIT;
   - `uvloop` → MIT OR Apache-2.0 (both texts shipped);
   - `defusedxml` → PSF-2.0.
3. **Images:** read the versions inside the running containers. The Redis license was taken from the upstream repository at tag `7.4.8` (`LICENSE.txt`), because the image ships no license file.
4. **Apache-2.0 NOTICE obligations:** checked every Apache-2.0 runtime package (npm and Python) for a `NOTICE` file. None was found.
5. **Assets:** inspected `frontend/public/*`, font loading (`frontend/app/layout.tsx`) and the icon library. Verified the Inter license from the upstream repository and the Lucide license from the installed package.
6. **History:** searched all commits for committed `.env` files, dumps, keys and session files.

The complete per-package list is in [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

## 3. Findings

### F-1. No project license (owner decision)
Without a license nobody else may use, modify or redistribute the code. Contributions also arrive without explicit terms. → Approve a model in [LICENSING_DECISION.md](LICENSING_DECISION.md). Until then, accept outside contributions only with written terms, or not at all.

### F-2. Redis 7.4.8 is not under an open-source license
- Since 7.4, Redis is dual-licensed under RSALv2 or SSPLv1 (verified in upstream `LICENSE.txt` at tag `7.4.8`).
- RSALv2 forbids making "the functionality of the Software … available to third parties as a service", or offering a product "that accomplishes for users the primary purpose of the Software".
- BudgetAnalytics uses Redis internally as a rate-limit counter store, not as a service offered to users. This is commonly regarded as permitted use, but **needs legal confirmation** before a commercial hosted launch.

Options that avoid the question:

- pin `redis:7.2-alpine` (BSD-3-Clause; check its support status first);
- use a BSD-licensed fork such as Valkey;
- use Redis 8.x under its AGPLv3 option, after reviewing the AGPL obligations.

Each is a configuration change, to be validated by the owner. **Not changed by this audit.**

### F-3. LGPL-3.0 libvips in the frontend image
- `next` depends optionally on `sharp`, which installs `@img/sharp-libvips-linuxmusl-x64` 1.3.4 (LGPL-3.0-or-later) in the Docker image.
- The app disables Next image optimization, so the library is installed but not used.
- If the image is **distributed** (for example pushed to a public registry), LGPL obligations apply to that library: license text, access to source, permission to replace it.

→ Either keep the library and document how to obtain its source, or exclude it from the production install. The second is a build change to validate.

### F-4. CC-BY-4.0 data (`caniuse-lite`)
Browser-support data used by build tooling. Attribution is required when it is redistributed. It is not used by application logic.

### F-5. `shadcn` CLI in production dependencies
`shadcn` 4.23.0 is a production dependency, but the app only imports `shadcn/tailwind.css` at build time. It brings CLI and Model Context Protocol packages (`@modelcontextprotocol/*`, Apache-2.0) into the runtime tree and image. This is not a license conflict, but it increases attack surface and size. → Consider moving it to `devDependencies`, after verifying the build.

### F-6. Third-party icon in `frontend/public/`
`icon.svg` draws the "v0" mark used by Vercel's v0 templates. Trademarks and brand assets are not covered by the dependency licenses. → Replace with the project's own mark. See [ASSET_ATTRIBUTION.md](ASSET_ATTRIBUTION.md).

### F-7. Synthetic personal identifiers in tests
Tests of the redaction logic use realistic-format values:

- an e-mail on the real `mail.kz` domain in `backend/tests/integration/test_advisor_api.py` and `backend/tests/unit/ai/test_guard_and_rules.py`;
- a 12-digit IIN-format number in `backend/tests/unit/ai/test_guard_and_rules.py` and `backend/tests/unit/imports/test_normalize.py`;
- a `+7 701 …` phone number.

They are almost certainly invented, but realistic values can coincide with real people. → Prefer `example.com` addresses and identifiers that are clearly invalid (failing the checksum). Low priority.

## 4. Required remediation (owner)

| # | Action | Priority |
|---|---|---|
| R-1 | Decide the license and the copyright holder; add `LICENSE` ([LICENSING_DECISION.md](LICENSING_DECISION.md)) | High, before any public release or outside contribution |
| R-2 | Get legal review of Redis RSALv2 for the intended use, or switch to a BSD-licensed alternative | High, before a commercial hosted launch |
| R-3 | Replace `frontend/public/icon.svg` and confirm the origin of the `.png` icons | Medium |
| R-4 | Decide how to handle LGPL libvips if images are distributed | Medium, before publishing images |
| R-5 | Move `shadcn` to `devDependencies` (verify the build) | Low |
| R-6 | Replace realistic test identifiers | Low |
| R-7 | Re-run this inventory whenever lock files change (for example, add a license check to CI) | Ongoing |

## 5. Limitations

- The licenses are the packages' **declared** licenses. Full license texts were read for direct dependencies and flagged packages only, not for all 653 frontend packages. Packages can contain files under other licenses that their metadata does not show.
- The licenses of operating-system packages inside the base images were not inventoried.
- Dependencies installed on other platforms (Windows, macOS, ARM) may include different platform-specific packages.
- No external database (such as SPDX tooling or ClearlyDefined) was used to cross-check the metadata.
- Copyright in AI-assisted code and the terms of the AI tools used were **not** assessed; that requires legal review.
