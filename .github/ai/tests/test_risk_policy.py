"""Tests for orchestrator.risk_policy (T3). Offline and deterministic."""

from __future__ import annotations

import copy
import dataclasses
import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from orchestrator.paths import (
    MODE_EXECUTABLE,
    MODE_FILE,
    MODE_GITLINK,
    MODE_SYMLINK,
    ChangeType,
    EntryKind,
    RepoIndex,
    ValidatedPath,
    validate_changes,
)
from orchestrator.risk_policy import (
    DEFAULT_POLICY_PATH,
    MAX_CHANGED_LINES,
    ChangeFacts,
    EvaluationErrorCode,
    PolicyError,
    PolicyErrorCode,
    RiskAssessment,
    RiskEvaluationError,
    RiskLevel,
    RiskPolicy,
    classify_path,
    evaluate,
    load_policy,
    parse_policy,
)

P = PolicyErrorCode
V = EvaluationErrorCode
K = EntryKind
L1, L2, L3 = RiskLevel.L1, RiskLevel.L2, RiskLevel.L3

POLICY = load_policy()
VERSION = POLICY.policy_version
_REPO_ROOT = Path(__file__).resolve().parents[3]
_POLICY_MD = Path(__file__).resolve().parents[1] / "policy" / "POLICY.md"


# ------------------------------------------------------------------ helpers


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)  # JSON string escapes are valid TOML basic strings
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(type(value))


def to_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    tables: list[tuple[str, dict[str, Any]]] = []
    arrays: list[tuple[str, list[dict[str, Any]]]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            tables.append((key, value))
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            arrays.append((key, value))
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    for key, table in tables:
        lines.append(f"[{key}]")
        lines += [f"{k} = {_toml_value(v)}" for k, v in table.items()]
    for key, items in arrays:
        for item in items:
            lines.append(f"[[{key}]]")
            lines += [f"{k} = {_toml_value(v)}" for k, v in item.items()]
    return "\n".join(lines) + "\n"


def base() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy_version": "1.0.0",
        "defaults": {
            "unclassified_level": "L3",
            "forbidden_level": "L3",
            "empty_change_set_level": "L3",
        },
        "limits": {
            "l1_max_files": 10,
            "l1_max_lines": 300,
            "l2_max_files": 25,
            "l2_max_lines": 1000,
        },
        "change_rules": {
            "delete": "L2",
            "rename": "L2",
            "executable_file": "L2",
            "binary": "L3",
            "mode_change": "L3",
            "symlink": "L3",
            "submodule": "L3",
            "new_top_level": "L3",
        },
        "rules": [
            {"id": "l3.core", "level": "L3", "description": "Core", "patterns": ["core/**"]},
            {"id": "l2.app", "level": "L2", "description": "App", "patterns": ["app/**"]},
            {"id": "l1.docs", "level": "L1", "description": "Docs", "patterns": ["docs/**"]},
        ],
    }


def policy_code(data: dict[str, Any]) -> PolicyErrorCode:
    with pytest.raises(PolicyError) as info:
        parse_policy(to_toml(data))
    return info.value.code


def vp(
    path: str,
    change: str = "modify",
    kind: EntryKind | None = None,
    new_top_level: bool = False,
) -> ValidatedPath:
    change_type = ChangeType(change)
    if kind is None:
        kind = K.NEW if change_type is ChangeType.ADD else K.REGULAR_FILE
    return ValidatedPath(path, change_type, kind, new_top_level)


_SAME = object()  # sentinel: derive a consistent new_kind


def facts(
    path: str,
    change: str = "modify",
    *,
    kind: EntryKind | None = None,
    new_kind: object = _SAME,
    new_top_level: bool = False,
    binary: bool = False,
    mode_change: bool = False,
    renamed_from: ValidatedPath | None = None,
) -> ChangeFacts:
    record = vp(path, change, kind, new_top_level)
    if new_kind is _SAME:
        if record.change is ChangeType.DELETE:
            new_kind = None
        elif record.change is ChangeType.ADD:
            new_kind = renamed_from.kind if renamed_from is not None else K.REGULAR_FILE
        else:
            new_kind = record.kind
    return ChangeFacts(
        change=record,
        new_kind=new_kind,  # type: ignore[arg-type]
        binary=binary,
        mode_change=mode_change,
        renamed_from=renamed_from,
    )


def same_kind(record: ValidatedPath) -> ChangeFacts:
    """ChangeFacts for a validated record whose kind does not change."""

    new_kind: EntryKind | None
    if record.change is ChangeType.DELETE:
        new_kind = None
    elif record.change is ChangeType.ADD:
        new_kind = K.REGULAR_FILE
    else:
        new_kind = record.kind
    return ChangeFacts(change=record, new_kind=new_kind, binary=False, mode_change=False)


def run(
    changes: list[ChangeFacts],
    *,
    lines: int = 1,
    files: int | None = None,
    policy: RiskPolicy = POLICY,
) -> RiskAssessment:
    return evaluate(
        policy,
        changes,
        changed_files=len(changes) if files is None else files,
        changed_lines=lines,
        expected_policy_version=policy.policy_version,
    )


def eval_error(call: Callable[[], object]) -> EvaluationErrorCode:
    with pytest.raises(RiskEvaluationError) as info:
        call()
    return info.value.code


# -------------------------------------------------------------- shipped policy


def test_shipped_policy_loads_with_explicit_values() -> None:
    assert POLICY.schema_version == 1
    assert VERSION == "0.5.0-draft"
    assert POLICY.unclassified_level is L3
    assert POLICY.forbidden_level is L3
    assert POLICY.empty_change_set_level is L3
    limits = POLICY.limits
    assert (limits.l1_max_files, limits.l1_max_lines) == (10, 300)
    assert (limits.l2_max_files, limits.l2_max_lines) == (25, 1000)
    rules = POLICY.change_rules
    assert (rules.delete, rules.rename, rules.executable_file) == (L2, L2, L2)
    assert {rules.binary, rules.mode_change, rules.symlink, rules.submodule} == {L3}
    assert rules.new_top_level is L3
    assert {rule.level for rule in POLICY.rules} == {L1, L2, L3}
    assert load_policy(DEFAULT_POLICY_PATH) == POLICY


