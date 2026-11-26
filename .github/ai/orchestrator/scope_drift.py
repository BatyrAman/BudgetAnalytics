"""Deterministic scope-drift detection (POLICY.md section 3.1).

Compares an *approved scope* (the plan a human approved) with the *actual*
diff from :mod:`orchestrator.git_diff`. Pure functions only: no Git, no
filesystem, no network, no clock, no environment; inputs are never mutated.

Approved scope
    Built with :func:`approve_scope` from ``(operation, path)`` items
    (``add``, ``modify``, ``delete``) and ``("rename", source, destination)``
    items. Every path goes through :func:`orchestrator.paths.validate_changes`
    against the base index (a rename is validated as the delete of its source
    plus the add of its destination), so raw Planner strings are never
    trusted. Duplicates, case duplicates, conflicts, forbidden paths and
    malformed items are rejected. An empty scope is allowed (it only matches
    an empty diff). There is no approval identifier: the architecture has
    none yet.

Matching semantics
    Each change is the exact triple ``(operation, source, target)``;
    ``source`` is set only for renames. Paths are compared literally and
    case-sensitively; no patterns, directories or wildcards. The approved and
    actual sets must be identical, independent of order. A rename matches only
    a rename with the same source and destination; it never matches an
    unrelated delete plus add (and vice versa). Entry kinds, type changes,
    binary flags and line counts are not part of the scope; the Risk Policy
    classifies them on the actual diff (a planned ``modify`` matches an actual
    modify or type change of the same path).

Drift
    Any difference is drift: unexpected changes (by operation), missing
    changes, operation mismatches, rename source/destination mismatches,
    rename-versus-separate-operations mismatches and case-only differences.
    Invalid or inconsistent input on either side is reported as drift too
    (``invalid_scope`` / ``invalid_actual``); a no-drift result is returned
    only after both inputs were fully checked.

Risk
    :func:`apply_scope_drift` wraps the actual ``RiskAssessment`` without
    changing it: drift raises the effective level to at least L2, an invalid
    comparison to at least L3 (unknown scope), and nothing is ever lowered.
    Drift or an invalid comparison invalidates the previous approval and
    requires a fresh one. A valid no-drift result is **not** an approval and
    does not authorise execution or merge; all other gates still apply.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass

from orchestrator.git_diff import DiffEntry, GitDiff
from orchestrator.paths import (
    ChangeType,
    PathValidationError,
    RepoIndex,
    ValidatedPath,
    is_forbidden_path,
    normalize_path,
    validate_changes,
)
from orchestrator.risk_policy import ChangeFacts, RiskAssessment, RiskLevel


class ScopeOperation(enum.StrEnum):
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"


class ScopeErrorCode(enum.StrEnum):
    INVALID_ITEM = "invalid_item"
    INVALID_OPERATION = "invalid_operation"
    INVALID_PATH = "invalid_path"
    INCONSISTENT_INPUTS = "inconsistent_inputs"


class ScopeError(ValueError):
    """Unusable input. ``cause`` carries a nested stable code; raw input is not echoed."""

    def __init__(
        self, code: ScopeErrorCode, *, index: int | None = None, cause: str | None = None
    ) -> None:
        self.code = code
        self.index = index
        self.cause = cause
        details = "".join(
            [f" (item {index})" if index is not None else "", f" [{cause}]" if cause else ""]
        )
        super().__init__(f"scope rejected: {code.value}{details}")


# Stable reason codes.
UNEXPECTED_ADD = "unexpected_add"
UNEXPECTED_MODIFY = "unexpected_modify"
UNEXPECTED_DELETE = "unexpected_delete"
UNEXPECTED_RENAME = "unexpected_rename"
MISSING_CHANGE = "missing_change"
OPERATION_MISMATCH = "operation_mismatch"
RENAME_SOURCE_MISMATCH = "rename_source_mismatch"
RENAME_DESTINATION_MISMATCH = "rename_destination_mismatch"
RENAME_REPRESENTATION_MISMATCH = "rename_representation_mismatch"
CASE_MISMATCH = "case_mismatch"
INVALID_SCOPE = "invalid_scope"
INVALID_ACTUAL = "invalid_actual"

_UNEXPECTED_BY_OPERATION = {
    ScopeOperation.ADD: UNEXPECTED_ADD,
    ScopeOperation.MODIFY: UNEXPECTED_MODIFY,
    ScopeOperation.DELETE: UNEXPECTED_DELETE,
    ScopeOperation.RENAME: UNEXPECTED_RENAME,
}
_CHANGE_FOR_OPERATION = {
    ScopeOperation.ADD: ChangeType.ADD,
    ScopeOperation.MODIFY: ChangeType.MODIFY,
    ScopeOperation.DELETE: ChangeType.DELETE,
    ScopeOperation.RENAME: ChangeType.ADD,  # the destination
}
_OPERATION_FOR_CHANGE: dict[object, ScopeOperation] = {
    ChangeType.ADD: ScopeOperation.ADD,
    ChangeType.MODIFY: ScopeOperation.MODIFY,
    ChangeType.DELETE: ScopeOperation.DELETE,
}
_DIFF_STATUS_FOR_OPERATION = {
    ScopeOperation.ADD: {"A"},
    ScopeOperation.MODIFY: {"M", "T"},
    ScopeOperation.DELETE: {"D"},
    ScopeOperation.RENAME: {"R"},
}


# ------------------------------------------------------------------- models


@dataclass(frozen=True, slots=True, order=True)
class ScopeEntry:
    """One change as plain, already validated strings (sortable, comparable)."""

    operation: ScopeOperation
    target: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class PlannedChange:
    """An approved change; paths are ``ValidatedPath`` records, never raw strings.

    ``target`` is the path that is added, modified or deleted, or the rename
    destination (an ``add``); ``source`` is the rename source (a ``delete``)
    and ``None`` for every other operation.
    """

    operation: ScopeOperation
    target: ValidatedPath
    source: ValidatedPath | None = None


@dataclass(frozen=True, slots=True)
class ApprovedScope:
    """Immutable approved scope, sorted canonically. Build with :func:`approve_scope`."""

    changes: tuple[PlannedChange, ...]


@dataclass(frozen=True, slots=True)
class Mismatch:
    """A path present on both sides with a different change."""

    path: str
    reason: str
    expected: ScopeEntry
    actual: ScopeEntry


@dataclass(frozen=True, slots=True)
class ScopeDriftResult:
    """Immutable, order-independent comparison result.

    ``approval_valid`` is true only for a valid comparison without drift; it
    means the *previous* approval still covers the diff, never that execution
    or merge is authorised.
    """

    valid_input: bool
    has_drift: bool
    approval_valid: bool
    reasons: tuple[str, ...]
    expected: tuple[ScopeEntry, ...]
    actual: tuple[ScopeEntry, ...]
    unexpected_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]
    operation_mismatches: tuple[Mismatch, ...]
    rename_mismatches: tuple[Mismatch, ...]


@dataclass(frozen=True, slots=True)
class EffectiveRisk:
    """Actual diff risk combined with scope drift; never lower than ``actual_level``.

    ``policy_executable`` is copied from the ``RiskAssessment``; neither it nor
    ``previous_approval_valid`` authorises execution or merge.
    """

    actual_level: RiskLevel
    effective_level: RiskLevel
    scope_drift: bool
    scope_comparison_valid: bool
    previous_approval_valid: bool
    fresh_approval_required: bool
    policy_executable: bool
    reasons: tuple[str, ...]
    assessment: RiskAssessment
    drift: ScopeDriftResult


# ------------------------------------------------------------ approved scope


def _parse_operation(value: object, position: int) -> ScopeOperation:
    if isinstance(value, str):
        try:
            return ScopeOperation(value)
        except ValueError:
            pass
    raise ScopeError(ScopeErrorCode.INVALID_OPERATION, index=position)


def approve_scope(items: Iterable[object], base_index: RepoIndex) -> ApprovedScope:
    """Validate a planned scope against the index of the base commit.

    Items are ``(operation, path)`` tuples for ``add``/``modify``/``delete``
    and ``("rename", source, destination)`` tuples. Raises :class:`ScopeError`.
    """

    if isinstance(items, (str, bytes)):
        raise ScopeError(ScopeErrorCode.INVALID_ITEM)
    shapes: list[tuple[ScopeOperation, int]] = []  # operation, first validated slot
    validation_items: list[tuple[object, str]] = []
    owners: list[int] = []  # plan position of each validated slot
    for position, item in enumerate(items):
        if not isinstance(item, tuple) or len(item) not in {2, 3}:
            raise ScopeError(ScopeErrorCode.INVALID_ITEM, index=position)
        operation = _parse_operation(item[0], position)
        expected_length = 3 if operation is ScopeOperation.RENAME else 2
        if len(item) != expected_length:
            raise ScopeError(ScopeErrorCode.INVALID_ITEM, index=position)
        shapes.append((operation, len(validation_items)))
        if operation is ScopeOperation.RENAME:
            validation_items += [(item[2], "add"), (item[1], "delete")]
            owners += [position, position]
        else:
            validation_items.append((item[1], _CHANGE_FOR_OPERATION[operation].value))
            owners.append(position)
    if not shapes:
        return ApprovedScope(changes=())
    try:
        validated = validate_changes(validation_items, base_index)
    except PathValidationError as error:
        owner = None if error.index is None else owners[error.index]
        raise ScopeError(ScopeErrorCode.INVALID_PATH, index=owner, cause=error.code.value) from None
    changes = []
    for operation, slot in shapes:
        source = validated[slot + 1] if operation is ScopeOperation.RENAME else None
        changes.append(PlannedChange(operation, validated[slot], source))
    changes.sort(key=lambda change: _scope_entry(change))
    return ApprovedScope(changes=tuple(changes))


def _scope_entry(change: PlannedChange) -> ScopeEntry:
    source = change.source.path if change.source is not None else None
    return ScopeEntry(change.operation, change.target.path, source)


# ------------------------------------------------------------ input checking


class _InvalidInputError(Exception):
    pass


_MISSING = object()


def _field(value: object, name: str) -> object:
    """Read one attribute once; unset slots become an invalid-input error."""

    result = getattr(value, name, _MISSING)
    if result is _MISSING:
        raise _InvalidInputError
    return result


def _canonical(path: object) -> str:
    if type(path) is not str:  # no subclasses with overridden equality
        raise _InvalidInputError
    try:
        if normalize_path(path) != path:
            raise _InvalidInputError
    except PathValidationError:
        raise _InvalidInputError from None
    if is_forbidden_path(path):
        raise _InvalidInputError
    return path


def _check_record(record: object, change: ChangeType) -> str:
    if type(record) is not ValidatedPath or _field(record, "change") is not change:
        raise _InvalidInputError
    return _canonical(_field(record, "path"))


def _check_unique(entries: Iterable[ScopeEntry]) -> None:
    seen: set[str] = set()
    for entry in entries:
        for path in (entry.target, entry.source):
            if path is None:
                continue
            folded = path.casefold()
            if folded in seen:
                raise _InvalidInputError
            seen.add(folded)


def _scope_entries(scope: object) -> tuple[ScopeEntry, ...]:
    if type(scope) is not ApprovedScope:
        raise _InvalidInputError
    changes = _field(scope, "changes")
    if type(changes) is not tuple:
        raise _InvalidInputError
    entries: list[ScopeEntry] = []
    for change in changes:
        if type(change) is not PlannedChange:
            raise _InvalidInputError
        operation = _field(change, "operation")
        target_record = _field(change, "target")
        source_record = _field(change, "source")
        if type(operation) is not ScopeOperation:
            raise _InvalidInputError
        target = _check_record(target_record, _CHANGE_FOR_OPERATION[operation])
        source: str | None = None
        if operation is ScopeOperation.RENAME:
            source = _check_record(source_record, ChangeType.DELETE)
        elif source_record is not None:
            raise _InvalidInputError
        entries.append(ScopeEntry(operation, target, source))
    _check_unique(entries)
    return tuple(sorted(entries))


def _actual_entry(facts: object, status: object) -> ScopeEntry:
    if type(facts) is not ChangeFacts:
        raise _InvalidInputError
    record = _field(facts, "change")
    renamed_from = _field(facts, "renamed_from")
    if type(record) is not ValidatedPath:
        raise _InvalidInputError
    operation: ScopeOperation | None
    if renamed_from is not None:
        operation = ScopeOperation.RENAME
    else:
        operation = _OPERATION_FOR_CHANGE.get(_field(record, "change"))
    if operation is None:
        raise _InvalidInputError
    if type(status) is not str or status not in _DIFF_STATUS_FOR_OPERATION[operation]:
        raise _InvalidInputError
    target = _check_record(record, _CHANGE_FOR_OPERATION[operation])
    source = None
    if operation is ScopeOperation.RENAME:
        source = _check_record(renamed_from, ChangeType.DELETE)
        if source == target:
            raise _InvalidInputError
    return ScopeEntry(operation, target, source)


def expected_entries(scope: object) -> tuple[ScopeEntry, ...]:
    """Scope entries of an approved scope, sorted. Raises :class:`ScopeError` if invalid."""

    try:
        return _scope_entries(scope)
    except _InvalidInputError:
        raise ScopeError(ScopeErrorCode.INCONSISTENT_INPUTS) from None


def actual_entries(diff: object) -> tuple[ScopeEntry, ...]:
    """Scope entries of an actual diff, sorted. Raises :class:`ScopeError` if inconsistent."""

    try:
        return _actual_entries(diff)
    except _InvalidInputError:
        raise ScopeError(ScopeErrorCode.INCONSISTENT_INPUTS) from None


def _actual_entries(diff: object) -> tuple[ScopeEntry, ...]:
    if type(diff) is not GitDiff:
        raise _InvalidInputError
    changes = _field(diff, "changes")
    audit = _field(diff, "entries")
    changed_files = _field(diff, "changed_files")
    if (
        type(changes) is not tuple
        or type(audit) is not tuple
        or len(changes) != len(audit)
        or type(changed_files) is not int
        or changed_files != len(changes)
    ):
        raise _InvalidInputError
    entries: list[ScopeEntry] = []
    for facts, record in zip(changes, audit, strict=True):
        if type(record) is not DiffEntry:
            raise _InvalidInputError
        entry = _actual_entry(facts, _field(record, "status"))
        old_path = _field(record, "old_path")
        new_path = _field(record, "new_path")
        expected_old = {
            ScopeOperation.ADD: None,
            ScopeOperation.MODIFY: entry.target,
            ScopeOperation.DELETE: entry.target,
            ScopeOperation.RENAME: entry.source,
        }[entry.operation]
        expected_new = None if entry.operation is ScopeOperation.DELETE else entry.target
        if (old_path, new_path) != (expected_old, expected_new):
            raise _InvalidInputError
        entries.append(entry)
    _check_unique(entries)
    return tuple(sorted(entries))


# -------------------------------------------------------------- comparison


def _roles(entries: Iterable[ScopeEntry]) -> dict[str, tuple[ScopeEntry, str]]:
    """Map every path to its entry and role (``target`` or ``source``)."""

    roles: dict[str, tuple[ScopeEntry, str]] = {}
    for entry in entries:
        roles[entry.target] = (entry, "target")
        if entry.source is not None:
            roles[entry.source] = (entry, "source")
    return roles


def _invalid(reason: str) -> ScopeDriftResult:
    return ScopeDriftResult(
        valid_input=False,
        has_drift=True,
        approval_valid=False,
        reasons=(reason,),
        expected=(),
        actual=(),
        unexpected_paths=(),
        missing_paths=(),
        operation_mismatches=(),
        rename_mismatches=(),
    )


def compare_scope(scope: object, diff: object) -> ScopeDriftResult:
    """Compare an approved scope with an actual diff. Never raises on bad input.

    Invalid input on either side gives a drift result with ``valid_input``
    false; see the module docstring for the matching semantics.
    """

    try:
        expected = _scope_entries(scope)
    except _InvalidInputError:
        return _invalid(INVALID_SCOPE)
    try:
        actual = _actual_entries(diff)
    except _InvalidInputError:
        return _invalid(INVALID_ACTUAL)

    reasons: set[str] = set()
    expected_roles = _roles(expected)
    actual_roles = _roles(actual)
    unexpected = sorted(actual_roles.keys() - expected_roles.keys())
    missing = sorted(expected_roles.keys() - actual_roles.keys())
    for path in unexpected:
        reasons.add(_UNEXPECTED_BY_OPERATION[actual_roles[path][0].operation])
    if missing:
        reasons.add(MISSING_CHANGE)
    missing_folded = {path.casefold() for path in missing}
    if any(path.casefold() in missing_folded for path in unexpected):
        reasons.add(CASE_MISMATCH)

    operation_mismatches: list[Mismatch] = []
    rename_mismatches: list[Mismatch] = []
    for path in sorted(expected_roles.keys() & actual_roles.keys()):
        planned, planned_role = expected_roles[path]
        found, found_role = actual_roles[path]
        if planned == found:
            continue
        planned_rename = planned.operation is ScopeOperation.RENAME
        found_rename = found.operation is ScopeOperation.RENAME
        if not planned_rename and not found_rename:
            reason = OPERATION_MISMATCH
        elif planned_rename and found_rename and planned_role == found_role:
            reason = (
                RENAME_SOURCE_MISMATCH
                if planned_role == "target"
                else (RENAME_DESTINATION_MISMATCH)
            )
        else:
            reason = RENAME_REPRESENTATION_MISMATCH
        mismatch = Mismatch(path, reason, planned, found)
        reasons.add(reason)
        if reason == OPERATION_MISMATCH:
            operation_mismatches.append(mismatch)
        else:
            rename_mismatches.append(mismatch)

    has_drift = bool(reasons)
    return ScopeDriftResult(
        valid_input=True,
        has_drift=has_drift,
        approval_valid=not has_drift,
        reasons=tuple(sorted(reasons)),
        expected=expected,
        actual=actual,
        unexpected_paths=tuple(unexpected),
        missing_paths=tuple(missing),
        operation_mismatches=tuple(operation_mismatches),
        rename_mismatches=tuple(rename_mismatches),
    )


# ------------------------------------------------------------------- risk


DRIFT_FLOOR = RiskLevel.L2
INVALID_COMPARISON_FLOOR = RiskLevel.L3


def apply_scope_drift(
    diff: GitDiff, assessment: RiskAssessment, drift: ScopeDriftResult
) -> EffectiveRisk:
    """Combine the actual risk with scope drift. Never lowers the actual level.

    Raises :class:`ScopeError` (``inconsistent_inputs``) if the diff itself is
    inconsistent or the three inputs do not belong to the same diff; nothing is
    returned in that case, so no approval can survive it.
    """

    if not isinstance(assessment, RiskAssessment) or not isinstance(drift, ScopeDriftResult):
        raise ScopeError(ScopeErrorCode.INCONSISTENT_INPUTS)
    entries = actual_entries(diff)
    if (
        assessment.file_count != diff.changed_files
        or assessment.line_count != diff.changed_lines
        or tuple(p.path for p in assessment.paths) != tuple(c.change.path for c in diff.changes)
        or not isinstance(assessment.level, RiskLevel)
    ):
        raise ScopeError(ScopeErrorCode.INCONSISTENT_INPUTS)
    if drift.valid_input and (drift.actual != entries or drift.approval_valid == drift.has_drift):
        raise ScopeError(ScopeErrorCode.INCONSISTENT_INPUTS)

    actual_level = assessment.level
    reasons: list[str] = []
    if not drift.valid_input:
        effective = max(actual_level, INVALID_COMPARISON_FLOOR)
        reasons.append("invalid_scope_comparison")
        approval_valid = False
    elif drift.has_drift:
        effective = max(actual_level, DRIFT_FLOOR)
        reasons.append("scope_drift")
        approval_valid = False
    else:
        effective = actual_level
        approval_valid = True
    if effective > actual_level:
        reasons.append("scope_risk_floor")
    return EffectiveRisk(
        actual_level=actual_level,
        effective_level=effective,
        scope_drift=drift.has_drift,
        scope_comparison_valid=drift.valid_input,
        previous_approval_valid=approval_valid,
        fresh_approval_required=not approval_valid,
        policy_executable=assessment.executable,
        reasons=tuple(sorted(reasons)),
        assessment=assessment,
        drift=drift,
    )
