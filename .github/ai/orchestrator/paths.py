"""Validation of repository paths proposed by untrusted sources (T2, T2.1).

Every path that comes from the Planner (or any other untrusted source) must
pass through this module before anything else looks at it. The rules follow
``.github/ai/policy/POLICY.md`` section 4 and are deliberately strict: a path
that is unusual, ambiguous or merely *could* be interpreted differently on
another platform is rejected rather than repaired.

This module decides whether a path is a *valid, unambiguous* repository path
and enforces the hard path restrictions of POLICY.md section 8 (``.github``
and ``.env*`` segments). It does **not** assign risk levels: it reports facts
(:class:`ValidatedPath`: change type, Git entry kind, new top-level entry) for
the Risk Policy (T3) to classify. It is not a secret detector.

Design constraints:

* Standard library only.
* Pure string processing. Nothing here touches the filesystem, resolves paths
  or follows symlinks; existence is decided only against a snapshot of the Git
  index (:class:`RepoIndex`), never against the working tree.
* No subprocess receives an untrusted value. :meth:`RepoIndex.from_git` runs
  ``git`` with fixed argument vectors, no shell and a scrubbed ``GIT_*``
  environment, and only at the verified worktree root.
* Error messages never echo the raw input (it may contain control or bidi
  characters); errors carry a stable ``code`` and the item position instead.

Literal-path contract (for every downstream consumer):

* A validated path is a literal, repository-relative POSIX path. It is never a
  glob or pattern. ``[id]``, ``[...path]``, ``[action]``, ``(group)`` and
  ``@slot`` are ordinary characters of a Next.js route segment.
* Never apply ``fnmatch``, ``glob``, shell expansion or any implicit wildcard
  matching to a validated path; compare paths with string equality or
  segment-wise prefix checks only.
* Git commands that receive a validated path must use ``--literal-pathspecs``
  or the ``:(literal)`` pathspec magic (see :meth:`ValidatedPath.git_pathspec`)
  and must separate options from paths with ``--``.
* Never interpolate a path into a shell command; pass it as one element of an
  argument vector.
"""

from __future__ import annotations

import enum
import os
import shutil
import subprocess
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

MAX_PATH_LENGTH = 200
MAX_SEGMENTS = 20
MAX_SEGMENT_LENGTH = 100
MAX_CHANGES = 50

# Allowlist. Tracked paths today use only ``[-./0-9A-Za-z[\]_]``; ``()`` and
# ``@`` are added for Next.js route groups and parallel routes. Anything else
# (spaces, non-ASCII letters, look-alike separators, ``%``, ``*``, ``?``,
# ``\\``, ``:`` ...) is rejected.
_ALLOWED_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-[]()@/"
)

# Characters that could be read as a path separator by a human, a terminal
# or another platform.
_SEPARATOR_LOOKALIKES = frozenset(
    "\u2044"  # FRACTION SLASH
    "\u2215"  # DIVISION SLASH
    "\u2216"  # SET MINUS
    "\u29f5"  # REVERSE SOLIDUS OPERATOR
    "\u29f8"  # BIG SOLIDUS
    "\u29f9"  # BIG REVERSE SOLIDUS
    "\ufe68"  # SMALL REVERSE SOLIDUS
    "\uff0f"  # FULLWIDTH SOLIDUS
    "\uff3c"  # FULLWIDTH REVERSE SOLIDUS
    "\u2571"  # BOX DRAWINGS LIGHT DIAGONAL UPPER RIGHT TO LOWER LEFT
    "\u2572"  # BOX DRAWINGS LIGHT DIAGONAL UPPER LEFT TO LOWER RIGHT
)

# Windows device names are reserved with any extension (``con.txt``).
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)

# Git index modes. Anything else (including sparse-index directory entries,
# mode 040000) makes the index snapshot malformed.
MODE_FILE = "100644"
MODE_EXECUTABLE = "100755"
MODE_SYMLINK = "120000"
MODE_GITLINK = "160000"

