"""Tests for orchestrator.paths (T2, T2.1). Offline; table-driven plus seeded fuzzing."""

from __future__ import annotations

import fnmatch
import itertools
import random
import shutil
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from orchestrator import paths as paths_module
from orchestrator.paths import (
    MAX_CHANGES,
    MAX_PATH_LENGTH,
    MODE_EXECUTABLE,
    MODE_FILE,
    MODE_GITLINK,
    MODE_SYMLINK,
    ChangeType,
    EntryKind,
    PathErrorCode,
    PathValidationError,
    RepoIndex,
    RepoIndexError,
    RepoIndexErrorCode,
    ValidatedPath,
    normalize_path,
    validate_change,
    validate_changes,
)

E = PathErrorCode
K = EntryKind
R = RepoIndexErrorCode

# Synthetic index shaped like the real repository.
INDEX = RepoIndex(
    {
        "README.md": MODE_FILE,
        ".env.example": MODE_FILE,
        ".github/workflows/ci.yml": MODE_FILE,
        "backend/app/api/deposits.py": MODE_FILE,
        "backend/app/models/user.py": MODE_FILE,
        "backend/app/services/finance/deposit.py": MODE_FILE,
        "backend/scripts/backup.sh": MODE_EXECUTABLE,
        "docs/design/USER_FLOWS.md": MODE_FILE,
        "docs/link": MODE_SYMLINK,
        "frontend/app/deposits/[id]/page.tsx": MODE_FILE,
        "frontend/app/api/v1/[...path]/route.ts": MODE_FILE,
        "frontend/app/api/session/[action]/route.ts": MODE_FILE,
        "frontend/components/deposits/deposit-form.tsx": MODE_FILE,
        "vendor/sub": MODE_GITLINK,
    }
)

# Two segments of 99 + 100 characters joined by "/": 200 characters.
LONGEST = "x" * 99 + "/" + "x" * 100
assert len(LONGEST) == MAX_PATH_LENGTH


def code_of(raw: object) -> PathErrorCode:
    with pytest.raises(PathValidationError) as info:
        normalize_path(raw)
    return info.value.code


def change_code(raw: object, change: object, index: RepoIndex = INDEX) -> PathErrorCode:
    with pytest.raises(PathValidationError) as info:
        validate_change(raw, change, index)
    return info.value.code


def set_error(items: list[object], index: RepoIndex = INDEX) -> tuple[PathErrorCode, int | None]:
    with pytest.raises(PathValidationError) as info:
        validate_changes(items, index)
    return info.value.code, info.value.index


