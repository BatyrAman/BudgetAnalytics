"""Tests for orchestrator.scope_drift (T3.2 scope drift). Offline; temporary repos only."""

from __future__ import annotations

import copy
import dataclasses
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from orchestrator.git_diff import DiffEntry, GitDiff, diff_commits
from orchestrator.paths import ChangeType, EntryKind, RepoIndex, ValidatedPath
from orchestrator.risk_policy import (
    ChangeFacts,
    RiskAssessment,
    RiskLevel,
    evaluate,
    load_policy,
)
from orchestrator.scope_drift import (
    CASE_MISMATCH,
    INVALID_ACTUAL,
    INVALID_SCOPE,
    MISSING_CHANGE,
    OPERATION_MISMATCH,
    RENAME_DESTINATION_MISMATCH,
    RENAME_REPRESENTATION_MISMATCH,
    RENAME_SOURCE_MISMATCH,
    UNEXPECTED_ADD,
    UNEXPECTED_DELETE,
    UNEXPECTED_MODIFY,
    UNEXPECTED_RENAME,
    ApprovedScope,
    PlannedChange,
    ScopeDriftResult,
    ScopeEntry,
    ScopeError,
    ScopeErrorCode,
    ScopeOperation,
    actual_entries,
    apply_scope_drift,
    approve_scope,
    compare_scope,
)

L1, L2, L3 = RiskLevel.L1, RiskLevel.L2, RiskLevel.L3
K = EntryKind
OP = ScopeOperation
POLICY = load_policy()
GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(GIT is None, reason="git is not installed")


# ------------------------------------------------------------------ helpers


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True)
        self.git("init", "-q")

    def git(self, *args: str) -> str:
        argv = [GIT or "git", "-C", str(self.root), *args]
        result = subprocess.run(argv, check=True, capture_output=True)  # noqa: S603 - test argv
        return result.stdout.decode()

    def write(self, path: str, content: str = "x\n") -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def remove(self, path: str) -> None:
        (self.root / path).unlink()

    def commit(self) -> str:
        self.git("add", "--all")
        self.git(
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "--no-verify",
            "--allow-empty",
            "-m",
            "c",
        )
        return self.git("rev-parse", "HEAD").strip()


@dataclasses.dataclass(frozen=True)
class Scenario:
    repo: Repo
    base: str
    index: RepoIndex  # index of the base commit, taken before the target changes

    def diff(self, mutate: object) -> GitDiff:
        assert callable(mutate)
        mutate(self.repo)
        target = self.repo.commit()
        return diff_commits(self.repo.root, self.base, target)


@pytest.fixture
def scenario(tmp_path: Path) -> Scenario:
    repo = Repo(tmp_path / "repo")
    for name in ("a", "b", "c", "d"):
        repo.write(f"docs/design/{name}.md", f"{name}\n")
    repo.write("docs/legal/terms.md", "legal\n")
    repo.write("backend/app/main.py", "print(1)\n")
    base = repo.commit()
    return Scenario(repo, base, RepoIndex.from_git(repo.root))


def standard_change(repo: Repo) -> None:
    repo.write("docs/design/a.md", "changed\n")
    repo.write("docs/design/new.md", "new\n")
    repo.remove("docs/design/b.md")
    repo.git("mv", "docs/design/c.md", "docs/design/c2.md")


STANDARD_PLAN: list[tuple[str, ...]] = [
    ("modify", "docs/design/a.md"),
    ("add", "docs/design/new.md"),
    ("delete", "docs/design/b.md"),
    ("rename", "docs/design/c.md", "docs/design/c2.md"),
]


def assess(diff: GitDiff) -> RiskAssessment:
    return evaluate(
        POLICY,
        diff.changes,
        changed_files=diff.changed_files,
        changed_lines=diff.changed_lines,
        expected_policy_version=POLICY.policy_version,
    )


def scope_error(items: list[object], index: RepoIndex) -> ScopeError:
    with pytest.raises(ScopeError) as info:
        approve_scope(items, index)
    return info.value


# ------------------------------------------------------------ approved scope


