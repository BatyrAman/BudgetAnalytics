"""Tests for orchestrator.approval (T3.3, hardened in T3.3.2). Offline; temporary repos only."""

from __future__ import annotations

import builtins
import dataclasses
import inspect
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from orchestrator.approval import (
    BASE_COMMIT_MISMATCH,
    FILE_COUNT_EXCEEDS_APPROVAL,
    INCONSISTENT_INPUTS,
    INVALID_BINDING,
    LINE_COUNT_EXCEEDS_APPROVAL,
    POLICY_VERSION_MISMATCH,
    RISK_EXCEEDS_APPROVAL,
    SCOPE_DRIFT,
    TARGET_COMMIT_MISMATCH,
    ApprovalBinding,
    ApprovalError,
    ApprovalValidation,
    bind_approval,
    validate_approval,
)
from orchestrator.git_diff import DiffEntry, GitDiff, diff_commits
from orchestrator.paths import RepoIndex, ValidatedPath
from orchestrator.risk_policy import (
    DEFAULT_POLICY_PATH,
    ChangeFacts,
    Pattern,
    RiskEvaluationError,
    RiskLevel,
    RiskPolicy,
    evaluate,
    is_valid_policy,
    is_valid_policy_version,
    load_policy,
    parse_policy,
)
from orchestrator.scope_drift import ApprovedScope, PlannedChange, ScopeOperation, approve_scope

L1, L2, L3 = RiskLevel.L1, RiskLevel.L2, RiskLevel.L3
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
class Review:
    diff: GitDiff
    scope: ApprovedScope
    binding: ApprovalBinding


class World:
    def __init__(self, root: Path) -> None:
        self.repo = Repo(root)
        for name in ("a", "b", "c"):
            self.repo.write(f"docs/design/{name}.md", f"{name}\n")
        self.repo.write("docs/legal/terms.md", "legal\n")
        self.base = self.repo.commit()
        self.index = RepoIndex.from_git(self.repo.root)

    def diff(self, mutate: Callable[[Repo], object]) -> GitDiff:
        mutate(self.repo)
        return diff_commits(self.repo.root, self.base, self.repo.commit())

    def review(
        self, plan: Sequence[object], mutate: Callable[[Repo], object], **overrides: Any
    ) -> Review:
        return self.review_diff(plan, self.diff(mutate), **overrides)

    def review_diff(self, plan: Sequence[object], diff: GitDiff, **overrides: Any) -> Review:
        scope = approve_scope(plan, self.index)
        fields: dict[str, Any] = {
            "scope": scope,
            "approved_level": L3,
            "policy_version": POLICY.policy_version,
            "approved_files": len(scope.changes),
            "approved_lines": diff.changed_lines,
            "base_commit": diff.base_commit,
            "target_commit": diff.target_commit,
        }
        fields.update(overrides)
        return Review(diff, scope, bind_approval(**fields))


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path / "repo")


def check(review: Review, **replace: Any) -> ApprovalValidation:
    parts: dict[str, Any] = {"binding": review.binding, "diff": review.diff, "policy": POLICY}
    parts.update(replace)
    result = validate_approval(parts["binding"], parts["diff"], parts["policy"])
    assert type(result) is ApprovalValidation
    return result


def forge(cls: type, **fields: object) -> Any:
    """An instance of ``cls`` built without its constructor (slots set or left unset)."""

    instance: Any = object.__new__(cls)
    for name, value in fields.items():
        object.__setattr__(instance, name, value)
    return instance


def all_fields(value: Any) -> dict[str, Any]:
    return {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}


def modify_a(repo: Repo) -> None:
    repo.write("docs/design/a.md", "changed\n")


def modify_terms(repo: Repo) -> None:
    repo.write("docs/legal/terms.md", "changed\n")


PLAN_A = [("modify", "docs/design/a.md")]
OTHER_OID = "f" * 40


class AlwaysEqual(str):
    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