def test_policy_version_matches_policy_md() -> None:
    # POLICY.md records the executable Risk Policy version separately from its
    # own document version (section 12); the executable one must match the TOML.
    text = _POLICY_MD.read_text(encoding="utf-8")
    match = re.search(r"\| Executable Risk Policy version \| `([^`]+)` ", text)
    assert match is not None
    assert match.group(1) == VERSION
    document = re.search(r"\| Policy document version \| `([^`]+)` \|", text)
    assert document is not None


def test_shipped_policy_sources_are_ascii() -> None:
    assert DEFAULT_POLICY_PATH.read_bytes().isascii()


# -------------------------------------------------------------------- loader


def test_minimal_policy_loads_and_preserves_version() -> None:
    data = base()
    data["policy_version"] = "2.7.13-rc.1"
    policy = parse_policy(to_toml(data))
    assert policy.policy_version == "2.7.13-rc.1"
    assert [rule.id for rule in policy.rules] == ["l3.core", "l2.app", "l1.docs"]


def _drop(path: tuple[Any, ...]) -> Callable[[dict[str, Any]], None]:
    def mutate(data: dict[str, Any]) -> None:
        target: Any = data
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


def _set(path: tuple[Any, ...], value: object) -> Callable[[dict[str, Any]], None]:
    def mutate(data: dict[str, Any]) -> None:
        target: Any = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return mutate


def _add_rule(rule: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    def mutate(data: dict[str, Any]) -> None:
        data["rules"].append(rule)

    return mutate


def _rule(rule_id: str, level: str, *patterns: str) -> dict[str, Any]:
    return {"id": rule_id, "level": level, "description": "Test", "patterns": list(patterns)}


LOADER_CASES: list[tuple[str, Callable[[dict[str, Any]], None], PolicyErrorCode]] = [
    # top level
    *[(f"missing {key}", _drop((key,)), P.MISSING_KEY) for key in base()],
    ("unknown top key", _set(("allow_all",), True), P.UNKNOWN_KEY),
    ("schema str", _set(("schema_version",), "1"), P.INVALID_TYPE),
    ("schema bool", _set(("schema_version",), True), P.INVALID_TYPE),
    ("schema 2", _set(("schema_version",), 2), P.INVALID_VERSION),
    ("version int", _set(("policy_version",), 1), P.INVALID_TYPE),
    ("version empty", _set(("policy_version",), ""), P.INVALID_VALUE),
    ("version v1", _set(("policy_version",), "v1"), P.INVALID_VERSION),
    ("version spaces", _set(("policy_version",), "1.0.0 "), P.INVALID_VERSION),
    # defaults
    ("defaults not table", _set(("defaults",), "L3"), P.INVALID_TYPE),
    ("defaults missing", _drop(("defaults", "unclassified_level")), P.MISSING_KEY),
    ("defaults unknown", _set(("defaults", "fallback"), "L3"), P.UNKNOWN_KEY),
    ("unclassified L2", _set(("defaults", "unclassified_level"), "L2"), P.INVALID_VALUE),
    ("unclassified L1", _set(("defaults", "unclassified_level"), "L1"), P.INVALID_VALUE),
    ("forbidden L2", _set(("defaults", "forbidden_level"), "L2"), P.INVALID_VALUE),
    ("empty L1", _set(("defaults", "empty_change_set_level"), "L1"), P.INVALID_VALUE),
    ("level L4", _set(("defaults", "unclassified_level"), "L4"), P.INVALID_LEVEL),
    ("level lower case", _set(("defaults", "unclassified_level"), "l3"), P.INVALID_LEVEL),
    ("level int", _set(("defaults", "unclassified_level"), 3), P.INVALID_TYPE),
    # limits
    ("limits missing", _drop(("limits", "l2_max_lines")), P.MISSING_KEY),
    ("limits unknown", _set(("limits", "l3_max_files"), 50), P.UNKNOWN_KEY),
    ("limit zero", _set(("limits", "l1_max_files"), 0), P.INVALID_LIMIT),
    ("limit negative", _set(("limits", "l1_max_lines"), -1), P.INVALID_LIMIT),
    ("limit huge", _set(("limits", "l2_max_lines"), 100_001), P.INVALID_LIMIT),
    ("limit bool", _set(("limits", "l1_max_files"), True), P.INVALID_TYPE),
    ("limit str", _set(("limits", "l1_max_files"), "10"), P.INVALID_TYPE),
    ("limit float", _set(("limits", "l1_max_files"), 10.0), P.INVALID_TYPE),
    ("l1 files > l2", _set(("limits", "l1_max_files"), 26), P.INVALID_LIMIT),
    ("l1 lines > l2", _set(("limits", "l1_max_lines"), 1001), P.INVALID_LIMIT),
    # change rules
    ("change missing", _drop(("change_rules", "symlink")), P.MISSING_KEY),
    ("change unknown", _set(("change_rules", "chmod"), "L3"), P.UNKNOWN_KEY),
    ("delete L1", _set(("change_rules", "delete"), "L1"), P.INVALID_VALUE),
    ("rename L1", _set(("change_rules", "rename"), "L1"), P.INVALID_VALUE),
    ("executable L1", _set(("change_rules", "executable_file"), "L1"), P.INVALID_VALUE),
    ("binary L2", _set(("change_rules", "binary"), "L2"), P.INVALID_VALUE),
    ("mode L2", _set(("change_rules", "mode_change"), "L2"), P.INVALID_VALUE),
    ("symlink L2", _set(("change_rules", "symlink"), "L2"), P.INVALID_VALUE),
    ("submodule L1", _set(("change_rules", "submodule"), "L1"), P.INVALID_VALUE),
    ("new top L2", _set(("change_rules", "new_top_level"), "L2"), P.INVALID_VALUE),
    ("change invalid level", _set(("change_rules", "delete"), "L5"), P.INVALID_LEVEL),
    # rules container
    ("rules empty", _set(("rules",), []), P.EMPTY_RULES),
    ("rules table", _set(("rules",), "docs/**"), P.INVALID_TYPE),
    ("no L3 rule", _set(("rules",), [_rule("l1.docs", "L1", "docs/**")]), P.INCOMPLETE_RULES),
    # rule fields
    ("rule missing id", _drop(("rules", 0, "id")), P.MISSING_KEY),
    ("rule missing patterns", _drop(("rules", 2, "patterns")), P.MISSING_KEY),
    ("rule unknown key", _set(("rules", 1, "priority"), 1), P.UNKNOWN_KEY),
    ("rule id int", _set(("rules", 0, "id"), 3), P.INVALID_TYPE),
    ("rule id upper", _set(("rules", 0, "id"), "L3.core"), P.INVALID_RULE_ID),
    ("rule id no dot", _set(("rules", 0, "id"), "l3core"), P.INVALID_RULE_ID),
    ("rule id level mismatch", _set(("rules", 0, "id"), "l1.core"), P.INVALID_RULE_ID),
    ("rule level invalid", _set(("rules", 0, "level"), "L0"), P.INVALID_LEVEL),
    ("rule description empty", _set(("rules", 0, "description"), ""), P.INVALID_VALUE),
    ("rule description list", _set(("rules", 0, "description"), ["x"]), P.INVALID_TYPE),
    ("patterns empty", _set(("rules", 2, "patterns"), []), P.INVALID_VALUE),
    ("patterns string", _set(("rules", 2, "patterns"), "docs/**"), P.INVALID_TYPE),
    ("pattern int", _set(("rules", 2, "patterns"), [3]), P.INVALID_TYPE),
    ("duplicate id", _add_rule(_rule("l2.app", "L2", "web/**")), P.DUPLICATE_RULE_ID),
    # conflicting / duplicate patterns
    (
        "pattern repeated in rule",
        _set(("rules", 2, "patterns"), ["docs/**", "docs/**"]),
        P.DUPLICATE_PATTERN,
    ),
    ("pattern in two rules", _add_rule(_rule("l2.more", "L2", "app/**")), P.DUPLICATE_PATTERN),
    ("pattern two levels", _add_rule(_rule("l3.docs", "L3", "docs/**")), P.CONFLICTING_PATTERN),
    ("pattern case conflict", _add_rule(_rule("l3.docs", "L3", "DOCS/**")), P.CONFLICTING_PATTERN),
    # over-broad and forbidden allow rules
    ("catch-all L1", _set(("rules", 2, "patterns"), ["**"]), P.OVERBROAD_PATTERN),
    ("catch-all L2", _set(("rules", 1, "patterns"), ["**/*"]), P.OVERBROAD_PATTERN),
    ("star L1", _set(("rules", 2, "patterns"), ["*"]), P.OVERBROAD_PATTERN),
    ("github L1", _set(("rules", 2, "patterns"), [".github/x.md"]), P.FORBIDDEN_PATTERN),
    ("nested github L2", _set(("rules", 1, "patterns"), ["**/.GITHUB/**"]), P.FORBIDDEN_PATTERN),
    ("env L2", _set(("rules", 1, "patterns"), ["app/.env*"]), P.FORBIDDEN_PATTERN),
    ("env dir L1", _set(("rules", 2, "patterns"), ["docs/.env/**"]), P.FORBIDDEN_PATTERN),
]

INVALID_PATTERNS = [
    "/docs/**",
    "docs/",
    "docs//x.md",
    "./docs/x.md",
    "docs/../x.md",
    "docs/./x.md",
    "docs/a**",
    "**/**/x.md",
    "a/**/b/**/c/**",
    "docs/?.md",
    "docs/{a,b}.md",
    "docs\\x.md",
    "docs/x.",
    "docs/a b.md",
    "docs/%2e.md",
    "docs/x:y.md",
    "d\u00f6cs/**",
    "con.txt",
    ".git/**",
    "x" * 201,
    "/".join(["a"] * 21),
]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [(case[1], case[2]) for case in LOADER_CASES],
    ids=[case[0] for case in LOADER_CASES],
)
def test_loader_rejects_invalid_policies(
    mutate: Callable[[dict[str, Any]], None], expected: PolicyErrorCode
) -> None:
    data = copy.deepcopy(base())
    mutate(data)
    assert policy_code(data) == expected