def test_approved_scope_is_validated_and_canonical(scenario: Scenario) -> None:
    scope = approve_scope(STANDARD_PLAN, scenario.index)
    entries = [
        (c.operation, c.target.path, c.source.path if c.source else None) for c in scope.changes
    ]
    assert entries == sorted(entries)
    rename = next(c for c in scope.changes if c.operation is OP.RENAME)
    assert (rename.target.change, rename.source and rename.source.change) == (
        ChangeType.ADD,
        ChangeType.DELETE,
    )
    assert approve_scope(list(reversed(STANDARD_PLAN)), scenario.index) == scope
    assert approve_scope([], scenario.index) == ApprovedScope(changes=())


@pytest.mark.parametrize(
    ("items", "code", "cause", "index"),
    [
        ([None], ScopeErrorCode.INVALID_ITEM, None, 0),
        (["add"], ScopeErrorCode.INVALID_ITEM, None, 0),
        ([("add",)], ScopeErrorCode.INVALID_ITEM, None, 0),
        ([["add", "docs/design/x.md"]], ScopeErrorCode.INVALID_ITEM, None, 0),
        ([("add", "docs/design/x.md", "extra")], ScopeErrorCode.INVALID_ITEM, None, 0),
        ([("rename", "docs/design/c.md")], ScopeErrorCode.INVALID_ITEM, None, 0),
        ([("copy", "docs/design/x.md")], ScopeErrorCode.INVALID_OPERATION, None, 0),
        ([("ADD", "docs/design/x.md")], ScopeErrorCode.INVALID_OPERATION, None, 0),
        ([(1, "docs/design/x.md")], ScopeErrorCode.INVALID_OPERATION, None, 0),
        ([("add", "../x.md")], ScopeErrorCode.INVALID_PATH, "traversal", 0),
        ([("add", "docs/*.md")], ScopeErrorCode.INVALID_PATH, "wildcard", 0),
        ([("add", ".github/workflows/x.yml")], ScopeErrorCode.INVALID_PATH, "forbidden_area", 0),
        ([("modify", "docs/design/missing.md")], ScopeErrorCode.INVALID_PATH, "not_tracked", 0),
        ([("modify", "docs/design/A.md")], ScopeErrorCode.INVALID_PATH, "case_mismatch", 0),
        (
            [("modify", "docs/design/a.md"), ("delete", "docs/design/a.md")],
            ScopeErrorCode.INVALID_PATH,
            "duplicate_path",
            1,
        ),
        (
            [("add", "docs/design/n.md"), ("add", "docs/design/N.md")],
            ScopeErrorCode.INVALID_PATH,
            "case_duplicate",
            1,
        ),
        (
            [("rename", "docs/design/c.md", "docs/design/x.md"), ("delete", "docs/design/c.md")],
            ScopeErrorCode.INVALID_PATH,
            "duplicate_path",
            1,
        ),
        (
            [("rename", "docs/design/c.md", "docs/design/c.md")],
            ScopeErrorCode.INVALID_PATH,
            "already_tracked",
            0,
        ),
        (
            [("rename", "docs/design/missing.md", "docs/design/x.md")],
            ScopeErrorCode.INVALID_PATH,
            "not_tracked",
            0,
        ),
        (
            [("add", "docs/design/n"), ("add", "docs/design/n/x.md")],
            ScopeErrorCode.INVALID_PATH,
            "path_conflict",
            1,
        ),
    ],
)
def test_invalid_plans_are_rejected(
    scenario: Scenario, items: list[object], code: ScopeErrorCode, cause: str | None, index: int
) -> None:
    error = scope_error(items, scenario.index)
    assert (error.code, error.cause, error.index) == (code, cause, index)
    assert "docs/" not in str(error)  # raw input is not echoed


def test_plan_rejects_non_iterables_and_strings(scenario: Scenario) -> None:
    with pytest.raises(ScopeError):
        approve_scope("add docs/x.md", scenario.index)


# ----------------------------------------------------------- exact matching


def test_identical_scope_has_no_drift(scenario: Scenario) -> None:
    diff = scenario.diff(standard_change)
    scope = approve_scope(STANDARD_PLAN, scenario.index)
    result = compare_scope(scope, diff)
    assert (result.valid_input, result.has_drift, result.approval_valid) == (True, False, True)
    assert result.reasons == ()
    assert result.expected == result.actual
    assert ScopeEntry(OP.RENAME, "docs/design/c2.md", "docs/design/c.md") in result.actual
    assert (result.unexpected_paths, result.missing_paths) == ((), ())