class NeverDifferent(str):
    __slots__ = ()

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


# ---------------------------------------------------------------- positive


def test_unchanged_approval_is_consistent(world: World) -> None:
    review = world.review(PLAN_A, modify_a, approved_level=L1)
    result = check(review)
    assert result.binding_consistent is True
    assert result.reasons == ()
    assert (result.approved_level, result.actual_level, result.effective_level) == (L1, L1, L1)
    assert (result.approved_files, result.actual_files) == (1, 1)
    assert (result.approved_lines, result.actual_lines) == (2, 2)
    assert result.policy_version_matches and result.base_commit_matches
    assert result.target_commit_matches and not result.scope_drift
    # The assessment is recomputed from the trusted policy and the actual diff.
    assert result.assessment == evaluate(
        POLICY,
        review.diff.changes,
        changed_files=review.diff.changed_files,
        changed_lines=review.diff.changed_lines,
        expected_policy_version=POLICY.policy_version,
    )
    assert result.effective is not None
    assert result.effective.assessment == result.assessment


def test_higher_approval_covers_a_lower_effective_level(world: World) -> None:
    result = check(world.review(PLAN_A, modify_a, approved_level=L3))
    assert (result.binding_consistent, result.effective_level) == (True, L1)


def test_rename_counts_follow_the_adapter(world: World) -> None:
    review = world.review(
        [("rename", "docs/design/c.md", "docs/design/c2.md")],
        lambda r: r.git("mv", "docs/design/c.md", "docs/design/c2.md"),
    )
    assert (review.binding.approved_files, review.binding.approved_lines) == (1, 0)
    result = check(review)
    assert (result.binding_consistent, result.actual_files, result.actual_lines) == (True, 1, 0)


def test_api_accepts_no_precomputed_results() -> None:
    assert list(inspect.signature(validate_approval).parameters) == ["binding", "diff", "policy"]


# ------------------------------------------------- F1: drift is recomputed


def test_f1_same_file_count_with_an_unapproved_path(world: World) -> None:
    def a_and_terms(repo: Repo) -> None:
        modify_a(repo)
        modify_terms(repo)

    plan = [("modify", "docs/design/a.md"), ("modify", "docs/design/b.md")]
    result = check(world.review(plan, a_and_terms))
    assert result.binding_consistent is False
    assert result.reasons == (SCOPE_DRIFT,)
    assert result.effective is not None
    assert result.effective.drift.unexpected_paths == ("docs/legal/terms.md",)
    assert result.effective.drift.missing_paths == ("docs/design/b.md",)


def test_f1_missing_approved_path(world: World) -> None:
    plan = [("modify", "docs/design/a.md"), ("modify", "docs/design/c.md")]
    result = check(world.review(plan, modify_a))
    assert result.reasons == (SCOPE_DRIFT,)
    assert result.effective is not None
    assert result.effective.drift.missing_paths == ("docs/design/c.md",)


def test_f1_operation_mismatch(world: World) -> None:
    result = check(world.review([("delete", "docs/design/a.md")], modify_a))
    assert result.reasons == (SCOPE_DRIFT,)
    assert result.effective is not None
    assert result.effective.drift.operation_mismatches[0].path == "docs/design/a.md"


def test_f1_rename_semantics(world: World) -> None:
    def edited_rename(repo: Repo) -> None:
        repo.remove("docs/design/c.md")
        repo.write("docs/design/c2.md", "different\n")

    review = world.review(
        [("rename", "docs/design/c.md", "docs/design/c2.md")], edited_rename, approved_lines=2
    )
    result = check(review)
    # The diff is a delete plus an add (two files), never the approved rename.
    assert result.reasons == (FILE_COUNT_EXCEEDS_APPROVAL, SCOPE_DRIFT)


