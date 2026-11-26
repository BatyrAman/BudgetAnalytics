"""In-memory approval binding and pure approval validation (T3.3, hardened T3.3.2).

An :class:`ApprovalBinding` records exactly what a human approved: the approved
scope, the approved effective risk level, the executable Risk Policy version
(``risk_policy.toml`` ``policy_version``), the approved changed file and line
counts, and the full base and target commit IDs.

:func:`validate_approval` (``binding, diff, policy``) checks a binding against
the current actual diff. It accepts **no precomputed results**: it recomputes
the ``RiskAssessment`` with :func:`orchestrator.risk_policy.evaluate` from the
supplied trusted policy and the diff, recomputes the scope comparison with
:func:`orchestrator.scope_drift.compare_scope` from the binding's approved
scope and the diff, and derives the effective level with
:func:`orchestrator.scope_drift.apply_scope_drift`. It is pure (no
filesystem, subprocess, network, environment or persistence) and
deterministic.

**This is not an authorisation mechanism.** A binding is an unsigned,
unpersisted in-memory value without approver identity. ``binding_consistent``
only means that the binding is consistent with the supplied diff and policy;
it never authorises execution or merge. Trusted, persisted approvals
(POLICY.md section 9) and all other gates remain mandatory.

Trust boundary: ``policy`` must be the object returned by
:func:`orchestrator.risk_policy.load_policy` and ``diff`` the object returned
by :func:`orchestrator.git_diff.diff_commits`, computed locally. The validator
verifies their structure and internal consistency (a policy object must be
exactly what the loader produces from its own values; diff records, counts
and commit IDs must be complete and consistent) but cannot prove provenance.

Malformed input (contract): exact types are required (no subclasses), every
field is read once (unset slots are detected), counts must be non-negative
``int`` (not ``bool``), and strings compared for security decisions must be
exact ``str``. A malformed binding yields ``invalid_binding``; a malformed or
inconsistent diff or policy yields ``inconsistent_inputs``. Only
``RiskEvaluationError`` and ``ScopeError`` from the recomputation are mapped,
after the structural checks; any other exception would indicate a defect in
this code and is deliberately not swallowed.

Semantics: commit IDs are full lower-case object IDs (40 or 64 hex
characters, same length); levels compare by ``RiskLevel`` ordering (an L1
approval never covers L2 or L3, L2 never covers L3, nothing is downgraded;
the *effective* level including the scope-drift floor is compared); any
scope drift invalidates the binding; file and line counts follow the Git diff
adapter (a rename is one file; lines are added plus deleted) and must not
exceed the approved counts.
"""

from __future__ import annotations

import dataclasses
import enum
import re
from dataclasses import dataclass
from typing import Any, TypeGuard

from orchestrator.git_diff import DiffEntry, GitDiff
from orchestrator.paths import ChangeType, EntryKind, ValidatedPath
from orchestrator.risk_policy import (
    MAX_CHANGED_LINES,
    MAX_EVALUATED_CHANGES,
    ChangeFacts,
    RiskAssessment,
    RiskEvaluationError,
    RiskLevel,
    RiskPolicy,
    evaluate,
    is_valid_policy,
    is_valid_policy_version,
)
from orchestrator.scope_drift import (
    ApprovedScope,
    EffectiveRisk,
    PlannedChange,
    ScopeEntry,
    ScopeError,
    ScopeOperation,
    apply_scope_drift,
    compare_scope,
    expected_entries,
)

_COMMIT_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_MISSING = object()


class ApprovalErrorCode(enum.StrEnum):
    INVALID_BINDING = "invalid_binding"


class ApprovalError(ValueError):
    """An approval binding cannot be created. ``field`` names the offending field;
    the offending value is never included."""

    def __init__(self, code: ApprovalErrorCode, *, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"approval binding rejected: {code.value} ({field})")