def test_input_order_does_not_matter(scenario: Scenario) -> None:
    diff = scenario.diff(standard_change)
    forward = compare_scope(approve_scope(STANDARD_PLAN, scenario.index), diff)
    backward = compare_scope(approve_scope(list(reversed(STANDARD_PLAN)), scenario.index), diff)
    shuffled = dataclasses.replace(diff, changes=diff.changes[::-1], entries=diff.entries[::-1])
    assert (
        forward == backward == compare_scope(approve_scope(STANDARD_PLAN, scenario.index), shuffled)
    )


def test_empty_scope_and_empty_diff(scenario: Scenario) -> None:
    diff = diff_commits(scenario.repo.root, scenario.base, scenario.base)
    result = compare_scope(approve_scope([], scenario.index), diff)
    assert (result.has_drift, result.approval_valid, result.reasons) == (False, True, ())


def test_type_changes_match_a_planned_modify(scenario: Scenario) -> None:
    def to_symlink(repo: Repo) -> None:
        repo.remove("docs/design/a.md")
        (repo.root / "docs/design/a.md").symlink_to("b.md")

    diff = scenario.diff(to_symlink)
    assert diff.entries[0].status == "T"
    result = compare_scope(approve_scope([("modify", "docs/design/a.md")], scenario.index), diff)
    assert result.has_drift is False


# --------------------------------------------------------------- drift cases


def _drift(scenario: Scenario, plan: Sequence[object], mutate: object) -> ScopeDriftResult:
    diff = scenario.diff(mutate)
    return compare_scope(approve_scope(plan, scenario.index), diff)


@pytest.mark.parametrize(
    ("plan_without", "reason", "path"),
    [
        (("add", "docs/design/new.md"), UNEXPECTED_ADD, "docs/design/new.md"),
        (("modify", "docs/design/a.md"), UNEXPECTED_MODIFY, "docs/design/a.md"),
        (("delete", "docs/design/b.md"), UNEXPECTED_DELETE, "docs/design/b.md"),
    ],
)
def test_unexpected_changes(
    scenario: Scenario, plan_without: tuple[str, str], reason: str, path: str
) -> None:
    plan = [item for item in STANDARD_PLAN if item != plan_without]
    result = _drift(scenario, plan, standard_change)
    assert result.has_drift and not result.approval_valid and result.valid_input
    assert result.reasons == (reason,)
    assert result.unexpected_paths == (path,)
    assert result.missing_paths == ()


def test_unexpected_rename(scenario: Scenario) -> None:
    plan = [item for item in STANDARD_PLAN if item[0] != "rename"]
    result = _drift(scenario, plan, standard_change)
    assert result.reasons == (UNEXPECTED_RENAME,)
    assert result.unexpected_paths == ("docs/design/c.md", "docs/design/c2.md")


def test_approved_change_missing_from_the_diff(scenario: Scenario) -> None:
    plan = [*STANDARD_PLAN, ("modify", "docs/design/d.md")]
    result = _drift(scenario, plan, standard_change)
    assert result.reasons == (MISSING_CHANGE,)
    assert result.missing_paths == ("docs/design/d.md",)


def test_operation_mismatch(scenario: Scenario) -> None:
    plan = [("delete", "docs/design/a.md")]
    result = _drift(scenario, plan, lambda r: r.write("docs/design/a.md", "changed\n"))
    assert result.reasons == (OPERATION_MISMATCH,)
    (mismatch,) = result.operation_mismatches
    assert (mismatch.path, mismatch.expected.operation, mismatch.actual.operation) == (
        "docs/design/a.md",
        OP.DELETE,
        OP.MODIFY,
    )


def test_multiple_simultaneous_mismatches(scenario: Scenario) -> None:
    plan = [
        ("delete", "docs/design/a.md"),  # actual: modify
        ("modify", "docs/design/d.md"),  # actual: untouched
        ("rename", "docs/design/c.md", "docs/design/c3.md"),  # actual: c -> c2
    ]
    result = _drift(scenario, plan, standard_change)
    assert result.reasons == (
        MISSING_CHANGE,
        OPERATION_MISMATCH,
        RENAME_DESTINATION_MISMATCH,
        UNEXPECTED_ADD,
        UNEXPECTED_DELETE,
        UNEXPECTED_RENAME,
    )
    assert result.missing_paths == ("docs/design/c3.md", "docs/design/d.md")
    assert result.unexpected_paths == (
        "docs/design/b.md",
        "docs/design/c2.md",
        "docs/design/new.md",
    )