def test_f1_drift_invalidates_even_within_the_approved_level(world: World) -> None:
    def two_files(repo: Repo) -> None:
        modify_a(repo)
        repo.write("docs/design/b.md", "changed\n")

    result = check(world.review(PLAN_A, two_files, approved_level=L2, approved_lines=4))
    assert result.effective_level is L2  # within the approved level ...
    assert result.binding_consistent is False  # ... still not consistent
    assert result.reasons == (FILE_COUNT_EXCEEDS_APPROVAL, SCOPE_DRIFT)


# -------------------------------------------- F2: assessment is recomputed


@pytest.mark.parametrize(
    ("approved", "plan", "mutate", "actual"),
    [
        (L1, [("delete", "docs/design/b.md")], lambda r: r.remove("docs/design/b.md"), L2),
        (L1, [("modify", "docs/legal/terms.md")], modify_terms, L3),
        (L2, [("modify", "docs/legal/terms.md")], modify_terms, L3),
    ],
    ids=["L1->L2", "L1->L3", "L2->L3"],
)
def test_f2_lower_approval_never_covers_higher_risk(
    world: World,
    approved: RiskLevel,
    plan: list[object],
    mutate: Callable[[Repo], object],
    actual: RiskLevel,
) -> None:
    result = check(world.review(plan, mutate, approved_level=approved))
    assert result.reasons == (RISK_EXCEEDS_APPROVAL,)
    assert (result.approved_level, result.effective_level) == (approved, actual)


def test_f2_real_l3_diff_cannot_validate_under_l1(world: World) -> None:
    def a_and_terms(repo: Repo) -> None:
        modify_a(repo)
        modify_terms(repo)

    plan = [("modify", "docs/design/a.md"), ("modify", "docs/legal/terms.md")]
    result = check(world.review(plan, a_and_terms, approved_level=L1))
    assert result.reasons == (RISK_EXCEEDS_APPROVAL,)
    assert result.assessment is not None
    assert [p.level for p in result.assessment.paths] == [L1, L3]


def test_f2_correct_policy_positive_control(world: World) -> None:
    result = check(world.review([("modify", "docs/legal/terms.md")], modify_terms))
    assert (result.binding_consistent, result.effective_level) == (True, L3)


def test_f2_binding_with_nonexistent_policy_version(world: World) -> None:
    result = check(world.review(PLAN_A, modify_a, policy_version="9.9.9"))
    assert result.reasons == (POLICY_VERSION_MISMATCH,)


def test_f2_policy_object_with_a_different_version(world: World) -> None:
    other = dataclasses.replace(POLICY, policy_version="0.5.1-draft")
    assert is_valid_policy(other)
    result = check(world.review(PLAN_A, modify_a), policy=other)
    assert result.reasons == (POLICY_VERSION_MISMATCH,)
    assert result.policy_version_matches is False


def test_f2_the_supplied_policy_is_what_classifies_the_diff(world: World) -> None:
    text = DEFAULT_POLICY_PATH.read_text()
    stricter_text = text.replace('id = "l1.docs"\nlevel = "L1"', 'id = "l3.docs_all"\nlevel = "L3"')
    assert stricter_text != text
    stricter = parse_policy(stricter_text)
    assert stricter.policy_version == POLICY.policy_version
    review = world.review(PLAN_A, modify_a, approved_level=L1)
    assert check(review).binding_consistent is True
    result = check(review, policy=stricter)
    assert (result.reasons, result.effective_level) == ((RISK_EXCEEDS_APPROVAL,), L3)


