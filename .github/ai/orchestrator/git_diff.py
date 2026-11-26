"""Git diff adapter: actual diff between two commits -> Risk Policy input (T3.1).

This module is the authoritative bridge between Git and the Risk Policy. It
never trusts path lists, change types, file metadata, line counts or risk
estimates from a Planner or Executor; everything comes from Git and is
cross-checked.

Semantics:

* ``base_commit -> target_commit``: two immutable commit trees are compared
  with ``git diff-tree``. The working tree, the index, untracked files and the
  current branch play no part. Both references must be given explicitly: a
  full object ID (40 or 64 lower-case hex characters) or a fully qualified ref
  under ``refs/heads/``, ``refs/tags/`` or ``refs/remotes/``. Short names,
  abbreviations and revision expressions (``HEAD~1``, ``@{u}``, ``a..b`` ...)
  are rejected. Each reference must resolve to a *commit* object; annotated
  tags must be peeled by the caller.
* Paths and modes come from the NUL-delimited raw diff (``--raw -z``); line
  counts from ``--numstat -z``. ``numstat`` alone is insufficient: it carries
  no modes, object IDs or change status, so it cannot tell additions from
  modifications, detect symlinks, submodules or mode changes, or prove that
  a rename is a rename. Both outputs are produced with the same fixed options
  and must describe exactly the same records, and every record is checked
  against ``git ls-tree`` of both commits; any disagreement rejects the diff.
* Renames: only exact renames are detected (``--find-renames=100%``, copies
  disabled), which is deterministic. A rename with edits appears as a delete
  plus an add. A rename is **one** change record (``ChangeFacts`` with
  ``renamed_from``) and counts as one changed file, matching the Risk Policy
  contract (``changed_files == len(changes)``); both paths are validated and
  classified.
* Lines: ``changed_lines`` is the sum of added plus deleted lines over all
  records. Binary files (``-`` in ``numstat``) contribute 0 lines and are
  marked ``binary``, which is L3, so the zero count can never lower the risk.
  Binary detection is content-based only: attributes are read from the empty
  tree (``--attr-source``), so a ``.gitattributes`` file cannot turn a binary
  file into text or enable a textconv driver.
* Every path goes through :func:`orchestrator.paths.validate_changes` against
  an index built from ``git ls-tree`` of the **base** commit, so existence,
  Git entry kind and ``new_top_level`` are decided by the existing POLICY
  definitions.
* Entry kinds: ``ChangeFacts.change.kind`` is the kind before the change
  (from the base tree, via path validation) and ``ChangeFacts.new_kind`` the
  kind after it, derived only from the target Git mode (``None`` for a
  delete). New executable files, symlinks and submodules, type changes and
  renames that change the mode are therefore emitted with their real kinds
  and classified by the Risk Policy (executable L2, symlink/submodule and
  mode changes L3).
* Fail closed: any Git error, unknown status or mode, malformed or truncated
  output, metadata mismatch or invalid path raises :class:`GitDiffError`; no
  partial result is ever returned.

Git runs like :meth:`orchestrator.paths.RepoIndex.from_git`: fixed argument
vectors, no shell, no inherited ``GIT_*`` variables, ``core.fsmonitor=false``,
no stdin, a timeout and an output size limit. External diff drivers and
textconv are disabled. The repository root is validated with
``RepoIndex.from_git`` first.
"""

from __future__ import annotations

import enum
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from orchestrator.paths import (
    MAX_CHANGES,
    MODE_EXECUTABLE,
    MODE_FILE,
    MODE_GITLINK,
    MODE_SYMLINK,
    ChangeType,
    EntryKind,
    PathValidationError,
    RepoIndex,
    RepoIndexError,
    ValidatedPath,
    _git_environment,
    validate_changes,
)
from orchestrator.risk_policy import MAX_CHANGED_LINES, ChangeFacts