@pytest.mark.parametrize("pattern", INVALID_PATTERNS)
def test_loader_rejects_malformed_patterns(pattern: str) -> None:
    data = base()
    data["rules"][0]["patterns"] = [pattern]
    assert policy_code(data) == P.INVALID_PATTERN


def test_l3_rules_may_use_broad_or_forbidden_patterns() -> None:
    data = base()
    data["rules"][0]["patterns"] = ["**", ".github/**", "**/.env*"]
    assert parse_policy(to_toml(data)).rules[0].level is L3


@pytest.mark.parametrize(
    "text",
    ["", "schema_version = ", "[[rules]\n", "schema_version = 1\nschema_version = 1\n"],
)
def test_invalid_toml_fails_closed(text: str) -> None:
    with pytest.raises(PolicyError) as info:
        parse_policy(text)
    assert info.value.code in {P.INVALID_TOML, P.MISSING_KEY}
    if text:
        assert info.value.code == P.INVALID_TOML


def test_policy_file_errors(tmp_path: Path) -> None:
    def load_code(path: Path) -> PolicyErrorCode:
        with pytest.raises(PolicyError) as info:
            load_policy(path)
        return info.value.code

    assert load_code(tmp_path / "missing.toml") == P.FILE_NOT_FOUND
    assert load_code(tmp_path) == P.FILE_UNREADABLE  # a directory
    big = tmp_path / "big.toml"
    big.write_bytes(b"#" * 1_000_001)
    assert load_code(big) == P.FILE_TOO_LARGE
    latin = tmp_path / "latin.toml"
    latin.write_bytes(b"# \xff\n")
    assert load_code(latin) == P.INVALID_TOML
    good = tmp_path / "good.toml"
    good.write_text(to_toml(base()))
    assert load_policy(good).policy_version == "1.0.0"


# ------------------------------------------------------------------ matching


def _pattern_policy(level: str, pattern: str) -> RiskPolicy:
    data = base()
    if level == "L3":
        data["rules"][0]["patterns"] = [pattern]
    else:
        data["rules"].append(_rule(f"l{level[1]}.under_test", level, pattern))
    return parse_policy(to_toml(data))