# --------------------------------------------------------------- normalize_path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("README.md", "README.md"),
        ("./docs/design/USER_FLOWS.md", "docs/design/USER_FLOWS.md"),
        ("frontend/app/deposits/[id]/page.tsx", "frontend/app/deposits/[id]/page.tsx"),
        ("frontend/app/api/v1/[...path]/route.ts", "frontend/app/api/v1/[...path]/route.ts"),
        (
            "frontend/app/api/session/[action]/route.ts",
            "frontend/app/api/session/[action]/route.ts",
        ),
        ("frontend/app/[[...slug]]/page.tsx", "frontend/app/[[...slug]]/page.tsx"),
        ("frontend/app/(marketing)/page.tsx", "frontend/app/(marketing)/page.tsx"),
        ("frontend/app/@modal/page.tsx", "frontend/app/@modal/page.tsx"),
        (".env.example", ".env.example"),  # valid syntax; forbidden at change level
        (".prettierrc", ".prettierrc"),
        ("a.b.c", "a.b.c"),
        (LONGEST, LONGEST),  # exactly MAX_PATH_LENGTH
        ("./" + LONGEST, LONGEST),
        ("a/" + "x" * 100, "a/" + "x" * 100),  # longest segment
    ],
)
def test_accepts_valid_paths(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # empty / type
        ("", E.EMPTY),
        ("./", E.EMPTY),
        (None, E.NOT_A_STRING),
        (b"README.md", E.NOT_A_STRING),
        (1, E.NOT_A_STRING),
        (["README.md"], E.NOT_A_STRING),
        # absolute, traversal, dot segments
        ("/etc/passwd", E.ABSOLUTE),
        ("//server/share/x", E.ABSOLUTE),
        ("..", E.TRAVERSAL),
        ("../README.md", E.TRAVERSAL),
        ("a/../b", E.TRAVERSAL),
        ("backend/app/../alembic/env.py", E.TRAVERSAL),
        ("./../x", E.TRAVERSAL),
        (".", E.DOT_SEGMENT),
        ("a/./b", E.DOT_SEGMENT),
        ("././a", E.DOT_SEGMENT),
        ("a//b", E.EMPTY_SEGMENT),
        ("a/", E.EMPTY_SEGMENT),
        # Windows / POSIX confusion
        ("backend\\app\\models\\user.py", E.BACKSLASH),
        ("a/..\\b", E.BACKSLASH),
        ("C:\\Windows", E.BACKSLASH),
        ("C:/Windows/x", E.DRIVE_OR_COLON),
        ("README.md:stream", E.DRIVE_OR_COLON),
        (":(literal)README.md", E.DRIVE_OR_COLON),  # Git pathspec magic
        ("file.txt.", E.TRAILING_DOT),
        ("a/...", E.TRAILING_DOT),
        ("con.txt", E.WINDOWS_RESERVED),
        ("docs/CON", E.WINDOWS_RESERVED),
        ("docs/Lpt1.md", E.WINDOWS_RESERVED),
        ("docs/nul", E.WINDOWS_RESERVED),
        ("docs/PROGRA~1/x", E.DISALLOWED_CHARACTER),
        # percent-encoding and wildcards
        ("%2e%2e/README.md", E.PERCENT_ENCODED),
        ("docs%2Fdesign", E.PERCENT_ENCODED),
        ("docs/100%", E.PERCENT_ENCODED),
        ("docs/*.md", E.WILDCARD),
        ("docs/?.md", E.WILDCARD),
        ("docs/**", E.WILDCARD),
        ("docs/{a,b}.md", E.WILDCARD),
        # control characters
        ("README.md\x00", E.NUL_OR_CONTROL),
        ("a\x00/../b", E.NUL_OR_CONTROL),
        ("a\nb", E.NUL_OR_CONTROL),
        ("a\tb", E.NUL_OR_CONTROL),
        ("a\rb", E.NUL_OR_CONTROL),
        ("a\x7fb", E.NUL_OR_CONTROL),
        ("a\x1bb", E.NUL_OR_CONTROL),
        ("a\ud800b", E.NUL_OR_CONTROL),  # lone surrogate
        ("a\U000e0001b", E.BIDI_OR_INVISIBLE),  # language tag (Cf)
        # whitespace
        ("README.md ", E.WHITESPACE),
        (" README.md", E.WHITESPACE),
        ("docs /a.md", E.WHITESPACE),
        ("docs/a b.md", E.WHITESPACE),
        ("a\u00a0b", E.WHITESPACE),  # NO-BREAK SPACE
        ("a\u3000b", E.WHITESPACE),  # IDEOGRAPHIC SPACE
        ("a\u2028b", E.WHITESPACE),  # LINE SEPARATOR
        # bidi / invisible
        ("a\u202eb", E.BIDI_OR_INVISIBLE),  # RIGHT-TO-LEFT OVERRIDE
        ("a\u2066b", E.BIDI_OR_INVISIBLE),  # LEFT-TO-RIGHT ISOLATE
        ("a\u200bb", E.BIDI_OR_INVISIBLE),  # ZERO WIDTH SPACE
        ("a\u200db", E.BIDI_OR_INVISIBLE),  # ZERO WIDTH JOINER
        ("\ufeffREADME.md", E.BIDI_OR_INVISIBLE),  # BOM
        ("a\u00adb", E.BIDI_OR_INVISIBLE),  # SOFT HYPHEN
        # ambiguous separators
        ("docs\u2215a.md", E.SEPARATOR_LOOKALIKE),  # DIVISION SLASH
        ("docs\u2044a.md", E.SEPARATOR_LOOKALIKE),  # FRACTION SLASH
        ("docs\uff0fa.md", E.SEPARATOR_LOOKALIKE),  # FULLWIDTH SOLIDUS
        ("docs\uff3ca.md", E.SEPARATOR_LOOKALIKE),  # FULLWIDTH REVERSE SOLIDUS
        ("docs\u29f8a.md", E.SEPARATOR_LOOKALIKE),  # BIG SOLIDUS
        # Unicode look-alikes: rejected, never normalised
        ("\uff42ackend/app/x.py", E.UNICODE_CONFUSABLE),  # FULLWIDTH b
        ("docs/\ufb01le.md", E.UNICODE_CONFUSABLE),  # LATIN SMALL LIGATURE FI
        ("\uff0e\uff0e/x", E.UNICODE_CONFUSABLE),  # FULLWIDTH FULL STOPs
        ("b\u0430ckend/app/x.py", E.NON_ASCII),  # CYRILLIC SMALL LETTER A
        ("caf\u00e9/x.md", E.NON_ASCII),  # NFC e-acute
        ("cafe\u0301/x.md", E.NON_ASCII),  # NFD e + COMBINING ACUTE
        ("\u0391PI.md", E.NON_ASCII),  # GREEK CAPITAL ALPHA
        # other characters
        ("a;b", E.DISALLOWED_CHARACTER),
        ("a|b", E.DISALLOWED_CHARACTER),
        ("a$b", E.DISALLOWED_CHARACTER),
        ("a'b", E.DISALLOWED_CHARACTER),
        ('a"b', E.DISALLOWED_CHARACTER),
        ("a<b>", E.DISALLOWED_CHARACTER),
        ("a&b", E.DISALLOWED_CHARACTER),
        ("a+b", E.DISALLOWED_CHARACTER),
        ("a#b", E.DISALLOWED_CHARACTER),
        ("a!b", E.DISALLOWED_CHARACTER),
        ("~/x", E.DISALLOWED_CHARACTER),
        ("$(id)", E.DISALLOWED_CHARACTER),
        ("`id`", E.DISALLOWED_CHARACTER),
        # git internals
        (".git/config", E.GIT_INTERNAL),
        ("x/.GIT/hooks/pre-commit", E.GIT_INTERNAL),
        # length
        ("x" * (MAX_PATH_LENGTH + 1), E.TOO_LONG),
        ("x" * 100_000, E.TOO_LONG),
        ("/".join(["a"] * 21), E.TOO_DEEP),
        ("a/" + "x" * 101, E.SEGMENT_TOO_LONG),
    ],
)
def test_rejects_invalid_paths(raw: object, expected: PathErrorCode) -> None:
    assert code_of(raw) == expected