GIT_TIMEOUT_SECONDS = 60
MAX_GIT_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_LINES_PER_FILE = 1_000_000_000
MODE_NONE = "000000"
_KNOWN_MODES = frozenset({MODE_FILE, MODE_EXECUTABLE, MODE_SYMLINK, MODE_GITLINK})
_REGULAR_MODES = frozenset({MODE_FILE, MODE_EXECUTABLE})
_EMPTY_TREES = {
    40: "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
    64: "6ef19b41225c5369f1c104d45d8d85efa9b057b53b14b4b9b939dd74decc5321",
}
_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_REF_RE = re.compile(
    r"refs/(?:heads|tags|remotes)/[A-Za-z0-9_][A-Za-z0-9._-]*(?:/[A-Za-z0-9_][A-Za-z0-9._-]*)*"
)
_DIGITS_RE = re.compile(r"^[0-9]{1,10}$")
_KIND_BY_MODE = {
    MODE_FILE: EntryKind.REGULAR_FILE,
    MODE_EXECUTABLE: EntryKind.EXECUTABLE_FILE,
    MODE_SYMLINK: EntryKind.SYMLINK,
    MODE_GITLINK: EntryKind.SUBMODULE,
}
# Options shared by both diff-tree invocations; never caller-controlled.
_DIFF_OPTIONS = (
    "-r",
    "-z",
    "--no-abbrev",
    "--full-index",
    "--find-renames=100%",
    "--no-ext-diff",
    "--no-textconv",
    "--ignore-submodules=none",
    "--no-color",
)


class GitDiffErrorCode(enum.StrEnum):
    GIT_UNAVAILABLE = "git_unavailable"
    GIT_FAILED = "git_failed"
    INVALID_REPOSITORY = "invalid_repository"
    INVALID_REF = "invalid_ref"
    REF_NOT_FOUND = "ref_not_found"
    NOT_A_COMMIT = "not_a_commit"
    OUTPUT_TOO_LARGE = "output_too_large"
    MALFORMED_OUTPUT = "malformed_output"
    UNKNOWN_STATUS = "unknown_status"
    UNKNOWN_MODE = "unknown_mode"
    METADATA_MISMATCH = "metadata_mismatch"
    INVALID_PATH = "invalid_path"
    TOO_MANY_CHANGES = "too_many_changes"
    COUNT_OVERFLOW = "count_overflow"


class GitDiffError(RuntimeError):
    """The diff cannot be used. ``cause`` carries a nested stable code, if any."""

    def __init__(self, code: GitDiffErrorCode, *, cause: str | None = None) -> None:
        self.code = code
        self.cause = cause
        suffix = f" ({cause})" if cause else ""
        super().__init__(f"git diff rejected: {code.value}{suffix}")


def _error(code: GitDiffErrorCode, cause: str | None = None) -> GitDiffError:
    return GitDiffError(code, cause=cause)


# ------------------------------------------------------------------ records


@dataclass(frozen=True, slots=True)
class RawEntry:
    """One record of ``git diff-tree --raw -z`` (paths not yet validated)."""

    status: str  # "A", "M", "D", "T" or "R"
    old_mode: str
    new_mode: str
    old_oid: str
    new_oid: str
    old_path: str | None
    new_path: str | None

    @property
    def key(self) -> tuple[str | None, str | None]:
        return (self.old_path, self.new_path)

    @property
    def numstat_key(self) -> tuple[str | None, str | None]:
        """Paths as ``--numstat`` reports them (one path twice unless renamed)."""

        if self.status == "R":
            return (self.old_path, self.new_path)
        path = self.new_path if self.old_path is None else self.old_path
        return (path, path)


@dataclass(frozen=True, slots=True)
class NumstatEntry:
    """One record of ``git diff-tree --numstat -z``; ``None`` counts = binary."""

    added: int | None
    deleted: int | None
    old_path: str | None
    new_path: str | None

    @property
    def binary(self) -> bool:
        return self.added is None