def _matches(level: str, pattern: str, path: str) -> bool:
    policy = _pattern_policy(level, pattern)
    rule_id = "l3.core" if level == "L3" else f"l{level[1]}.under_test"
    return rule_id in classify_path(policy, path)[1]


@pytest.mark.parametrize(
    ("level", "pattern", "path", "expected"),
    [
        # trailing ** matches the contents of a directory, not the directory
        ("L1", "guide/**", "guide/a.md", True),
        ("L1", "guide/**", "guide/x/y/z.md", True),
        ("L1", "guide/**", "guide", False),
        ("L1", "guide/**", "guidex/a.md", False),
        # leading **/ matches at any depth including the root
        ("L3", "**/Dockerfile", "Dockerfile", True),
        ("L3", "**/Dockerfile", "a/b/Dockerfile", True),
        ("L3", "**/Dockerfile", "a/Dockerfile.dev", False),
        # inner ** matches zero or more segments
        ("L2", "web/**/conftest.py", "web/conftest.py", True),
        ("L2", "web/**/conftest.py", "web/a/b/conftest.py", True),
        # * stays inside one segment
        ("L2", "web/*.md", "web/a.md", True),
        ("L2", "web/*.md", "web/x/a.md", False),
        ("L3", "**/compose*.yaml", "compose.yaml", True),
        ("L3", "**/compose*.yaml", "x/compose.dev-ports.yaml", True),
        ("L3", "**/compose*.yaml", "compose/x.yaml", False),
        # brackets, parentheses and @ are literal
        ("L2", "web/app/[id]/**", "web/app/[id]/page.tsx", True),
        ("L2", "web/app/[id]/**", "web/app/i/page.tsx", False),
        ("L2", "web/app/[id]/**", "web/app/d/page.tsx", False),
        ("L2", "web/(group)/@slot/page.tsx", "web/(group)/@slot/page.tsx", True),
        # exact paths match only themselves
        ("L2", "web/main.py", "web/main.py", True),
        ("L2", "web/main.py", "web/main.pyc", False),
        ("L2", "web/main.py", "x/web/main.py", False),
        # L3 is case-insensitive, L1/L2 are case-sensitive
        ("L3", "secure/**", "Secure/Key.pem", True),
        ("L2", "web/**", "WEB/a.tsx", False),
        ("L1", "guide/**", "Guide/a.md", False),
    ],
)
def test_pattern_semantics(level: str, pattern: str, path: str, expected: bool) -> None:
    assert _matches(level, pattern, path) is expected


# ------------------------------------------------------------- classification


def test_l1_change_set() -> None:
    result = run([facts("docs/design/USER_FLOWS.md"), facts("docs/design/NEW.md", "add")], lines=40)
    assert result.level is L1
    assert result.executable is True
    assert result.matched_rules == ("l1.docs",)
    assert result.reasons == ()
    assert result.policy_version == VERSION
    assert (result.file_count, result.line_count) == (2, 40)


@pytest.mark.parametrize(
    ("path", "level", "rule_ids"),
    [
        ("docs/design/USER_FLOWS.md", L1, ("l1.docs",)),
        ("docs/DEPLOYMENT.md", L2, ("l1.docs", "l2.docs")),
        ("docs/design/v0/README.md", L2, ("l1.docs", "l2.docs")),
        ("docs/legal/LICENSE_AUDIT.md", L3, ("l1.docs", "l3.legal")),
        ("docs/SECURITY_REVIEW.md", L3, ("l1.docs", "l3.security")),
        ("README.md", L2, ("l2.docs",)),
        ("frontend/components/goals/goal-card.tsx", L2, ("l2.frontend_app",)),
        ("frontend/lib/format.ts", L3, ("l2.frontend_app", "l3.finance")),
        ("frontend/lib/server/session.ts", L3, ("l2.frontend_app", "l3.auth")),
        ("backend/app/services/finance/deposit.py", L3, ("l2.backend_app", "l3.finance")),
        ("backend/app/api/deposits.py", L2, ("l2.backend_app",)),
        ("backend/tests/unit/test_money.py", L2, ("l2.backend_tests",)),
        ("backend/tests/conftest.py", L3, ("l2.backend_tests", "l3.test_infrastructure")),
        ("backend/tests/unit/finance/test_deposit.py", L3, ("l2.backend_tests", "l3.tests")),
        ("frontend/e2e/flows.spec.ts", L2, ("l2.frontend_tests",)),
        ("frontend/e2e/auth.spec.ts", L3, ("l2.frontend_tests", "l3.tests")),
        ("backend/requirements.txt", L3, ("l3.dependencies",)),
        ("frontend/package.json", L3, ("l3.dependencies",)),
        ("compose.yaml", L3, ("l3.security",)),
        ("CLAUDE.md", L3, ("l3.ai_policy",)),
    ],
)
def test_path_classification(path: str, level: RiskLevel, rule_ids: tuple[str, ...]) -> None:
    result = run([facts(path)])
    assert result.level is level
    assert result.paths[0].rule_ids == rule_ids
    assert result.matched_rules == rule_ids


def test_highest_risk_wins_across_the_change_set() -> None:
    l1 = facts("docs/design/USER_FLOWS.md")
    l2 = facts("frontend/components/goals/goal-card.tsx")
    l3 = facts("backend/app/services/finance/deposit.py")
    assert run([l1, l2]).level is L2
    assert run([l1, l3]).level is L3
    assert run([l1, l2, l3]).level is L3
    assert [p.level for p in run([l1, l2, l3]).paths] == [L1, L2, L3]


def test_rule_order_does_not_matter() -> None:
    reversed_policy = dataclasses.replace(POLICY, rules=tuple(reversed(POLICY.rules)))
    changes = [facts("docs/legal/LICENSE_AUDIT.md"), facts("README.md")]
    assert run(changes, policy=reversed_policy) == run(changes)


def test_unknown_paths_are_l3() -> None:
    result = run([facts("tools/new-script.py")])
    assert result.level is L3
    assert result.matched_rules == ()
    assert result.reasons == ("unclassified_path",)
    assert result.executable is True  # allowed, but only with L3 approval