def test_error_message_does_not_echo_input() -> None:
    hostile = "docs/\u202eSECRET-token-123.md"
    with pytest.raises(PathValidationError) as info:
        normalize_path(hostile)
    assert "SECRET" not in str(info.value)
    assert "\u202e" not in str(info.value)


def test_every_single_code_point_outside_the_allowlist_is_rejected() -> None:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-[]()@/")
    accepted = []
    for code_point in range(0x110000):
        char = chr(code_point)
        try:
            normalize_path("docs/a" + char + "b.md")
        except PathValidationError:
            continue
        accepted.append(char)
    assert set(accepted) <= allowed
    assert set(accepted) == allowed  # every allowed character is usable inside a name


# ------------------------------------------------------------- validate_change


@pytest.mark.parametrize(
    ("raw", "change", "kind", "new_top_level"),
    [
        ("README.md", "modify", K.REGULAR_FILE, False),
        ("README.md", "delete", K.REGULAR_FILE, False),
        ("./backend/app/api/deposits.py", ChangeType.MODIFY, K.REGULAR_FILE, False),
        ("backend/scripts/backup.sh", "modify", K.EXECUTABLE_FILE, False),
        ("frontend/app/deposits/[id]/page.tsx", "modify", K.REGULAR_FILE, False),
        ("frontend/app/api/v1/[...path]/route.ts", "delete", K.REGULAR_FILE, False),
        ("frontend/app/api/session/[action]/route.ts", "modify", K.REGULAR_FILE, False),
        # symlinks and submodules keep their type; T3 classifies them (L3)
        ("docs/link", "modify", K.SYMLINK, False),
        ("docs/link", "delete", K.SYMLINK, False),
        ("vendor/sub", "modify", K.SUBMODULE, False),
        ("vendor/sub", "delete", K.SUBMODULE, False),
        # additions
        ("docs/design/NEW_FLOW.md", "add", K.NEW, False),
        ("frontend/components/newfeature/panel.tsx", "add", K.NEW, False),
        ("frontend/app/deposits/[id]/edit/page.tsx", "add", K.NEW, False),
        ("frontend/app/goals/[goalId]/page.tsx", "add", K.NEW, False),
        # repository root and new top-level directories are valid (T3: L3)
        ("NEW.md", "add", K.NEW, True),
        ("AGENTS.md", "add", K.NEW, True),
        ("newtop/x.md", "add", K.NEW, True),
        ("newtop/a/b/c.md", "add", K.NEW, True),
        # look-alikes of forbidden names are not forbidden
        ("docs/.github-notes.md", "add", K.NEW, False),
        ("docs/github/x.md", "add", K.NEW, False),
        ("docs/env/x.md", "add", K.NEW, False),
        ("docs/x.env", "add", K.NEW, False),
    ],
)
def test_valid_changes(raw: str, change: str, kind: EntryKind, new_top_level: bool) -> None:
    result = validate_change(raw, change, INDEX)
    assert result == ValidatedPath(normalize_path(raw), ChangeType(change), kind, new_top_level)