# Hard path restrictions (POLICY.md section 8). Always applied; callers can only
# add restrictions. Compared case-insensitively against every path segment.
FORBIDDEN_SEGMENTS: frozenset[str] = frozenset({".github"})
FORBIDDEN_SEGMENT_PREFIXES: tuple[str, ...] = (".env",)

_HEX = frozenset("0123456789abcdef")
_OBJECT_ID_LENGTHS = frozenset({40, 64})  # SHA-1, SHA-256
_STAGES = frozenset({"0", "1", "2", "3"})


class ChangeType(enum.StrEnum):
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"


class EntryKind(enum.StrEnum):
    """Git index type of the target. Symlinks and submodules are never followed
    and never treated as ordinary files; the Risk Policy classifies them."""

    NEW = "new"
    REGULAR_FILE = "regular_file"
    EXECUTABLE_FILE = "executable_file"
    SYMLINK = "symlink"
    SUBMODULE = "submodule"


_KIND_BY_MODE: Mapping[str, EntryKind] = {
    MODE_FILE: EntryKind.REGULAR_FILE,
    MODE_EXECUTABLE: EntryKind.EXECUTABLE_FILE,
    MODE_SYMLINK: EntryKind.SYMLINK,
    MODE_GITLINK: EntryKind.SUBMODULE,
}


class PathErrorCode(enum.StrEnum):
    NOT_A_STRING = "not_a_string"
    EMPTY = "empty"
    TOO_LONG = "too_long"
    TOO_DEEP = "too_deep"
    SEGMENT_TOO_LONG = "segment_too_long"
    NUL_OR_CONTROL = "nul_or_control"
    BIDI_OR_INVISIBLE = "bidi_or_invisible"
    WHITESPACE = "whitespace"
    SEPARATOR_LOOKALIKE = "separator_lookalike"
    UNICODE_CONFUSABLE = "unicode_confusable"
    NON_ASCII = "non_ascii"
    BACKSLASH = "backslash"
    DRIVE_OR_COLON = "drive_or_colon"
    ABSOLUTE = "absolute"
    PERCENT_ENCODED = "percent_encoded"
    WILDCARD = "wildcard"
    DISALLOWED_CHARACTER = "disallowed_character"
    EMPTY_SEGMENT = "empty_segment"
    DOT_SEGMENT = "dot_segment"
    TRAVERSAL = "traversal"
    TRAILING_DOT = "trailing_dot"
    WINDOWS_RESERVED = "windows_reserved"
    GIT_INTERNAL = "git_internal"
    # Checks against the Git index.
    NOT_TRACKED = "not_tracked"
    CASE_MISMATCH = "case_mismatch"
    ALREADY_TRACKED = "already_tracked"
    CASE_COLLISION = "case_collision"
    IS_DIRECTORY = "is_directory"
    PARENT_NOT_DIRECTORY = "parent_not_directory"
    AMBIGUOUS_INDEX_ENTRY = "ambiguous_index_entry"
    FORBIDDEN_AREA = "forbidden_area"
    INVALID_RESTRICTION = "invalid_restriction"
    INVALID_CHANGE_TYPE = "invalid_change_type"
    # Checks across a set of paths.
    INVALID_ITEM = "invalid_item"
    TOO_MANY_ITEMS = "too_many_items"
    EMPTY_CHANGE_SET = "empty_change_set"
    DUPLICATE_PATH = "duplicate_path"
    CASE_DUPLICATE = "case_duplicate"
    PATH_CONFLICT = "path_conflict"


class PathValidationError(ValueError):
    """A path was rejected. ``code`` is stable; the raw input is not echoed."""

    def __init__(self, code: PathErrorCode, *, index: int | None = None) -> None:
        self.code = code
        self.index = index
        where = f" (item {index})" if index is not None else ""
        super().__init__(f"path rejected: {code.value}{where}")


class RepoIndexErrorCode(enum.StrEnum):
    GIT_UNAVAILABLE = "git_unavailable"
    GIT_FAILED = "git_failed"
    NOT_WORKTREE_ROOT = "not_worktree_root"
    MALFORMED_INDEX = "malformed_index"


