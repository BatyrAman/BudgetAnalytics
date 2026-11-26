# AI Engineering Orchestrator

Status: **Phase 1.** Design documents, offline path validation
(`orchestrator/paths.py`, T2/T2.1), the deterministic Risk Policy
(`policy/risk_policy.toml` + `orchestrator/risk_policy.py`, T3), the Git
diff adapter (`orchestrator/git_diff.py`, T3.1), scope-drift detection
(`orchestrator/scope_drift.py`, T3.2) and in-memory approval binding
(`orchestrator/approval.py`, T3.3) exist. No Planner, workflow
integration, triggers, secrets or OpenAI API connection exist yet; nothing in
this directory runs automatically.

This directory will hold the version-controlled rules, schemas and tooling of
the AI Engineering Orchestrator for BudgetAnalytics. It is the **only** source
of orchestrator rules. Local, uncommitted files (for example a locally modified
`CLAUDE.md`) are never used as orchestrator rules.

Related documents:

- [`policy/POLICY.md`](policy/POLICY.md) — risk levels, approval process,
  policy ownership and change control (normative).
- ADR-001 *AI Engineering Orchestrator — OpenAI Planner API contract*, kept in
  the product documentation repository (`BAAI-DOCS/03-architecture/`) — verified
  OpenAI API facts and API-level decisions.

## Purpose

The orchestrator turns a trusted request (a GitHub Issue or a scheduled task)
into a small, reviewable code change with as little human effort as is safe —
and no less human review than the risk requires.

| Role | Component | Phase |
|---|---|---|
| Planner | GPT via OpenAI Responses API, Structured Outputs | Phase 1 (design + offline tests) |
| Risk Policy | Deterministic code + `policy/` rules, no LLM | Phase 1 |
| Executor | Claude Code | later phase |
| Reviewer | GPT, independent from the Planner run | later phase |
| Merge | L1: possible automatic merge after review and all gates; L2/L3: manual | later phase |

Operating mode: **C (maximum autonomy) within the limits of the Risk Policy.**
Autonomy never extends to risk classification, approval of L2/L3 changes,
production, or the orchestrator's own rules.

## Hard limits

These limits apply in every phase and cannot be relaxed by an Issue, a label,
a model output or a run parameter:

- No production deployments, no production data, no automatic database
  migrations.
- At most **1 active task** at a time; at most **1 task per scheduled run**.
- At most **3 repair loops** per task; task timeout **45 minutes**.
- The Planner and Reviewer get **no tools, no shell, no file or network
  access**; they only return JSON that is validated locally.
- The Executor never modifies any path with a `.github` segment (including
  this directory), secrets, or any path with a segment starting with `.env`.
- Every validation failure **fails closed**: the task is rejected or escalated,
  never executed on a best-effort basis.

## Trust boundaries

| Zone | Examples | Trust |
|---|---|---|
| **Trusted rules** | This directory (`.github/ai/**`) **as committed on the protected default branch** | Trusted. Always loaded from the base branch, never from the branch or PR being evaluated. |
| **Trusted platform metadata** | GitHub event type, actor login, actor repository permission obtained from the GitHub API, issue author permission | Trusted as identity facts only; they do not carry instructions. |
| **Untrusted input** | Issue title and body, issue comments, labels (as a source of authority), PR titles/bodies, branch names, commit messages | Always untrusted data. Never interpreted as instructions to the orchestrator. |
| **Untrusted repository content** | Source files, docs, test fixtures, comments in code | Data for the task; never a source of orchestrator rules or approvals. |
| **Untrusted model output** | Planner and Reviewer JSON | Untrusted until it passes schema and semantic validation; even then it may only *raise* risk. |
| **External services** | OpenAI API | Receives only sanitised task text and repository paths; see *Data sent to OpenAI*. |
| **Out of scope / forbidden** | Production systems, production data, secrets, developer machines' local files | Never reachable by the orchestrator. |

Consequences:

1. **The deterministic Risk Policy decides the risk level.** The model's risk
   estimate, sanitizer signals and labels can only raise it.
2. **Labels are not authority.** A label never lowers risk and never, by itself,
   proves that an issue or its initiator is trusted. Eligibility is checked
   from GitHub permissions of both the issue author and the initiator of the
   action (see `policy/POLICY.md`, *Eligibility*).