def test_case_only_path_mismatch(scenario: Scenario) -> None:
    plan = [("add", "docs/design/New.md")]
    result = _drift(scenario, plan, lambda r: r.write("docs/design/new.md", "n\n"))
    assert set(result.reasons) == {CASE_MISMATCH, MISSING_CHANGE, UNEXPECTED_ADD}
    assert result.missing_paths == ("docs/design/New.md",)
    assert result.unexpected_paths == ("docs/design/new.md",)


def test_rename_source_mismatch(scenario: Scenario) -> None:
    plan = [("rename", "docs/design/d.md", "docs/design/c2.md")]
    result = _drift(scenario, plan, lambda r: r.git("mv", "docs/design/c.md", "docs/design/c2.md"))
    assert RENAME_SOURCE_MISMATCH in result.reasons
    (mismatch,) = result.rename_mismatches
    assert mismatch.path == "docs/design/c2.md"
    assert (mismatch.expected.source, mismatch.actual.source) == (
        "docs/design/d.md",
        "docs/design/c.md",
    )
    assert result.missing_paths == ("docs/design/d.md",)
    assert result.unexpected_paths == ("docs/design/c.md",)


def test_rename_destination_mismatch(scenario: Scenario) -> None:
    plan = [("rename", "docs/design/c.md", "docs/design/c3.md")]
    result = _drift(scenario, plan, lambda r: r.git("mv", "docs/design/c.md", "docs/design/c2.md"))
    assert RENAME_DESTINATION_MISMATCH in result.reasons
    assert result.rename_mismatches[0].path == "docs/design/c.md"


def test_planned_rename_versus_actual_delete_plus_add(scenario: Scenario) -> None:
    def edit_rename(repo: Repo) -> None:
        repo.remove("docs/design/c.md")
        repo.write("docs/design/c2.md", "different content\n")

    plan = [("rename", "docs/design/c.md", "docs/design/c2.md")]
    result = _drift(scenario, plan, edit_rename)
    assert result.reasons == (RENAME_REPRESENTATION_MISMATCH,)
    assert [m.path for m in result.rename_mismatches] == ["docs/design/c.md", "docs/design/c2.md"]


def test_planned_delete_plus_add_versus_actual_rename(scenario: Scenario) -> None:
    plan = [("delete", "docs/design/c.md"), ("add", "docs/design/c2.md")]
    result = _drift(scenario, plan, lambda r: r.git("mv", "docs/design/c.md", "docs/design/c2.md"))
    assert result.reasons == (RENAME_REPRESENTATION_MISMATCH,)
    assert len(result.rename_mismatches) == 2


# ------------------------------------------------------------ invalid inputs


def _forged(cls: type, **fields: object) -> object:
    instance: object = object.__new__(cls)
    for name, value in fields.items():
        object.__setattr__(instance, name, value)
    return instance


def _vp(path: str, change: ChangeType, kind: EntryKind = K.REGULAR_FILE) -> ValidatedPath:
    return ValidatedPath(path, change, K.NEW if change is ChangeType.ADD else kind, False)


GOOD_ADD = PlannedChange(OP.ADD, _vp("docs/design/x.md", ChangeType.ADD))


