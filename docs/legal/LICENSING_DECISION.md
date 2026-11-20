# Licensing Decision — DRAFT, pending owner approval

> **Status: no license has been selected.** This document prepares the decision; it is not a license grant. Until the owner approves a license and a `LICENSE` file is added, the repository has no license, so it is effectively *all rights reserved*. This is a technical summary, not legal advice.

## 1. Current state (verified)

| Item | Finding |
|---|---|
| `LICENSE`, `COPYING`, `NOTICE` | None in the repository or its history |
| Copyright or SPDX headers in source files | None |
| `frontend/package.json` | `"private": true`, no `license` field |
| `backend/pyproject.toml` | No `license` field or license classifier |
| Commit authorship | All commits are by one GitHub account (the repository owner) |
| Hosting | Remote `github.com/BatyrAman/BudgetAnalytics`; this audit cannot determine whether the repository is public or private |

## 2. Ownership questions to settle first

A license can only be granted by whoever holds the copyright. Before choosing one, the owner should confirm:

1. **Who the copyright holder is:** an individual, or a company the owner works for or represents. Employment and contractor agreements can assign copyright to an employer or client. This document does not name a holder.
2. **AI-assisted code.** A large part of the code and documentation was produced with AI tools: Claude (Anthropic) during development, and v0 (Vercel) for the design prototype the frontend was built from. Two questions follow:
   - Whether and how such output is protected by copyright differs between jurisdictions, and it depends on the human contribution.
   - The terms of the tools at the time of use govern rights in their output.
   Both need review before an ownership claim is asserted in a `LICENSE` or `NOTICE`.
3. **Third-party material in the repository.** `frontend/public/icon.svg` appears to be the v0 template icon, which is a third-party brand mark; see [ASSET_ATTRIBUTION.md](ASSET_ATTRIBUTION.md). It should be replaced or removed regardless of the license chosen.

## 3. Options

| Model | What others may do | Commercial use by others | Obligations on others | Fits when |
|---|---|---|---|---|
| **Proprietary / All Rights Reserved** (the status today) | Nothing beyond what the law allows without permission. On GitHub, public repositories can be viewed and forked under GitHub's Terms of Service, but not used, modified or redistributed. | Only with a separate agreement | Not applicable | The product will be a commercial or hosted service, the code is a business asset, or ownership is still unclear |
| **MIT** | Use, copy, modify, sublicense and sell, including closed-source derivatives | Allowed, including competing hosted services | Keep the copyright and license notice | Maximum adoption is the goal and competition from forks is acceptable |
| **Apache-2.0** | Like MIT | Allowed | Keep notices, state changes, pass on `NOTICE` contents; includes an explicit patent license and patent-retaliation clause | Like MIT, but with explicit patent terms; common for company-backed projects |
| **GPL-3.0** | Use, modify, redistribute | Allowed, but distributed derivatives must also be GPL-3.0 with source | Share source of distributed derivatives; **does not cover use over a network** (a hosted service can stay closed) | Keeping distributed forks open is the goal |
| *(not requested, for completeness)* **AGPL-3.0** | Like GPL-3.0 | Allowed with obligations | Also requires offering source to users of a **network service** | Keeping hosted forks open is the goal |

**Compatibility with the dependencies.**

- All runtime dependencies are under permissive or weak-copyleft licenses (see [LICENSE_AUDIT.md](LICENSE_AUDIT.md)), so none of them blocks any of the options above.
- Redis 7.4 (RSALv2/SSPLv1) is a separate server program in its own container, not linked into the code, so it does not dictate the project's license. Its own use restrictions still need review.

## 4. Recommendation

**Keep Proprietary / All Rights Reserved for now and add an explicit statement**, rather than choosing an open-source license at this point. Reasons:

1. **The product direction looks like a hosted service.** The docs talk about a closed pilot, a public beta and a possible hosted service. With MIT or Apache-2.0, anyone could run a competing hosted copy, and GPL-3.0 would not prevent closed hosted forks either.
2. **Ownership is not confirmed** (section 2). Granting an open-source license cannot be taken back for copies already distributed.
3. **Moving later is easy in one direction.** Going from proprietary to open source later is straightforward; going back is not.

**If the owner prefers open source:**

- **Apache-2.0** is the most balanced choice for a project that may be backed by a company: permissive, with explicit patent terms.
- **AGPL-3.0** fits if the owner wants hosted forks to stay open.

Either way, first resolve section 2 and replace the v0 icon.

## 5. What to do after the decision

| Decision | Files to add or change |
|---|---|
| Proprietary | `LICENSE` with an "All rights reserved" statement naming the confirmed copyright holder and year. Update the README "License" section. Optionally `"license": "UNLICENSED"` in `frontend/package.json`. |
| MIT / Apache-2.0 / GPL-3.0 / AGPL-3.0 | `LICENSE` with the **unmodified official text** from <https://spdx.org/licenses/> or the license steward, plus the confirmed copyright line. For Apache-2.0, a `NOTICE` file. `license` fields in `package.json` and `pyproject.toml`. Update the README. |

## 6. Owner approval

| Question | Answer (owner) |
|---|---|
| Copyright holder (exact legal name) | *pending* |
| Year(s) of first publication | *pending* |
| Selected license | *pending* |
| AI-tool output and employer/client rights reviewed | *pending* |
| Approved by / date | *pending* |