class RepoIndexError(RuntimeError):
    """The Git index snapshot could not be obtained safely. Always fail closed."""

    def __init__(self, code: RepoIndexErrorCode) -> None:
        self.code = code
        super().__init__(f"repository index unavailable: {code.value}")


@dataclass(frozen=True, slots=True)
class ValidatedPath:
    """A validated change. Facts only; risk is decided by the Risk Policy.

    ``kind`` is :attr:`EntryKind.NEW` for ``add`` and the Git index type of the
    existing entry for ``modify``/``delete``. ``new_top_level`` is true for an
    ``add`` at the repository root or in a top-level directory that does not
    exist yet (POLICY.md: L3).
    """

    path: str
    change: ChangeType
    kind: EntryKind
    new_top_level: bool = False

    @property
    def git_pathspec(self) -> str:
        """Literal Git pathspec for this path; pass it after ``--``."""

        return ":(literal)" + self.path


def _is_invisible(char: str) -> bool:
    # Cf: format characters - zero-width (U+200B..U+200D), bidi controls
    # (U+202A..U+202E, U+2066..U+2069), BOM, soft hyphen, ...
    return unicodedata.category(char) == "Cf"


def _is_control(char: str) -> bool:
    return unicodedata.category(char) in {"Cc", "Cs", "Co", "Cn"}


def _check_characters(raw: str) -> None:
    """Reject characters, most specific reason first."""

    for char in raw:
        if _is_control(char):
            raise PathValidationError(PathErrorCode.NUL_OR_CONTROL)
    for char in raw:
        if _is_invisible(char):
            raise PathValidationError(PathErrorCode.BIDI_OR_INVISIBLE)
    for char in raw:
        if char.isspace() or unicodedata.category(char) in {"Zs", "Zl", "Zp"}:
            raise PathValidationError(PathErrorCode.WHITESPACE)
    for char in raw:
        if char in _SEPARATOR_LOOKALIKES:
            raise PathValidationError(PathErrorCode.SEPARATOR_LOOKALIKE)
    if not raw.isascii():
        # A compatibility form that folds to ASCII (fullwidth letters,
        # ligatures, ...) is a deliberate look-alike, not a real name.
        folded = unicodedata.normalize("NFKC", raw)
        if folded != raw and folded.isascii():
            raise PathValidationError(PathErrorCode.UNICODE_CONFUSABLE)
        raise PathValidationError(PathErrorCode.NON_ASCII)
    if "\\" in raw:
        raise PathValidationError(PathErrorCode.BACKSLASH)
    if ":" in raw:
        raise PathValidationError(PathErrorCode.DRIVE_OR_COLON)
    if "%" in raw:
        raise PathValidationError(PathErrorCode.PERCENT_ENCODED)
    if "*" in raw or "?" in raw or "{" in raw or "}" in raw:
        raise PathValidationError(PathErrorCode.WILDCARD)
    for char in raw:
        if char not in _ALLOWED_CHARS:
            raise PathValidationError(PathErrorCode.DISALLOWED_CHARACTER)


def _check_segment(segment: str) -> None:
    if segment == "":
        raise PathValidationError(PathErrorCode.EMPTY_SEGMENT)
    if segment == ".":
        raise PathValidationError(PathErrorCode.DOT_SEGMENT)
    if segment == "..":
        raise PathValidationError(PathErrorCode.TRAVERSAL)
    if len(segment) > MAX_SEGMENT_LENGTH:
        raise PathValidationError(PathErrorCode.SEGMENT_TOO_LONG)
    # Windows strips trailing dots ("a." == "a"); "..." is also ambiguous.
    if segment.endswith("."):
        raise PathValidationError(PathErrorCode.TRAILING_DOT)
    if segment.casefold() == ".git":
        raise PathValidationError(PathErrorCode.GIT_INTERNAL)
    if segment.split(".", 1)[0].casefold() in _WINDOWS_RESERVED:
        raise PathValidationError(PathErrorCode.WINDOWS_RESERVED)