# Stable reason codes, reported sorted.
INVALID_BINDING = "invalid_binding"
INCONSISTENT_INPUTS = "inconsistent_inputs"
BASE_COMMIT_MISMATCH = "base_commit_mismatch"
TARGET_COMMIT_MISMATCH = "target_commit_mismatch"
POLICY_VERSION_MISMATCH = "policy_version_mismatch"
RISK_EXCEEDS_APPROVAL = "risk_exceeds_approval"
SCOPE_DRIFT = "scope_drift"
FILE_COUNT_EXCEEDS_APPROVAL = "file_count_exceeds_approval"
LINE_COUNT_EXCEEDS_APPROVAL = "line_count_exceeds_approval"


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    """Immutable record of an approval. Build with :func:`bind_approval`."""

    scope: ApprovedScope
    approved_level: RiskLevel
    policy_version: str
    approved_files: int
    approved_lines: int
    base_commit: str
    target_commit: str


@dataclass(frozen=True, slots=True)
class ApprovalValidation:
    """Immutable result of :func:`validate_approval`.

    ``binding_consistent`` means only that the in-memory binding is consistent
    with the supplied diff and policy. It is **not** an authorisation to
    execute or merge; there is deliberately no such field. Values that could
    not be established from trustworthy input are ``None``.
    """

    binding_consistent: bool
    reasons: tuple[str, ...]
    approved_level: RiskLevel | None
    actual_level: RiskLevel | None
    effective_level: RiskLevel | None
    approved_files: int | None
    actual_files: int | None
    approved_lines: int | None
    actual_lines: int | None
    policy_version_matches: bool
    base_commit_matches: bool
    target_commit_matches: bool
    scope_drift: bool
    policy_executable: bool
    assessment: RiskAssessment | None
    effective: EffectiveRisk | None


# ------------------------------------------------------------- structure


def _fields_of(value: object, cls: type[Any]) -> dict[str, object] | None:
    """Snapshot all fields of an exact ``cls`` instance once, or ``None``."""

    names = [field.name for field in dataclasses.fields(cls)]
    if type(value) is not cls:
        return None
    snapshot = {name: getattr(value, name, _MISSING) for name in names}
    if any(item is _MISSING for item in snapshot.values()):
        return None
    return snapshot


def _is_commit(value: object) -> TypeGuard[str]:
    return type(value) is str and _COMMIT_RE.fullmatch(value) is not None


def _is_count(value: object, maximum: int) -> TypeGuard[int]:
    return type(value) is int and 0 <= value <= maximum


def _is_version(value: object) -> TypeGuard[str]:
    return is_valid_policy_version(value)


def _is_optional_str(value: object) -> bool:
    return value is None or type(value) is str


def _valid_path_record(value: object) -> bool:
    fields = _fields_of(value, ValidatedPath)
    return (
        fields is not None
        and type(fields["path"]) is str
        and type(fields["change"]) is ChangeType
        and type(fields["kind"]) is EntryKind
        and type(fields["new_top_level"]) is bool
    )


def _valid_scope_structure(scope: object) -> TypeGuard[ApprovedScope]:
    fields = _fields_of(scope, ApprovedScope)
    if fields is None:
        return False
    changes = fields["changes"]
    if type(changes) is not tuple:
        return False
    for change in changes:
        change_fields = _fields_of(change, PlannedChange)
        if (
            change_fields is None
            or type(change_fields["operation"]) is not ScopeOperation
            or not _valid_path_record(change_fields["target"])
            or not (change_fields["source"] is None or _valid_path_record(change_fields["source"]))
        ):
            return False
    return True


@dataclass(frozen=True, slots=True)
class _Binding:
    """Validated snapshot of a binding (each field read once)."""

    scope: ApprovedScope
    entries: tuple[ScopeEntry, ...]
    approved_level: RiskLevel
    policy_version: str
    approved_files: int
    approved_lines: int
    base_commit: str
    target_commit: str