@dataclass(frozen=True, slots=True)
class DiffEntry:
    """Validated audit record of one change."""

    status: str
    old_path: str | None
    new_path: str | None
    old_mode: str | None
    new_mode: str | None
    old_oid: str | None
    new_oid: str | None
    added_lines: int
    deleted_lines: int
    binary: bool
    mode_change: bool


@dataclass(frozen=True, slots=True)
class GitDiff:
    """Adapter result; ``changes``/counts go directly into ``risk_policy.evaluate``."""

    base_commit: str
    target_commit: str
    changes: tuple[ChangeFacts, ...]
    entries: tuple[DiffEntry, ...]
    changed_files: int
    changed_lines: int


# ------------------------------------------------------------------ parsing


def _decode_path(raw: bytes) -> str:
    if not raw:
        raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _error(GitDiffErrorCode.INVALID_PATH, "not_utf8") from None


def _tokens(data: bytes) -> list[bytes]:
    """Split NUL-terminated output; reject truncated output."""

    if not data:
        return []
    if not data.endswith(b"\0"):
        raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
    return data[:-1].split(b"\0")


def _check_oid(oid: str, length: int) -> None:
    if len(oid) != length or not _OID_RE.fullmatch(oid):
        raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)


def parse_raw_diff(data: bytes, oid_length: int) -> tuple[RawEntry, ...]:
    """Parse ``git diff-tree --raw -z`` output strictly."""

    zero = "0" * oid_length
    tokens = _tokens(data)
    entries: list[RawEntry] = []
    position = 0
    while position < len(tokens):
        header = tokens[position]
        position += 1
        if not header.startswith(b":"):
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
        try:
            fields = header[1:].decode("ascii").split(" ")
        except UnicodeDecodeError:
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT) from None
        if len(fields) != 5:
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
        old_mode, new_mode, old_oid, new_oid, status = fields
        for mode in (old_mode, new_mode):
            if mode != MODE_NONE and mode not in _KNOWN_MODES:
                raise _error(GitDiffErrorCode.UNKNOWN_MODE)
        _check_oid(old_oid, oid_length)
        _check_oid(new_oid, oid_length)
        letter = status[:1]
        if letter == "R":
            if status != "R100":  # only exact renames are requested
                raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
            needed = 2
        elif status in {"A", "M", "D", "T"}:
            needed = 1
        else:
            raise _error(GitDiffErrorCode.UNKNOWN_STATUS)
        if position + needed > len(tokens):
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
        paths = [_decode_path(token) for token in tokens[position : position + needed]]
        position += needed

        added_side = old_mode == MODE_NONE
        deleted_side = new_mode == MODE_NONE
        if (old_oid == zero) != added_side or (new_oid == zero) != deleted_side:
            raise _error(GitDiffErrorCode.METADATA_MISMATCH)
        if letter == "A" and not (added_side and not deleted_side):
            raise _error(GitDiffErrorCode.METADATA_MISMATCH)
        if letter == "D" and not (deleted_side and not added_side):
            raise _error(GitDiffErrorCode.METADATA_MISMATCH)
        if letter in {"M", "T", "R"} and (added_side or deleted_side):
            raise _error(GitDiffErrorCode.METADATA_MISMATCH)
        if letter == "M" and old_mode != new_mode and not {old_mode, new_mode} <= _REGULAR_MODES:
            raise _error(GitDiffErrorCode.METADATA_MISMATCH)  # a type change must be "T"
        if letter == "T" and old_mode == new_mode:
            raise _error(GitDiffErrorCode.METADATA_MISMATCH)
        if letter == "R" and (old_oid != new_oid or paths[0] == paths[1]):
            raise _error(GitDiffErrorCode.METADATA_MISMATCH)

        if letter == "A":
            old_path, new_path = None, paths[0]
        elif letter == "D":
            old_path, new_path = paths[0], None
        elif letter == "R":
            old_path, new_path = paths[0], paths[1]
        else:
            old_path = new_path = paths[0]
        entries.append(RawEntry(letter, old_mode, new_mode, old_oid, new_oid, old_path, new_path))
    return tuple(entries)


