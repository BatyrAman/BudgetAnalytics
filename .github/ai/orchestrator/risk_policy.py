"""Deterministic, fail-closed Risk Policy (T3).

Loads ``policy/risk_policy.toml`` strictly and classifies a set of validated
changes as ``L1``, ``L2`` or ``L3`` (POLICY.md sections 3, 5 and 6).

Semantics (POLICY.md section 5.0):

* Patterns are repository-relative POSIX paths matched against the whole path
  by a small segment matcher of this module, never by ``fnmatch``/``glob``.
  ``**`` is a whole segment matching zero or more segments (a trailing ``**``
  matches one or more); ``*`` matches zero or more characters inside one
  segment; every other character is literal (``[id]`` is a literal segment).
* L3 rules match case-insensitively, L1 and L2 rules case-sensitively, so case
  variations can only raise a level.
* Every matching rule applies and the highest level wins; rule order is
  irrelevant and no rule can lower another. A path matching no rule gets the
  policy's ``unclassified_level`` (always L3).
* The hard path restrictions of ``paths.py`` (``.github`` segments, segments
  starting with ``.env``) always give L3 and make the result non-executable,
  whatever the policy file says.
* Change type, Git entry kind, binary/mode changes and the actual diff size
  can only raise the level.

``RiskAssessment.executable`` only states that the Risk Policy itself does
not prohibit the change set. It is **not** an approval: eligibility, human
approval for L2/L3, review and CI gates remain mandatory (POLICY.md section 9).

Inputs must come from :func:`orchestrator.paths.validate_changes` (planned
changes) or, in a later phase, from the actual Git diff. The evaluator
re-checks the structural invariants of every record and never touches the
filesystem except to read the policy file it is given.
"""

from __future__ import annotations

import dataclasses
import enum
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.paths import (
    ChangeType,
    EntryKind,
    PathValidationError,
    ValidatedPath,
    is_forbidden_path,
    normalize_path,
)

DEFAULT_POLICY_PATH = Path(__file__).parent.parent / "policy" / "risk_policy.toml"
SCHEMA_VERSION = 1
MAX_POLICY_BYTES = 1_000_000
MAX_RULES = 500
MAX_PATTERNS_PER_RULE = 200
MAX_PATTERN_LENGTH = 200
MAX_PATTERN_SEGMENTS = 20
MAX_DOUBLE_STARS = 2
MAX_LIMIT = 100_000
MAX_EVALUATED_CHANGES = 10_000
MAX_CHANGED_LINES = 10_000_000

# Always used with fullmatch(): "$" alone would accept a trailing newline.
_POLICY_VERSION_RE = re.compile(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}(-[a-z0-9]+(\.[a-z0-9]+)*)?")
_RULE_ID_RE = re.compile(r"l[123](\.[a-z0-9_]{1,40}){1,3}")
_PATTERN_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-[]()@*"
)


class RiskLevel(enum.IntEnum):
    L1 = 1
    L2 = 2
    L3 = 3

    def __str__(self) -> str:
        return self.name


_LEVEL_NAMES: Mapping[str, RiskLevel] = {level.name: level for level in RiskLevel}

# File names that are always at least L3, whatever the policy file says:
# they change how Git checks out, diffs and filters every other file.
HARD_L3_FILE_NAMES: frozenset[str] = frozenset({".gitattributes"})


def is_hard_l3_path(path: str) -> bool:
    """True if the final segment is a built-in L3 file name (case-insensitive)."""

    return path.rsplit("/", 1)[-1].casefold() in HARD_L3_FILE_NAMES


# -------------------------------------------------------------------- errors