def _binding_snapshot(binding: object) -> tuple[_Binding | None, str]:
    """Return ``(snapshot, "")`` or ``(None, name_of_first_invalid_field)``."""

    fields = _fields_of(binding, ApprovalBinding)
    if fields is None:
        return None, "binding"
    level = fields["approved_level"]
    version = fields["policy_version"]
    files = fields["approved_files"]
    lines = fields["approved_lines"]
    base = fields["base_commit"]
    target = fields["target_commit"]
    scope = fields["scope"]
    if type(level) is not RiskLevel:
        return None, "approved_level"
    if not _is_version(version):
        return None, "policy_version"
    if not _is_count(files, MAX_EVALUATED_CHANGES):
        return None, "approved_files"
    if not _is_count(lines, MAX_CHANGED_LINES):
        return None, "approved_lines"
    if not _is_commit(base):
        return None, "base_commit"
    if not _is_commit(target) or len(target) != len(base):
        return None, "target_commit"
    if not _valid_scope_structure(scope):
        return None, "scope"
    try:
        entries = expected_entries(scope)
    except ScopeError:
        return None, "scope"
    # Internal consistency: one approved change record per changed file
    # (Git diff adapter convention: a rename is one file).
    if files != len(entries):
        return None, "approved_files"
    if not entries and lines != 0:
        return None, "approved_lines"
    snapshot = _Binding(
        scope=scope,
        entries=entries,
        approved_level=level,
        policy_version=version,
        approved_files=files,
        approved_lines=lines,
        base_commit=base,
        target_commit=target,
    )
    return snapshot, ""


@dataclass(frozen=True, slots=True)
class _Diff:
    """Validated snapshot of a diff's security-relevant fields."""

    base_commit: str
    target_commit: str
    changes: tuple[ChangeFacts, ...]
    changed_files: int
    changed_lines: int


def _change_lines(facts: object, entry: object) -> int | None:
    """Validate one change record and its audit entry; return its line count."""

    facts_fields = _fields_of(facts, ChangeFacts)
    entry_fields = _fields_of(entry, DiffEntry)
    if facts_fields is None or entry_fields is None:
        return None
    new_kind = facts_fields["new_kind"]
    renamed_from = facts_fields["renamed_from"]
    binary = facts_fields["binary"]
    mode_change = facts_fields["mode_change"]
    added = entry_fields["added_lines"]
    deleted = entry_fields["deleted_lines"]
    if not _is_count(added, MAX_CHANGED_LINES) or not _is_count(deleted, MAX_CHANGED_LINES):
        return None
    if (
        not _valid_path_record(facts_fields["change"])
        or not (new_kind is None or type(new_kind) is EntryKind)
        or not (renamed_from is None or _valid_path_record(renamed_from))
        or type(binary) is not bool
        or type(mode_change) is not bool
        or type(entry_fields["status"]) is not str
        or not all(
            _is_optional_str(entry_fields[name])
            for name in ("old_path", "new_path", "old_mode", "new_mode", "old_oid", "new_oid")
        )
        or entry_fields["binary"] is not binary
        or entry_fields["mode_change"] is not mode_change
        or (binary and (added or deleted))
    ):
        return None
    return added + deleted


def _diff_snapshot(diff: object) -> _Diff | None:
    """Structural and internal-consistency checks of a ``GitDiff``."""

    fields = _fields_of(diff, GitDiff)
    if fields is None:
        return None
    base, target = fields["base_commit"], fields["target_commit"]
    changes, entries = fields["changes"], fields["entries"]
    files, lines = fields["changed_files"], fields["changed_lines"]
    if not _is_commit(base) or not _is_commit(target) or len(base) != len(target):
        return None
    if type(changes) is not tuple or type(entries) is not tuple:
        return None
    if not _is_count(files, MAX_EVALUATED_CHANGES) or not _is_count(lines, MAX_CHANGED_LINES):
        return None
    if len(changes) != len(entries) or files != len(changes):
        return None
    total = 0
    for facts, entry in zip(changes, entries, strict=True):
        count = _change_lines(facts, entry)
        if count is None:
            return None
        total += count
    # The line count is derived from the audit records, not trusted as given.
    if total != lines:
        return None
    return _Diff(base, target, changes, files, lines)


# ----------------------------------------------------------------- binding