def _count(token: bytes) -> int | None:
    if token == b"-":
        return None
    try:
        text = token.decode("ascii")
    except UnicodeDecodeError:
        raise _error(GitDiffErrorCode.MALFORMED_OUTPUT) from None
    if not _DIGITS_RE.fullmatch(text):
        raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
    value = int(text)
    if value > MAX_LINES_PER_FILE:
        raise _error(GitDiffErrorCode.COUNT_OVERFLOW)
    return value


def parse_numstat(data: bytes) -> tuple[NumstatEntry, ...]:
    """Parse ``git diff-tree --numstat -z`` output strictly."""

    tokens = _tokens(data)
    entries: list[NumstatEntry] = []
    position = 0
    while position < len(tokens):
        parts = tokens[position].split(b"\t")
        position += 1
        if len(parts) != 3:
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
        added, deleted = _count(parts[0]), _count(parts[1])
        if (added is None) != (deleted is None):
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
        if parts[2]:
            path = _decode_path(parts[2])
            entries.append(NumstatEntry(added, deleted, path, path))
            continue
        # Rename: "<added>\t<deleted>\t" NUL <source> NUL <destination> NUL
        if position + 2 > len(tokens):
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
        source = _decode_path(tokens[position])
        destination = _decode_path(tokens[position + 1])
        position += 2
        entries.append(NumstatEntry(added, deleted, source, destination))
    return tuple(entries)


def parse_tree(data: bytes, oid_length: int) -> dict[str, tuple[str, str]]:
    """Parse ``git ls-tree -r -z --full-tree`` into ``path -> (mode, oid)``.

    Paths that are not valid UTF-8 are kept with surrogate escapes; path
    validation later refuses to use them.
    """

    tree: dict[str, tuple[str, str]] = {}
    for token in _tokens(data):
        meta, sep, raw_path = token.partition(b"\t")
        fields = meta.split(b" ")
        if not sep or not raw_path or len(fields) != 3:
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
        try:
            mode, kind, oid = (field.decode("ascii") for field in fields)
        except UnicodeDecodeError:
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT) from None
        if mode not in _KNOWN_MODES:
            raise _error(GitDiffErrorCode.UNKNOWN_MODE)
        expected_kind = "commit" if mode == MODE_GITLINK else "blob"
        if kind != expected_kind:
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
        _check_oid(oid, oid_length)
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if path in tree:
            raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
        tree[path] = (mode, oid)
    return tree


# ------------------------------------------------------------- reconciliation


def _expected_changed_paths(
    base: dict[str, tuple[str, str]], target: dict[str, tuple[str, str]]
) -> set[str]:
    return {path for path in base.keys() | target.keys() if base.get(path) != target.get(path)}


def _check_against_trees(
    entry: RawEntry,
    base: dict[str, tuple[str, str]],
    target: dict[str, tuple[str, str]],
) -> None:
    if entry.old_path is not None and base.get(entry.old_path) != (entry.old_mode, entry.old_oid):
        raise _error(GitDiffErrorCode.METADATA_MISMATCH)
    if entry.new_path is not None and target.get(entry.new_path) != (
        entry.new_mode,
        entry.new_oid,
    ):
        raise _error(GitDiffErrorCode.METADATA_MISMATCH)
    if entry.status in {"D", "R"} and entry.old_path in target:
        raise _error(GitDiffErrorCode.METADATA_MISMATCH)
    if entry.status in {"A", "R"} and entry.new_path in base:
        raise _error(GitDiffErrorCode.METADATA_MISMATCH)