def normalize_path(raw: object) -> str:
    """Return the canonical form of a repository-relative path, or raise.

    The only normalisation performed is the removal of one leading ``./``.
    Anything that would need further interpretation is rejected; in particular
    non-ASCII input is rejected, never Unicode-normalised. The result is
    ASCII and ``normalize_path`` is idempotent.
    """

    if not isinstance(raw, str):
        raise PathValidationError(PathErrorCode.NOT_A_STRING)
    if raw == "":
        raise PathValidationError(PathErrorCode.EMPTY)
    # Bound the work done on hostile input before any per-character scan.
    if len(raw) > MAX_PATH_LENGTH + 2:
        raise PathValidationError(PathErrorCode.TOO_LONG)

    _check_characters(raw)

    path = raw[2:] if raw.startswith("./") else raw
    if path == "":
        raise PathValidationError(PathErrorCode.EMPTY)
    if path.startswith("/"):
        raise PathValidationError(PathErrorCode.ABSOLUTE)
    if len(path) > MAX_PATH_LENGTH:
        raise PathValidationError(PathErrorCode.TOO_LONG)

    segments = path.split("/")
    if len(segments) > MAX_SEGMENTS:
        raise PathValidationError(PathErrorCode.TOO_DEEP)
    for segment in segments:
        _check_segment(segment)
    return path


def _is_canonical(path: str) -> bool:
    try:
        return normalize_path(path) == path
    except PathValidationError:
        return False


# ------------------------------------------------------------------ Git index


@dataclass(frozen=True, slots=True)
class _Record:
    path: str
    mode: str
    stage: str
    utf8: bool


def _malformed() -> RepoIndexError:
    return RepoIndexError(RepoIndexErrorCode.MALFORMED_INDEX)


def _parse_record(chunk: bytes) -> _Record:
    """Parse one ``<mode> <object> <stage>\\t<path>`` record strictly."""

    meta, sep, raw_path = chunk.partition(b"\t")
    fields = meta.split(b" ")
    if not sep or len(fields) != 3 or not raw_path:
        raise _malformed()
    try:
        mode, object_id, stage = (field.decode("ascii") for field in fields)
    except UnicodeDecodeError:
        raise _malformed() from None
    if (
        mode not in _KIND_BY_MODE
        or len(object_id) not in _OBJECT_ID_LENGTHS
        or not set(object_id) <= _HEX
        or stage not in _STAGES
        or raw_path.endswith(b"/")  # sparse-index directory entry
    ):
        raise _malformed()
    try:
        return _Record(raw_path.decode("utf-8"), mode, stage, True)
    except UnicodeDecodeError:
        return _Record(raw_path.decode("utf-8", errors="surrogateescape"), mode, stage, False)


def _git_environment() -> dict[str, str]:
    """Inherited environment without any ``GIT_*`` variable.

    Trust model:

    * Every inherited ``GIT_*`` variable is dropped. Variables such as
      ``GIT_DIR``, ``GIT_WORK_TREE``, ``GIT_INDEX_FILE``, ``GIT_COMMON_DIR``,
      ``GIT_OBJECT_DIRECTORY``, ``GIT_CEILING_DIRECTORIES``,
      ``GIT_CONFIG_PARAMETERS`` or ``GIT_CONFIG_COUNT``/``KEY``/``VALUE`` could
      redirect Git to another repository or index or inject configuration.
    * ``GIT_CONFIG_GLOBAL`` and ``GIT_CONFIG_SYSTEM`` are not trusted and are
      dropped too, so a ``safe.directory`` set only through them is **not**
      honoured (Git then fails with ``git_failed``).
    * ``HOME`` and ``XDG_CONFIG_HOME`` are preserved: global Git configuration
      read through them (``~/.gitconfig``, ``$XDG_CONFIG_HOME/git/config``) and
      the system configuration are part of the trusted environment, as is
      ``PATH`` (which provides the ``git`` executable).
    * ``core.fsmonitor=false`` is always passed on the command line, which
      overrides any configured fsmonitor hook.
    """

    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _run_git(git: str, repo_root: Path, *args: str) -> bytes:
    # core.fsmonitor=false: never let repository config run a hook here.
    argv = [git, "-c", "core.fsmonitor=false", "-C", str(repo_root), *args]
    try:
        result = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
            argv,
            check=False,
            capture_output=True,
            timeout=60,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        raise RepoIndexError(RepoIndexErrorCode.GIT_FAILED) from None
    if result.returncode != 0:
        raise RepoIndexError(RepoIndexErrorCode.GIT_FAILED)
    return result.stdout