@pytest.mark.parametrize(
    "scope",
    [
        None,
        "scope",
        _forged(ApprovedScope, changes=[GOOD_ADD]),  # list, not tuple
        ApprovedScope(changes=("docs/design/x.md",)),  # type: ignore[arg-type]
        ApprovedScope(
            changes=(  # type: ignore[arg-type]
                _forged(PlannedChange, operation="add", target=GOOD_ADD.target, source=None),
            )
        ),
        ApprovedScope(changes=(PlannedChange(OP.ADD, "docs/design/x.md"),)),  # type: ignore[arg-type]
        ApprovedScope(changes=(PlannedChange(OP.MODIFY, GOOD_ADD.target),)),  # wrong change type
        ApprovedScope(changes=(PlannedChange(OP.ADD, GOOD_ADD.target, GOOD_ADD.target),)),
        ApprovedScope(changes=(PlannedChange(OP.RENAME, GOOD_ADD.target, None),)),
        ApprovedScope(
            changes=(PlannedChange(OP.RENAME, GOOD_ADD.target, _vp("docs/a.md", ChangeType.ADD)),)
        ),
        ApprovedScope(changes=(PlannedChange(OP.ADD, _vp("docs/../x.md", ChangeType.ADD)),)),
        ApprovedScope(changes=(PlannedChange(OP.ADD, _vp(".github/x.yml", ChangeType.ADD)),)),
        ApprovedScope(changes=(GOOD_ADD, GOOD_ADD)),  # duplicate
        ApprovedScope(
            changes=(GOOD_ADD, PlannedChange(OP.ADD, _vp("docs/design/X.md", ChangeType.ADD)))
        ),  # case duplicate
    ],
)
def test_invalid_scope_fails_closed(scenario: Scenario, scope: object) -> None:
    diff = scenario.diff(lambda r: r.write("docs/design/x.md", "x\n"))
    result = compare_scope(scope, diff)
    assert (result.valid_input, result.has_drift, result.approval_valid) == (False, True, False)
    assert result.reasons == (INVALID_SCOPE,)
    assert result.expected == result.actual == ()


def _actual_cases(diff: GitDiff) -> list[object]:
    change = diff.changes[0]
    entry = diff.entries[0]
    renamed = ChangeFacts(
        change=change.change,
        new_kind=K.REGULAR_FILE,
        binary=False,
        mode_change=False,
        renamed_from=_vp("docs/design/b.md", ChangeType.DELETE),
    )
    return [
        None,
        "diff",
        dataclasses.replace(diff, changes=list(diff.changes)),  # type: ignore[arg-type]
        dataclasses.replace(diff, changed_files=diff.changed_files + 1),
        dataclasses.replace(diff, entries=diff.entries[1:]),
        dataclasses.replace(
            diff,
            changes=(diff.changes[0], diff.changes[0]),
            entries=(entry, entry),
            changed_files=2,
        ),  # duplicate
        dataclasses.replace(diff, changes=("docs/x.md",)),  # type: ignore[arg-type]
        dataclasses.replace(diff, entries=(dataclasses.replace(entry, status="M"),)),
        dataclasses.replace(diff, entries=(dataclasses.replace(entry, new_path="docs/y.md"),)),
        dataclasses.replace(
            diff,
            changes=(dataclasses.replace(change, change=_vp("docs/../x.md", ChangeType.ADD)),),
        ),
        dataclasses.replace(diff, changes=(renamed,)),  # rename metadata with an "A" record
        dataclasses.replace(
            diff,
            changes=(
                dataclasses.replace(change, change=_vp("docs/design/x.md", ChangeType.MODIFY)),
            ),
        ),
    ]


def test_invalid_actual_metadata_fails_closed(scenario: Scenario) -> None:
    diff = scenario.diff(lambda r: r.write("docs/design/x.md", "x\n"))
    scope = approve_scope([("add", "docs/design/x.md")], scenario.index)
    assert compare_scope(scope, diff).has_drift is False
    for forged in _actual_cases(diff):
        result = compare_scope(scope, forged)
        assert (result.valid_input, result.has_drift, result.approval_valid) == (
            False,
            True,
            False,
        )
        assert result.reasons == (INVALID_ACTUAL,)


def test_invalid_rename_metadata_in_actual_diff(scenario: Scenario) -> None:
    diff = scenario.diff(lambda r: r.git("mv", "docs/design/c.md", "docs/design/c2.md"))
    scope = approve_scope([("rename", "docs/design/c.md", "docs/design/c2.md")], scenario.index)
    assert compare_scope(scope, diff).has_drift is False
    (change,) = diff.changes
    assert change.renamed_from is not None
    forged = [
        dataclasses.replace(
            change, renamed_from=dataclasses.replace(change.renamed_from, change=ChangeType.ADD)
        ),
        dataclasses.replace(change, renamed_from=change.change),  # source == target
        dataclasses.replace(change, renamed_from=None),  # "R" record without a source
    ]
    for facts in forged:
        result = compare_scope(scope, dataclasses.replace(diff, changes=(facts,)))
        assert result.reasons == (INVALID_ACTUAL,)
    entry = diff.entries[0]
    wrong_source = dataclasses.replace(entry, old_path="docs/design/d.md")
    result = compare_scope(scope, dataclasses.replace(diff, entries=(wrong_source,)))
    assert result.reasons == (INVALID_ACTUAL,)