@pytest.mark.parametrize(
    ("raw", "change", "expected"),
    [
        # modify / delete need an exact tracked entry
        ("backend/app/api/missing.py", "modify", E.NOT_TRACKED),
        ("backend/app/api/missing.py", "delete", E.NOT_TRACKED),
        ("readme.md", "modify", E.CASE_MISMATCH),
        ("Backend/app/api/deposits.py", "delete", E.CASE_MISMATCH),
        ("docs/design", "modify", E.IS_DIRECTORY),
        ("docs/design", "delete", E.IS_DIRECTORY),
        ("docs/link/target.md", "modify", E.NOT_TRACKED),  # never through a symlink
        # add needs an absent path whose parents are directories
        ("README.md", "add", E.ALREADY_TRACKED),
        ("readme.md", "add", E.CASE_COLLISION),
        ("docs/design/user_flows.md", "add", E.CASE_COLLISION),
        ("Docs/new.md", "add", E.CASE_COLLISION),
        ("docs/Design/new.md", "add", E.CASE_COLLISION),
        ("BACKEND/new.py", "add", E.CASE_COLLISION),
        ("docs/design", "add", E.IS_DIRECTORY),
        ("README.md/x.md", "add", E.PARENT_NOT_DIRECTORY),
        ("docs/link/x.md", "add", E.PARENT_NOT_DIRECTORY),  # under a symlink
        ("vendor/sub/x.py", "add", E.PARENT_NOT_DIRECTORY),  # under a submodule
        # hard restriction: any ".github" segment, any change type, any case
        (".github/workflows/ci.yml", "modify", E.FORBIDDEN_AREA),
        (".GitHub/workflows/ci.yml", "modify", E.FORBIDDEN_AREA),
        (".github/ai/policy/new.md", "add", E.FORBIDDEN_AREA),
        (".github/new.yml", "add", E.FORBIDDEN_AREA),
        ("frontend/.github/workflows/x.yml", "add", E.FORBIDDEN_AREA),
        ("docs/.GITHUB/x.md", "add", E.FORBIDDEN_AREA),
        ("docs/.github", "add", E.FORBIDDEN_AREA),
        # hard restriction: any segment starting with ".env", files and directories
        (".env", "add", E.FORBIDDEN_AREA),
        (".env.local", "add", E.FORBIDDEN_AREA),
        (".env.production", "add", E.FORBIDDEN_AREA),
        (".envrc", "add", E.FORBIDDEN_AREA),
        (".env/secrets.json", "add", E.FORBIDDEN_AREA),
        ("backend/.env", "add", E.FORBIDDEN_AREA),
        ("backend/.env.local", "add", E.FORBIDDEN_AREA),
        ("backend/.env/secrets.json", "add", E.FORBIDDEN_AREA),
        ("frontend/.ENV.local", "add", E.FORBIDDEN_AREA),
        ("docs/.environment.md", "add", E.FORBIDDEN_AREA),
        (".env.example", "modify", E.FORBIDDEN_AREA),
        (".env.example", "delete", E.FORBIDDEN_AREA),
        # syntax errors still win over index checks
        ("../README.md", "modify", E.TRAVERSAL),
        ("docs/*.md", "delete", E.WILDCARD),
        # change type is validated strictly
        ("README.md", "rename", E.INVALID_CHANGE_TYPE),
        ("README.md", "MODIFY", E.INVALID_CHANGE_TYPE),
        ("README.md", " modify", E.INVALID_CHANGE_TYPE),
        ("README.md", None, E.INVALID_CHANGE_TYPE),
        ("README.md", 1, E.INVALID_CHANGE_TYPE),
    ],
)
def test_invalid_changes(raw: str, change: object, expected: PathErrorCode) -> None:
    assert change_code(raw, change) == expected


def test_index_with_case_variant_files_is_ambiguous() -> None:
    index = RepoIndex({"docs/A.md": MODE_FILE, "docs/a.md": MODE_FILE})
    assert change_code("docs/a.md", "modify", index) == E.AMBIGUOUS_INDEX_ENTRY
    assert change_code("docs/A.md", "delete", index) == E.AMBIGUOUS_INDEX_ENTRY


def test_index_with_case_variant_directories_is_ambiguous() -> None:
    index = RepoIndex({"docs/a.md": MODE_FILE, "Docs/b.md": MODE_FILE, "backend/x.py": MODE_FILE})
    assert change_code("docs/new.md", "add", index) == E.AMBIGUOUS_INDEX_ENTRY
    assert change_code("Docs/new.md", "add", index) == E.AMBIGUOUS_INDEX_ENTRY
    assert change_code("docs/a.md", "modify", index) == E.AMBIGUOUS_INDEX_ENTRY
    assert validate_change("backend/y.py", "add", index).path == "backend/y.py"


# -------------------------------------------------- hard and extra restrictions


@pytest.mark.parametrize("empty", [(), [], set(), frozenset(), iter(())])
def test_empty_extra_restrictions_do_not_disable_hard_ones(empty: object) -> None:
    with pytest.raises(PathValidationError) as info:
        validate_change(".github/x.yml", "add", INDEX, extra_forbidden=empty)  # type: ignore[arg-type]
    assert info.value.code == E.FORBIDDEN_AREA
    with pytest.raises(PathValidationError) as info:
        validate_change("backend/.env.local", "add", INDEX, extra_forbidden=[])
    assert info.value.code == E.FORBIDDEN_AREA


def test_extra_restrictions_only_extend() -> None:
    extra = ["backend/app/models", "README.md"]
    for raw, change in [
        ("backend/app/models/user.py", "modify"),
        ("backend/app/models/new.py", "add"),
        ("Backend/App/Models/new.py", "add"),
        ("README.md", "delete"),
        (".github/x.yml", "add"),  # hard rule still applies
    ]:
        with pytest.raises(PathValidationError) as info:
            validate_change(raw, change, INDEX, extra_forbidden=extra)
        assert info.value.code in {E.FORBIDDEN_AREA, E.CASE_COLLISION}
    # Literal prefix of a directory, not of a name.
    assert validate_change("backend/app/models_extra.py", "add", INDEX, extra_forbidden=extra)
    with pytest.raises(PathValidationError) as info:
        validate_changes([("README.md", "modify")], INDEX, extra_forbidden=extra)
    assert info.value.code == E.FORBIDDEN_AREA


@pytest.mark.parametrize(
    "extra",
    [["../x"], ["docs/*"], ["docs/"], [""], [None], "backend", b"backend"],
)
def test_invalid_extra_restrictions_are_rejected(extra: object) -> None:
    with pytest.raises(PathValidationError) as info:
        validate_change("README.md", "modify", INDEX, extra_forbidden=extra)  # type: ignore[arg-type]
    assert info.value.code == E.INVALID_RESTRICTION


# ------------------------------------------------------- literal path contract