class RepoIndex:
    """Immutable snapshot of tracked paths from the Git index.

    Existence checks are exact and case-sensitive. Case-insensitive lookups are
    used only to *detect* collisions, never to accept a path. Entries that are
    not canonical paths (unmerged stages, non-UTF-8, non-NFC, or failing
    :func:`normalize_path`) are kept but marked invalid, so they can never be
    the target of a change.
    """

    def __init__(self, entries: Mapping[str, str]) -> None:
        """``entries`` maps a tracked path to its Git mode (e.g. ``100644``)."""

        for path, mode in entries.items():
            if mode not in _KIND_BY_MODE or not path or path.endswith("/"):
                raise _malformed()
        self._build(_Record(path, mode, "0", True) for path, mode in entries.items())

    def _build(self, records: Iterable[_Record]) -> None:
        self._modes: dict[str, str] = {}
        self._invalid: set[str] = set()
        for record in records:
            path = record.path
            if (
                path in self._modes  # several merge stages: unresolved conflict
                or record.stage != "0"
                or not record.utf8
                or unicodedata.normalize("NFC", path) != path
                or not _is_canonical(path)
            ):
                self._invalid.add(path)
            self._modes[path] = record.mode
        self._dirs: set[str] = set()
        for path in self._modes:
            parts = path.split("/")
            for depth in range(1, len(parts)):
                self._dirs.add("/".join(parts[:depth]))
        self._folded: dict[str, set[str]] = {}
        for name in [*self._modes, *self._dirs]:
            self._folded.setdefault(name.casefold(), set()).add(name)

    @classmethod
    def from_ls_files_stage(cls, data: bytes) -> RepoIndex:
        """Parse the output of ``git ls-files --stage -z`` strictly.

        Raises :class:`RepoIndexError` (``malformed_index``) for truncated
        output, empty records, unknown modes (including directory entries),
        invalid object IDs or stages, and empty paths.
        """

        if data and not data.endswith(b"\0"):
            raise _malformed()
        chunks = data.split(b"\0")[:-1] if data else []
        records = []
        for chunk in chunks:
            if not chunk:
                raise _malformed()
            records.append(_parse_record(chunk))
        index = cls.__new__(cls)
        index._build(records)
        return index

    @classmethod
    def from_git(cls, repo_root: Path) -> RepoIndex:
        """Snapshot the index of the worktree whose root is ``repo_root``.

        ``repo_root`` must be the top level of a non-bare worktree; the main
        worktree and linked worktrees (``git worktree add``) are supported.
        Errors (all fail closed):

        * ``git_unavailable`` - no ``git`` executable on ``PATH``;
        * ``git_failed`` - a Git command could not run or exited non-zero
          (for example: not a repository, missing directory, "dubious
          ownership" without a trusted ``safe.directory``);
        * ``not_worktree_root`` - the root probe succeeded but ``repo_root``
          is a subdirectory, a ``.git`` or worktree administrative directory,
          or a bare repository;
        * ``malformed_index`` - the index listing is malformed.

        Git runs with fixed arguments, no shell, ``core.fsmonitor=false`` and
        none of the inherited ``GIT_*`` variables (see :func:`_git_environment`).
        """

        git = shutil.which("git")
        if git is None:
            raise RepoIndexError(RepoIndexErrorCode.GIT_UNAVAILABLE)
        probe = _run_git(
            git,
            repo_root,
            "rev-parse",
            "--is-inside-work-tree",
            "--is-inside-git-dir",
            "--is-bare-repository",
            "--show-prefix",
        )
        # At the worktree root --show-prefix prints an empty line.
        if probe != b"true\nfalse\nfalse\n\n":
            raise RepoIndexError(RepoIndexErrorCode.NOT_WORKTREE_ROOT)
        data = _run_git(git, repo_root, "ls-files", "--stage", "--full-name", "-z")
        return cls.from_ls_files_stage(data)

    def is_tracked(self, path: str) -> bool:
        return path in self._modes

    def mode(self, path: str) -> str | None:
        return self._modes.get(path)

    def tracked_paths(self) -> frozenset[str]:
        return frozenset(self._modes)

    def is_directory(self, path: str) -> bool:
        return path in self._dirs

    def is_invalid(self, path: str) -> bool:
        return path in self._invalid

    def case_variants(self, path: str) -> set[str]:
        """Tracked files or directories equal to ``path`` ignoring case."""

        return set(self._folded.get(path.casefold(), set()))

    def top_level_directories(self) -> set[str]:
        return {d for d in self._dirs if "/" not in d}


