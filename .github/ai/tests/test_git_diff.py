"""Tests for orchestrator.git_diff (T3.1). Offline; temporary Git repositories only."""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from orchestrator import git_diff as git_diff_module
from orchestrator.git_diff import (
    GitDiff,
    GitDiffError,
    GitDiffErrorCode,
    NumstatEntry,
    RawEntry,
    build_diff,
    diff_commits,
    parse_numstat,
    parse_raw_diff,
    parse_tree,
)
from orchestrator.paths import ChangeType, EntryKind, RepoIndex, validate_changes
from orchestrator.risk_policy import (
    MAX_CHANGED_LINES,
    ChangeFacts,
    RiskAssessment,
    RiskLevel,
    evaluate,
    load_policy,
)

G = GitDiffErrorCode
K = EntryKind
L1, L2, L3 = RiskLevel.L1, RiskLevel.L2, RiskLevel.L3
POLICY = load_policy()
GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(GIT is None, reason="git is not installed")

Z40 = "0" * 40
A40 = "a" * 40
B40 = "b" * 40


# ------------------------------------------------------------------ helpers


class Repo:
    """A throw-away repository with deterministic commits."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True)
        self.git("init", "-q")

    def git(self, *args: str) -> str:
        argv = [GIT or "git", "-C", str(self.root), *args]
        result = subprocess.run(argv, check=True, capture_output=True)  # noqa: S603 - test argv
        return result.stdout.decode()

    def write(self, path: str, content: str | bytes = "x\n") -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)

    def remove(self, path: str) -> None:
        (self.root / path).unlink()

    def symlink(self, path: str, target: str) -> None:
        link = self.root / path
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)

    def chmod(self, path: str, mode: int) -> None:
        (self.root / path).chmod(mode)

    def gitlink(self, path: str, oid: str) -> None:
        self.git("update-index", "--add", "--cacheinfo", f"160000,{oid},{path}")

    def commit(self, *paths: str) -> str:
        if paths:
            self.git("add", "--", *paths)
        else:
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


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path / "repo")


def diff_error(call: Callable[[], object]) -> GitDiffError:
    with pytest.raises(GitDiffError) as info:
        call()
    return info.value


def assess(diff: GitDiff) -> RiskAssessment:
    return evaluate(
        POLICY,
        diff.changes,
        changed_files=diff.changed_files,
        changed_lines=diff.changed_lines,
        expected_policy_version=POLICY.policy_version,
    )


def base_repo(repo: Repo) -> str:
    repo.write("docs/design/a.md", "one\ntwo\n")
    repo.write("docs/design/keep.md", "keep\n")
    repo.write("docs/legal/terms.md", "legal\n")
    repo.write("backend/app/main.py", "print(1)\n")
    return repo.commit()


# -------------------------------------------------------- commit comparison


def test_add_modify_delete_between_two_commits(repo: Repo) -> None:
    base = base_repo(repo)
    repo.write("docs/design/a.md", "one\nTWO\nthree\n")
    repo.write("docs/design/new.md", "n1\nn2\n")
    repo.remove("docs/design/keep.md")
    target = repo.commit()

    diff = diff_commits(repo.root, base, target)
    assert (diff.base_commit, diff.target_commit) == (base, target)
    assert [(e.status, e.old_path, e.new_path) for e in diff.entries] == [
        ("M", "docs/design/a.md", "docs/design/a.md"),
        ("D", "docs/design/keep.md", None),
        ("A", None, "docs/design/new.md"),
    ]
    assert [(c.change.path, c.change.change) for c in diff.changes] == [
        ("docs/design/a.md", ChangeType.MODIFY),
        ("docs/design/keep.md", ChangeType.DELETE),
        ("docs/design/new.md", ChangeType.ADD),
    ]
    # 2+1 modified, 1 deleted, 2 added
    assert (diff.changed_files, diff.changed_lines) == (3, 6)
    result = assess(diff)
    assert result.level is L2  # the delete
    assert result.reasons == ("delete",)


def test_refs_are_resolved_to_full_commit_ids(repo: Repo) -> None:
    base = base_repo(repo)
    repo.git("tag", "light", base)
    repo.write("docs/design/a.md", "changed\n")
    target = repo.commit()
    repo.git("branch", "feature", target)
    diff = diff_commits(repo.root, "refs/tags/light", "refs/heads/feature")
    assert (diff.base_commit, diff.target_commit) == (base, target)
    assert len(diff.base_commit) == 40


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "HEAD",
        "HEAD~1",
        "main",
        "feature",
        "@{u}",
        ":/message",
        "--output=pwned-output",
        "-p",
        "abc1234",  # abbreviated: ambiguous
        "A" * 40,  # upper-case hex
        "a" * 39,
        "a" * 41,
        "a" * 40 + "\n",
        "refs/heads/../x",
        "refs/heads/a..b",
        "refs/heads/x y",
        "refs/heads/x;rm -rf ~",
        "refs/heads/$(id)",
        "refs/heads/x.lock",
        "refs/heads/.hidden",
        "refs/heads/-x",
        "refs/heads/",
        "refs/heads//x",
        "refs/notes/commits",
        "refs/heads/x^{tree}",
        "refs/heads/x:path",
        "refs/heads/x@{1}",
        None,
        b"refs/heads/main",
        40,
    ],
)
def test_invalid_ref_syntax_is_rejected_before_git_runs(repo: Repo, ref: object) -> None:
    base = base_repo(repo)
    for args in ((ref, base), (base, ref)):
        error = diff_error(lambda a=args: diff_commits(repo.root, a[0], a[1]))  # type: ignore[misc]
        assert error.code is G.INVALID_REF
    assert not (repo.root / "pwned-output").exists()
    assert not Path("pwned-output").exists()


def test_missing_refs_and_objects(repo: Repo) -> None:
    base = base_repo(repo)
    assert diff_error(lambda: diff_commits(repo.root, "refs/heads/nope", base)).code is (
        G.REF_NOT_FOUND
    )
    assert diff_error(lambda: diff_commits(repo.root, base, "1" * 40)).code is G.REF_NOT_FOUND


def test_non_commit_objects_are_rejected(repo: Repo) -> None:
    base = base_repo(repo)
    tree = repo.git("rev-parse", f"{base}^{{tree}}").strip()
    blob = repo.git("rev-parse", f"{base}:docs/design/a.md").strip()
    repo.git("tag", "-a", "-m", "annotated", "annotated", base)
    assert diff_error(lambda: diff_commits(repo.root, tree, base)).code is G.NOT_A_COMMIT
    assert diff_error(lambda: diff_commits(repo.root, base, blob)).code is G.NOT_A_COMMIT
    assert diff_error(lambda: diff_commits(repo.root, "refs/tags/annotated", base)).code is (
        G.NOT_A_COMMIT
    )


def test_same_commit_is_an_empty_non_executable_diff(repo: Repo) -> None:
    base = base_repo(repo)
    diff = diff_commits(repo.root, base, base)
    assert diff.changes == () and diff.entries == ()
    assert (diff.changed_files, diff.changed_lines) == (0, 0)
    result = assess(diff)
    assert (result.level, result.executable, result.reasons) == (L3, False, ("empty_change_set",))


def test_working_tree_index_and_untracked_files_are_ignored(repo: Repo) -> None:
    base = base_repo(repo)
    repo.write("docs/design/a.md", "committed change\n")
    target = repo.commit()
    repo.write("docs/design/untracked.md", "u\n")
    repo.write("docs/design/keep.md", "modified in work tree\n")
    repo.write("docs/design/staged.md", "s\n")
    repo.git("add", "docs/design/staged.md")
    diff = diff_commits(repo.root, base, target)
    assert [c.change.path for c in diff.changes] == ["docs/design/a.md"]


def test_repository_root_is_validated(repo: Repo, tmp_path: Path) -> None:
    base = base_repo(repo)
    error = diff_error(lambda: diff_commits(repo.root / "docs", base, base))
    assert (error.code, error.cause) == (G.INVALID_REPOSITORY, "not_worktree_root")
    plain = tmp_path / "plain"
    plain.mkdir()
    error = diff_error(lambda: diff_commits(plain, base, base))
    assert (error.code, error.cause) == (G.INVALID_REPOSITORY, "git_failed")


# ------------------------------------------------------------- change types


def test_exact_rename_is_one_record(repo: Repo) -> None:
    base = base_repo(repo)
    repo.git("mv", "docs/design/keep.md", "docs/design/kept.md")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    (change,) = diff.changes
    assert change.change.path == "docs/design/kept.md"
    assert change.renamed_from is not None
    assert change.renamed_from.path == "docs/design/keep.md"
    assert (diff.changed_files, diff.changed_lines) == (1, 0)
    assert diff.entries[0].status == "R"
    result = assess(diff)
    assert (result.level, result.reasons) == (L2, ("rename",))


def test_rename_from_a_higher_risk_path_keeps_its_risk(repo: Repo) -> None:
    base = base_repo(repo)
    repo.git("mv", "docs/legal/terms.md", "docs/design/terms.md")
    target = repo.commit()
    result = assess(diff_commits(repo.root, base, target))
    assert result.level is L3
    assert "l3.legal" in result.matched_rules


def test_rename_with_edits_is_a_delete_plus_an_add(repo: Repo) -> None:
    base = base_repo(repo)
    repo.remove("docs/design/a.md")
    repo.write("docs/design/b.md", "one\ntwo\nthree\n")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    assert [e.status for e in diff.entries] == ["D", "A"]
    assert (diff.changed_files, diff.changed_lines) == (2, 5)
    assert assess(diff).level is L2


@pytest.mark.parametrize("operation", ["add", "modify", "delete"])
def test_binary_files_are_l3(repo: Repo, operation: str) -> None:
    repo.write("docs/design/img.bin", b"\x89PNG\x00\x01")
    base = base_repo(repo)
    if operation == "add":
        repo.write("docs/design/other.bin", b"\x00\x02")
    elif operation == "modify":
        repo.write("docs/design/img.bin", b"\x89PNG\x00\x02")
    else:
        repo.remove("docs/design/img.bin")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    (entry,) = diff.entries
    assert entry.binary is True
    assert (entry.added_lines, entry.deleted_lines) == (0, 0)
    assert diff.changed_lines == 0
    result = assess(diff)
    assert result.level is L3
    assert "binary" in result.reasons


def test_executable_bit_change_is_a_mode_change(repo: Repo) -> None:
    base = base_repo(repo)
    repo.chmod("docs/design/a.md", 0o755)
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    (entry,) = diff.entries
    assert (entry.old_mode, entry.new_mode, entry.mode_change) == ("100644", "100755", True)
    assert diff.changes[0].new_kind is K.EXECUTABLE_FILE
    result = assess(diff)
    assert result.level is L3
    assert result.reasons == ("executable_file", "mode_change")


def test_existing_executable_file_keeps_its_kind(repo: Repo) -> None:
    repo.write("docs/tools/run.sh", "echo 1\n")
    repo.chmod("docs/tools/run.sh", 0o755)
    base = base_repo(repo)
    repo.write("docs/tools/run.sh", "echo 2\n")
    repo.chmod("docs/tools/run.sh", 0o755)
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    assert diff.changes[0].change.kind is K.EXECUTABLE_FILE
    assert assess(diff).level is L2


@pytest.mark.parametrize(
    ("prepare", "path", "new_kind", "level", "reason"),
    [
        (
            lambda r: (r.write("docs/design/run.sh", "x\n"), r.chmod("docs/design/run.sh", 0o755)),
            "docs/design/run.sh",
            K.EXECUTABLE_FILE,
            L2,
            "executable_file",
        ),
        (
            lambda r: r.symlink("docs/design/link.md", "a.md"),
            "docs/design/link.md",
            K.SYMLINK,
            L3,
            "symlink",
        ),
        (
            lambda r: r.gitlink("docs/vendor/sub", "1" * 40),
            "docs/vendor/sub",
            K.SUBMODULE,
            L3,
            "submodule",
        ),
    ],
)
def test_new_special_entries_keep_their_target_kind(
    repo: Repo,
    prepare: Callable[[Repo], object],
    path: str,
    new_kind: EntryKind,
    level: RiskLevel,
    reason: str,
) -> None:
    base = base_repo(repo)
    prepare(repo)
    target = repo.commit("docs/design")  # "git add" would drop a bare gitlink
    diff = diff_commits(repo.root, base, target)
    (change,) = diff.changes
    assert (change.change.path, change.change.kind, change.new_kind) == (path, K.NEW, new_kind)
    assert change.mode_change is False
    result = assess(diff)
    assert result.level is level
    assert reason in result.reasons


def test_rename_with_mode_change_is_a_mode_change(repo: Repo) -> None:
    base = base_repo(repo)
    repo.git("mv", "docs/design/keep.md", "docs/design/kept.md")
    repo.chmod("docs/design/kept.md", 0o755)
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    (change,) = diff.changes
    assert diff.entries[0].status == "R"
    assert change.renamed_from is not None
    assert (change.renamed_from.kind, change.new_kind) == (K.REGULAR_FILE, K.EXECUTABLE_FILE)
    result = assess(diff)
    assert result.level is L3
    assert {"rename", "mode_change", "executable_file"} <= set(result.reasons)


def test_rename_into_a_symlink_is_l3(repo: Repo) -> None:
    repo.write("docs/design/pointer.txt", "keep.md")  # same bytes as the link target
    base = base_repo(repo)
    repo.remove("docs/design/pointer.txt")
    repo.symlink("docs/design/pointer.md", "keep.md")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    added = [c for c in diff.changes if c.change.path == "docs/design/pointer.md"]
    assert added[0].new_kind is K.SYMLINK
    result = assess(diff)
    assert result.level is L3
    assert "symlink" in result.reasons


def test_rename_from_l3_source_into_executable_stays_l3(repo: Repo) -> None:
    base = base_repo(repo)
    repo.git("mv", "docs/legal/terms.md", "docs/design/terms.sh")
    repo.chmod("docs/design/terms.sh", 0o755)
    target = repo.commit()
    result = assess(diff_commits(repo.root, base, target))
    assert result.level is L3
    assert "l3.legal" in result.matched_rules


def test_gitattributes_changes_are_l3(repo: Repo) -> None:
    repo.write(".gitattributes", "*.md text\n")
    base = base_repo(repo)
    repo.write(".gitattributes", "*.md -text\n")
    repo.write("docs/design/.gitattributes", "*.bin binary\n")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    result = assess(diff)
    assert result.level is L3
    assert "git_attributes" in result.reasons
    assert all(p.level is L3 for p in result.paths)


@pytest.mark.parametrize("operation", ["modify", "delete", "to_file", "from_file"])
def test_symlink_changes_are_l3(repo: Repo, operation: str) -> None:
    repo.symlink("docs/design/link.md", "a.md")
    base = base_repo(repo)
    if operation == "modify":
        repo.symlink("docs/design/link.md", "keep.md")
    elif operation == "delete":
        repo.remove("docs/design/link.md")
    elif operation == "to_file":
        repo.remove("docs/design/link.md")
        repo.write("docs/design/link.md", "now a file\n")
    else:
        repo.remove("docs/design/a.md")
        repo.symlink("docs/design/a.md", "keep.md")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    (entry,) = diff.entries
    result = assess(diff)
    assert result.level is L3
    if operation in {"modify", "delete"}:
        assert diff.changes[0].change.kind is K.SYMLINK
        assert "symlink" in result.reasons
    else:
        assert entry.status == "T"
        assert "mode_change" in result.reasons


@pytest.mark.parametrize("operation", ["modify", "delete"])
def test_submodule_changes_are_l3(repo: Repo, operation: str) -> None:
    repo.write("docs/design/a.md", "a\n")
    repo.gitlink("vendor/sub", "1" * 40)
    base = repo.commit("docs")
    if operation == "modify":
        repo.gitlink("vendor/sub", "2" * 40)
    else:
        repo.git("rm", "-q", "--cached", "vendor/sub")
    target = repo.commit("docs")
    diff = diff_commits(repo.root, base, target)
    (entry,) = diff.entries
    assert entry.old_mode == "160000"
    assert diff.changes[0].change.kind is K.SUBMODULE
    result = assess(diff)
    assert (result.level, "submodule" in result.reasons) == (L3, True)


def test_new_top_level_additions_are_l3(repo: Repo) -> None:
    base = base_repo(repo)
    repo.write("tools/x.py", "x\n")
    repo.write("ROOT.md", "r\n")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    assert all(c.change.new_top_level for c in diff.changes)
    result = assess(diff)
    assert (result.level, "new_top_level" in result.reasons) == (L3, True)


def test_size_limits_use_actual_counts(repo: Repo) -> None:
    base = base_repo(repo)
    for i in range(11):
        repo.write(f"docs/design/n{i}.md", "line\n")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    assert (diff.changed_files, diff.changed_lines) == (11, 11)
    assert assess(diff).level is L2

    repo.write("docs/design/a.md", "".join(f"{i}\n" for i in range(400)))
    big = repo.commit()
    diff = diff_commits(repo.root, target, big)
    assert diff.changed_lines == 402  # 400 added + 2 deleted
    assert assess(diff).level is L2


def test_too_many_paths_are_rejected(repo: Repo) -> None:
    base = base_repo(repo)
    for i in range(51):
        repo.write(f"docs/design/n{i}.md", "x\n")
    target = repo.commit()
    assert diff_error(lambda: diff_commits(repo.root, base, target)).code is G.TOO_MANY_CHANGES


# ------------------------------------------------------------- path safety


@pytest.mark.parametrize(
    ("path", "cause"),
    [
        ("docs/design/with space.md", "whitespace"),
        ("docs/design/$(touch PWNED).md", "whitespace"),
        ("docs/design/$(id).md", "disallowed_character"),
        ("docs/design/`id`.md", "disallowed_character"),
        ("docs/design/a;b.md", "disallowed_character"),
        ("docs/.env.local", "forbidden_area"),
        (".github/workflows/x.yml", "forbidden_area"),
        ("docs/.github/x.md", "forbidden_area"),
        ("docs/design/caf\u00e9.md", "non_ascii"),
    ],
)
def test_invalid_paths_are_rejected(repo: Repo, path: str, cause: str) -> None:
    base = base_repo(repo)
    repo.write(path, "x\n")
    target = repo.commit()
    error = diff_error(lambda: diff_commits(repo.root, base, target))
    assert (error.code, error.cause) == (G.INVALID_PATH, cause)
    assert not (repo.root / "PWNED").exists()
    assert not Path("PWNED").exists()


def test_non_utf8_paths_are_rejected(repo: Repo) -> None:
    base = base_repo(repo)
    directory = os.fsencode(repo.root / "docs" / "design")
    with open(os.path.join(directory, b"\xff.md"), "wb") as handle:
        handle.write(b"x\n")
    target = repo.commit()
    error = diff_error(lambda: diff_commits(repo.root, base, target))
    assert (error.code, error.cause) == (G.INVALID_PATH, "not_utf8")


def test_unusual_but_valid_paths_are_accepted(repo: Repo) -> None:
    base = base_repo(repo)
    path = "docs/app/[id]/(group)/@slot/page-v1_0.md"
    repo.write(path, "x\n")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)
    assert [c.change.path for c in diff.changes] == [path]


def test_case_only_changes_are_rejected(repo: Repo) -> None:
    base = base_repo(repo)
    repo.git("mv", "docs/design/keep.md", "docs/design/KEEP.md")
    target = repo.commit()
    error = diff_error(lambda: diff_commits(repo.root, base, target))
    assert (error.code, error.cause) == (G.INVALID_PATH, "case_collision")

    repo.remove("docs/design/KEEP.md")
    repo.write("docs/design/keep.md", "different content\n")
    again = repo.commit()
    error = diff_error(lambda: diff_commits(repo.root, target, again))
    assert (error.code, error.cause) == (G.INVALID_PATH, "case_collision")


def test_file_replaced_by_directory_is_rejected(repo: Repo) -> None:
    base = base_repo(repo)
    repo.remove("docs/design/keep.md")
    repo.write("docs/design/keep.md/inner.md", "x\n")
    target = repo.commit()
    error = diff_error(lambda: diff_commits(repo.root, base, target))
    assert (error.code, error.cause) == (G.INVALID_PATH, "parent_not_directory")


# ----------------------------------------------------- parser (synthetic)


def raw(old: str, new: str, old_oid: str, new_oid: str, status: str, *paths: str) -> bytes:
    header = f":{old} {new} {old_oid} {new_oid} {status}".encode()
    return header + b"\0" + b"".join(p.encode() + b"\0" for p in paths)


def test_parse_raw_diff_valid_records() -> None:
    data = (
        raw("100644", "100644", A40, B40, "M", "docs/a.md")
        + raw("000000", "100644", Z40, B40, "A", "docs/b.md")
        + raw("100644", "000000", A40, Z40, "D", "docs/c.md")
        + raw("100644", "100644", A40, A40, "R100", "docs/d.md", "docs/e.md")
        + raw("100644", "120000", A40, B40, "T", "docs/f.md")
    )
    entries = parse_raw_diff(data, 40)
    assert [(e.status, e.old_path, e.new_path) for e in entries] == [
        ("M", "docs/a.md", "docs/a.md"),
        ("A", None, "docs/b.md"),
        ("D", "docs/c.md", None),
        ("R", "docs/d.md", "docs/e.md"),
        ("T", "docs/f.md", "docs/f.md"),
    ]
    assert parse_raw_diff(b"", 40) == ()


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (raw("100644", "100644", A40, B40, "M", "docs/a.md")[:-1], G.MALFORMED_OUTPUT),
        (
            b"100644 100644 " + A40.encode() + b" " + B40.encode() + b" M\0docs/a.md\0",
            G.MALFORMED_OUTPUT,
        ),
        (b":100644 100644 " + A40.encode() + b" M\0docs/a.md\0", G.MALFORMED_OUTPUT),
        (raw("100644", "100644", A40, B40, "M"), G.MALFORMED_OUTPUT),  # missing path
        (raw("100644", "100644", A40, B40, "M", ""), G.MALFORMED_OUTPUT),  # empty path
        (raw("100644", "100644", A40, A40, "R100", "docs/a.md"), G.MALFORMED_OUTPUT),
        (raw("100644", "100644", A40, A40, "R090", "docs/a.md", "docs/b.md"), G.MALFORMED_OUTPUT),
        (raw("100644", "100644", A40, B40[:39], "M", "docs/a.md"), G.MALFORMED_OUTPUT),
        (raw("100644", "100644", A40.upper(), B40, "M", "docs/a.md"), G.MALFORMED_OUTPUT),
        (
            b":100644 100644 \xff" + A40[1:].encode() + b" " + B40.encode() + b" M\0x\0",
            G.MALFORMED_OUTPUT,
        ),
        (raw("100644", "100644", A40, B40, "C75", "docs/a.md", "docs/b.md"), G.UNKNOWN_STATUS),
        (raw("100644", "100644", A40, B40, "U", "docs/a.md"), G.UNKNOWN_STATUS),
        (raw("100644", "100644", A40, B40, "X", "docs/a.md"), G.UNKNOWN_STATUS),
        (raw("100644", "100644", A40, B40, "Q", "docs/a.md"), G.UNKNOWN_STATUS),
        (raw("100644", "100644", A40, B40, "", "docs/a.md"), G.UNKNOWN_STATUS),
        (raw("100664", "100644", A40, B40, "M", "docs/a.md"), G.UNKNOWN_MODE),
        (raw("040000", "040000", A40, B40, "M", "docs"), G.UNKNOWN_MODE),
        (raw("100644", "100644", Z40, B40, "A", "docs/a.md"), G.METADATA_MISMATCH),
        (raw("000000", "100644", A40, B40, "A", "docs/a.md"), G.METADATA_MISMATCH),
        (raw("100644", "000000", A40, Z40, "A", "docs/a.md"), G.METADATA_MISMATCH),
        (raw("000000", "100644", Z40, B40, "D", "docs/a.md"), G.METADATA_MISMATCH),
        (raw("000000", "100644", Z40, B40, "M", "docs/a.md"), G.METADATA_MISMATCH),
        (raw("100644", "120000", A40, B40, "M", "docs/a.md"), G.METADATA_MISMATCH),
        (raw("100644", "100644", A40, B40, "T", "docs/a.md"), G.METADATA_MISMATCH),
        (raw("100644", "100644", A40, B40, "R100", "docs/a.md", "docs/b.md"), G.METADATA_MISMATCH),
        (raw("100644", "100644", A40, A40, "R100", "docs/a.md", "docs/a.md"), G.METADATA_MISMATCH),
        (raw("100644", "100644", A40, B40, "M", "docs/a.md") + b"trailing\0", G.MALFORMED_OUTPUT),
    ],
)
def test_parse_raw_diff_rejects(data: bytes, code: GitDiffErrorCode) -> None:
    assert diff_error(lambda: parse_raw_diff(data, 40)).code is code


def test_parse_raw_diff_rejects_non_utf8_paths() -> None:
    data = raw("100644", "100644", A40, B40, "M", "x")[:-2] + b"\xff\0"
    error = diff_error(lambda: parse_raw_diff(data, 40))
    assert (error.code, error.cause) == (G.INVALID_PATH, "not_utf8")


def test_parse_numstat() -> None:
    data = b"1\t2\tdocs/a.md\0-\t-\tdocs/b.bin\0" + b"0\t0\t\0docs/c.md\0docs/d.md\0"
    assert parse_numstat(data) == (
        NumstatEntry(1, 2, "docs/a.md", "docs/a.md"),
        NumstatEntry(None, None, "docs/b.bin", "docs/b.bin"),
        NumstatEntry(0, 0, "docs/c.md", "docs/d.md"),
    )


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"1\t2\tdocs/a.md", G.MALFORMED_OUTPUT),  # truncated
        (b"1\t-\tdocs/a.md\0", G.MALFORMED_OUTPUT),
        (b"x\t2\tdocs/a.md\0", G.MALFORMED_OUTPUT),
        (b"+1\t2\tdocs/a.md\0", G.MALFORMED_OUTPUT),
        (b"1\t2\0", G.MALFORMED_OUTPUT),
        (b"1\t2\tdocs/a\tb.md\0", G.MALFORMED_OUTPUT),
        (b"0\t0\t\0docs/c.md\0", G.MALFORMED_OUTPUT),  # rename without destination
        (b"0\t0\t\0\0docs/d.md\0", G.MALFORMED_OUTPUT),  # empty source
        (b"12345678901\t0\tdocs/a.md\0", G.MALFORMED_OUTPUT),
        (b"1000000001\t0\tdocs/a.md\0", G.COUNT_OVERFLOW),
        (b"1\n\t0\tdocs/a.md\0", G.MALFORMED_OUTPUT),  # trailing newline in a count
    ],
)
def test_parse_numstat_rejects(data: bytes, code: GitDiffErrorCode) -> None:
    assert diff_error(lambda: parse_numstat(data)).code is code


def tree(*entries: tuple[str, str, str, str]) -> bytes:
    return b"".join(f"{m} {k} {o}\t{p}".encode() + b"\0" for m, k, o, p in entries)


def test_parse_tree() -> None:
    data = tree(("100644", "blob", A40, "docs/a.md"), ("160000", "commit", B40, "vendor/sub"))
    assert parse_tree(data, 40) == {"docs/a.md": ("100644", A40), "vendor/sub": ("160000", B40)}


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (tree(("100664", "blob", A40, "docs/a.md")), G.UNKNOWN_MODE),
        (tree(("040000", "tree", A40, "docs")), G.UNKNOWN_MODE),
        (tree(("160000", "blob", A40, "vendor/sub")), G.MALFORMED_OUTPUT),
        (tree(("100644", "commit", A40, "docs/a.md")), G.MALFORMED_OUTPUT),
        (
            tree(("100644", "blob", A40, "docs/a.md"), ("100644", "blob", B40, "docs/a.md")),
            G.MALFORMED_OUTPUT,
        ),
        (tree(("100644", "blob", A40, "docs/a.md"))[:-1], G.MALFORMED_OUTPUT),
        (b"100644 blob\tdocs/a.md\0", G.MALFORMED_OUTPUT),
    ],
)
def test_parse_tree_rejects(data: bytes, code: GitDiffErrorCode) -> None:
    assert diff_error(lambda: parse_tree(data, 40)).code is code


# ------------------------------------------------ reconciliation (synthetic)

BASE_TREE = {"docs/a.md": ("100644", A40), "docs/b.md": ("100644", A40)}
TARGET_TREE = {"docs/a.md": ("100644", B40), "docs/b.md": ("100644", A40)}
M_A = RawEntry("M", "100644", "100644", A40, B40, "docs/a.md", "docs/a.md")
N_A = NumstatEntry(1, 1, "docs/a.md", "docs/a.md")


def build(
    raw_entries: tuple[RawEntry, ...] = (M_A,),
    numstat: tuple[NumstatEntry, ...] = (N_A,),
    base_tree: dict[str, tuple[str, str]] | None = None,
    target_tree: dict[str, tuple[str, str]] | None = None,
) -> GitDiff:
    return build_diff(
        base_commit=A40,
        target_commit=B40,
        raw=raw_entries,
        numstat=numstat,
        base_tree=BASE_TREE if base_tree is None else base_tree,
        target_tree=TARGET_TREE if target_tree is None else target_tree,
    )


def test_build_diff_valid() -> None:
    diff = build()
    assert (diff.changed_files, diff.changed_lines) == (1, 2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"numstat": (NumstatEntry(1, 1, "docs/b.md", "docs/b.md"),)},  # path differs
        {"numstat": ()},  # numstat record missing
        {"numstat": (N_A, N_A)},  # extra numstat record
        {"raw_entries": (M_A, M_A), "numstat": (N_A, N_A)},  # duplicate record
        {"raw_entries": ()},  # raw record missing
        {"target_tree": {**TARGET_TREE, "docs/b.md": ("100644", B40)}},  # change omitted
        {"base_tree": {"docs/a.md": ("100755", A40), "docs/b.md": ("100644", A40)}},  # mode
        {"base_tree": {"docs/a.md": ("100644", B40), "docs/b.md": ("100644", A40)}},  # oid
        {"target_tree": {"docs/b.md": ("100644", A40)}},  # modified path missing in target
        {
            "raw_entries": (RawEntry("D", "100644", "000000", A40, Z40, "docs/a.md", None),),
            "numstat": (NumstatEntry(0, 1, "docs/a.md", "docs/a.md"),),
        },  # deleted path still in target
    ],
)
def test_build_diff_rejects_conflicting_metadata(kwargs: dict[str, object]) -> None:
    error = diff_error(lambda: build(**kwargs))  # type: ignore[arg-type]
    assert error.code is G.METADATA_MISMATCH


def test_build_diff_rejects_count_overflow() -> None:
    entries = []
    counts = []
    base_tree: dict[str, tuple[str, str]] = {}
    target_tree: dict[str, tuple[str, str]] = {}
    for i in range(11):
        path = f"docs/f{i}.md"
        entries.append(RawEntry("M", "100644", "100644", A40, B40, path, path))
        counts.append(NumstatEntry(1_000_000, 0, path, path))
        base_tree[path] = ("100644", A40)
        target_tree[path] = ("100644", B40)
    error = diff_error(lambda: build(tuple(entries), tuple(counts), base_tree, target_tree))
    assert MAX_CHANGED_LINES < 11 * 1_000_000
    assert error.code is G.COUNT_OVERFLOW


def test_build_diff_rejects_target_mode_mismatch() -> None:
    # The raw record claims the target became a symlink, the target tree disagrees.
    entry = RawEntry("T", "100644", "120000", A40, B40, "docs/a.md", "docs/a.md")
    error = diff_error(lambda: build((entry,), (N_A,)))
    assert error.code is G.METADATA_MISMATCH


def test_build_diff_emits_new_kind_from_the_target_mode() -> None:
    entry = RawEntry("T", "100644", "120000", A40, B40, "docs/a.md", "docs/a.md")
    target_tree = {"docs/a.md": ("120000", B40), "docs/b.md": ("100644", A40)}
    diff = build((entry,), (N_A,), target_tree=target_tree)
    (change,) = diff.changes
    assert (change.change.kind, change.new_kind, change.mode_change) == (
        K.REGULAR_FILE,
        K.SYMLINK,
        True,
    )
    deleted = RawEntry("D", "100644", "000000", A40, Z40, "docs/a.md", None)
    diff = build(
        (deleted,),
        (NumstatEntry(0, 1, "docs/a.md", "docs/a.md"),),
        target_tree={"docs/b.md": ("100644", A40)},
    )
    assert diff.changes[0].new_kind is None


def test_build_diff_rejects_kind_mismatch_between_raw_and_tree() -> None:
    # The tree says symlink, the raw record claims a regular file.
    base_tree = {"docs/a.md": ("120000", A40)}
    target_tree = {"docs/a.md": ("120000", B40)}
    error = diff_error(lambda: build((M_A,), (N_A,), base_tree, target_tree))
    assert error.code is G.METADATA_MISMATCH


# --------------------------------------------------- integration and safety


def test_adapter_never_lowers_risk_compared_with_direct_evaluation(repo: Repo) -> None:
    base = base_repo(repo)
    repo.write("docs/design/a.md", "changed\n")
    repo.git("mv", "docs/legal/terms.md", "docs/design/terms.md")
    repo.write("backend/app/main.py", "print(2)\n")
    target = repo.commit()
    diff = diff_commits(repo.root, base, target)

    # The same changes, validated directly against the base commit's tree.
    base_index = RepoIndex(
        {
            "docs/design/a.md": "100644",
            "docs/design/keep.md": "100644",
            "docs/legal/terms.md": "100644",
            "backend/app/main.py": "100644",
        }
    )
    validated = validate_changes(
        [
            ("backend/app/main.py", "modify"),
            ("docs/design/a.md", "modify"),
            ("docs/design/terms.md", "add"),
            ("docs/legal/terms.md", "delete"),
        ],
        base_index,
    )
    regular = K.REGULAR_FILE
    direct = [
        ChangeFacts(change=validated[0], new_kind=regular, binary=False, mode_change=False),
        ChangeFacts(change=validated[1], new_kind=regular, binary=False, mode_change=False),
        ChangeFacts(
            change=validated[2],
            new_kind=regular,
            binary=False,
            mode_change=False,
            renamed_from=validated[3],
        ),
    ]
    assert list(diff.changes) == direct
    expected = evaluate(
        POLICY,
        direct,
        changed_files=3,
        changed_lines=diff.changed_lines,
        expected_policy_version=POLICY.policy_version,
    )
    assert assess(diff) == expected
    assert expected.level is L3


def test_hostile_environment_and_attributes_are_ignored(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.write("docs/design/img.bin", b"\x00\x01\x02")
    base = base_repo(repo)
    repo.write("docs/design/img.bin", b"\x00\x01\x03")
    repo.write("docs/design/a.md", "one\ntwo\nthree\n")
    target = repo.commit()
    expected = diff_commits(repo.root, base, target)

    other = Repo(tmp_path / "other")
    other.write("docs/other.md", "o\n")
    other.commit()
    marker = tmp_path / "EXECUTED"
    script = tmp_path / "tool.sh"
    script.write_text(f'#!/bin/sh\ntouch {marker}\ncat "$1" 2>/dev/null\n')
    script.chmod(0o755)
    # Working-tree attributes that would force text and a textconv driver.
    repo.write(".gitattributes", "*.bin diff\n*.md diff=evil\n")
    repo.git("config", "diff.evil.textconv", str(script))
    repo.git("config", "diff.external", str(script))
    repo.git("config", "core.fsmonitor", str(script))
    monkeypatch.setenv("GIT_DIR", str(other.root / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other.root))
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", str(script))
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", f"'diff.external'='{script}'")
    monkeypatch.setenv("GIT_ATTR_SOURCE", base)
    monkeypatch.setenv("GIT_INDEX_FILE", str(other.root / ".git" / "index"))

    actual = diff_commits(repo.root, base, target)
    assert actual == expected
    assert not marker.exists()
    binary = [e for e in actual.entries if e.new_path == "docs/design/img.bin"]
    assert binary[0].binary is True


def test_results_are_deterministic_and_immutable(repo: Repo) -> None:
    base = base_repo(repo)
    repo.write("docs/design/a.md", "changed\n")
    repo.git("mv", "docs/design/keep.md", "docs/design/kept.md")
    repo.symlink("docs/design/link.md", "a.md")
    repo.write("docs/design/run.sh", "x\n")
    repo.chmod("docs/design/run.sh", 0o755)
    target = repo.commit()
    first = diff_commits(repo.root, base, target)
    assert all(diff_commits(repo.root, base, target) == first for _ in range(3))
    assessment = assess(first)
    assert all(assess(diff_commits(repo.root, base, target)) == assessment for _ in range(3))
    assert assessment.level is L3
    assert isinstance(first.changes, tuple) and isinstance(first.entries, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.changed_lines = 0  # type: ignore[misc]


def test_failures_never_return_partial_results(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base = base_repo(repo)
    repo.write("docs/design/a.md", "changed\n")
    target = repo.commit()
    # Too large while resolving a ref and while diffing: never "not found".
    for limit in (10, 64):
        monkeypatch.setattr(git_diff_module, "MAX_GIT_OUTPUT_BYTES", limit)
        assert diff_error(lambda: diff_commits(repo.root, base, target)).code is (
            G.OUTPUT_TOO_LARGE
        )
    monkeypatch.undo()

    real_run = git_diff_module._run

    def truncated(git: str, root: Path, *args: str) -> bytes:
        out = real_run(git, root, *args)
        return out[:-1] if "--numstat" in args else out

    monkeypatch.setattr(git_diff_module, "_run", truncated)
    assert diff_error(lambda: diff_commits(repo.root, base, target)).code is G.MALFORMED_OUTPUT

    def failing(git: str, root: Path, *args: str) -> bytes:
        if "diff-tree" in args:
            raise GitDiffError(G.GIT_FAILED)
        return real_run(git, root, *args)

    monkeypatch.setattr(git_diff_module, "_run", failing)
    assert diff_error(lambda: diff_commits(repo.root, base, target)).code is G.GIT_FAILED


def test_git_unavailable(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    base = base_repo(repo)
    monkeypatch.setattr("orchestrator.paths.shutil.which", lambda _name: None)
    error = diff_error(lambda: diff_commits(repo.root, base, base))
    assert (error.code, error.cause) == (G.INVALID_REPOSITORY, "git_unavailable")