# --------------------------------------------------------- risk integration


def _effective(scenario: Scenario, plan: Sequence[object], mutate: object) -> tuple[object, ...]:
    diff = scenario.diff(mutate)
    assessment = assess(diff)
    drift = compare_scope(approve_scope(plan, scenario.index), diff)
    return diff, assessment, drift, apply_scope_drift(diff, assessment, drift)


def test_no_drift_keeps_l1_and_approval(scenario: Scenario) -> None:
    _diff, assessment, _drift, effective = _effective(
        scenario, [("modify", "docs/design/a.md")], lambda r: r.write("docs/design/a.md", "c\n")
    )
    assert assessment.level is L1  # type: ignore[attr-defined]
    assert effective.effective_level is L1  # type: ignore[attr-defined]
    assert effective.previous_approval_valid is True  # type: ignore[attr-defined]
    assert effective.fresh_approval_required is False  # type: ignore[attr-defined]
    assert effective.reasons == ()  # type: ignore[attr-defined]


def test_drift_raises_l1_to_l2_and_requires_fresh_approval(scenario: Scenario) -> None:
    def two_docs(repo: Repo) -> None:
        repo.write("docs/design/a.md", "c\n")
        repo.write("docs/design/d.md", "c\n")

    _diff, assessment, drift, effective = _effective(
        scenario, [("modify", "docs/design/a.md")], two_docs
    )
    assert assessment.level is L1  # type: ignore[attr-defined]
    assert drift.has_drift is True  # type: ignore[attr-defined]
    assert effective.actual_level is L1  # type: ignore[attr-defined]
    assert effective.effective_level is L2  # type: ignore[attr-defined]
    assert effective.scope_drift is True  # type: ignore[attr-defined]
    assert effective.previous_approval_valid is False  # type: ignore[attr-defined]
    assert effective.fresh_approval_required is True  # type: ignore[attr-defined]
    assert effective.reasons == ("scope_drift", "scope_risk_floor")  # type: ignore[attr-defined]
    assert effective.assessment is assessment  # type: ignore[attr-defined]
    assert assessment.level is L1  # the RiskAssessment itself is unchanged  # type: ignore[attr-defined]


def test_drift_keeps_l2_and_l3(scenario: Scenario) -> None:
    def delete_and_touch(repo: Repo) -> None:
        repo.remove("docs/design/b.md")
        repo.write("docs/design/a.md", "c\n")

    _d, assessment, _dr, effective = _effective(
        scenario, [("delete", "docs/design/b.md")], delete_and_touch
    )
    assert (assessment.level, effective.effective_level) == (L2, L2)  # type: ignore[attr-defined]
    assert effective.reasons == ("scope_drift",)  # type: ignore[attr-defined]


def test_drift_with_l3_actual_stays_l3(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "repo")
    repo.write("docs/legal/terms.md", "legal\n")
    repo.write("docs/design/a.md", "a\n")
    base = repo.commit()
    index = RepoIndex.from_git(repo.root)
    repo.git("mv", "docs/legal/terms.md", "docs/design/terms.md")
    repo.write("docs/design/a.md", "c\n")
    diff = diff_commits(repo.root, base, repo.commit())
    assessment = assess(diff)
    drift = compare_scope(approve_scope([("modify", "docs/design/a.md")], index), diff)
    effective = apply_scope_drift(diff, assessment, drift)
    assert (assessment.level, effective.effective_level, drift.has_drift) == (L3, L3, True)


def test_no_integration_path_lowers_the_actual_level(scenario: Scenario) -> None:
    diff = scenario.diff(lambda r: r.write("docs/design/a.md", "c\n"))
    real = assess(diff)
    scopes: list[object] = [
        approve_scope([("modify", "docs/design/a.md")], scenario.index),  # no drift
        approve_scope([("delete", "docs/design/a.md")], scenario.index),  # drift
        "forged",  # invalid comparison
    ]
    for level in RiskLevel:
        assessment = dataclasses.replace(real, level=level)
        for scope in scopes:
            drift = compare_scope(scope, diff)
            effective = apply_scope_drift(diff, assessment, drift)
            assert effective.effective_level >= level
            assert effective.actual_level is level
            if drift.has_drift:
                assert effective.effective_level >= L2
                assert effective.fresh_approval_required is True