def test_bracket_paths_are_literal_not_patterns() -> None:
    index = RepoIndex(
        {
            "app/[id]/page.tsx": MODE_FILE,
            "app/i/page.tsx": MODE_FILE,
            "app/d/page.tsx": MODE_FILE,
        }
    )
    literal = validate_change("app/[id]/page.tsx", "modify", index)
    assert literal.path == "app/[id]/page.tsx"
    assert literal.git_pathspec == ":(literal)app/[id]/page.tsx"
    # fnmatch would treat [id] as a character class; never use it on paths.
    assert fnmatch.fnmatchcase("app/i/page.tsx", literal.path)
    # The module compares literally.
    assert index.is_tracked("app/[id]/page.tsx")
    assert not index.is_tracked("app/[i]/page.tsx")
    assert validate_change("app/[i]/page.tsx", "add", index).kind is K.NEW


# ------------------------------------------------------------ RepoIndex parsing

OID = "0" * 40


def _record(mode: str, stage: str, path: bytes, oid: str = OID) -> bytes:
    return mode.encode() + b" " + oid.encode() + b" " + stage.encode() + b"\t" + path + b"\0"


def test_parses_ls_files_stage_output() -> None:
    data = (
        _record(MODE_FILE, "0", b"docs/a.md")
        + _record(MODE_SYMLINK, "0", b"docs/link")
        + _record(MODE_GITLINK, "0", b"vendor/sub", "a" * 40)
        + _record(MODE_EXECUTABLE, "0", b"bin/run", "f" * 64)  # SHA-256 repository
    )
    index = RepoIndex.from_ls_files_stage(data)
    assert index.mode("docs/link") == MODE_SYMLINK
    assert index.is_directory("docs")
    assert validate_change("docs/a.md", "modify", index).kind is K.REGULAR_FILE
    assert validate_change("vendor/sub", "delete", index).kind is K.SUBMODULE
    assert validate_change("bin/run", "modify", index).kind is K.EXECUTABLE_FILE
    assert RepoIndex.from_ls_files_stage(b"").tracked_paths() == frozenset()


def test_unmerged_index_entries_are_ambiguous() -> None:
    data = (
        _record(MODE_FILE, "1", b"docs/c.md")
        + _record(MODE_SYMLINK, "2", b"docs/c.md")
        + _record(MODE_GITLINK, "3", b"docs/c.md")
    )
    index = RepoIndex.from_ls_files_stage(data)
    assert change_code("docs/c.md", "modify", index) == E.AMBIGUOUS_INDEX_ENTRY
    assert change_code("docs/c.md", "add", index) == E.ALREADY_TRACKED
    assert change_code("docs/c.md/x", "add", index) == E.PARENT_NOT_DIRECTORY


@pytest.mark.parametrize(
    "path",
    [
        "docs/cafe\u0301.md".encode(),  # NFD
        b"docs/\xff.md",  # not UTF-8
        b"docs/a\tb.md",  # tab inside the name
        b"docs/a b.md",
        b"docs/new line\nname.md",
        b"../evil.md",
        b"docs/x/../y.md",
        b".git/config",
        b"docs/*.md",
    ],
)
def test_unsafe_index_paths_are_marked_invalid(path: bytes) -> None:
    index = RepoIndex.from_ls_files_stage(_record(MODE_FILE, "0", path))
    (stored,) = index.tracked_paths()
    assert index.is_invalid(stored)


@pytest.mark.parametrize(
    "data",
    [
        b"100644 abc\tdocs/a.md\0",  # two fields
        b"no-tab-here\0",
        b"100644 x 0 docs/a.md\0",  # no tab
        b"100644  0\tdocs/e.md\0",  # empty object id
        _record("abcdef", "0", b"docs/m.md"),  # non-numeric mode
        _record("040000", "0", b"docs/sparse/"),  # sparse directory entry
        _record("040000", "0", b"docs/sparse"),  # tree mode
        _record("100664", "0", b"docs/l.md"),  # legacy mode
        _record(MODE_FILE, "4", b"docs/s.md"),
        _record(MODE_FILE, "x", b"docs/s.md"),
        _record(MODE_FILE, "0", b""),  # empty path
        _record(MODE_FILE, "0", b"docs/dir/"),  # directory entry
        _record(MODE_FILE, "0", b"docs/a.md", "g" * 40),  # not hex
        _record(MODE_FILE, "0", b"docs/a.md", "A" * 40),  # not lower-case hex
        _record(MODE_FILE, "0", b"docs/a.md", "0" * 39),  # wrong length
        "100644 \u00e9 0\tdocs/n.md\0".encode(),  # non-ASCII metadata
        _record(MODE_FILE, "0", b"docs/a.md")[:-1],  # truncated: no final NUL
        _record(MODE_FILE, "0", b"docs/a.md") + b"\0",  # empty record
        b"\0",
    ],
)
def test_malformed_ls_files_output_fails_closed(data: bytes) -> None:
    with pytest.raises(RepoIndexError) as info:
        RepoIndex.from_ls_files_stage(data)
    assert info.value.code == R.MALFORMED_INDEX


@pytest.mark.parametrize(
    "entries",
    [{"docs/a.md": "040000"}, {"docs/a.md": "100664"}, {"": MODE_FILE}, {"docs/": MODE_FILE}],
)
def test_constructor_rejects_malformed_entries(entries: dict[str, str]) -> None:
    with pytest.raises(RepoIndexError) as info:
        RepoIndex(entries)
    assert info.value.code == R.MALFORMED_INDEX