@pytest.mark.parametrize(
    ("path", "change", "kind", "new_top_level"),
    [
        ("NEW.md", "add", None, True),
        ("AGENTS.md", "add", None, True),
        ("tools/x.py", "add", None, True),
        ("docs2/guide.md", "add", None, True),
    ],
)
def test_new_top_level_additions_are_l3(
    path: str, change: str, kind: EntryKind | None, new_top_level: bool
) -> None:
    result = run([facts(path, change, kind=kind, new_top_level=new_top_level)])
    assert result.level is L3
    assert "new_top_level" in result.reasons


@pytest.mark.parametrize(
    ("change", "kind", "reason"),
    [
        ("modify", K.SYMLINK, "symlink"),
        ("delete", K.SYMLINK, "symlink"),
        ("modify", K.SUBMODULE, "submodule"),
        ("delete", K.SUBMODULE, "submodule"),
    ],
)
def test_symlinks_and_submodules_are_l3(change: str, kind: EntryKind, reason: str) -> None:
    result = run([facts("docs/design/link.md", change, kind=kind)])
    assert result.level is L3
    assert reason in result.reasons


@pytest.mark.parametrize(
    "path",
    [
        ".github/ai/policy/risk_policy.toml",
        ".github/ai/policy/POLICY.md",
        ".github/ai/orchestrator/risk_policy.py",
        ".github/ai/orchestrator/paths.py",
        ".github/workflows/ci.yml",
    ],
)
def test_policy_and_orchestrator_files_are_l3_and_never_executable(path: str) -> None:
    result = run([facts(path)])
    assert result.level is L3
    assert result.executable is False
    assert "forbidden_area" in result.reasons
    assert "l3.ci" in result.matched_rules
    if path.startswith(".github/ai/"):
        assert "l3.orchestrator" in result.matched_rules


@pytest.mark.parametrize(
    "path",
    ["docs/.github/x.md", "docs/.env.local", "docs/.env/secrets.md", "docs/.envrc", ".env.example"],
)
def test_hard_restrictions_cannot_be_overridden_by_policy(path: str) -> None:
    # The shipped policy would classify docs/** as L1; the hard rule still wins.
    for policy in (POLICY, parse_policy(to_toml(base()))):
        result = run([facts(path, "add" if path != ".env.example" else "modify")], policy=policy)
        assert result.level is L3
        assert result.executable is False
        assert "forbidden_area" in result.reasons


def test_a_forbidden_path_makes_the_whole_set_non_executable() -> None:
    result = run([facts("docs/design/USER_FLOWS.md"), facts(".github/workflows/ci.yml")])
    assert (result.level, result.executable) == (L3, False)


def test_empty_change_set_is_not_executable() -> None:
    result = run([], lines=0)
    assert result.level is L3
    assert result.executable is False
    assert result.reasons == ("empty_change_set",)
    assert result.policy_version == VERSION
    assert eval_error(lambda: run([], lines=5)) == V.INCONSISTENT_COUNT


@pytest.mark.parametrize(
    ("files", "lines", "level", "reason"),
    [
        (10, 300, L1, None),
        (11, 300, L2, "exceeds_l1_limits"),
        (10, 301, L2, "exceeds_l1_limits"),
        (25, 1000, L2, "exceeds_l1_limits"),
        (26, 1000, L3, "exceeds_l2_limits"),
        (25, 1001, L3, "exceeds_l2_limits"),
        (1, 0, L1, None),
    ],
)
def test_size_boundaries(files: int, lines: int, level: RiskLevel, reason: str | None) -> None:
    changes = [facts(f"docs/design/new-{i}.md", "add") for i in range(files)]
    result = run(changes, lines=lines)
    assert result.level is level
    assert (result.file_count, result.line_count) == (files, lines)
    if reason is None:
        assert result.reasons == ()
    else:
        assert reason in result.reasons


@pytest.mark.parametrize(
    ("change", "level", "reason"),
    [
        (facts("docs/design/USER_FLOWS.md", "delete"), L2, "delete"),
        (facts("docs/design/diagram.png", "add", binary=True), L3, "binary"),
        (facts("docs/design/USER_FLOWS.md", binary=True), L3, "binary"),
        (
            facts("docs/design/USER_FLOWS.md", mode_change=True, new_kind=K.EXECUTABLE_FILE),
            L3,
            "mode_change",
        ),
        (facts("docs/tools/build.sh", kind=K.EXECUTABLE_FILE), L2, "executable_file"),
        (facts("docs/legal/LICENSE_AUDIT.md", "delete"), L3, "delete"),
        (
            facts("docs/design/B.md", "add", renamed_from=vp("docs/design/A.md", "delete")),
            L2,
            "rename",
        ),
        (
            facts("docs/design/B.md", "add", renamed_from=vp("docs/legal/A.md", "delete")),
            L3,
            "rename",
        ),
        (
            facts(
                "docs/design/B.md",
                "add",
                renamed_from=vp("docs/design/A.md", "delete", K.SYMLINK),
            ),
            L3,
            "symlink",
        ),
    ],
)
def test_change_types_never_qualify_for_l1(
    change: ChangeFacts, level: RiskLevel, reason: str
) -> None:
    result = run([change])
    assert result.level is level
    assert reason in result.reasons


def test_rename_source_rules_are_included() -> None:
    result = run([facts("docs/design/B.md", "add", renamed_from=vp("docs/legal/A.md", "delete"))])
    assert "l3.legal" in result.matched_rules


# ---------------------------------------------------------- invalid metadata


def _with(record: ValidatedPath, **changes: object) -> ValidatedPath:
    # Bypass the dataclass constructor's typing to forge invalid records.
    forged = object.__new__(ValidatedPath)
    for field in dataclasses.fields(ValidatedPath):
        object.__setattr__(forged, field.name, changes.get(field.name, getattr(record, field.name)))
    return forged


def _facts_with(**fields: object) -> ChangeFacts:
    forged = object.__new__(ChangeFacts)
    defaults: dict[str, object] = {
        "change": vp("docs/design/USER_FLOWS.md"),
        "new_kind": K.REGULAR_FILE,
        "binary": False,
        "mode_change": False,
        "renamed_from": None,
    }
    defaults.update(fields)
    for name, value in defaults.items():
        object.__setattr__(forged, name, value)
    return forged