def test_invalid_comparison_never_preserves_approval(scenario: Scenario) -> None:
    diff = scenario.diff(lambda r: r.write("docs/design/a.md", "c\n"))
    assessment = assess(diff)
    effective = apply_scope_drift(diff, assessment, compare_scope(None, diff))
    assert effective.scope_comparison_valid is False
    assert effective.previous_approval_valid is False
    assert effective.fresh_approval_required is True
    assert effective.effective_level is L3  # unknown scope
    assert effective.reasons == ("invalid_scope_comparison", "scope_risk_floor")


def test_no_drift_is_not_an_authorisation(scenario: Scenario) -> None:
    # Empty plan and empty diff: no drift, but the Risk Policy still says
    # "not executable" (empty change set) and the flag is passed through.
    diff = diff_commits(scenario.repo.root, scenario.base, scenario.base)
    assessment = assess(diff)
    effective = apply_scope_drift(diff, assessment, compare_scope(ApprovedScope(()), diff))
    assert effective.previous_approval_valid is True
    assert effective.policy_executable is False
    assert effective.effective_level is L3
    field_names = {f.name for f in dataclasses.fields(effective)}
    assert not field_names & {"authorized", "approved", "merge_allowed", "execute"}


def test_mismatched_inputs_are_rejected(scenario: Scenario) -> None:
    diff = scenario.diff(lambda r: r.write("docs/design/a.md", "c\n"))
    other = diff_commits(scenario.repo.root, scenario.base, scenario.base)
    assessment = assess(diff)
    drift = compare_scope(approve_scope([("modify", "docs/design/a.md")], scenario.index), diff)
    with pytest.raises(ScopeError) as info:
        apply_scope_drift(other, assessment, drift)
    assert info.value.code is ScopeErrorCode.INCONSISTENT_INPUTS
    with pytest.raises(ScopeError):
        apply_scope_drift(diff, assess(other), drift)
    with pytest.raises(ScopeError):
        apply_scope_drift(diff, assessment, compare_scope(ApprovedScope(()), other))
    with pytest.raises(ScopeError):
        apply_scope_drift(diff, assessment, dataclasses.replace(drift, approval_valid=False))
    with pytest.raises(ScopeError):
        apply_scope_drift(diff, "assessment", drift)  # type: ignore[arg-type]
    with pytest.raises(ScopeError):
        actual_entries("diff")


# ------------------------------------------------ determinism and immutability


def test_repeated_comparisons_are_identical_and_inputs_unchanged(scenario: Scenario) -> None:
    diff = scenario.diff(standard_change)
    plan = [item for item in STANDARD_PLAN if item[0] != "delete"]
    scope = approve_scope(plan, scenario.index)
    scope_copy, diff_copy = copy.deepcopy(scope), copy.deepcopy(diff)
    first = compare_scope(scope, diff)
    assert all(compare_scope(scope, diff) == first for _ in range(5))
    assert (scope, diff) == (scope_copy, diff_copy)
    assert first.reasons == tuple(sorted(first.reasons))
    assert first.unexpected_paths == tuple(sorted(first.unexpected_paths))
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.has_drift = False  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.expected[0].target = "x"  # type: ignore[misc]
    effective = apply_scope_drift(diff, assess(diff), first)
    with pytest.raises(dataclasses.FrozenInstanceError):
        effective.effective_level = L1  # type: ignore[misc]


def test_reason_codes_do_not_depend_on_ordering(scenario: Scenario) -> None:
    diff = scenario.diff(standard_change)
    plan = [("delete", "docs/design/a.md"), ("modify", "docs/design/d.md")]
    results = {
        compare_scope(approve_scope(order, scenario.index), shuffled)
        for order in (plan, plan[::-1])
        for shuffled in (
            diff,
            dataclasses.replace(diff, changes=diff.changes[::-1], entries=diff.entries[::-1]),
        )
    }
    assert len(results) == 1


def test_diff_entries_are_real_audit_records(scenario: Scenario) -> None:
    diff = scenario.diff(standard_change)
    assert all(isinstance(entry, DiffEntry) for entry in diff.entries)