def _malformed_policies() -> list[tuple[str, object]]:
    rule = POLICY.rules[0]
    bad_pattern = dataclasses.replace(rule.patterns[0], segments=("**",))
    rule_level_int = forge(type(rule), **{**all_fields(rule), "level": 3})
    return [
        ("none", None),
        ("string", "policy"),
        ("unset slots", forge(RiskPolicy)),
        ("partly set", forge(RiskPolicy, policy_version=POLICY.policy_version)),
        ("unclassified L1", dataclasses.replace(POLICY, unclassified_level=L1)),
        ("forbidden L2", dataclasses.replace(POLICY, forbidden_level=L2)),
        (
            "symlink rule L1",
            dataclasses.replace(
                POLICY, change_rules=dataclasses.replace(POLICY.change_rules, symlink=L1)
            ),
        ),
        (
            "limits inverted",
            dataclasses.replace(POLICY, limits=dataclasses.replace(POLICY.limits, l1_max_files=99)),
        ),
        ("rules list", dataclasses.replace(POLICY, rules=list(POLICY.rules))),  # type: ignore[arg-type]
        ("no rules", dataclasses.replace(POLICY, rules=())),
        ("rule level int", dataclasses.replace(POLICY, rules=(rule_level_int,))),
        (
            "pattern text and segments disagree",
            dataclasses.replace(
                POLICY,
                rules=(dataclasses.replace(rule, patterns=(bad_pattern,)), *POLICY.rules[1:]),
            ),
        ),
        (
            "version str subclass",
            dataclasses.replace(POLICY, policy_version=AlwaysEqual(POLICY.policy_version)),
        ),
        ("version with newline", dataclasses.replace(POLICY, policy_version="0.5.0-draft\n")),
    ]


MALFORMED_POLICIES = _malformed_policies()


@pytest.mark.parametrize(
    ("name", "policy"), MALFORMED_POLICIES, ids=[case[0] for case in MALFORMED_POLICIES]
)
def test_f2_malformed_policy_objects_are_inconsistent_inputs(
    world: World, name: str, policy: object
) -> None:
    assert is_valid_policy(policy) is False, name
    result = check(world.review(PLAN_A, modify_a), policy=policy)
    assert (result.binding_consistent, result.reasons) == (False, (INCONSISTENT_INPUTS,))
    assert result.assessment is None and result.effective is None


def test_f2_evaluate_itself_rejects_malformed_policies() -> None:
    with pytest.raises(RiskEvaluationError):
        evaluate(
            dataclasses.replace(POLICY, unclassified_level=L1),
            [],
            changed_files=0,
            changed_lines=0,
            expected_policy_version=POLICY.policy_version,
        )


def test_policy_helpers() -> None:
    assert is_valid_policy(POLICY) is True
    assert is_valid_policy(dataclasses.replace(POLICY, rules=tuple(reversed(POLICY.rules))))
    assert is_valid_policy_version("0.5.0-draft") is True
    for value in (
        "0.5.0-draft\n",
        "",
        "v1",
        None,
        5,
        AlwaysEqual("1.0.0"),
        NeverDifferent("1.0.0"),
    ):
        assert is_valid_policy_version(value) is False


def test_pattern_flags_are_part_of_policy_validation() -> None:
    rule = POLICY.rules[0]
    twisted = dataclasses.replace(rule.patterns[0], case_insensitive=False)
    assert type(twisted) is Pattern
    altered = dataclasses.replace(
        POLICY,
        rules=(
            dataclasses.replace(rule, patterns=(twisted, *rule.patterns[1:])),
            *POLICY.rules[1:],
        ),
    )
    assert is_valid_policy(altered) is False


# ------------------------------------------------ F3/F5: structural checks