class PolicyErrorCode(enum.StrEnum):
    FILE_NOT_FOUND = "file_not_found"
    FILE_UNREADABLE = "file_unreadable"
    FILE_TOO_LARGE = "file_too_large"
    INVALID_TOML = "invalid_toml"
    MISSING_KEY = "missing_key"
    UNKNOWN_KEY = "unknown_key"
    INVALID_TYPE = "invalid_type"
    INVALID_VALUE = "invalid_value"
    INVALID_LEVEL = "invalid_level"
    INVALID_VERSION = "invalid_version"
    INVALID_LIMIT = "invalid_limit"
    EMPTY_RULES = "empty_rules"
    INCOMPLETE_RULES = "incomplete_rules"
    INVALID_RULE_ID = "invalid_rule_id"
    DUPLICATE_RULE_ID = "duplicate_rule_id"
    INVALID_PATTERN = "invalid_pattern"
    DUPLICATE_PATTERN = "duplicate_pattern"
    CONFLICTING_PATTERN = "conflicting_pattern"
    OVERBROAD_PATTERN = "overbroad_pattern"
    FORBIDDEN_PATTERN = "forbidden_pattern"


class PolicyError(ValueError):
    """The policy file is unusable. Never fall back to a default policy."""

    def __init__(self, code: PolicyErrorCode, location: str = "") -> None:
        self.code = code
        self.location = location
        suffix = f" at {location}" if location else ""
        super().__init__(f"invalid risk policy: {code.value}{suffix}")


class EvaluationErrorCode(enum.StrEnum):
    INVALID_POLICY = "invalid_policy"
    POLICY_VERSION_MISMATCH = "policy_version_mismatch"
    INVALID_CHANGES = "invalid_changes"
    TOO_MANY_CHANGES = "too_many_changes"
    INVALID_RECORD = "invalid_record"
    NON_CANONICAL_PATH = "non_canonical_path"
    INCONSISTENT_METADATA = "inconsistent_metadata"
    DUPLICATE_PATH = "duplicate_path"
    INVALID_COUNT = "invalid_count"
    INCONSISTENT_COUNT = "inconsistent_count"


class RiskEvaluationError(ValueError):
    """The input cannot be evaluated safely. The change set must be rejected."""

    def __init__(self, code: EvaluationErrorCode, *, index: int | None = None) -> None:
        self.code = code
        self.index = index
        where = f" (item {index})" if index is not None else ""
        super().__init__(f"risk evaluation rejected: {code.value}{where}")


# ------------------------------------------------------------------- policy


@dataclass(frozen=True, slots=True)
class Pattern:
    """A compiled policy pattern (see module docstring for the semantics)."""

    text: str
    segments: tuple[str, ...]
    case_insensitive: bool

    def matches(self, path: str) -> bool:
        target = path.casefold() if self.case_insensitive else path
        segments = self.segments
        if self.case_insensitive:
            segments = tuple(segment.casefold() for segment in segments)
        return _match_segments(segments, tuple(target.split("/")))


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    level: RiskLevel
    description: str
    patterns: tuple[Pattern, ...]

    def matches(self, path: str) -> bool:
        return any(pattern.matches(path) for pattern in self.patterns)


@dataclass(frozen=True, slots=True)
class Limits:
    l1_max_files: int
    l1_max_lines: int
    l2_max_files: int
    l2_max_lines: int


@dataclass(frozen=True, slots=True)
class ChangeRules:
    delete: RiskLevel
    rename: RiskLevel
    executable_file: RiskLevel
    binary: RiskLevel
    mode_change: RiskLevel
    symlink: RiskLevel
    submodule: RiskLevel
    new_top_level: RiskLevel


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    schema_version: int
    policy_version: str
    unclassified_level: RiskLevel
    forbidden_level: RiskLevel
    empty_change_set_level: RiskLevel
    limits: Limits
    change_rules: ChangeRules
    rules: tuple[Rule, ...]


def _segment_regex(segment: str) -> re.Pattern[str]:
    return re.compile("[^/]*".join(re.escape(part) for part in segment.split("*")))


def _segment_matches(pattern: str, segment: str) -> bool:
    if "*" not in pattern:
        return pattern == segment
    return _segment_regex(pattern).fullmatch(segment) is not None


def _match_segments(pattern: tuple[str, ...], path: tuple[str, ...]) -> bool:
    memo: dict[tuple[int, int], bool] = {}

    def match(i: int, j: int) -> bool:
        key = (i, j)
        if key in memo:
            return memo[key]
        if i == len(pattern):
            result = j == len(path)
        elif pattern[i] == "**":
            if i == len(pattern) - 1:
                result = j < len(path)  # trailing "**": one or more segments
            else:
                result = any(match(i + 1, k) for k in range(j, len(path) + 1))
        else:
            result = j < len(path) and _segment_matches(pattern[i], path[j]) and match(i + 1, j + 1)
        memo[key] = result
        return result

    return match(0, 0)