def build_diff(
    *,
    base_commit: str,
    target_commit: str,
    raw: tuple[RawEntry, ...],
    numstat: tuple[NumstatEntry, ...],
    base_tree: dict[str, tuple[str, str]],
    target_tree: dict[str, tuple[str, str]],
) -> GitDiff:
    """Reconcile parsed Git output into a validated :class:`GitDiff`.

    Pure function (no Git calls), so every consistency rule is testable with
    synthetic input.
    """

    if [entry.numstat_key for entry in raw] != [(n.old_path, n.new_path) for n in numstat]:
        raise _error(GitDiffErrorCode.METADATA_MISMATCH)
    covered: set[str] = set()
    for entry in raw:
        _check_against_trees(entry, base_tree, target_tree)
        for path in {path for path in entry.key if path is not None}:
            if path in covered:
                raise _error(GitDiffErrorCode.METADATA_MISMATCH)
            covered.add(path)
    if covered != _expected_changed_paths(base_tree, target_tree):
        raise _error(GitDiffErrorCode.METADATA_MISMATCH)

    if not raw:
        return GitDiff(base_commit, target_commit, (), (), 0, 0)

    items: list[tuple[str, str]] = []
    for entry in raw:
        if entry.status == "A":
            items.append((entry.new_path or "", "add"))
        elif entry.status == "D":
            items.append((entry.old_path or "", "delete"))
        elif entry.status == "R":
            items.append((entry.new_path or "", "add"))
            items.append((entry.old_path or "", "delete"))
        else:  # M, T
            items.append((entry.old_path or "", "modify"))
    if len(items) > MAX_CHANGES:
        raise _error(GitDiffErrorCode.TOO_MANY_CHANGES)

    index = RepoIndex({path: mode for path, (mode, _oid) in base_tree.items()})
    try:
        validated = validate_changes(items, index)
    except PathValidationError as error:
        raise _error(GitDiffErrorCode.INVALID_PATH, error.code.value) from None

    changes: list[ChangeFacts] = []
    audit: list[DiffEntry] = []
    total = 0
    cursor = 0
    for entry, counts in zip(raw, numstat, strict=True):
        record: ValidatedPath = validated[cursor]
        cursor += 1
        source: ValidatedPath | None = None
        if entry.status == "R":
            source = validated[cursor]
            cursor += 1
        # The kind found by path validation (base tree) must match the raw old mode.
        for checked in (record, source):
            if (
                checked is not None
                and checked.change is not ChangeType.ADD
                and checked.kind is not _KIND_BY_MODE.get(entry.old_mode)
            ):
                raise _error(GitDiffErrorCode.METADATA_MISMATCH)
        # The kind after the change comes only from the target Git mode, which
        # was checked against the target tree; a delete has no target.
        new_kind: EntryKind | None = None
        if entry.status != "D":
            new_kind = _KIND_BY_MODE.get(entry.new_mode)
            if new_kind is None:
                raise _error(GitDiffErrorCode.METADATA_MISMATCH)
        mode_change = entry.status in {"M", "T"} and entry.old_mode != entry.new_mode
        changes.append(
            ChangeFacts(
                change=record,
                new_kind=new_kind,
                binary=counts.binary,
                mode_change=mode_change,
                renamed_from=source,
            )
        )
        added = counts.added or 0
        deleted = counts.deleted or 0
        total += added + deleted
        if total > MAX_CHANGED_LINES:
            raise _error(GitDiffErrorCode.COUNT_OVERFLOW)
        audit.append(
            DiffEntry(
                status=entry.status,
                old_path=entry.old_path,
                new_path=entry.new_path,
                old_mode=None if entry.status == "A" else entry.old_mode,
                new_mode=None if entry.status == "D" else entry.new_mode,
                old_oid=None if entry.status == "A" else entry.old_oid,
                new_oid=None if entry.status == "D" else entry.new_oid,
                added_lines=added,
                deleted_lines=deleted,
                binary=counts.binary,
                mode_change=mode_change,
            )
        )
    return GitDiff(
        base_commit=base_commit,
        target_commit=target_commit,
        changes=tuple(changes),
        entries=tuple(audit),
        changed_files=len(changes),
        changed_lines=total,
    )