def _diff_forgeries(diff: GitDiff) -> list[tuple[str, object]]:
    change, entry = diff.changes[0], diff.entries[0]
    path = change.change

    def with_change(**fields: Any) -> GitDiff:
        return dataclasses.replace(diff, changes=(dataclasses.replace(change, **fields),))

    def with_entry(**fields: Any) -> GitDiff:
        return dataclasses.replace(diff, entries=(dataclasses.replace(entry, **fields),))

    subclass_path = dataclasses.replace(path, path=AlwaysEqual(path.path))
    return [
        ("none", None),
        ("string", "diff"),
        ("unset slots", forge(GitDiff)),
        ("partly set", forge(GitDiff, base_commit=diff.base_commit)),
        ("changes list", dataclasses.replace(diff, changes=list(diff.changes))),  # type: ignore[arg-type]
        ("change int", dataclasses.replace(diff, changes=(1,))),  # type: ignore[arg-type]
        ("entry str", dataclasses.replace(diff, entries=("M",))),  # type: ignore[arg-type]
        ("ChangeFacts unset", dataclasses.replace(diff, changes=(forge(ChangeFacts),))),
        ("DiffEntry unset", dataclasses.replace(diff, entries=(forge(DiffEntry),))),
        ("ValidatedPath unset", with_change(change=forge(ValidatedPath))),
        ("path str subclass", with_change(change=subclass_path)),
        ("new_kind str", with_change(new_kind="regular_file")),
        ("binary int", with_change(binary=1)),
        ("status int", with_entry(status=1)),
        ("added lines str", with_entry(added_lines="1")),
        ("added lines bool", with_entry(added_lines=True)),
        ("negative entry lines", with_entry(added_lines=-1, deleted_lines=3)),
        ("binary disagrees", with_entry(binary=True)),
        ("mode change disagrees", with_entry(mode_change=True)),
        ("old path int", with_entry(old_path=1)),
        ("changed_lines str", dataclasses.replace(diff, changed_lines="2")),  # type: ignore[arg-type]
        ("changed_lines bool", dataclasses.replace(diff, changed_lines=True)),
        ("changed_lines negative", dataclasses.replace(diff, changed_lines=-2)),
        ("changed_files negative", dataclasses.replace(diff, changed_files=-1)),
        ("changed_files bool", dataclasses.replace(diff, changed_files=True)),
        ("changed_lines inconsistent", dataclasses.replace(diff, changed_lines=1)),
        ("changed_files inconsistent", dataclasses.replace(diff, changed_files=2)),
        ("base commit short", dataclasses.replace(diff, base_commit="abc1234")),
        ("target commit branch", dataclasses.replace(diff, target_commit="main")),
        ("commit lengths differ", dataclasses.replace(diff, target_commit="b" * 64)),
        (
            "base commit __eq__ subclass",
            dataclasses.replace(diff, base_commit=AlwaysEqual(diff.base_commit)),
        ),
        (
            "target commit __ne__ subclass",
            dataclasses.replace(diff, target_commit=NeverDifferent(diff.target_commit)),
        ),
    ]


def test_f3_f5_malformed_diffs_never_raise(world: World) -> None:
    review = world.review(PLAN_A, modify_a)
    assert check(review).binding_consistent is True
    for name, forged in _diff_forgeries(review.diff):
        result = check(review, diff=forged)
        assert (result.binding_consistent, result.reasons) == (False, (INCONSISTENT_INPUTS,)), name
        assert result.effective is None and result.assessment is None, name