# ------------------------------------------------------------ validate_changes


def test_validates_a_set_of_changes() -> None:
    result = validate_changes(
        [("README.md", "modify"), ("docs/design/NEW.md", "add"), ("NEW.md", "add")],
        INDEX,
    )
    assert [(item.path, item.new_top_level) for item in result] == [
        ("README.md", False),
        ("docs/design/NEW.md", False),
        ("NEW.md", True),
    ]
    assert validate_changes(iter([("README.md", "delete")]), INDEX)[0].change is ChangeType.DELETE


def test_empty_change_set_is_not_executable() -> None:
    assert set_error([]) == (E.EMPTY_CHANGE_SET, None)


def test_change_set_size_is_bounded() -> None:
    items: list[object] = [(f"docs/new/f{i}.md", "add") for i in range(MAX_CHANGES)]
    assert len(validate_changes(items, INDEX)) == MAX_CHANGES
    assert set_error([*items, ("docs/new/extra.md", "add")]) == (E.TOO_MANY_ITEMS, MAX_CHANGES)


def test_unbounded_iterables_are_not_consumed() -> None:
    consumed = 0

    def endless() -> Iterator[object]:
        nonlocal consumed
        for i in itertools.count():
            consumed += 1
            yield (f"docs/new/f{i}.md", "add")

    with pytest.raises(PathValidationError) as info:
        validate_changes(endless(), INDEX)
    assert info.value.code == E.TOO_MANY_ITEMS
    assert consumed == MAX_CHANGES + 1


@pytest.mark.parametrize(
    "item",
    [("README.md",), ("README.md", "modify", "x"), None, "ab", ["README.md", "modify"], 42],
)
def test_malformed_items_have_a_stable_code(item: object) -> None:
    assert set_error([("docs/design/NEW.md", "add"), item]) == (E.INVALID_ITEM, 1)


@pytest.mark.parametrize(
    ("items", "expected", "position"),
    [
        ([("README.md", "modify"), ("./README.md", "modify")], E.DUPLICATE_PATH, 1),
        ([("README.md", "modify"), ("README.md", "delete")], E.DUPLICATE_PATH, 1),
        ([("docs/design/new.md", "add"), ("docs/design/NEW.md", "add")], E.CASE_DUPLICATE, 1),
        ([("docs/design/new", "add"), ("docs/design/new/x.md", "add")], E.PATH_CONFLICT, 1),
        ([("docs/design/new/x.md", "add"), ("docs/design/new", "add")], E.PATH_CONFLICT, 1),
        ([("docs/design/N/x.md", "add"), ("docs/design/n", "add")], E.PATH_CONFLICT, 1),
        ([("README.md", "modify"), ("../etc/passwd", "modify")], E.TRAVERSAL, 1),
        ([("README.md", "modify"), (".github/x.yml", "add")], E.FORBIDDEN_AREA, 1),
        # The first position at which the prefix becomes invalid is reported.
        (
            [("docs/n", "add"), ("docs/n/x.md", "add"), ("../x", "modify")],
            E.PATH_CONFLICT,
            1,
        ),
        ([("../x", "modify"), ("docs/n", "add"), ("docs/n/x.md", "add")], E.TRAVERSAL, 0),
        ([("docs/n", "add"), ("docs/n", "add"), None], E.DUPLICATE_PATH, 1),
    ],
)
def test_invalid_change_sets(items: list[object], expected: PathErrorCode, position: int) -> None:
    assert set_error(items) == (expected, position)


# ----------------------------------------------------- generated (seeded) inputs

_DANGEROUS = [
    "/",
    "\\",
    ".",
    "..",
    "%",
    "*",
    "?",
    ":",
    " ",
    "\x00",
    "\n",
    "\u202e",
    "\u200b",
    "\u2215",
    "\uff0f",
    "\u0430",
    "\uff42",
    "\u00a0",
    "~",
    "{",
    "}",
    "[",
    "]",
    "(",
    ")",
    "@",
    "e\u0301",
    "\ufeff",
]
_SAFE = [*"abcXYZ019_-.", "/", "[", "]"]


def _random_path(rng: random.Random) -> str:
    alphabet = _SAFE * 4 + _DANGEROUS
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))


def test_generated_inputs_either_reject_or_yield_canonical_paths() -> None:
    rng = random.Random(20261123)  # noqa: S311 - deterministic test data
    accepted = 0
    for _ in range(20_000):
        raw = _random_path(rng)
        try:
            path = normalize_path(raw)
        except PathValidationError:
            continue
        accepted += 1
        assert path.isascii()
        assert set(path) <= set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-[]()@/"
        )
        assert 0 < len(path) <= MAX_PATH_LENGTH
        assert not path.startswith("/")
        assert "//" not in path
        assert ".." not in path.split("/")
        assert "." not in path.split("/")
        assert normalize_path(path) == path  # idempotent
    assert accepted > 100  # the generator also produces valid paths