# ------------------------------------------------------------- restrictions


def _check_hard_restrictions(path: str) -> None:
    for segment in path.casefold().split("/"):
        if segment in FORBIDDEN_SEGMENTS or segment.startswith(FORBIDDEN_SEGMENT_PREFIXES):
            raise PathValidationError(PathErrorCode.FORBIDDEN_AREA)


def is_forbidden_path(path: str) -> bool:
    """True if ``path`` has a ``.github`` segment or a segment starting with ``.env``."""

    try:
        _check_hard_restrictions(path)
    except PathValidationError:
        return True
    return False


def _normalize_restrictions(extra: Iterable[str]) -> tuple[str, ...]:
    """Validate caller-supplied restrictions (literal paths or directories)."""

    if isinstance(extra, (str, bytes)):
        raise PathValidationError(PathErrorCode.INVALID_RESTRICTION)
    restrictions: list[str] = []
    for entry in extra:
        try:
            restrictions.append(normalize_path(entry).casefold())
        except PathValidationError:
            raise PathValidationError(PathErrorCode.INVALID_RESTRICTION) from None
    return tuple(restrictions)


def _check_extra_restrictions(path: str, restrictions: tuple[str, ...]) -> None:
    folded = path.casefold()
    for restriction in restrictions:
        if folded == restriction or folded.startswith(restriction + "/"):
            raise PathValidationError(PathErrorCode.FORBIDDEN_AREA)


# ------------------------------------------------------------------ changes


def _ancestors(path: str) -> list[str]:
    parts = path.split("/")
    return ["/".join(parts[:depth]) for depth in range(1, len(parts))]


def _check_unambiguous_ancestors(path: str, index: RepoIndex) -> None:
    # "docs" and "Docs" both tracked: the target directory is ambiguous on a
    # case-insensitive filesystem.
    for ancestor in _ancestors(path):
        if len(index.case_variants(ancestor)) > 1:
            raise PathValidationError(PathErrorCode.AMBIGUOUS_INDEX_ENTRY)


def _check_existing(path: str, index: RepoIndex) -> EntryKind:
    if index.is_invalid(path):
        raise PathValidationError(PathErrorCode.AMBIGUOUS_INDEX_ENTRY)
    if not index.is_tracked(path):
        if index.is_directory(path):
            raise PathValidationError(PathErrorCode.IS_DIRECTORY)
        if index.case_variants(path):
            raise PathValidationError(PathErrorCode.CASE_MISMATCH)
        raise PathValidationError(PathErrorCode.NOT_TRACKED)
    if len(index.case_variants(path)) > 1:
        raise PathValidationError(PathErrorCode.AMBIGUOUS_INDEX_ENTRY)
    mode = index.mode(path)
    if mode is None or mode not in _KIND_BY_MODE:  # unreachable: modes are validated
        raise PathValidationError(PathErrorCode.AMBIGUOUS_INDEX_ENTRY)
    return _KIND_BY_MODE[mode]