def bind_approval(
    *,
    scope: ApprovedScope,
    approved_level: RiskLevel,
    policy_version: str,
    approved_files: int,
    approved_lines: int,
    base_commit: str,
    target_commit: str,
) -> ApprovalBinding:
    """Create a validated binding. Raises :class:`ApprovalError` on any invalid field."""

    binding = ApprovalBinding(
        scope=scope,
        approved_level=approved_level,
        policy_version=policy_version,
        approved_files=approved_files,
        approved_lines=approved_lines,
        base_commit=base_commit,
        target_commit=target_commit,
    )
    snapshot, problem = _binding_snapshot(binding)
    if snapshot is None:
        raise ApprovalError(ApprovalErrorCode.INVALID_BINDING, field=problem)
    return binding


# --------------------------------------------------------------- validation


def _rejected(reason: str, snapshot: _Binding | None) -> ApprovalValidation:
    return ApprovalValidation(
        binding_consistent=False,
        reasons=(reason,),
        approved_level=snapshot.approved_level if snapshot else None,
        actual_level=None,
        effective_level=None,
        approved_files=snapshot.approved_files if snapshot else None,
        actual_files=None,
        approved_lines=snapshot.approved_lines if snapshot else None,
        actual_lines=None,
        policy_version_matches=False,
        base_commit_matches=False,
        target_commit_matches=False,
        scope_drift=True,
        policy_executable=False,
        assessment=None,
        effective=None,
    )


def validate_approval(binding: object, diff: object, policy: object) -> ApprovalValidation:
    """Check an approval binding against the actual diff under the trusted policy.

    Recomputes the risk assessment and the scope comparison; see the module
    docstring for the trust boundary and the malformed-input contract.
    """

    snapshot, _problem = _binding_snapshot(binding)
    if snapshot is None:
        return _rejected(INVALID_BINDING, None)
    actual = _diff_snapshot(diff)
    if actual is None or type(policy) is not RiskPolicy or not is_valid_policy(policy):
        return _rejected(INCONSISTENT_INPUTS, snapshot)
    assert isinstance(diff, GitDiff)  # established by _diff_snapshot (exact type)
    policy_version = policy.policy_version

    try:
        assessment = evaluate(
            policy,
            actual.changes,
            changed_files=actual.changed_files,
            changed_lines=actual.changed_lines,
            expected_policy_version=policy_version,
        )
    except RiskEvaluationError:
        return _rejected(INCONSISTENT_INPUTS, snapshot)
    drift = compare_scope(snapshot.scope, diff)
    if not drift.valid_input:
        # The scope was validated above, so the diff is inconsistent.
        return _rejected(INCONSISTENT_INPUTS, snapshot)
    try:
        effective = apply_scope_drift(diff, assessment, drift)
    except ScopeError:
        return _rejected(INCONSISTENT_INPUTS, snapshot)

    base_matches = actual.base_commit == snapshot.base_commit
    target_matches = actual.target_commit == snapshot.target_commit
    version_matches = policy_version == snapshot.policy_version
    reasons: set[str] = set()
    if not base_matches:
        reasons.add(BASE_COMMIT_MISMATCH)
    if not target_matches:
        reasons.add(TARGET_COMMIT_MISMATCH)
    if not version_matches:
        reasons.add(POLICY_VERSION_MISMATCH)
    if drift.has_drift:
        reasons.add(SCOPE_DRIFT)
    if effective.effective_level > snapshot.approved_level:
        reasons.add(RISK_EXCEEDS_APPROVAL)
    if actual.changed_files > snapshot.approved_files:
        reasons.add(FILE_COUNT_EXCEEDS_APPROVAL)
    if actual.changed_lines > snapshot.approved_lines:
        reasons.add(LINE_COUNT_EXCEEDS_APPROVAL)

    return ApprovalValidation(
        binding_consistent=not reasons,
        reasons=tuple(sorted(reasons)),
        approved_level=snapshot.approved_level,
        actual_level=effective.actual_level,
        effective_level=effective.effective_level,
        approved_files=snapshot.approved_files,
        actual_files=actual.changed_files,
        approved_lines=snapshot.approved_lines,
        actual_lines=actual.changed_lines,
        policy_version_matches=version_matches,
        base_commit_matches=base_matches,
        target_commit_matches=target_matches,
        scope_drift=drift.has_drift,
        policy_executable=effective.policy_executable,
        assessment=assessment,
        effective=effective,
    )