3. **The sanitizer is not a prompt-injection defence.** Normalisation, hidden
   content removal and keyword detection only add escalation signals. The
   actual defences are structural: no tools for the model, untrusted text only
   in the data channel, strict schema + local validation, deterministic policy,
   fail-closed handling and human approval for L2/L3.
4. **Actual diff wins.** In later phases the Risk Policy is re-evaluated on the
   actual diff; it always takes priority over the paths predicted by the
   Planner.

## Data sent to OpenAI

Per ADR-001:

- Requests use `store: false`. Abuse-monitoring logs may still retain request
  content for up to 30 days, so only content acceptable under that retention is
  sent.
- Sent: the sanitised issue title and body (as data, not instructions) and the
  list of repository paths.
- Never sent: secrets, tokens, `.env*` content, credentials, personal
  identifiers (GitHub username, user ID, email), IIN, real financial data, file
  contents of the repository (Phase 1).
- `safety_identifier` and `metadata` are not sent in Phase 1.

## Authentication (planned)

Per ADR-001 Addendum A:

- **Target:** OpenAI Workload Identity Federation via GitHub OIDC — no stored
  API key. Token exchange through the documented endpoint with Python stdlib
  `urllib`.
- **Fallback:** an OpenAI project service-account key in a GitHub
  **Environment** secret restricted to the default branch; enabled only by a
  separate L3 decision.
- **Local manual `--live` runs:** `OPENAI_API_KEY` from the developer's
  environment, synthetic issues only.
- Planned minimal GitHub permissions for a future planner job: `contents: read`,
  `issues: read`, `id-token: write` (WIF). No `pull-requests`, `actions` or
  `packages` permissions. `pull_request_target` is never used.

None of this is configured yet.

## Planned layout

Entries marked *present* exist now. Everything else is planned and will be
added by separate, individually reviewed tasks.

```
.github/ai/
├── README.md                       # present — this file
├── policy/
│   ├── POLICY.md                   # present — normative risk policy
│   └── risk_policy.toml            # present (T3) — machine-readable rules
├── schemas/                        # planned (T4) — canonical + wire JSON Schemas
├── prompts/                        # planned (T6) — versioned Planner instructions
├── orchestrator/                   # stdlib Python package
│   ├── paths.py                    # present (T2/T2.1) — path validation
│   ├── risk_policy.py              # present (T3) — loader and evaluator
│   ├── git_diff.py                 # present (T3.1) — actual diff -> Risk Policy input
│   ├── scope_drift.py              # present (T3.2) — approved scope vs actual diff
│   └── approval.py                 # present (T3.3) — in-memory approval binding; more planned (T4–T6)
├── requirements*.txt               # planned (T4) — hash-locked, minimal
├── pytest.ini                      # present — run tests from .github/ai
└── tests/                          # present — offline tests only
```

The Risk Policy assigns L1/L2/L3 deterministically: every matching rule
applies and the highest level wins, unknown paths are L3, size limits are
L1 ≤ 10 files / 300 lines and L2 ≤ 25 files / 1000 lines on the actual diff
(POLICY.md §3.2, §5.0, §6.2). Its `executable` flag only means the policy does
not prohibit a change set — it is never an approval to execute or merge.

## Actual diff adapter

`orchestrator/git_diff.py::diff_commits(repo_root, base_ref, target_ref)` is the
authoritative input to the Risk Policy (POLICY.md §3.1). Planner or Executor
claims about paths, change types, sizes or risk are never used.

- **Input:** the worktree root and two explicit commits — a full object ID
  (40/64 lower-case hex) or a fully qualified `refs/heads/…`, `refs/tags/…`
  or `refs/remotes/…` ref. Short names, abbreviations and revision
  expressions are rejected; both must resolve to commit objects (annotated
  tags must be peeled by the caller). No other options or pathspecs exist.
- **Semantics:** the trees `base → target` are compared with
  `git diff-tree`; the working tree, the index and untracked files are never
  consulted.