DOC = vp("docs/design/USER_FLOWS.md")

INVALID_RECORDS: list[tuple[str, object, EvaluationErrorCode]] = [
    ("not ChangeFacts", DOC, V.INVALID_RECORD),
    ("change not ValidatedPath", _facts_with(change="docs/a.md"), V.INVALID_RECORD),
    ("binary int", _facts_with(binary=1), V.INVALID_RECORD),
    ("mode str", _facts_with(mode_change="no"), V.INVALID_RECORD),
    ("change plain str", _facts_with(change=_with(DOC, change="modify")), V.INVALID_RECORD),
    ("kind plain str", _facts_with(change=_with(DOC, kind="regular_file")), V.INVALID_RECORD),
    ("top-level int", _facts_with(change=_with(DOC, new_top_level=0)), V.INVALID_RECORD),
    ("leading ./", _facts_with(change=_with(DOC, path="./docs/a.md")), V.NON_CANONICAL_PATH),
    ("traversal", _facts_with(change=_with(DOC, path="docs/../x.md")), V.NON_CANONICAL_PATH),
    ("space", _facts_with(change=_with(DOC, path="docs/a b.md")), V.NON_CANONICAL_PATH),
    ("glob", _facts_with(change=_with(DOC, path="docs/*.md")), V.NON_CANONICAL_PATH),
    ("path int", _facts_with(change=_with(DOC, path=7)), V.NON_CANONICAL_PATH),
    ("add regular", _facts_with(change=_with(DOC, change=ChangeType.ADD)), V.INCONSISTENT_METADATA),
    ("modify new", _facts_with(change=_with(DOC, kind=K.NEW)), V.INCONSISTENT_METADATA),
    (
        "modify top-level",
        _facts_with(change=_with(DOC, new_top_level=True)),
        V.INCONSISTENT_METADATA,
    ),
    ("root add not top-level", _facts_with(change=vp("NEW.md", "add")), V.INCONSISTENT_METADATA),
    (
        "mode change on new file",
        _facts_with(change=vp("docs/x.md", "add"), mode_change=True),
        V.INCONSISTENT_METADATA,
    ),
    (
        "rename source not delete",
        _facts_with(change=vp("docs/b.md", "add"), renamed_from=vp("docs/a.md")),
        V.INCONSISTENT_METADATA,
    ),
    (
        "rename target not add",
        _facts_with(renamed_from=vp("docs/a.md", "delete")),
        V.INCONSISTENT_METADATA,
    ),
    (
        "rename onto itself",
        _facts_with(change=vp("docs/a.md", "add"), renamed_from=vp("docs/a.md", "delete")),
        V.INCONSISTENT_METADATA,
    ),
    (
        "rename source not validated",
        _facts_with(change=vp("docs/b.md", "add"), renamed_from="docs/a.md"),
        V.INVALID_RECORD,
    ),
]


@pytest.mark.parametrize(
    ("record", "expected"),
    [(case[1], case[2]) for case in INVALID_RECORDS],
    ids=[case[0] for case in INVALID_RECORDS],
)
def test_invalid_records_fail_closed(record: object, expected: EvaluationErrorCode) -> None:
    good = facts("docs/design/OTHER.md")
    with pytest.raises(RiskEvaluationError) as info:
        run([good, record])  # type: ignore[list-item]
    assert info.value.code == expected
    assert info.value.index == 1


def test_invalid_call_arguments_fail_closed() -> None:
    one = [facts("docs/design/USER_FLOWS.md")]

    def call(**overrides: Any) -> Callable[[], object]:
        arguments: dict[str, Any] = {
            "changed_files": 1,
            "changed_lines": 1,
            "expected_policy_version": VERSION,
        }
        arguments.update(overrides)
        policy = arguments.pop("policy", POLICY)
        changes = arguments.pop("changes", one)
        return lambda: evaluate(policy, changes, **arguments)

    assert eval_error(call(policy="policy")) == V.INVALID_POLICY
    assert eval_error(call(expected_policy_version="0.3.0-draft")) == V.POLICY_VERSION_MISMATCH
    assert eval_error(call(expected_policy_version=None)) == V.POLICY_VERSION_MISMATCH
    assert eval_error(call(changes=iter(one))) == V.INVALID_CHANGES
    assert eval_error(call(changes={"a": 1})) == V.INVALID_CHANGES
    assert eval_error(call(changed_files=2)) == V.INCONSISTENT_COUNT
    assert eval_error(call(changed_files=-1)) == V.INVALID_COUNT
    assert eval_error(call(changed_files=True)) == V.INVALID_COUNT
    assert eval_error(call(changed_lines=-1)) == V.INVALID_COUNT
    assert eval_error(call(changed_lines="5")) == V.INVALID_COUNT
    assert eval_error(call(changed_lines=1.0)) == V.INVALID_COUNT
    assert eval_error(call(changed_lines=MAX_CHANGED_LINES + 1)) == V.INVALID_COUNT
    assert (
        evaluate(
            POLICY,
            one,
            changed_files=1,
            changed_lines=MAX_CHANGED_LINES,
            expected_policy_version=VERSION,
        ).level
        is L3
    )


@pytest.mark.parametrize(
    "changes",
    [
        [facts("docs/a.md"), facts("docs/a.md", "delete")],
        [facts("docs/a.md"), facts("docs/A.md")],
        [facts("docs/b.md", "add", renamed_from=vp("docs/a.md", "delete")), facts("docs/a.md")],
    ],
)
def test_duplicate_paths_fail_closed(changes: list[ChangeFacts]) -> None:
    with pytest.raises(RiskEvaluationError) as info:
        run(changes)
    assert info.value.code == V.DUPLICATE_PATH
    assert info.value.index == 1


# ------------------------------------------------------------ result contract