def test_f3_malformed_bindings_never_raise(world: World) -> None:
    review = world.review(PLAN_A, modify_a)
    binding = review.binding
    target = review.scope.changes[0].target
    cases: list[tuple[str, object]] = [
        ("none", None),
        ("dict", all_fields(binding)),
        ("unset slots", forge(ApprovalBinding)),
        ("partly set", forge(ApprovalBinding, approved_level=L3)),
        ("scope unset", dataclasses.replace(binding, scope=forge(ApprovedScope))),
        (
            "scope changes list",
            dataclasses.replace(
                binding, scope=forge(ApprovedScope, changes=list(review.scope.changes))
            ),
        ),
        (
            "planned change unset",
            dataclasses.replace(binding, scope=ApprovedScope((forge(PlannedChange),))),
        ),
        (
            "planned target str",
            dataclasses.replace(
                binding,
                scope=ApprovedScope((PlannedChange(ScopeOperation.MODIFY, "docs/design/a.md"),)),  # type: ignore[arg-type]
            ),
        ),
        (
            "planned operation str",
            dataclasses.replace(
                binding,
                scope=ApprovedScope(
                    (forge(PlannedChange, operation="modify", target=target, source=None),)
                ),
            ),
        ),
        (
            "planned path unset",
            dataclasses.replace(
                binding,
                scope=ApprovedScope((PlannedChange(ScopeOperation.MODIFY, forge(ValidatedPath)),)),
            ),
        ),
        ("scope element int", dataclasses.replace(binding, scope=ApprovedScope((1,)))),  # type: ignore[arg-type]
        ("level int", dataclasses.replace(binding, approved_level=1)),  # type: ignore[arg-type]
        ("files bool", dataclasses.replace(binding, approved_files=True)),
        ("lines negative", dataclasses.replace(binding, approved_lines=-1)),
        ("lines str", dataclasses.replace(binding, approved_lines="2")),  # type: ignore[arg-type]
    ]
    for name, forged in cases:
        result = check(review, binding=forged)
        assert (result.binding_consistent, result.reasons) == (False, (INVALID_BINDING,)), name
        assert result.approved_level is None, name


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_commit", "abc1234"),
        ("base_commit", "main"),
        ("base_commit", "refs/heads/main"),
        ("base_commit", "HEAD"),
        ("base_commit", "A" * 40),
        ("base_commit", "a" * 39),
        ("base_commit", "a" * 41),
        ("base_commit", "a" * 40 + "\n"),
        ("base_commit", None),
        ("target_commit", "abc1234"),
        ("target_commit", "b" * 64),
        ("approved_level", 1),
        ("approved_level", "L1"),
        ("approved_level", True),
        ("policy_version", ""),
        ("policy_version", "0.5.0-draft\n"),
        ("policy_version", 5),
        ("approved_files", -1),
        ("approved_files", True),
        ("approved_files", 2),  # the scope has one change
        ("approved_lines", -1),
        ("approved_lines", "2"),
        ("approved_lines", 10_000_001),
        ("scope", None),
        ("scope", "docs/design/a.md"),
    ],
)
def test_invalid_binding_fields_are_rejected(world: World, field: str, value: object) -> None:
    review = world.review(PLAN_A, modify_a)
    fields = all_fields(review.binding)
    fields[field] = value
    with pytest.raises(ApprovalError) as info:
        bind_approval(**fields)
    assert info.value.field == field
    if isinstance(value, str) and value.strip():
        assert value.strip() not in str(info.value)
    forged = dataclasses.replace(review.binding, **{field: value})  # type: ignore[arg-type]
    assert check(review, binding=forged).reasons == (INVALID_BINDING,)


def test_empty_scope_must_bind_zero_lines(world: World) -> None:
    diff = diff_commits(world.repo.root, world.base, world.base)
    with pytest.raises(ApprovalError) as info:
        world.review_diff([], diff, approved_lines=5)
    assert info.value.field == "approved_lines"


# ------------------------------------------------ F4: exact string types


@pytest.mark.parametrize("cls", [AlwaysEqual, NeverDifferent])
@pytest.mark.parametrize("field", ["base_commit", "target_commit", "policy_version"])
def test_f4_str_subclasses_are_rejected(world: World, cls: type[str], field: str) -> None:
    review = world.review(PLAN_A, modify_a)
    wrong = {"base_commit": "0" * 40, "target_commit": "1" * 40, "policy_version": "1.0.0"}[field]
    fields = all_fields(review.binding)
    fields[field] = cls(wrong)
    with pytest.raises(ApprovalError) as info:
        bind_approval(**fields)
    assert info.value.field == field
    forged = dataclasses.replace(review.binding, **{field: cls(wrong)})  # type: ignore[arg-type]
    assert check(review, binding=forged).reasons == (INVALID_BINDING,)


# ------------------------------------------------ F6: exact input types