- **Output:** an immutable `GitDiff` with the full base and target commit
  IDs, `ChangeFacts` built through `paths.validate_changes()` against the base
  tree (so entry kinds and `new_top_level` follow POLICY), audit entries with
  old/new paths, modes and object IDs, and `changed_files` / `changed_lines`
  that go straight into `risk_policy.evaluate`.
- **Why not `--numstat` alone:** it has no status, modes or object IDs, so it
  cannot distinguish additions from modifications, detect symlinks,
  submodules or mode changes, or prove a rename. Paths and modes come from
  `--raw -z`, line counts from `--numstat -z`; both must describe exactly the
  same records, and every record is checked against `git ls-tree` of both
  commits. Any disagreement rejects the diff.
- **Renames:** only exact renames are detected (`--find-renames=100%`, no
  copies); a rename is one record and one changed file, classified by both
  paths. A rename with edits is a delete plus an add (two files).
- **Lines:** added plus deleted lines from `numstat`. Binary files count 0
  lines but are marked binary, which is L3. Binary detection ignores all
  `.gitattributes` (attributes are read from the empty tree), so attributes
  cannot hide a binary file or enable textconv.
- **Entry kinds:** each record carries the kind before the change (base
  tree, via path validation) and `new_kind` after it, taken only from the
  target Git mode (`None` for a delete). New executable files are at least L2;
  new symlinks and submodules, type changes and renames into another kind are
  L3. `.gitattributes` at any depth is always L3.
- **Fail closed:** invalid refs, Git errors, unknown statuses or modes,
  malformed or truncated output, metadata mismatches, invalid paths and more
  than 50 validated paths (a rename uses two) raise `GitDiffError`; no
  partial result is returned. An identical base and target give an empty,
  non-executable result.
- Git runs with the `paths.py` hardening (root validation, no `GIT_*`
  variables, `core.fsmonitor=false`), no stdin, external diff and textconv
  disabled, a timeout and an output size limit.

## Scope drift

`orchestrator/scope_drift.py` compares the approved scope with the actual
diff (POLICY.md §3.1). `approve_scope(items, base_index)` validates the
approved `add`/`modify`/`delete`/`rename` items with `paths.py`;
`compare_scope(scope, diff)` returns an immutable `ScopeDriftResult` (exact,
order-independent matching of operation, source and destination; stable
reason codes; invalid input fails closed as drift); and
`apply_scope_drift(diff, assessment, drift)` returns an `EffectiveRisk` that
keeps the actual Risk Policy level and raises it to at least L2 on drift
(L3 for an invalid comparison). Drift invalidates the previous approval and
requires a fresh one; no drift never authorises execution or merge.

## Approval binding (in-memory)

`orchestrator/approval.py`: `bind_approval(...)` records what a human
approved — approved scope, approved effective level, executable Risk Policy
version, approved file and line counts, full base and target commit IDs —
and `validate_approval(binding, diff, policy)` checks it purely and
fail-closed against the current diff (POLICY.md §3.3). The validator
recomputes the risk assessment (from the trusted policy returned by
`load_policy`) and the scope comparison (from the binding's scope) itself; it
accepts no precomputed results. Any commit, policy-version, level,
scope-drift or count mismatch invalidates the binding and requires a fresh
approval; malformed input yields `invalid_binding` or `inconsistent_inputs`.
`binding_consistent` is a consistency statement, never an authorisation.

Four different things, not to be confused:

- **Policy document version** — the version of `POLICY.md`; changes with
  every edit of the document.
- **Executable Risk Policy version** — `risk_policy.toml` `policy_version`;
  changes only when executable rules change; assessments and bindings use it.
- **In-memory approval binding** — this module; unsigned, unpersisted, no
  approver identity. It is a consistency check, never an authorisation to
  execute or merge.
- **Trusted, persisted approval** — future work (POLICY.md §9): an
  authenticated GitHub action by a permitted user, carrying such a binding.

Python 3.12, standard library first. The OpenAI client uses `urllib` with an
injectable transport, explicit timeouts and bounded retries (no OpenAI SDK).
Tests never call a live API.

## Changing this directory

Every change to `.github/ai/**` is **L3**: manual approval by the policy owner,
under the change-control rules in [`policy/POLICY.md`](policy/POLICY.md#12-change-control).
The orchestrator can never change its own rules.