def test_results_are_deterministic_and_immutable() -> None:
    changes = [
        facts("backend/app/services/finance/deposit.py"),
        facts("docs/design/USER_FLOWS.md"),
        facts("tools/x.py", "add", new_top_level=True),
    ]
    first = run(changes, lines=120)
    assert all(run(changes, lines=120) == first for _ in range(5))
    assert isinstance(first.matched_rules, tuple)
    assert isinstance(first.reasons, tuple)
    assert first.matched_rules == tuple(sorted(first.matched_rules))
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.level = L1  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.paths[0].level = L1  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        POLICY.limits.l1_max_files = 1_000  # type: ignore[misc]
    assert str(L3) == "L3"


def test_end_to_end_with_path_validation() -> None:
    index = RepoIndex(
        {
            "docs/design/USER_FLOWS.md": MODE_FILE,
            "backend/scripts/backup.sh": MODE_EXECUTABLE,
            "docs/link": MODE_SYMLINK,
            "vendor/sub": MODE_GITLINK,
        }
    )
    validated = validate_changes(
        [
            ("docs/design/USER_FLOWS.md", "modify"),
            ("docs/design/NEW.md", "add"),
        ],
        index,
    )
    changes = [same_kind(v) for v in validated]
    assert run(changes, lines=12).level is L1

    risky = validate_changes(
        [("backend/scripts/backup.sh", "modify"), ("docs/link", "delete"), ("NEW.md", "add")],
        index,
    )
    result = run([same_kind(v) for v in risky])
    assert result.level is L3
    assert {"executable_file", "symlink", "new_top_level"} <= set(result.reasons)


# ----------------------------------------------------- rule and repo coverage


def _sample_path(pattern: str) -> str:
    segments = pattern.split("/")
    out: list[str] = []
    for position, segment in enumerate(segments):
        if segment == "**":
            out.append("sample" if position < len(segments) - 1 else "sample/file.md")
        else:
            out.append(segment.replace("*", "x"))
    return "/".join(out)


def test_every_pattern_of_every_rule_is_exercised() -> None:
    exercised: set[str] = set()
    for rule in POLICY.rules:
        for pattern in rule.patterns:
            sample = _sample_path(pattern.text)
            level, matched, _forbidden = classify_path(POLICY, sample)
            assert rule.id in matched, (rule.id, pattern.text, sample)
            assert level >= rule.level
            exercised.add(rule.id)
    assert exercised == {rule.id for rule in POLICY.rules}


@pytest.mark.skipif(
    shutil.which("git") is None or not (_REPO_ROOT / ".git").exists(),
    reason="not a git checkout",
)
def test_every_tracked_file_is_explicitly_classified() -> None:
    index = RepoIndex.from_git(_REPO_ROOT)
    tracked = sorted(index.tracked_paths())
    assert tracked
    # Documented conservative fallback: a path matching no rule is L3
    # ("unclassified_path"). Today no tracked file relies on it.
    expected_fallback: set[str] = set()
    unclassified = {path for path in tracked if not classify_path(POLICY, path)[1]}
    assert unclassified == expected_fallback, sorted(unclassified)
    for path in tracked:
        level, _matched, forbidden = classify_path(POLICY, path)
        if forbidden:
            assert level is L3
    spot_checks = {
        "README.md": L2,
        "docs/design/USER_FLOWS.md": L1,
        "docs/legal/LICENSING_DECISION.md": L3,
        "backend/app/main.py": L2,
        "frontend/lib/format.ts": L3,
        ".github/workflows/ci.yml": L3,
    }
    for path, expected in spot_checks.items():
        if path in index.tracked_paths():
            assert classify_path(POLICY, path)[0] is expected, path


# ------------------------------------------------- T3.2: target kind (new_kind)


@pytest.mark.parametrize(
    ("new_kind", "level", "reason"),
    [
        (K.REGULAR_FILE, L1, None),
        (K.EXECUTABLE_FILE, L2, "executable_file"),
        (K.SYMLINK, L3, "symlink"),
        (K.SUBMODULE, L3, "submodule"),
    ],
)
def test_new_entries_are_classified_by_their_target_kind(
    new_kind: EntryKind, level: RiskLevel, reason: str | None
) -> None:
    result = run([facts("docs/design/new-entry", "add", new_kind=new_kind)])
    assert result.level is level
    if reason is not None:
        assert reason in result.reasons


@pytest.mark.parametrize(
    ("old", "new", "reasons"),
    [
        (K.REGULAR_FILE, K.EXECUTABLE_FILE, {"mode_change", "executable_file"}),
        (K.REGULAR_FILE, K.SYMLINK, {"mode_change", "symlink"}),
        (K.SYMLINK, K.REGULAR_FILE, {"mode_change", "symlink"}),
        (K.REGULAR_FILE, K.SUBMODULE, {"mode_change", "submodule"}),
        (K.EXECUTABLE_FILE, K.REGULAR_FILE, {"mode_change", "executable_file"}),
    ],
)
def test_type_changes_are_l3(old: EntryKind, new: EntryKind, reasons: set[str]) -> None:
    result = run([facts("docs/design/x.md", kind=old, new_kind=new, mode_change=True)])
    assert result.level is L3
    assert reasons <= set(result.reasons)


@pytest.mark.parametrize(
    ("source_kind", "new_kind", "level", "reasons"),
    [
        (K.REGULAR_FILE, K.REGULAR_FILE, L2, {"rename"}),
        (K.EXECUTABLE_FILE, K.EXECUTABLE_FILE, L2, {"rename", "executable_file"}),
        (K.REGULAR_FILE, K.SYMLINK, L3, {"rename", "symlink", "mode_change"}),
        (K.REGULAR_FILE, K.SUBMODULE, L3, {"rename", "submodule", "mode_change"}),
        (K.REGULAR_FILE, K.EXECUTABLE_FILE, L3, {"rename", "executable_file", "mode_change"}),
        (K.SYMLINK, K.REGULAR_FILE, L3, {"rename", "symlink", "mode_change"}),
    ],
)
def test_renames_into_special_kinds_cannot_lower_risk(
    source_kind: EntryKind, new_kind: EntryKind, level: RiskLevel, reasons: set[str]
) -> None:
    source = vp("docs/design/a.md", "delete", source_kind)
    result = run([facts("docs/design/b.md", "add", new_kind=new_kind, renamed_from=source)])
    assert result.level is level
    assert reasons <= set(result.reasons)