def test_f6_binding_subclass_with_property_is_rejected_unread(world: World) -> None:
    review = world.review(PLAN_A, modify_a, approved_level=L1)
    reads = {"count": 0}

    class Flipping(ApprovalBinding):
        __slots__ = ()

    def level(_self: object) -> RiskLevel:
        reads["count"] += 1
        return L3 if reads["count"] > 1 else L1

    Flipping.approved_level = property(level)  # type: ignore[assignment,misc]
    fields = {k: v for k, v in all_fields(review.binding).items() if k != "approved_level"}
    result = check(review, binding=forge(Flipping, **fields))
    assert result.reasons == (INVALID_BINDING,)
    assert reads["count"] == 0


def test_f6_subclasses_of_inputs_are_rejected(world: World) -> None:
    review = world.review(PLAN_A, modify_a)

    class SubDiff(GitDiff):
        __slots__ = ()

    class SubPolicy(RiskPolicy):
        __slots__ = ()

    class SubPath(ValidatedPath):
        __slots__ = ()

    assert check(review, diff=SubDiff(**all_fields(review.diff))).reasons == (INCONSISTENT_INPUTS,)
    assert check(review, policy=SubPolicy(**all_fields(POLICY))).reasons == (INCONSISTENT_INPUTS,)
    change = review.diff.changes[0]
    sub_path = SubPath(**all_fields(change.change))
    diff = dataclasses.replace(review.diff, changes=(dataclasses.replace(change, change=sub_path),))
    assert check(review, diff=diff).reasons == (INCONSISTENT_INPUTS,)


def test_f6_binding_fields_are_read_once(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    review = world.review(PLAN_A, modify_a)
    reads: dict[str, int] = {}
    original = object.__getattribute__

    def counting(self: object, name: str) -> object:
        reads[name] = reads.get(name, 0) + 1
        return original(self, name)

    monkeypatch.setattr(ApprovalBinding, "__getattribute__", counting, raising=False)
    assert check(review).binding_consistent is True
    for name in (
        "approved_level",
        "policy_version",
        "approved_files",
        "approved_lines",
        "base_commit",
        "target_commit",
        "scope",
    ):
        assert reads.get(name) == 1, (name, reads)


# ------------------------------------------------------ remaining contract


def test_mismatches_and_their_order(world: World) -> None:
    review = world.review(
        PLAN_A,
        modify_a,
        base_commit=OTHER_OID,
        target_commit="e" * 40,
        policy_version="0.1.0",
        approved_lines=0,
    )
    first = check(review)
    assert first.reasons == (
        BASE_COMMIT_MISMATCH,
        LINE_COUNT_EXCEEDS_APPROVAL,
        POLICY_VERSION_MISMATCH,
        TARGET_COMMIT_MISMATCH,
    )
    assert all(check(review) == first for _ in range(5))


def test_empty_diff(world: World) -> None:
    diff = diff_commits(world.repo.root, world.base, world.base)
    review = world.review_diff([], diff)
    result = check(review)
    # Consistent, but the empty change set is L3 and not executable.
    assert (result.binding_consistent, result.effective_level, result.policy_executable) == (
        True,
        L3,
        False,
    )
    lower = dataclasses.replace(review.binding, approved_level=L1)
    assert check(review, binding=lower).reasons == (RISK_EXCEEDS_APPROVAL,)


def test_f7_no_authorisation_semantics(world: World) -> None:
    result = check(world.review(PLAN_A, modify_a))
    names = {f.name for f in dataclasses.fields(result)}
    assert "binding_consistent" in names and "valid" not in names
    assert not names & {"authorized", "authorised", "approved", "merge_allowed", "execute"}


def test_results_are_immutable_and_inputs_unchanged(world: World) -> None:
    review = world.review(PLAN_A, modify_a)
    before = (all_fields(review.binding), all_fields(review.diff))
    result = check(review)
    assert (all_fields(review.binding), all_fields(review.diff)) == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.binding_consistent = False  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        review.binding.approved_level = L1  # type: ignore[misc]


def test_validation_is_pure(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    review = world.review(PLAN_A, modify_a)
    expected = check(review)

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("validation must not touch processes or files")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    assert check(review) == expected