# ------------------------------------------------------------------- loader


def _require_table(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PolicyError(PolicyErrorCode.INVALID_TYPE, location)
    return value


def _check_keys(table: Mapping[str, object], expected: frozenset[str], location: str) -> None:
    for key in sorted(expected - table.keys()):
        raise PolicyError(PolicyErrorCode.MISSING_KEY, f"{location}{key}")
    for key in sorted(table.keys() - expected):
        raise PolicyError(PolicyErrorCode.UNKNOWN_KEY, f"{location}{key}")


def _int(value: object, location: str) -> int:
    if type(value) is not int:  # bool is rejected
        raise PolicyError(PolicyErrorCode.INVALID_TYPE, location)
    return value


def _str(value: object, location: str, max_length: int = 200) -> str:
    if not isinstance(value, str):
        raise PolicyError(PolicyErrorCode.INVALID_TYPE, location)
    if not value or len(value) > max_length or not value.isascii():
        raise PolicyError(PolicyErrorCode.INVALID_VALUE, location)
    return value


def _level(value: object, location: str) -> RiskLevel:
    if not isinstance(value, str):
        raise PolicyError(PolicyErrorCode.INVALID_TYPE, location)
    if value not in _LEVEL_NAMES:
        raise PolicyError(PolicyErrorCode.INVALID_LEVEL, location)
    return _LEVEL_NAMES[value]


def _is_canonical_path(segment: str) -> bool:
    try:
        return normalize_path(segment) == segment
    except PathValidationError:
        return False


def _parse_pattern(text: object, level: RiskLevel, location: str) -> Pattern:
    if not isinstance(text, str):
        raise PolicyError(PolicyErrorCode.INVALID_TYPE, location)
    if not text or len(text) > MAX_PATTERN_LENGTH or not text.isascii():
        raise PolicyError(PolicyErrorCode.INVALID_PATTERN, location)
    segments = tuple(text.split("/"))
    if len(segments) > MAX_PATTERN_SEGMENTS:
        raise PolicyError(PolicyErrorCode.INVALID_PATTERN, location)
    double_stars = 0
    previous = ""
    for segment in segments:
        if segment == "**":
            double_stars += 1
            if previous == "**":
                raise PolicyError(PolicyErrorCode.INVALID_PATTERN, location)
        elif "*" in segment:
            if "**" in segment or not set(segment) <= _PATTERN_CHARS or segment.endswith("."):
                raise PolicyError(PolicyErrorCode.INVALID_PATTERN, location)
        elif not _is_canonical_path(segment):
            # A literal segment must be a valid path segment (no "", ".",
            # "..", ".git", Windows device names, invalid characters ...).
            raise PolicyError(PolicyErrorCode.INVALID_PATTERN, location)
        previous = segment
    if double_stars > MAX_DOUBLE_STARS:
        raise PolicyError(PolicyErrorCode.INVALID_PATTERN, location)
    if "*" not in text and not _is_canonical_path(text):
        # A literal pattern must itself be a canonical repository path.
        raise PolicyError(PolicyErrorCode.INVALID_PATTERN, location)
    if level < RiskLevel.L3:
        if all(segment in {"*", "**"} for segment in segments):
            raise PolicyError(PolicyErrorCode.OVERBROAD_PATTERN, location)
        for segment in segments:
            folded = segment.casefold()
            if folded == ".github" or folded.startswith(".env") or folded in HARD_L3_FILE_NAMES:
                raise PolicyError(PolicyErrorCode.FORBIDDEN_PATTERN, location)
    return Pattern(text, segments, case_insensitive=level is RiskLevel.L3)


_TOP_KEYS = frozenset(
    {"schema_version", "policy_version", "defaults", "limits", "change_rules", "rules"}
)
_DEFAULT_KEYS = frozenset({"unclassified_level", "forbidden_level", "empty_change_set_level"})
_LIMIT_KEYS = frozenset({"l1_max_files", "l1_max_lines", "l2_max_files", "l2_max_lines"})
_CHANGE_RULE_KEYS = frozenset(
    {
        "delete",
        "rename",
        "executable_file",
        "binary",
        "mode_change",
        "symlink",
        "submodule",
        "new_top_level",
    }
)
# Hard floors: these change types can never be L1; the L3 ones are fixed.
_CHANGE_RULE_FLOORS: Mapping[str, RiskLevel] = {
    "delete": RiskLevel.L2,
    "rename": RiskLevel.L2,
    "executable_file": RiskLevel.L2,
    "binary": RiskLevel.L3,
    "mode_change": RiskLevel.L3,
    "symlink": RiskLevel.L3,
    "submodule": RiskLevel.L3,
    "new_top_level": RiskLevel.L3,
}
_RULE_KEYS = frozenset({"id", "level", "description", "patterns"})


def _parse_rules(value: object) -> tuple[Rule, ...]:
    if not isinstance(value, list):
        raise PolicyError(PolicyErrorCode.INVALID_TYPE, "rules")
    if not value:
        raise PolicyError(PolicyErrorCode.EMPTY_RULES, "rules")
    if len(value) > MAX_RULES:
        raise PolicyError(PolicyErrorCode.INVALID_VALUE, "rules")
    rules: list[Rule] = []
    ids: set[str] = set()
    pattern_levels: dict[str, RiskLevel] = {}
    for position, raw in enumerate(value):
        table = _require_table(raw, f"rules[{position}]")
        _check_keys(table, _RULE_KEYS, f"rules[{position}].")
        rule_id = _str(table["id"], f"rules[{position}].id", 64)
        location = f"rules[{rule_id}]"
        level = _level(table["level"], f"{location}.level")
        if not _RULE_ID_RE.fullmatch(rule_id) or not rule_id.startswith(f"l{int(level)}."):
            raise PolicyError(PolicyErrorCode.INVALID_RULE_ID, location)
        if rule_id in ids:
            raise PolicyError(PolicyErrorCode.DUPLICATE_RULE_ID, location)
        ids.add(rule_id)
        description = _str(table["description"], f"{location}.description")
        raw_patterns = table["patterns"]
        if not isinstance(raw_patterns, list):
            raise PolicyError(PolicyErrorCode.INVALID_TYPE, f"{location}.patterns")
        if not raw_patterns or len(raw_patterns) > MAX_PATTERNS_PER_RULE:
            raise PolicyError(PolicyErrorCode.INVALID_VALUE, f"{location}.patterns")
        patterns: list[Pattern] = []
        for index, raw_pattern in enumerate(raw_patterns):
            pattern_location = f"{location}.patterns[{index}]"
            pattern = _parse_pattern(raw_pattern, level, pattern_location)
            key = pattern.text.casefold()
            if key in pattern_levels:
                code = (
                    PolicyErrorCode.DUPLICATE_PATTERN
                    if pattern_levels[key] == level
                    else PolicyErrorCode.CONFLICTING_PATTERN
                )
                raise PolicyError(code, pattern_location)
            pattern_levels[key] = level
            patterns.append(pattern)
        rules.append(Rule(rule_id, level, description, tuple(patterns)))
    if not any(rule.level is RiskLevel.L3 for rule in rules):
        raise PolicyError(PolicyErrorCode.INCOMPLETE_RULES, "rules")
    return tuple(rules)


def is_valid_policy_version(value: object) -> bool:
    """True for an exact ``str`` that is a complete, valid policy version.

    Subclasses of ``str`` are rejected so that overridden equality cannot be
    smuggled into version comparisons.
    """

    return type(value) is str and _POLICY_VERSION_RE.fullmatch(value) is not None


def parse_policy(text: str) -> RiskPolicy:
    """Parse and validate policy TOML text. Raises :class:`PolicyError`."""

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise PolicyError(PolicyErrorCode.INVALID_TOML) from None
    return _parse_data(data)


def _parse_data(data: dict[str, object]) -> RiskPolicy:
    """Validate decoded policy data (the loader proper). Raises :class:`PolicyError`."""

    _check_keys(data, _TOP_KEYS, "")

    schema_version = _int(data["schema_version"], "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise PolicyError(PolicyErrorCode.INVALID_VERSION, "schema_version")
    policy_version = _str(data["policy_version"], "policy_version", 40)
    if not is_valid_policy_version(policy_version):
        raise PolicyError(PolicyErrorCode.INVALID_VERSION, "policy_version")

    defaults = _require_table(data["defaults"], "defaults")
    _check_keys(defaults, _DEFAULT_KEYS, "defaults.")
    default_levels = {key: _level(defaults[key], f"defaults.{key}") for key in _DEFAULT_KEYS}
    for key, level in sorted(default_levels.items()):
        if level is not RiskLevel.L3:
            raise PolicyError(PolicyErrorCode.INVALID_VALUE, f"defaults.{key}")

    limits_table = _require_table(data["limits"], "limits")
    _check_keys(limits_table, _LIMIT_KEYS, "limits.")
    values = {key: _int(limits_table[key], f"limits.{key}") for key in sorted(_LIMIT_KEYS)}
    for key, number in values.items():
        if not 1 <= number <= MAX_LIMIT:
            raise PolicyError(PolicyErrorCode.INVALID_LIMIT, f"limits.{key}")
    limits = Limits(**values)
    if limits.l1_max_files > limits.l2_max_files:
        raise PolicyError(PolicyErrorCode.INVALID_LIMIT, "limits.l1_max_files")
    if limits.l1_max_lines > limits.l2_max_lines:
        raise PolicyError(PolicyErrorCode.INVALID_LIMIT, "limits.l1_max_lines")

    change_table = _require_table(data["change_rules"], "change_rules")
    _check_keys(change_table, _CHANGE_RULE_KEYS, "change_rules.")
    change_levels: dict[str, RiskLevel] = {}
    for key in sorted(_CHANGE_RULE_KEYS):
        level = _level(change_table[key], f"change_rules.{key}")
        floor = _CHANGE_RULE_FLOORS[key]
        if level < floor:
            raise PolicyError(PolicyErrorCode.INVALID_VALUE, f"change_rules.{key}")
        change_levels[key] = level

    return RiskPolicy(
        schema_version=schema_version,
        policy_version=policy_version,
        unclassified_level=default_levels["unclassified_level"],
        forbidden_level=default_levels["forbidden_level"],
        empty_change_set_level=default_levels["empty_change_set_level"],
        limits=limits,
        change_rules=ChangeRules(**change_levels),
        rules=_parse_rules(data["rules"]),
    )


_MISSING = object()


def _fields_of(value: object, cls: type[Any]) -> dict[str, object] | None:
    """Snapshot every dataclass field of an exact ``cls`` instance, or ``None``.

    Subclasses are rejected (a subclass could override fields with
    properties) and unset slots (``object.__new__``) are detected; each field
    is read exactly once.
    """

    names = [field.name for field in dataclasses.fields(cls)]
    if type(value) is not cls:
        return None
    snapshot = {name: getattr(value, name, _MISSING) for name in names}
    if any(item is _MISSING for item in snapshot.values()):
        return None
    return snapshot


def _exact_str(value: object) -> str | None:
    return value if type(value) is str else None


def _level_name(value: object) -> str | None:
    return value.name if type(value) is RiskLevel else None


def _policy_data(policy: object) -> dict[str, object] | None:
    """Rebuild the loader input from a policy object, or ``None`` if malformed."""

    top = _fields_of(policy, RiskPolicy)
    limits = _fields_of(top["limits"], Limits) if top else None
    changes = _fields_of(top["change_rules"], ChangeRules) if top else None
    if top is None or limits is None or changes is None:
        return None
    defaults = {
        key: _level_name(top[key])
        for key in ("unclassified_level", "forbidden_level", "empty_change_set_level")
    }
    change_names = {key: _level_name(value) for key, value in changes.items()}
    rules_value = top["rules"]
    if type(rules_value) is not tuple:
        return None
    rules: list[dict[str, object]] = []
    for rule in rules_value:
        fields = _fields_of(rule, Rule)
        if fields is None or type(fields["patterns"]) is not tuple:
            return None
        texts: list[str] = []
        for pattern in fields["patterns"]:
            pattern_fields = _fields_of(pattern, Pattern)
            text = _exact_str(pattern_fields["text"]) if pattern_fields else None
            if text is None:
                return None
            texts.append(text)
        rule_id = _exact_str(fields["id"])
        description = _exact_str(fields["description"])
        level = _level_name(fields["level"])
        if rule_id is None or description is None or level is None:
            return None
        rules.append({"id": rule_id, "level": level, "description": description, "patterns": texts})
    if None in defaults.values() or None in change_names.values():
        return None
    if _exact_str(top["policy_version"]) is None or type(top["schema_version"]) is not int:
        return None
    return {
        "schema_version": top["schema_version"],
        "policy_version": top["policy_version"],
        "defaults": defaults,
        "limits": dict(limits),
        "change_rules": change_names,
        "rules": rules,
    }


def is_valid_policy(policy: object) -> bool:
    """True if ``policy`` is exactly what the loader produces from its own values.

    Detects hand-built or altered ``RiskPolicy`` objects: subclasses, unset or
    wrongly typed fields, defaults below L3, change rules below their floors,
    invalid limits, rule ids or patterns, and compiled patterns that do not
    match their text. It does not prove *provenance*: callers must still pass
    the policy returned by :func:`load_policy`.
    """

    data = _policy_data(policy)
    if data is None:
        return False
    try:
        rebuilt = _parse_data(data)
    except PolicyError:
        return False
    return rebuilt == policy


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> RiskPolicy:
    """Read and validate the policy file. Raises :class:`PolicyError`."""

    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_POLICY_BYTES + 1)
    except FileNotFoundError:
        raise PolicyError(PolicyErrorCode.FILE_NOT_FOUND) from None
    except OSError:
        raise PolicyError(PolicyErrorCode.FILE_UNREADABLE) from None
    if len(data) > MAX_POLICY_BYTES:
        raise PolicyError(PolicyErrorCode.FILE_TOO_LARGE)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise PolicyError(PolicyErrorCode.INVALID_TOML) from None
    return parse_policy(text)


# ---------------------------------------------------------------- evaluation


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeFacts:
    """One change of a change set, with facts from the actual Git diff.

    ``change`` comes from path validation; its ``kind`` is the entry kind
    *before* the change (``NEW`` for additions). ``new_kind`` is the entry
    kind *after* the change, from the target Git mode: ``None`` for a delete,
    a concrete kind (never ``NEW``) otherwise. For a modify, ``mode_change``
    must be true exactly when ``new_kind`` differs from ``change.kind``; an
    addition never has ``mode_change``. A rename is an ``add`` whose
    ``renamed_from`` is the validated ``delete`` of the source; a rename
    whose ``new_kind`` differs from the source kind is a mode change.
    ``new_kind``, ``binary`` and ``mode_change`` have no defaults on purpose:
    the caller must state them.
    """

    change: ValidatedPath
    new_kind: EntryKind | None
    binary: bool
    mode_change: bool
    renamed_from: ValidatedPath | None = None


@dataclass(frozen=True, slots=True)
class PathAssessment:
    path: str
    change: ChangeType
    level: RiskLevel
    rule_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Immutable result. ``executable`` is not an approval (see module docstring)."""

    level: RiskLevel
    policy_version: str
    executable: bool
    matched_rules: tuple[str, ...]
    file_count: int
    line_count: int
    reasons: tuple[str, ...]
    paths: tuple[PathAssessment, ...]


def classify_path(policy: RiskPolicy, path: str) -> tuple[RiskLevel, tuple[str, ...], bool]:
    """Classify one canonical path by rules only.

    Returns ``(level, matched_rule_ids, forbidden)``. A path matching no rule
    gets ``unclassified_level``; a forbidden path gets at least
    ``forbidden_level``; a built-in L3 file name (``.gitattributes``) is at
    least L3.
    """

    matched = tuple(sorted(rule.id for rule in policy.rules if rule.matches(path)))
    levels = [rule.level for rule in policy.rules if rule.id in matched]
    level = max(levels) if levels else policy.unclassified_level
    if is_hard_l3_path(path):
        level = max(level, RiskLevel.L3)
    forbidden = is_forbidden_path(path)
    if forbidden:
        level = max(level, policy.forbidden_level)
    return level, matched, forbidden


def _check_count(value: object, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise RiskEvaluationError(EvaluationErrorCode.INVALID_COUNT)
    return value


def _check_validated(record: object, position: int) -> ValidatedPath:
    if not isinstance(record, ValidatedPath):
        raise RiskEvaluationError(EvaluationErrorCode.INVALID_RECORD, index=position)
    if (
        not isinstance(record.change, ChangeType)
        or not isinstance(record.kind, EntryKind)
        or type(record.new_top_level) is not bool
    ):
        raise RiskEvaluationError(EvaluationErrorCode.INVALID_RECORD, index=position)
    try:
        canonical = normalize_path(record.path)
    except PathValidationError:
        raise RiskEvaluationError(EvaluationErrorCode.NON_CANONICAL_PATH, index=position) from None
    if canonical != record.path:
        raise RiskEvaluationError(EvaluationErrorCode.NON_CANONICAL_PATH, index=position)
    is_add = record.change is ChangeType.ADD
    if is_add != (record.kind is EntryKind.NEW):
        raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_METADATA, index=position)
    if record.new_top_level and not is_add:
        raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_METADATA, index=position)
    if is_add and "/" not in record.path and not record.new_top_level:
        raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_METADATA, index=position)
    return record


def _assess(
    policy: RiskPolicy, facts: object, position: int
) -> tuple[PathAssessment, list[str], bool]:
    if not isinstance(facts, ChangeFacts):
        raise RiskEvaluationError(EvaluationErrorCode.INVALID_RECORD, index=position)
    if type(facts.binary) is not bool or type(facts.mode_change) is not bool:
        raise RiskEvaluationError(EvaluationErrorCode.INVALID_RECORD, index=position)
    record = _check_validated(facts.change, position)
    if facts.mode_change and record.kind is EntryKind.NEW:
        raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_METADATA, index=position)
    new_kind = facts.new_kind
    if new_kind is not None and not isinstance(new_kind, EntryKind):
        raise RiskEvaluationError(EvaluationErrorCode.INVALID_RECORD, index=position)
    if record.change is ChangeType.DELETE:
        if new_kind is not None:
            raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_METADATA, index=position)
    elif new_kind is None or new_kind is EntryKind.NEW:
        raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_METADATA, index=position)
    if record.change is ChangeType.MODIFY and facts.mode_change != (new_kind is not record.kind):
        raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_METADATA, index=position)

    paths = [record.path]
    source = facts.renamed_from
    if source is not None:
        source = _check_validated(source, position)
        if (
            record.change is not ChangeType.ADD
            or source.change is not ChangeType.DELETE
            or source.path == record.path
        ):
            raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_METADATA, index=position)
        paths.append(source.path)

    rules = policy.change_rules
    level = RiskLevel.L1
    rule_ids: set[str] = set()
    reasons: set[str] = set()
    forbidden = False
    for path in paths:
        path_level, matched, path_forbidden = classify_path(policy, path)
        level = max(level, path_level)
        rule_ids.update(matched)
        if not matched:
            reasons.add("unclassified_path")
        if path_forbidden:
            reasons.add("forbidden_area")
            forbidden = True
        if is_hard_l3_path(path):
            reasons.add("git_attributes")

    escalations: list[tuple[bool, str, RiskLevel]] = [
        (record.change is ChangeType.DELETE, "delete", rules.delete),
        (source is not None, "rename", rules.rename),
        (record.kind is EntryKind.EXECUTABLE_FILE, "executable_file", rules.executable_file),
        (record.kind is EntryKind.SYMLINK, "symlink", rules.symlink),
        (record.kind is EntryKind.SUBMODULE, "submodule", rules.submodule),
        (record.new_top_level, "new_top_level", rules.new_top_level),
        (facts.binary, "binary", rules.binary),
        (facts.mode_change, "mode_change", rules.mode_change),
        # The kind after the change escalates exactly like an existing entry.
        (new_kind is EntryKind.EXECUTABLE_FILE, "executable_file", rules.executable_file),
        (new_kind is EntryKind.SYMLINK, "symlink", rules.symlink),
        (new_kind is EntryKind.SUBMODULE, "submodule", rules.submodule),
        (source is not None and new_kind is not source.kind, "mode_change", rules.mode_change),
    ]
    if source is not None:
        escalations += [
            (source.kind is EntryKind.EXECUTABLE_FILE, "executable_file", rules.executable_file),
            (source.kind is EntryKind.SYMLINK, "symlink", rules.symlink),
            (source.kind is EntryKind.SUBMODULE, "submodule", rules.submodule),
        ]
    for applies, reason, minimum in escalations:
        if applies:
            level = max(level, minimum)
            reasons.add(reason)

    assessment = PathAssessment(
        path=record.path,
        change=record.change,
        level=level,
        rule_ids=tuple(sorted(rule_ids)),
        reasons=tuple(sorted(reasons)),
    )
    return assessment, paths, forbidden


def evaluate(
    policy: RiskPolicy,
    changes: Sequence[ChangeFacts],
    *,
    changed_files: int,
    changed_lines: int,
    expected_policy_version: str,
) -> RiskAssessment:
    """Classify a change set. Raises :class:`RiskEvaluationError` on bad input.

    ``changed_files`` and ``changed_lines`` are the actual diff size (added
    plus deleted lines); ``changed_files`` must equal ``len(changes)``.
    ``expected_policy_version`` binds the caller to the policy it reviewed.
    """

    if not isinstance(policy, RiskPolicy) or not is_valid_policy(policy):
        raise RiskEvaluationError(EvaluationErrorCode.INVALID_POLICY)
    if (
        not isinstance(expected_policy_version, str)
        or expected_policy_version != policy.policy_version
    ):
        raise RiskEvaluationError(EvaluationErrorCode.POLICY_VERSION_MISMATCH)
    if not isinstance(changes, (list, tuple)):
        raise RiskEvaluationError(EvaluationErrorCode.INVALID_CHANGES)
    if len(changes) > MAX_EVALUATED_CHANGES:
        raise RiskEvaluationError(EvaluationErrorCode.TOO_MANY_CHANGES)
    files = _check_count(changed_files, MAX_EVALUATED_CHANGES)
    lines = _check_count(changed_lines, MAX_CHANGED_LINES)
    if files != len(changes):
        raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_COUNT)

    if not changes:
        if lines != 0:
            raise RiskEvaluationError(EvaluationErrorCode.INCONSISTENT_COUNT)
        return RiskAssessment(
            level=policy.empty_change_set_level,
            policy_version=policy.policy_version,
            executable=False,
            matched_rules=(),
            file_count=0,
            line_count=0,
            reasons=("empty_change_set",),
            paths=(),
        )

    assessments: list[PathAssessment] = []
    seen: set[str] = set()
    forbidden = False
    for position, facts in enumerate(changes):
        assessment, touched, path_forbidden = _assess(policy, facts, position)
        for path in touched:
            folded = path.casefold()
            if folded in seen:
                raise RiskEvaluationError(EvaluationErrorCode.DUPLICATE_PATH, index=position)
            seen.add(folded)
        assessments.append(assessment)
        forbidden = forbidden or path_forbidden

    level = max(assessment.level for assessment in assessments)
    reasons = {reason for assessment in assessments for reason in assessment.reasons}
    limits = policy.limits
    if files > limits.l2_max_files or lines > limits.l2_max_lines:
        level = max(level, RiskLevel.L3)
        reasons.add("exceeds_l2_limits")
    elif files > limits.l1_max_files or lines > limits.l1_max_lines:
        level = max(level, RiskLevel.L2)
        reasons.add("exceeds_l1_limits")

    return RiskAssessment(
        level=level,
        policy_version=policy.policy_version,
        executable=not forbidden,
        matched_rules=tuple(sorted({i for a in assessments for i in a.rule_ids})),
        file_count=files,
        line_count=lines,
        reasons=tuple(sorted(reasons)),
        paths=tuple(assessments),
    )