def test_rename_from_l3_source_into_special_kind_stays_l3() -> None:
    source = vp("docs/legal/terms.md", "delete")
    result = run(
        [facts("docs/design/terms.md", "add", new_kind=K.REGULAR_FILE, renamed_from=source)]
    )
    assert (result.level, "l3.legal" in result.matched_rules) == (L3, True)


FORGED_KINDS: list[tuple[str, ChangeFacts, EvaluationErrorCode]] = [
    ("plain string", _facts_with(new_kind="symlink"), V.INVALID_RECORD),
    ("integer", _facts_with(new_kind=3), V.INVALID_RECORD),
    ("NEW on modify", _facts_with(new_kind=K.NEW), V.INCONSISTENT_METADATA),
    ("missing on modify", _facts_with(new_kind=None), V.INCONSISTENT_METADATA),
    (
        "missing on add",
        _facts_with(change=vp("docs/x.md", "add"), new_kind=None),
        V.INCONSISTENT_METADATA,
    ),
    (
        "NEW on add",
        _facts_with(change=vp("docs/x.md", "add"), new_kind=K.NEW),
        V.INCONSISTENT_METADATA,
    ),
    (
        "target on delete",
        _facts_with(change=vp("docs/x.md", "delete"), new_kind=K.REGULAR_FILE),
        V.INCONSISTENT_METADATA,
    ),
    (
        "kind changed without mode_change",
        _facts_with(new_kind=K.SYMLINK, mode_change=False),
        V.INCONSISTENT_METADATA,
    ),
    (
        "mode_change without kind change",
        _facts_with(new_kind=K.REGULAR_FILE, mode_change=True),
        V.INCONSISTENT_METADATA,
    ),
    (
        "mode_change on rename target",
        _facts_with(
            change=vp("docs/b.md", "add"),
            new_kind=K.EXECUTABLE_FILE,
            mode_change=True,
            renamed_from=vp("docs/a.md", "delete"),
        ),
        V.INCONSISTENT_METADATA,
    ),
]


@pytest.mark.parametrize(
    ("record", "expected"),
    [(case[1], case[2]) for case in FORGED_KINDS],
    ids=[case[0] for case in FORGED_KINDS],
)
def test_forged_or_inconsistent_new_kind_fails_closed(
    record: ChangeFacts, expected: EvaluationErrorCode
) -> None:
    with pytest.raises(RiskEvaluationError) as info:
        run([facts("docs/design/OTHER.md"), record])
    assert (info.value.code, info.value.index) == (expected, 1)


def test_new_kind_is_required() -> None:
    with pytest.raises(TypeError):
        ChangeFacts(change=vp("docs/a.md"), binary=False, mode_change=False)  # type: ignore[call-arg]


# ------------------------------------------------- T3.2: .gitattributes is L3


@pytest.mark.parametrize(
    ("path", "change"),
    [
        (".gitattributes", "modify"),
        ("docs/.gitattributes", "add"),
        ("docs/design/deep/.gitattributes", "add"),
        ("frontend/app/.GitAttributes", "add"),
        ("backend/app/api/.gitattributes", "modify"),
    ],
)
def test_gitattributes_is_l3_at_any_depth(path: str, change: str) -> None:
    result = run([facts(path, change)])
    assert result.level is L3
    assert "git_attributes" in result.reasons
    assert classify_path(POLICY, path)[0] is L3


def test_gitattributes_is_explicitly_covered_by_the_policy() -> None:
    _level, matched, _forbidden = classify_path(POLICY, "docs/.gitattributes")
    assert "l3.security" in matched


@pytest.mark.parametrize("path", ["docs/.gitattributes", "app/.gitattributes", ".gitattributes"])
def test_gitattributes_cannot_be_lowered_by_a_permissive_policy(path: str) -> None:
    permissive = parse_policy(to_toml(base()))  # docs/** is L1, app/** is L2
    change = "modify" if "/" not in path else "add"
    result = run([facts(path, change)], policy=permissive)
    assert result.level is L3
    assert "git_attributes" in result.reasons
    assert classify_path(permissive, path)[0] is L3


@pytest.mark.parametrize(
    ("level", "pattern"),
    [
        ("L1", "docs/.gitattributes"),
        ("L2", "**/.gitattributes"),
        ("L1", "docs/.GITATTRIBUTES"),
    ],
)
def test_loader_rejects_allow_rules_naming_gitattributes(level: str, pattern: str) -> None:
    data = base()
    data["rules"].append(_rule(f"l{level[1]}.attrs", level, pattern))
    assert policy_code(data) == P.FORBIDDEN_PATTERN


def test_l3_rules_may_name_gitattributes() -> None:
    data = base()
    data["rules"][0]["patterns"] = ["**/.gitattributes"]
    assert parse_policy(to_toml(data)).rules[0].level is L3


# -------------------------------------- T3.2: strict full-string validation


@pytest.mark.parametrize(
    "version",
    ["1.0.0\n", "1.0.0-rc.1\n", "1.0.0\r", "1.0.0 ", "1.0.0\t", "1.0.0\n1", "\n1.0.0", "1.0.0x"],
)
def test_policy_version_with_trailing_characters_is_rejected(version: str) -> None:
    data = base()
    data["policy_version"] = version
    assert policy_code(data) == P.INVALID_VERSION


@pytest.mark.parametrize(
    "rule_id",
    ["l1.docs\n", "l1.docs\r", "l1.docs ", "l1.docs\t", "l1.docs\nl1.x", "l1.docs.", "\nl1.docs"],
)
def test_rule_id_with_trailing_characters_is_rejected(rule_id: str) -> None:
    data = base()
    data["rules"][2]["id"] = rule_id
    assert policy_code(data) == P.INVALID_RULE_ID


def test_repeated_evaluation_with_target_kinds_is_deterministic() -> None:
    changes = [
        facts("docs/design/link", "add", new_kind=K.SYMLINK),
        facts("docs/design/run.sh", "add", new_kind=K.EXECUTABLE_FILE),
        facts("docs/.gitattributes", "add"),
    ]
    first = run(changes, lines=3)
    assert all(run(changes, lines=3) == first for _ in range(5))
    assert first.level is L3
