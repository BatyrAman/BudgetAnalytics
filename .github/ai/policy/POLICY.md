# Orchestrator Risk Policy

| | |
|---|---|
| Policy document version | `0.7.0-draft` |
| Executable Risk Policy version | `0.5.0-draft` (`risk_policy.toml` `policy_version`) |
| Status | Draft. §4 and the path-level restrictions of §8 are implemented in `orchestrator/paths.py`; the path, change-type and size rules of §5 and §6.2 in `orchestrator/risk_policy.py` + `risk_policy.toml`. Domain, label, signal, model and content rules (§6.1, §6.3–§6.5) and the actual-diff integration are not implemented yet |
| Owner | Repository owner (see [Policy ownership](#11-policy-ownership)) |
| Machine-readable form | `risk_policy.toml` — must implement this document exactly. Its `policy_version` is the *executable Risk Policy version* above; it changes only when the executable rules change (§12) |
| Related | [`../README.md`](../README.md), ADR-001 (`BAAI-DOCS/03-architecture/`) |

The key words **MUST**, **MUST NOT**, **SHOULD** and **MAY** are normative.
If `risk_policy.toml` and this document disagree, the **higher** risk level
applies until the discrepancy is fixed.

## 1. Principles

1. **Deterministic.** The risk level is computed by code from this policy.
   No LLM decides or lowers a risk level.
2. **Raise-only inputs.** The Planner's `model_risk_level`, Reviewer findings,
   sanitizer signals and issue labels MAY raise the level and MUST NOT lower it.
3. **Maximum wins.** The final level is the maximum over all applicable rules
   (not first match). Rule order MUST NOT change the result.
4. **Fail closed.** Invalid input, invalid model output, unknown paths,
   unparseable diffs or any internal error result in *reject* or **L3** —
   never in L1 or L2 by default.
5. **Actual diff wins.** In phases that produce a diff, the policy is
   re-evaluated on the actual diff, which always takes priority over the
   Planner's predicted paths.
6. **Self-protection.** The orchestrator cannot change its own rules:
   every path with a `.github` segment is forbidden for the Executor (§8)
   and L3.

## 2. Risk levels

| Level | Meaning | Approval |
|---|---|---|
| **L1** | Documentation outside legal (except the docs listed as L2) and registered copy-only files; no logic changes | Possible automatic merge — only after an independent Reviewer pass **and** all gates (§9). Until that phase exists: manual. |
| **L2** | Ordinary application changes outside L3 areas | Manual approval |
| **L3** | Financial calculations, auth, permissions, database, security, CI, dependencies, AI policy, legal, and their tests; anything unknown | Manual approval by the policy owner |
| *reject* | Invalid or untrusted request, invalid path, invalid model output | Not executed |

## 3. Evaluation

Inputs: request metadata, the validated Planner output (predicted paths,
domains, task type, change types, model risk), sanitizer signals, labels and —
in later phases — the actual diff.

```
1. Eligibility (§7) fails                  → reject
2. Any path fails validation (§4)          → reject
3. level := max(
       path rules for every path (§5),      // predicted; later: actual diff
       domain rules (§6.1),
       change-type and size rules (§6.2),
       content rules on the actual diff (§6.3, later phases),
       sanitizer / injection signals (§6.4),
       label escalation (§6.5),
       Planner model_risk_level,
       Reviewer escalation (later phases))
4. No paths at all                          → not executable; L3 (unknown scope)
5. Path matches no rule                     → L3 (unclassified_path)
```

Matching is performed on canonical paths (§4) as defined in §5.0. Every rule
that matches applies.

### 3.2 Evaluation result (implemented)

`orchestrator/risk_policy.py::evaluate` takes validated change records
(`ValidatedPath` from §4 with the entry kind *before* the change, plus
`new_kind` — the entry kind *after* the change from the target Git mode,
`None` for a delete — `binary`, `mode_change` and an optional rename source),
the actual changed file and line counts, and the policy version the caller
expects. `new_kind` and `mode_change` must agree (a modify changes mode
exactly when the kind changes; a rename into another kind is a mode change);
forged or inconsistent values are rejected. It returns an immutable `RiskAssessment`: overall level, policy
version, matched rule ids, file and line counts, stable reason codes
(e.g. `unclassified_path`, `new_top_level`, `symlink`, `forbidden_area`,
`exceeds_l1_limits`, `empty_change_set`), per-path details and `executable`.

- Invalid or inconsistent input (non-canonical path, metadata that
  contradicts the change type, duplicate paths, counts that do not match the
  records, a different policy version) raises an error: the change set is
  rejected, never guessed.
- `executable = false` for an empty change set and for any change touching a
  hard-restricted path (§8); the level is then L3.
- **`executable = true` is not an authorisation.** It only means the Risk
  Policy itself does not prohibit the change set. Eligibility (§7), approval
  for the level (§9), Reviewer and CI gates remain mandatory.
- Raise-only inputs not yet wired in (domains, labels, sanitizer signals,
  model risk, content rules) can only raise the result when added.

### 3.1 Predicted paths vs actual diff (later phases)

- The actual Git diff is always re-evaluated by this deterministic policy. The
  level computed from the actual diff is authoritative; the Planner's predicted
  paths and estimates are never used in its place.
- **Scope drift** is any difference between the actual diff and the approved
  plan that matters for the policy: a path not in the plan, a different change
  type (e.g. `modify` became `delete`), or a size above the approved level's
  limits.
- Any scope drift **invalidates the previous approval**. The resulting level is
  at least **L2** (L3 if any L3 rule applies), and a **new approval** at that
  level is required before the task may continue.
- If the actual-diff level is higher than the approved level, the task stops
  and requires approval at the new level.
- A lower actual-diff level MUST NOT lower the approval already required.

**Implementation** (`orchestrator/scope_drift.py`, pure functions, no Git,
filesystem, network or clock):

- **Approved scope vs actual diff.** The approved scope is the explicit list of
  changes a human approved: `add`, `modify` or `delete` of a path, or a
  `rename` from a source to a destination. It is validated with §4 against
  the base commit (a rename as the delete of its source plus the add of its
  destination); raw Planner paths are never trusted. The actual side is the
  `GitDiff` of the Git diff adapter, never Planner or Executor claims.
- **Exact matching.** Each change is the triple (operation, source,
  destination); paths are literal and case-sensitive, never patterns or
  directories. The two sets must be identical, independent of order. A
  rename matches only a rename with the same source and destination, never a
  delete plus an add (or the reverse). Entry kinds, type changes, binary
  flags and sizes are not part of the scope: they are classified by the Risk
  Policy on the actual diff, so a planned `modify` matches an actual modify
  or type change of that path, and a rename keeps both paths classified (a
  rename from an L3 source stays L3).
- **Drift** is any difference: unexpected changes (by operation), approved
  changes missing from the diff, operation mismatches, rename source or
  destination mismatches, a rename represented differently, and case-only
  differences. Invalid or inconsistent input on either side is treated as
  drift (fail closed); a "no drift" result exists only after both sides were
  fully checked.
- **Why drift invalidates approval.** An approval covers exactly the
  reviewed scope; anything else was never reviewed, so the previous approval
  is void and a **fresh approval** is required.
- **Risk floor.** The actual `RiskAssessment` is never changed; an immutable
  `EffectiveRisk` wraps it. Drift raises the effective level to at least
  **L2**; an invalid comparison (unknown scope, §3 step 4) to at least
  **L3**. An actual L3 always stays L3, because the floor is only ever
  combined by taking the maximum — nothing can lower a level.
- **No drift is not authorisation.** A valid comparison without drift only
  means the previous approval still covers the diff. Eligibility, approval
  for the effective level, the Reviewer and all gates (§9) still apply.
- Size-based drift (a size above the approved level's limits) needs the
  approved level, which the approval process does not record yet; until then
  the effective level is compared with the approved level by that process.

### 3.3 Approval binding (in-memory, implemented)

`orchestrator/approval.py` binds an approval to exactly what was reviewed:
the approved scope (§3.1), the approved **effective** risk level, the
executable Risk Policy version, the approved changed file and line counts
(Git diff adapter semantics: a rename is one file; lines are added plus
deleted) and the full base and target commit IDs (40 or 64 lower-case hex
characters; branch names, refs and abbreviated IDs are never accepted).

`validate_approval(binding, diff, policy)` is pure and accepts **no
precomputed results**: it recomputes the `RiskAssessment` with `evaluate`
from the supplied policy and the actual diff, and recomputes the scope
comparison from the binding's approved scope and the diff, so a caller cannot
supply a lowered assessment or a "no drift" result. `policy` must be the
trusted policy returned by `load_policy`: a policy object is accepted only if
it is exactly what the loader produces from its own values (so altered
defaults, floors, limits, rules or patterns are rejected — `evaluate` itself
enforces the same check). The diff must be the locally computed result of the
Git diff adapter; its structure, commit IDs, records and counts are checked
(the line count is re-derived from the audit records). Inputs must have the
exact expected types (no subclasses, no unset fields, counts as non-negative
non-bool integers, security-relevant strings as exact `str`); a malformed
binding is reported as `invalid_binding`, a malformed or inconsistent diff or
policy as `inconsistent_inputs`.

The binding is no longer consistent — and a **fresh approval** is required —
when the base or target commit
differs, the executable Risk Policy version differs, the effective level
(actual level plus the scope-drift floor) is higher than the approved level
(by `RiskLevel` ordering: an L1 approval never covers L2 or L3, an L2
approval never covers L3, nothing is downgraded), any scope drift exists
(even within the approved level), the actual file or line count exceeds the
approved count, or any input is malformed or inconsistent.

**What a binding is not.** It is an unsigned, unpersisted in-memory value
without approver identity. `binding_consistent = true` only means that the
binding is consistent with the supplied diff and policy; it does not
authorise execution or merge, and the result has no authorisation field. The future *trusted, persisted* approval (§9: authenticated GitHub
action by a user with the required permission, bound to the plan envelope)
will carry such a binding; until it exists, every approval remains manual.

## 4. Path validation

Path validation is implemented by `orchestrator/paths.py`. It decides only
whether a path is a valid, unambiguous repository path and enforces the hard
path restrictions of §8. It reports facts for the Risk Policy; it does not
assign risk levels. Any violation rejects the **whole** change set.

### 4.1 Syntax

A path MUST be a repository-relative POSIX path. The only normalisation is the
removal of **one** leading `./`; everything else that would need interpretation
is rejected, never repaired:

- 1–200 characters in total, at most 20 segments, at most 100 characters per
  segment;
- **ASCII only.** Characters are limited to `A–Z a–z 0–9 . _ - [ ] ( ) @` and
  `/` as the separator. Non-ASCII input is **rejected, not
  Unicode-normalised**; compatibility look-alikes (fullwidth letters,
  ligatures) and other scripts (e.g. Cyrillic `а`) are rejected alike;
- rejected explicitly: control characters and NUL, invisible and bidirectional
  formatting characters, any whitespace (including leading or trailing spaces),
  look-alike slashes, backslash, `:` (drive letters, NTFS streams, Git pathspec
  magic), `%` (percent-encoding), `*`, `?`, `{`, `}`, and every other character
  outside the list above (e.g. `~ $ ; | & + # ! ' "`);
- no leading `/`, no empty segment, no `.` or `..` segment;
- Windows compatibility: no segment ending in `.` (this also rejects `...`), no
  Windows device name with or without extension (`CON`, `PRN`, `AUX`, `NUL`,
  `COM1`–`COM9`, `LPT1`–`LPT9`, case-insensitive);
- no `.git` segment (case-insensitive).

Next.js route segments are valid and stay literal: `[id]`, `[...path]`,
`[[...slug]]`, `[action]`, `(group)`, `@slot`.

### 4.2 Checks against the Git index

Existence is decided only against a snapshot of the Git index, never against
the working tree, and no symlink is ever followed.

- `modify` / `delete`: the path MUST be tracked with exactly this spelling
  (case-sensitive). A directory, a case-only mismatch, an untracked path or an
  ambiguous index entry (unmerged stages, case-variant files) is rejected.
  The result carries the Git entry kind: regular file, executable file,
  **symlink** or **submodule**. Symlinks and submodules keep their type and
  are never treated as ordinary files; operations on them are L3 (§6.2).
- `add`: the path MUST NOT be tracked or be a tracked directory and MUST NOT
  collide by case with a tracked file or directory. No parent may be a
  tracked file, symlink or submodule. Additions at the repository root or in
  a new top-level directory are **valid**; the result marks them as
  `new_top_level`, which is L3 (§6.2).
- For every change type, a parent directory that exists in more than one case
  variant (e.g. `docs/` and `Docs/`) makes the path ambiguous and rejected.

### 4.3 Change sets

- Each item is a `(path, change_type)` pair with `change_type` exactly `add`,
  `modify` or `delete`.
- At most 50 items. An empty change set is **not executable**.
- Rejected across items: duplicates after normalisation, case-only duplicates,
  and a path that is both a file and a parent directory of another item.
- The reported error position is the first position at which the items so far
  become invalid.

### 4.4 Index snapshot

- The snapshot MUST be taken at the top level of a non-bare worktree; a
  subdirectory (for example `.github/` or `backend/`), a `.git` or worktree
  administrative directory, or a bare repository is rejected
  (`not_worktree_root`), so paths are always relative to the repository root.
  Linked worktrees created with `git worktree add` are supported; each is
  evaluated against its own index.
- Any Git command that cannot run or exits non-zero — not a repository, a
  missing directory, "dubious ownership" without a trusted `safe.directory` —
  fails closed as `git_failed`. `not_worktree_root` is reported only when the
  root probe succeeds but does not describe a worktree root.
- Git runs with fixed arguments and no shell, with `core.fsmonitor=false`
  passed on the command line (overriding any configured fsmonitor hook).
- **Environment trust.** Every inherited `GIT_*` variable is cleared before
  Git runs (e.g. `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`,
  `GIT_CONFIG_PARAMETERS`). `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` are not
  trusted and are dropped as well, so a `safe.directory` configured only
  through them is **not** honoured. `HOME` and `XDG_CONFIG_HOME` are preserved:
  global Git configuration reached through them, the system Git configuration
  and `PATH` (which provides the `git` executable) are part of the trusted
  environment.
- The index listing is parsed strictly. Unknown modes (including sparse
  directory entries), invalid object IDs or stages, empty paths, directory
  entries, truncated output or malformed records fail closed
  (`malformed_index`). Tracked paths that are not canonical under §4.1 are
  kept but can never be the target of a change.

### 4.5 Literal-path contract

Every component that consumes a validated path MUST treat it as a literal path:

- never a glob or pattern; never apply `fnmatch`, glob expansion, shell
  expansion or other implicit wildcard matching to it — compare by string
  equality or segment-wise prefix only;
- Git commands MUST use `--literal-pathspecs` or the `:(literal)` pathspec
  magic, and MUST separate options from paths with `--`;
- never interpolate a path into a shell command; pass it as one element of an
  argument vector;
- policy patterns such as `.github/**` in §5 are written as patterns *about*
  paths; the Risk Policy matches them with its own deterministic matcher,
  never by expanding a validated path.

### 4.6 What path validation does not do

Path validation is **not** secret detection. Apart from the hard restrictions
in §8 it does not recognise credential files (keys, certificates, token files
and the like); those require Risk Policy and content checks.

## 5. Path rules

### 5.0 Rule matching

The rules of this section are encoded in `risk_policy.toml` and matched by
`orchestrator/risk_policy.py`; validated paths are never expanded as patterns
(§4.5).

- Patterns are repository-relative POSIX paths matched against the **whole**
  canonical path, segment by segment. No `fnmatch`, glob library or
  filesystem access is involved.
- `**` must be a whole segment and matches zero or more segments; a trailing
  `**` matches one or more segments, i.e. the contents of a directory
  (`docs/**` matches `docs/a.md`, not `docs`). `**/Dockerfile` also matches a
  root `Dockerfile`.
- `*` matches zero or more characters within one segment.
- Every other character is literal, including `[`, `]`, `(`, `)` and `@`
  (`frontend/app/[id]/**` does not match `frontend/app/i/...`). `?` and `{}`
  are not allowed in patterns; brace sets such as `{a,b}` in this document are
  written out as separate patterns in the TOML file.
- **Case:** L3 rules match case-insensitively; L1 and L2 rules match
  case-sensitively. A case variation can therefore only raise a level.
- **Precedence:** there is none by order. Every matching rule applies and the
  highest level wins; no rule can lower the level set by another rule, the
  change-type rules (§6.2), the size limits or the hard restrictions.
- A valid path matching no rule is **L3** (`unclassified_path`).
- Hard restrictions come first: a path with a `.github` segment or a segment
  starting with `.env` is L3 and not executable, whatever the rules say.
- Built-in L3 file names: a file named `.gitattributes` (any depth,
  case-insensitive) is always at least L3, whatever the rules say — it
  changes how Git checks out, diffs and filters other files.
- The loader rejects catch-all patterns (only `*`/`**` segments) and patterns
  naming `.github`, `.env*` or `.gitattributes` in L1/L2 rules, duplicate patterns, the same
  pattern at two levels, malformed patterns and literal segments that are not
  valid path segments (§4.1).
- Every tracked file is classified by an explicit rule; a test fails if a
  tracked file would fall back to `unclassified_path`.

### 5.1 L3 — manual approval by the policy owner

| Area | Paths |
|---|---|
| Financial calculations | `backend/app/services/finance/**`, `backend/app/services/analytics/**`, `backend/app/services/{deposits,deposit_service,financial_summary,budgets,goals,overview,transactions,accounts}.py`, `frontend/lib/format.ts`, `frontend/components/deposits/deposit-utils.ts` |
| Auth and sessions | `backend/app/core/security.py`, `backend/app/services/auth.py`, `backend/app/api/auth.py`, `frontend/proxy.ts`, `frontend/lib/server/**`, `frontend/app/api/**`, `frontend/lib/api/http.ts` |
| Permissions / tenant isolation | `backend/app/api/deps.py`, `backend/app/repositories/**` |
| Database | `backend/app/models/**`, `backend/alembic/**`, `backend/alembic.ini`, `backend/app/core/database.py`, `backend/scripts/**` (backup/restore) |
| Security and runtime configuration | `backend/app/core/{config,middleware,rate_limit,errors,logging}.py`, `backend/app/services/imports/**`, `backend/app/api/{upload,imports}.py`, `backend/app/integrations/**`, `**/Dockerfile`, `**/.dockerignore`, `**/compose*.y*ml`, `**/docker-compose*.y*ml`, any path with a segment starting with `.env` (forbidden for the Executor, §8), `**/.gitignore`, `**/.gitattributes` (also a built-in L3 name, §5.0), `frontend/next.config.mjs`, `SECURITY.md`, `docs/SECURITY_REVIEW.md` |
| CI and orchestrator | `.github/**` (including `.github/ai/**`) and any path with a `.github` segment (forbidden for the Executor, §8) |
| Dependencies and toolchain | `**/requirements*.txt`, `**/pyproject.toml`, `**/package.json`, `**/pnpm-lock.yaml`, `**/pnpm-workspace.yaml` |
| AI policy | `backend/app/services/ai/**`, `CLAUDE.md`, `AGENTS.md`, `.claude/**` |
| Legal | `PRIVACY_POLICY.md`, `TERMS_OF_SERVICE.md`, `DISCLAIMER.md`, `THIRD_PARTY_NOTICES.md`, `docs/legal/**` |
| Tests of L3 areas | see §5.4 |
| Unknown | any valid path matching no rule; empty path list |

### 5.2 L1 — narrow allowlist

A path is L1 **only** if it is in one of these sets and in no L2/L3 rule:

1. **Documentation outside legal:** `docs/**`, except `docs/legal/**` (L3),
   `docs/SECURITY_REVIEW.md` (L3), `docs/DEPLOYMENT.md` and
   `docs/DOCKER_COMPOSE.md` (L2, operational instructions) and
   `docs/design/v0/**` (L2, context for an external AI tool).
2. **Copy-only files:** files that contain only user-facing text and no logic,
   registered by exact path in `risk_policy.toml` as an L1 rule whose id
   starts with `l1.copy_only.`.
   *None are registered today.*

**Localization is not L1** (it is L2, §5.3). It MAY become L1 in the future
only through a separate explicit allowlist of localization files, added by a
loosening policy change (§12), together with deterministic checks that the
change does not add, remove or rename message keys and keeps every
placeholder/interpolation token identical to the source language.

Registering a file as copy-only is a policy change (L3, §12).
A file is eligible only if it contains no executable logic, no imports other
than types, no routing, no data access and no calculations; general React
components, CSS, tests and configuration are **never** L1.

A change is L1 only if **all** of the following hold; otherwise it is at least L2:

- every path is L1;
- task type is `docs` or `ui_copy`, and domains are a subset of
  `{docs, ui_copy}`;
- change types are `modify` or `add` only (no delete, rename, mode change,
  symlink, binary or submodule);
- at most 10 files and 300 changed lines, measured on the actual Git diff (§6.2);
- no content escalation (§6.3), sanitizer signal (§6.4) or higher model /
  Reviewer estimate.

### 5.3 L2 — manual approval

Every known path that is neither L1 nor L3, in particular:

- `backend/app/api/**`, `backend/app/schemas/**`, the remaining
  `backend/app/services/**`, `backend/app/{tasks,utils}/**`, `backend/app/main.py`;
- `frontend/app/**` (outside `frontend/app/api/**`), `frontend/components/**`
  (outside the L3 files), `frontend/lib/**` (outside the L3 files),
  CSS files, `frontend/public/**`;
- tool configuration: `frontend/{eslint,postcss,playwright,vitest}.config.*`,
  `frontend/.prettierrc`, `frontend/.prettierignore`, `frontend/tsconfig.json`;
- root documents `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`;
- `docs/DEPLOYMENT.md`, `docs/DOCKER_COMPOSE.md` and `docs/design/v0/**`;
- localization resources (until a localization allowlist exists, §5.2).

### 5.4 Tests

| Test files | Level |
|---|---|
| Tests of L3 areas: `backend/tests/unit/finance/**`, `backend/tests/unit/ai/**`, `backend/tests/unit/imports/**`, `backend/tests/migrations/**`, `backend/tests/unit/test_{calculations,goal_progress,security,config,logging}.py`, `backend/tests/integration/test_{auth_api,auth_tokens,oauth2_token,tenant_isolation,hardening,upload_api,imports_api,database,repositories,financial_summary,deposit_term_bounds_api,deposits_overview_api,budget_utilization_all_api,analytics_api,advisor_api}.py`, `frontend/lib/format.test.ts`, `frontend/lib/server/**`, `frontend/components/deposits/deposit-utils.test.ts`, `frontend/e2e/{auth,password}.spec.ts` | **L3** |
| Shared test infrastructure (can weaken every test): `backend/tests/conftest.py`, `backend/tests/**/conftest.py`, `backend/tests/**/helpers.py`, `backend/tests/unit/finance/reference.py`, `frontend/tests/**`, `frontend/e2e/{global-setup,helpers}.ts`, `frontend/e2e/start-backend.sh` | **L3** |
| Any other existing or new test | **L2** minimum |

A test inherits the level of the module it covers when that is higher. When
the covered module cannot be determined, the test is L2. Tests are never L1.

## 6. Non-path rules

### 6.1 Domain rules

| Planner domain | Minimum level |
|---|---|
| `financial_calculation`, `auth`, `permissions`, `database`, `security`, `ci`, `dependencies`, `ai_policy`, `legal`, `unknown` | L3 |
| `backend_api`, `frontend_logic`, `tests`, `localization` | L2 |
| `docs`, `ui_copy` | L1 (subject to §5.2) |

`requires_migration` or `requires_new_dependencies` set to `true` → L3.

### 6.2 Change type and size

| Condition | Minimum level |
|---|---|
| `delete` or rename of any file (a rename is classified by both its source and its target path) | L2 (L3 if a path is L3) |
| `modify` or `delete` of an existing executable file; creating an executable file or renaming into one (`new_kind`) | L2 |
| `add` in an L3 area, at the repository root, or in a new top-level directory (`new_top_level`, §4.2) | L3 |
| Any operation on an existing symlink or submodule (entry kind, §4.2); creating a symlink or submodule or renaming into one (`new_kind`); mode change, including a type change and a rename into another entry kind; binary file | L3 |

Size limits per level:

| Level | Maximum size |
|---|---|
| L1 | 10 files and 300 changed lines |
| L2 | 25 files and 1000 changed lines |
| L3 | above any L2 limit |

Exceeding an L1 limit makes the change at least L2; exceeding **any** L2 limit
makes it L3. Size is measured **only on the actual Git diff** (files changed;
added plus deleted lines). Planner estimates are never used for size rules.
Before an actual diff exists, size rules are not evaluated and cannot lower
the level.

### 6.3 Content rules (actual diff, later phases)

Even inside L1 paths, the following raise the change to at least **L2**:

- added or changed shell commands, fenced code blocks with commands, install
  instructions;
- new or changed URLs, especially new domains;
- added strings that look like credentials, tokens, keys, IIN or card/account
  numbers (also triggers secret-handling review);
- changes to monetary amounts, rates, percentages or legal wording in
  user-facing text.

### 6.4 Sanitizer and injection signals

The sanitizer removes hidden content (HTML comments, zero-width and
bidirectional characters), truncates oversized input and detects suspicious
phrases. Each finding is a **signal** that raises the task to **L3** and is
recorded in the plan envelope.

The sanitizer is **not** a complete prompt-injection defence. Absence of
signals MUST NOT be treated as evidence that input is safe or lower any level.

### 6.5 Labels

- Labels MAY raise risk (e.g. `risk:L3` → L3).
- Labels MUST NOT lower risk; a label such as `risk:L1` is ignored.
- Labels MUST NOT, by themselves, prove eligibility or approval (§7, §9).

## 7. Eligibility

A request is eligible only if **both** hold, verified from GitHub permissions
obtained from the GitHub API at evaluation time (not from text, labels or
`author_association` alone):

1. the **issue author** has `write`, `maintain` or `admin` permission on the
   repository; and
2. the **initiator** of the triggering action (the user who requested
   automation, e.g. applied the trigger label or dispatched the run) has
   `write`, `maintain` or `admin` permission.

Additionally:

- Bot accounts, deleted users and outside collaborators without the required
  permission are not eligible.
- Scheduled runs have no human initiator: they MAY only pick issues that
  already passed eligibility, with the approval bound to the issue content (§9).
- If the issue title or body changes after eligibility/approval, the approval
  is invalid and the request is re-evaluated.
- An ineligible request is rejected without calling the Planner.

## 8. Forbidden areas

The orchestrator MUST NOT, at any level and with any approval:

- modify any path with a `.github` segment (root `.github/**` and nested
  occurrences such as `frontend/.github/**`) through the Executor; policy
  changes are made by humans only, under §12;
- read, create or modify secrets or credentials, or any path with a segment
  starting with `.env` — files and directories alike (`.env`, `.env.local`,
  `.envrc`, `.env/secrets.json`, `backend/.env/…`), including `.env.example`
  (changes to example files are made only by human-authored L3 pull requests);
- access production systems or production data, run deployments, or apply
  migrations to any non-ephemeral database;
- rewrite history, force-push, or push directly to the default branch.

**Path-level enforcement.** Only the `.github` and `.env*` rules above are hard
path-level restrictions (§4). They are always applied and can be extended but
never disabled by configuration. The remaining prohibitions — in particular
other secrets and credentials — are enforced by the Risk Policy, content checks
and the Executor's own constraints; path validation alone does not detect
secrets.

## 9. Approval process

| Level | Before execution | Before merge |
|---|---|---|
| L1 | Eligibility (§7). No human plan approval required in the target state. | Actual diff re-evaluated as L1; independent Reviewer pass; all gates green. **Until the auto-merge phase is implemented and approved, L1 merges are manual.** |
| L2 | Manual plan approval by a trusted maintainer (`write`+) | Actual diff re-evaluated; Reviewer pass; all gates green; manual merge approval |
| L3 | Manual plan approval by the policy owner | Actual diff re-evaluated; Reviewer pass; all gates green; manual merge approval by the policy owner |

Rules:

- An approval is bound to the plan envelope: input hash, policy version and
  approved risk level. Any change to these invalidates it.
- Approval is given by an authenticated GitHub action of a user with the
  required permission — never by a label alone, a comment parsed by a model,
  or text in the issue.
- **Gates** (all levels): required checks from the policy's check mapping
  (union with checks requested by the Planner; Planner cannot remove any),
  existing CI green, no forbidden area touched, limits respected (§10).
- **The author of a pull request MUST NOT approve it.** For changes produced by
  the orchestrator, the approver MUST NOT be the initiator of the task.
- **L3, future requirement:** once the repository has enough maintainers, L3
  requires **two independent approvers** (neither the PR author nor the task
  initiator). Until then, L3 requires the policy owner's approval.

### 9.1 Preconditions for Executor and auto-merge

The Executor phase and any automatic merge MUST NOT be enabled until:

- branch protection is enabled on the default branch (required pull request
  reviews, required status checks, no force-push, no direct push);
- `CODEOWNERS` assigns the protected areas — at least `.github/**` and every
  L3 area in §5.1 and §5.4 — to the policy owner, with code-owner review
  required by branch protection.

Configuring both is itself an L3 change.

## 10. Execution limits

These caps live in `risk_policy.toml`; the effective value is
`min(planner value, cap)`:

| Limit | Cap |
|---|---|
| Active tasks | 1 |
| Tasks per scheduled run | 1 |
| Repair loops per task | 3 |
| Task timeout | 45 minutes |
| Production deployments / data / automatic migrations | none |

## 11. Policy ownership

- **Owner:** the repository owner. Only the owner approves changes to this
  policy, to `risk_policy.toml`, and to anything under `.github/**`.
- **Delegation:** the owner MAY name additional policy approvers by a policy
  change (§12). Until then there is a single approver.
- **Responsibilities:** keep this document and `risk_policy.toml` consistent,
  classify new top-level directories and new sensitive files, review escalation
  statistics, and run the policy review below.
- **Review cadence:** at least before enabling each new phase (Executor,
  Reviewer, triggers, auto-merge) and after any incident.

## 12. Change control

1. Every change to `.github/ai/**` is **L3** and is made by a human-authored
   pull request. The orchestrator MUST NOT propose, author or merge it.
2. The pull request MUST state whether the change **tightens** or **loosens**
   the policy:
   - *tightening* (higher levels, new L3 paths, fewer L1 paths, lower caps):
     owner approval;
   - *loosening* (lower levels, new L1/L2 paths, new copy-only registrations,
     a localization allowlist, higher caps, new triggers or permissions): owner approval
     **plus** a written rationale in an ADR or ADR addendum.
3. Versions use semantic versioning (major for loosening or semantics
   changes, minor for tightening, patch for wording) and are recorded in the
   changelog below. There are two versions:
   - the **policy document version** (this file) is bumped for every change
     of this document;
   - the **executable Risk Policy version** (`risk_policy.toml`
     `policy_version`) is bumped only when the executable rules, levels,
     limits or defaults change. Risk assessments and approval bindings (§3.3)
     bind to the executable version, so a documentation-only change does not
     invalidate existing approvals.
4. Once code exists, the change MUST keep `risk_policy.toml`, this document and
   the policy tests consistent; the coverage test MUST classify every tracked
   file in the repository.
5. The policy in effect is always the version on the protected default branch.
   A pull request is never evaluated with the policy from its own head.
6. Emergency: the owner MAY stop all automation at any time (disable
   triggers); re-enabling follows this section.

## 13. Changelog

| Version | Date | Change |
|---|---|---|
| `0.7.0-draft` (document; executable `0.5.0-draft`) | 2026-11-23 | T3.3.2 hardening (tightening, no executable rule change): `validate_approval(binding, diff, policy)` recomputes the risk assessment and the scope comparison itself and accepts no precomputed results; a `RiskPolicy` object is accepted (also by `evaluate`) only if it is exactly what the loader produces; exact input types, single field reads, strict counts and exact strings are required; the result field is `binding_consistent` and carries no authorisation (§3.3). No risk level lowered. |
| `0.6.0-draft` (document; executable `0.5.0-draft`) | 2026-11-23 | Tightening, documentation and process only — `risk_policy.toml` unchanged. §3.1 (T3.2): scope drift is implemented with exact, literal matching of operation, source and destination; a rename never equals a delete plus an add; invalid or inconsistent comparison input is drift and raises the effective level to at least L3 (unknown scope); drift raises it to at least L2; no drift never authorises. §3.3 (T3.3): in-memory approval binding to scope, effective level, executable Risk Policy version, file and line counts and full commit IDs; it is not an authorisation. §12: policy document version and executable Risk Policy version are distinct. No risk level lowered. |
| `0.5.0-draft` | 2026-11-23 | T3.2 (tightening): `.gitattributes` at any depth is L3 — explicit `l3.security` pattern plus a built-in L3 file name that L1/L2 rules cannot name or lower (§5.0, §5.1). Evaluator input gains `new_kind` (entry kind after the change): creating or renaming into an executable file is at least L2, into a symlink or submodule L3, and a rename into another kind is a mode change (L3) (§3.2, §6.2). The Git diff adapter now emits such changes instead of rejecting them. Policy version and rule ids are validated as whole strings. No risk level lowered. |
| `0.4.0-draft` | 2026-11-23 | T3: machine-readable `risk_policy.toml` and deterministic evaluator. New §5.0 (matching semantics, no precedence by order, L3 case-insensitive, unclassified → L3, every tracked file explicitly classified) and §3.2 (evaluation result; `executable` is not an authorisation). §6.2: renames are classified by source and target; existing executable files are at least L2 (tightening). §4.4: linked worktrees supported; Git failures are `git_failed`; `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` are dropped and HOME/XDG/system Git configuration and `PATH` are trusted. Copy-only files are registered as `l1.copy_only.*` rules. No risk level lowered. |
| `0.1.0-draft` | 2026-11-23 | Initial draft (T1): trust boundaries, L1/L2/L3, eligibility, approval, ownership, change control. Not yet enforced. |
| `0.3.0-draft` | 2026-11-23 | T2.1 alignment with `orchestrator/paths.py`: §4 rewritten (ASCII-only paths, rejected rather than Unicode-normalised; character, segment and Windows restrictions; index, change-set and snapshot rules; literal-path contract; no secret detection). `.github` forbidden in any segment and `.env*` in any segment including directories (§8, tightening). Additions at the repository root or in a new top-level directory are valid paths classified L3, and symlinks/submodules keep their type and are L3 operations (§6.2) — no risk level is lowered. Empty change sets are not executable. |
| `0.2.0-draft` | 2026-11-23 | Tightening after T1 review: localization removed from L1; `docs/DEPLOYMENT.md`, `docs/DOCKER_COMPOSE.md`, `docs/design/v0/**`, `README.md`, `CONTRIBUTING.md` fixed at L2; size limits L1 ≤ 10 files / 300 lines, L2 ≤ 25 files / 1000 lines, above → L3, measured on the actual Git diff only; scope drift invalidates approval; PR author cannot approve; future two-approver rule for L3; branch protection and CODEOWNERS required before Executor/auto-merge. |

## 14. Open questions

1. Format of future localization resources and the exact key/placeholder
   checks for a localization allowlist; criteria for registering copy-only
   files (none are registered yet).
2. Exact thresholds for content rules (§6.3).
3. The number of maintainers at which the two-approver rule for L3 starts
   to apply.
4. A credential filename/extension denylist (keys, certificates, token
   files) for the Risk Policy or content checks (§4.6).
5. Whether path segments starting with `-` should be rejected at the path
   level (today they are valid; the literal-path contract requires `--`).