# ---------------------------------------------------------------- Git calls


def _run(git: str, repo_root: Path, *args: str) -> bytes:
    argv = [git, "-c", "core.fsmonitor=false", "-C", str(repo_root), *args]
    try:
        result = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_SECONDS,
            env=_git_environment(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise _error(GitDiffErrorCode.GIT_FAILED) from None
    if result.returncode != 0:
        raise _error(GitDiffErrorCode.GIT_FAILED)
    if len(result.stdout) > MAX_GIT_OUTPUT_BYTES:
        raise _error(GitDiffErrorCode.OUTPUT_TOO_LARGE)
    return result.stdout


def _check_ref_syntax(ref: object) -> str:
    if not isinstance(ref, str) or len(ref) > 200:
        raise _error(GitDiffErrorCode.INVALID_REF)
    if _OID_RE.fullmatch(ref):
        return ref
    if (
        not _REF_RE.fullmatch(ref)
        or ".." in ref
        or ref.endswith((".", ".lock"))
        or "/." in ref
        or ".lock/" in ref
    ):
        raise _error(GitDiffErrorCode.INVALID_REF)
    return ref


def _resolve_commit(git: str, repo_root: Path, ref: str) -> str:
    # Only a failing Git command means "not found"; other errors keep their code.
    try:
        out = _run(git, repo_root, "rev-parse", "--verify", "--quiet", "--end-of-options", ref)
    except GitDiffError as error:
        if error.code is not GitDiffErrorCode.GIT_FAILED:
            raise
        raise _error(GitDiffErrorCode.REF_NOT_FOUND) from None
    oid = out.decode("ascii", errors="replace").strip()
    if not _OID_RE.fullmatch(oid) or out != (oid + "\n").encode("ascii"):
        raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
    try:
        kind = _run(git, repo_root, "cat-file", "-t", oid)
    except GitDiffError as error:
        if error.code is not GitDiffErrorCode.GIT_FAILED:
            raise
        raise _error(GitDiffErrorCode.REF_NOT_FOUND) from None
    if kind != b"commit\n":
        raise _error(GitDiffErrorCode.NOT_A_COMMIT)
    return oid


def diff_commits(repo_root: Path, base_ref: str, target_ref: str) -> GitDiff:
    """Return the validated diff ``base_ref -> target_ref``. Raises :class:`GitDiffError`."""

    base_ref = _check_ref_syntax(base_ref)
    target_ref = _check_ref_syntax(target_ref)
    try:
        RepoIndex.from_git(repo_root)  # validates the worktree root and the Git setup
    except RepoIndexError as error:
        raise _error(GitDiffErrorCode.INVALID_REPOSITORY, error.code.value) from None
    git = shutil.which("git")
    if git is None:
        raise _error(GitDiffErrorCode.GIT_UNAVAILABLE)

    base = _resolve_commit(git, repo_root, base_ref)
    target = _resolve_commit(git, repo_root, target_ref)
    if len(base) != len(target):
        raise _error(GitDiffErrorCode.MALFORMED_OUTPUT)
    oid_length = len(base)
    attr_source = f"--attr-source={_EMPTY_TREES[oid_length]}"

    raw = parse_raw_diff(
        _run(git, repo_root, attr_source, "diff-tree", "--raw", *_DIFF_OPTIONS, base, target),
        oid_length,
    )
    numstat = parse_numstat(
        _run(git, repo_root, attr_source, "diff-tree", "--numstat", *_DIFF_OPTIONS, base, target)
    )
    base_tree = parse_tree(
        _run(git, repo_root, "ls-tree", "-r", "-z", "--full-tree", base), oid_length
    )
    target_tree = parse_tree(
        _run(git, repo_root, "ls-tree", "-r", "-z", "--full-tree", target), oid_length
    )
    return build_diff(
        base_commit=base,
        target_commit=target,
        raw=raw,
        numstat=numstat,
        base_tree=base_tree,
        target_tree=target_tree,
    )