def test_inserting_any_dangerous_character_into_a_valid_path_rejects_it() -> None:
    rng = random.Random(7)  # noqa: S311 - deterministic test data
    base = "frontend/app/deposits/[id]/page.tsx"
    for char in [
        "%",
        "*",
        "?",
        ":",
        " ",
        "\x00",
        "\n",
        "\u202e",
        "\u200b",
        "\u2215",
        "\uff0f",
        "\u0430",
        "\uff42",
        "\u00a0",
        "\\",
        "~",
        "{",
        "\ufeff",
    ]:
        for _ in range(20):
            position = rng.randint(0, len(base))
            with pytest.raises(PathValidationError):
                normalize_path(base[:position] + char + base[position:])


# ------------------------------------------------------- real Git repositories

_GIT = shutil.which("git")
_REPO_ROOT = Path(__file__).resolve().parents[3]
needs_git = pytest.mark.skipif(_GIT is None, reason="git is not installed")


def _git(cwd: Path, *args: str) -> bytes:
    argv = [_GIT or "git", "-C", str(cwd), *args]
    result = subprocess.run(argv, check=True, capture_output=True)  # noqa: S603 - test-only argv
    return result.stdout


def _make_repo(path: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    _git(path, "init", "-q")
    _git(path, "add", "--all")
    return path


def _index_error(root: Path) -> RepoIndexErrorCode:
    with pytest.raises(RepoIndexError) as info:
        RepoIndex.from_git(root)
    return info.value.code


@needs_git
def test_from_git_requires_the_worktree_root(tmp_path: Path) -> None:
    repo = _make_repo(
        tmp_path / "repo",
        {".github/workflows/ci.yml": "x\n", "backend/app.py": "x\n", "README.md": "x\n"},
    )
    index = RepoIndex.from_git(repo)
    assert index.is_tracked(".github/workflows/ci.yml")
    assert change_code(".github/workflows/ci.yml", "modify", index) == E.FORBIDDEN_AREA
    assert _index_error(repo / ".github") == R.NOT_WORKTREE_ROOT
    assert _index_error(repo / ".github" / "workflows") == R.NOT_WORKTREE_ROOT
    assert _index_error(repo / "backend") == R.NOT_WORKTREE_ROOT
    assert _index_error(repo / ".git") == R.NOT_WORKTREE_ROOT
    # A plain directory inside the repository: the probe succeeds, wrong prefix.
    (repo / "untracked-dir").mkdir()
    assert _index_error(repo / "untracked-dir") == R.NOT_WORKTREE_ROOT


@needs_git
def test_from_git_reports_git_failures_as_git_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not a repository / missing directory: the root probe itself fails.
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # dropped by the module
    assert _index_error(plain) == R.GIT_FAILED
    assert _index_error(tmp_path / "missing") == R.GIT_FAILED


@needs_git
def test_dubious_ownership_fails_closed_as_git_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path / "repo", {"docs/a.md": "a\n"})
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    original = paths_module._git_environment

    def different_owner() -> dict[str, str]:
        # Git's own test hook: behave as if the repository had another owner.
        return {**original(), "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}

    monkeypatch.setattr(paths_module, "_git_environment", different_owner)
    assert _index_error(repo) == R.GIT_FAILED

    # safe.directory only through GIT_CONFIG_GLOBAL is not honoured ...
    custom = tmp_path / "custom.gitconfig"
    custom.write_text(f"[safe]\n\tdirectory = {repo}\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(custom))
    assert _index_error(repo) == R.GIT_FAILED
    monkeypatch.delenv("GIT_CONFIG_GLOBAL")

    # ... but the trusted global configuration under HOME is.
    (home / ".gitconfig").write_text(f"[safe]\n\tdirectory = {repo}\n")
    assert RepoIndex.from_git(repo).tracked_paths() == frozenset({"docs/a.md"})


@needs_git
def test_linked_worktrees_are_supported(tmp_path: Path) -> None:
    main = _make_repo(tmp_path / "main", {"docs/a.md": "a\n", "README.md": "r\n"})
    _git(
        main,
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        "init",
    )
    linked = tmp_path / "linked"
    _git(main, "worktree", "add", "-q", "-b", "feature", str(linked))
    assert (linked / ".git").is_file()  # a linked worktree has a .git file
    (linked / "docs" / "only-linked.md").write_text("l\n")
    _git(linked, "add", "docs/only-linked.md")

    index = RepoIndex.from_git(linked)
    assert index.tracked_paths() == frozenset({"README.md", "docs/a.md", "docs/only-linked.md"})
    assert validate_change("docs/only-linked.md", "modify", index).kind is K.REGULAR_FILE
    # The main worktree has its own index and does not see the staged file.
    main_index = RepoIndex.from_git(main)
    assert main_index.tracked_paths() == frozenset({"README.md", "docs/a.md"})
    assert change_code("docs/only-linked.md", "modify", main_index) == E.NOT_TRACKED

    assert _index_error(linked / "docs") == R.NOT_WORKTREE_ROOT
    admin = main / ".git" / "worktrees" / "linked"
    assert admin.is_dir()
    assert _index_error(admin) == R.NOT_WORKTREE_ROOT


@needs_git
def test_from_git_rejects_bare_repositories(tmp_path: Path) -> None:
    bare = tmp_path / "bare.git"
    bare.mkdir()
    _git(bare, "init", "-q", "--bare")
    assert _index_error(bare) == R.NOT_WORKTREE_ROOT


@needs_git
def test_from_git_ignores_git_environment_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path / "repo", {"docs/real.md": "x\n"})
    other = _make_repo(tmp_path / "other", {"docs/other.md": "x\n"})
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'core.fsmonitor'='true'")
    index = RepoIndex.from_git(repo)
    assert index.tracked_paths() == frozenset({"docs/real.md"})
    env = paths_module._git_environment()
    assert not {key for key in env if key.startswith("GIT_")} - {
        "GIT_OPTIONAL_LOCKS",
        "GIT_TERMINAL_PROMPT",
    }


def test_from_git_without_git_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("orchestrator.paths.shutil.which", lambda _name: None)
    assert _index_error(tmp_path) == R.GIT_UNAVAILABLE


@needs_git
def test_symlinks_in_a_real_index_keep_their_type(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "a.md").write_text("a\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret\n")
    (repo / "docs" / "outside").symlink_to(outside, target_is_directory=True)
    (repo / "docs" / "alias.md").symlink_to("a.md")
    _git(repo, "init", "-q")
    _git(repo, "add", "docs")

    index = RepoIndex.from_git(repo)
    assert index.mode("docs/outside") == MODE_SYMLINK
    assert validate_change("docs/alias.md", "modify", index).kind is K.SYMLINK
    assert validate_change("docs/outside", "delete", index).kind is K.SYMLINK
    # The target exists on disk through the symlink, but is never tracked.
    assert (repo / "docs" / "outside" / "secret.md").exists()
    assert change_code("docs/outside/secret.md", "modify", index) == E.NOT_TRACKED
    assert change_code("docs/outside/new.md", "add", index) == E.PARENT_NOT_DIRECTORY
    assert validate_change("docs/a.md", "modify", index).kind is K.REGULAR_FILE


@needs_git
def test_submodules_in_a_real_index_keep_their_type(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo", {"docs/a.md": "a\n"})
    _git(repo, "update-index", "--add", "--cacheinfo", f"{MODE_GITLINK},{'1' * 40},vendor/sub")
    index = RepoIndex.from_git(repo)
    assert validate_change("vendor/sub", "modify", index).kind is K.SUBMODULE
    assert change_code("vendor/sub/x.py", "add", index) == E.PARENT_NOT_DIRECTORY


@needs_git
def test_untracked_files_on_disk_do_not_count_as_existing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "tracked.md").write_text("t\n")
    (repo / "docs" / "untracked.md").write_text("u\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "docs/tracked.md")

    index = RepoIndex.from_git(repo)
    assert change_code("docs/untracked.md", "modify", index) == E.NOT_TRACKED
    assert validate_change("docs/untracked.md", "add", index).change is ChangeType.ADD


@needs_git
def test_git_needs_literal_pathspecs_for_bracket_paths(tmp_path: Path) -> None:
    repo = _make_repo(
        tmp_path / "repo",
        {"app/[id]/page.tsx": "x\n", "app/i/page.tsx": "x\n", "app/d/page.tsx": "x\n"},
    )
    result = validate_change("app/[id]/page.tsx", "modify", RepoIndex.from_git(repo))

    def listed(*args: str) -> set[str]:
        out = _git(repo, *args)
        return {p.decode() for p in out.split(b"\0") if p}

    # Without literal handling Git treats [id] as a character class.
    assert listed("ls-files", "-z", "--", result.path) >= {"app/i/page.tsx", "app/d/page.tsx"}
    # The contract: :(literal) magic, or --literal-pathspecs, after "--".
    assert listed("ls-files", "-z", "--", result.git_pathspec) == {"app/[id]/page.tsx"}
    assert listed("--literal-pathspecs", "ls-files", "-z", "--", result.path) == {
        "app/[id]/page.tsx"
    }


@pytest.mark.skipif(_GIT is None or not (_REPO_ROOT / ".git").exists(), reason="not a git checkout")
def test_this_repository() -> None:
    index = RepoIndex.from_git(_REPO_ROOT)
    tracked = sorted(index.tracked_paths())
    assert tracked, "expected tracked files"
    for path in tracked:
        assert normalize_path(path) == path
        segments = path.casefold().split("/")
        if ".github" in segments or any(s.startswith(".env") for s in segments):
            assert change_code(path, "modify", index) == E.FORBIDDEN_AREA
        else:
            kind = validate_change(path, "modify", index).kind
            assert kind in {K.REGULAR_FILE, K.EXECUTABLE_FILE}
    for subdirectory in (".github", "backend", ".github/ai"):
        assert _index_error(_REPO_ROOT / subdirectory) == R.NOT_WORKTREE_ROOT


# ------------------------------------------------------------- source hygiene


def test_orchestrator_sources_are_ascii_without_raw_control_characters() -> None:
    """Look-alike, invisible or control characters in security code must be escapes."""

    root = Path(__file__).resolve().parents[1]
    sources = sorted([*root.glob("orchestrator/*.py"), *root.glob("tests/*.py")])
    assert sources
    for source in sources:
        data = source.read_bytes()
        assert data.isascii(), source.name
        assert not any(byte < 0x20 and byte != 0x0A for byte in data), source.name


def test_network_access_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="network access"):
        socket.create_connection(("api.openai.com", 443), timeout=1)