def _check_new(path: str, index: RepoIndex) -> bool:
    """Validate an addition; return whether it creates a new top-level entry."""

    if index.is_tracked(path):
        raise PathValidationError(PathErrorCode.ALREADY_TRACKED)
    if index.is_directory(path):
        raise PathValidationError(PathErrorCode.IS_DIRECTORY)
    if index.case_variants(path):
        raise PathValidationError(PathErrorCode.CASE_COLLISION)
    for ancestor in _ancestors(path):
        if index.is_tracked(ancestor):
            # The parent is a tracked file, symlink or submodule.
            raise PathValidationError(PathErrorCode.PARENT_NOT_DIRECTORY)
        if not index.is_directory(ancestor) and index.case_variants(ancestor):
            raise PathValidationError(PathErrorCode.CASE_COLLISION)
    first = path.split("/", 1)[0]
    return "/" not in path or first not in index.top_level_directories()


def _parse_change_type(change: object) -> ChangeType:
    if isinstance(change, str):
        try:
            return ChangeType(change)
        except ValueError:
            pass
    raise PathValidationError(PathErrorCode.INVALID_CHANGE_TYPE)


def _validate_one(
    raw: object, change: object, index: RepoIndex, restrictions: tuple[str, ...]
) -> ValidatedPath:
    change_type = _parse_change_type(change)
    path = normalize_path(raw)
    _check_hard_restrictions(path)
    _check_extra_restrictions(path, restrictions)
    _check_unambiguous_ancestors(path, index)
    if change_type is ChangeType.ADD:
        new_top_level = _check_new(path, index)
        return ValidatedPath(path, change_type, EntryKind.NEW, new_top_level)
    return ValidatedPath(path, change_type, _check_existing(path, index))


def validate_change(
    raw: object,
    change: object,
    index: RepoIndex,
    *,
    extra_forbidden: Iterable[str] = (),
) -> ValidatedPath:
    """Validate one proposed change against the Git index snapshot.

    The hard restrictions (``.github`` and ``.env*`` segments) always apply.
    ``extra_forbidden`` can only add literal paths or directories to them.
    """

    return _validate_one(raw, change, index, _normalize_restrictions(extra_forbidden))


def validate_changes(
    items: Iterable[object],
    index: RepoIndex,
    *,
    extra_forbidden: Iterable[str] = (),
) -> list[ValidatedPath]:
    """Validate a whole change set. Any invalid item rejects the whole set.

    Each item must be a ``(path, change_type)`` tuple. At most
    :data:`MAX_CHANGES` items are read; an empty set is not an executable
    change set. The error ``index`` is the smallest position ``i`` such that
    ``items[0..i]`` is invalid: item ``i`` is checked for shape, then on its
    own, then against the items before it (duplicate, case duplicate,
    file/directory conflict).
    """

    restrictions = _normalize_restrictions(extra_forbidden)
    validated: list[ValidatedPath] = []
    exact: set[str] = set()
    folded_paths: set[str] = set()
    folded_ancestors: set[str] = set()
    for position, item in enumerate(items):
        if position >= MAX_CHANGES:
            raise PathValidationError(PathErrorCode.TOO_MANY_ITEMS, index=position)
        if not isinstance(item, tuple) or len(item) != 2:
            raise PathValidationError(PathErrorCode.INVALID_ITEM, index=position)
        raw, change = item
        try:
            result = _validate_one(raw, change, index, restrictions)
        except PathValidationError as error:
            raise PathValidationError(error.code, index=position) from None
        folded = result.path.casefold()
        if result.path in exact:
            raise PathValidationError(PathErrorCode.DUPLICATE_PATH, index=position)
        if folded in folded_paths:
            raise PathValidationError(PathErrorCode.CASE_DUPLICATE, index=position)
        ancestors = set(_ancestors(folded))
        if ancestors & folded_paths or folded in folded_ancestors:
            raise PathValidationError(PathErrorCode.PATH_CONFLICT, index=position)
        exact.add(result.path)
        folded_paths.add(folded)
        folded_ancestors |= ancestors
        validated.append(result)
    if not validated:
        raise PathValidationError(PathErrorCode.EMPTY_CHANGE_SET)
    return validated
