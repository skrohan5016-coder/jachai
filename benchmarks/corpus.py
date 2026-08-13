"""Load and validate the benchmark corpus.

Fail-closed is the rule here. A case that cannot be read, cannot be parsed, or
carries no verified ground truth is an *error*, not a silently skipped row. A
benchmark that quietly drops the cases it does not understand will report a
precision of 1.0 on an empty corpus and tell you nothing.

Validation is hand-written against the JSON Schema rather than delegated to
``jsonschema``, because the project keeps a zero-runtime-dependency promise and
the schema is small enough that a focused checker is clearer than a general one.
The schema file remains the published contract; ``test_schema_and_validator_agree``
guards the two against drifting apart.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BENCHMARK_ROOT = Path(__file__).resolve().parent
CASES_DIR = BENCHMARK_ROOT / "cases"
SCHEMA_PATH = BENCHMARK_ROOT / "schema" / "bug-case.schema.json"

CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

OUTCOMES = frozenset({"detect", "miss", "skip", "unsupported"})
ORIGINS = frozenset({"real", "synthetic"})
CATEGORIES = frozenset({
    "crash", "hang", "mutation", "contract", "shared-default",
    "determinism", "logic", "concurrency", "resource", "none", "other",
})

#: Placeholders people reach for when they have not actually verified anything.
UNVERIFIED = frozenset({"", "unverified", "unknown", "tbd", "todo", "n/a", "none"})


class CorpusError(Exception):
    """Raised for any case the harness refuses to score."""


@dataclass(frozen=True)
class BugCase:
    path: Path
    data: dict[str, Any]

    @property
    def case_id(self) -> str:
        return self.data["case_id"]

    @property
    def is_bug(self) -> bool:
        return bool(self.data["ground_truth"]["is_bug"])

    @property
    def expected_outcome(self) -> str:
        return self.data["jachai_expected"]["outcome"]

    @property
    def is_real(self) -> bool:
        return self.data["real_or_synthetic"] == "real"

    @property
    def fixture(self) -> Path:
        return BENCHMARK_ROOT / self.data["source"]["fixture"]


def _require(condition: bool, where: str, message: str) -> None:
    if not condition:
        raise CorpusError(f"{where}: {message}")


def validate(data: Any, where: str) -> None:
    """Raise CorpusError unless *data* is a scorable bug case."""
    _require(isinstance(data, dict), where, "case must be a JSON object")

    required = {
        "case_id", "source", "language", "bug_category", "real_or_synthetic",
        "input", "expected_behavior", "observed_behavior", "ground_truth",
        "jachai_expected", "tool_results",
    }
    missing = sorted(required - set(data))
    _require(not missing, where, f"missing required field(s): {', '.join(missing)}")

    _require(isinstance(data["case_id"], str) and bool(CASE_ID.match(data["case_id"])),
             where, "case_id must be lowercase-hyphenated, 3-64 characters")
    _require(data["language"] == "python", where, "language must be 'python' in this milestone")
    _require(data["bug_category"] in CATEGORIES, where,
             f"bug_category must be one of {sorted(CATEGORIES)}")
    _require(data["real_or_synthetic"] in ORIGINS, where,
             "real_or_synthetic must be 'real' or 'synthetic'")

    for field in ("expected_behavior", "observed_behavior"):
        _require(isinstance(data[field], str) and data[field].strip(), where,
                 f"{field} must be a non-empty string")

    source = data["source"]
    _require(isinstance(source, dict), where, "source must be an object")
    for field in ("origin", "fixture"):
        _require(isinstance(source.get(field), str) and source[field].strip(), where,
                 f"source.{field} is required")
    _require(not Path(source["fixture"]).is_absolute() and ".." not in Path(source["fixture"]).parts,
             where, "source.fixture must be a relative path inside benchmarks/")

    truth = data["ground_truth"]
    _require(isinstance(truth, dict), where, "ground_truth must be an object")
    _require(isinstance(truth.get("is_bug"), bool), where,
             "ground_truth.is_bug must be true or false — a case with no verdict cannot be scored")
    verified_by = truth.get("verified_by")
    _require(isinstance(verified_by, str) and verified_by.strip().lower() not in UNVERIFIED,
             where, "ground_truth.verified_by must name who verified it, and how")
    _require(isinstance(truth.get("verified_on"), str) and bool(DATE.match(truth["verified_on"])),
             where, "ground_truth.verified_on must be a YYYY-MM-DD date")

    expected = data["jachai_expected"]
    _require(isinstance(expected, dict), where, "jachai_expected must be an object")
    _require(expected.get("outcome") in OUTCOMES, where,
             f"jachai_expected.outcome must be one of {sorted(OUTCOMES)}")
    if expected["outcome"] == "detect":
        _require(isinstance(expected.get("kind"), str) and expected["kind"].strip(), where,
                 "jachai_expected.kind is required when outcome is 'detect'")
    _require(not (expected["outcome"] == "detect" and truth["is_bug"] is False), where,
             "a negative control cannot expect a detection")

    results = data["tool_results"]
    _require(isinstance(results, list), where, "tool_results must be an array")
    for i, entry in enumerate(results):
        spot = f"{where}: tool_results[{i}]"
        _require(isinstance(entry, dict), spot, "each tool result must be an object")
        for field in ("tool", "version", "command"):
            _require(isinstance(entry.get(field), str) and entry[field].strip(), spot,
                     f"{field} is required — an unrun tool must be omitted, not guessed")
        _require(isinstance(entry.get("detected"), bool), spot, "detected must be true or false")
        _require(isinstance(entry.get("run_on"), str) and bool(DATE.match(entry["run_on"])), spot,
                 "run_on must be a YYYY-MM-DD date")


def load_case(path: Path) -> BugCase:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{path.name}: not valid JSON ({exc})") from exc
    validate(data, path.name)
    return BugCase(path=path, data=data)


def load_corpus(cases_dir: Path | None = None) -> list[BugCase]:
    """Every case in *cases_dir*, sorted by id. Raises on the first bad one."""
    directory = CASES_DIR if cases_dir is None else cases_dir
    cases: list[BugCase] = []
    seen: dict[str, Path] = {}

    for path in sorted(directory.glob("*.json")):
        case = load_case(path)
        if case.case_id in seen:
            raise CorpusError(
                f"{path.name}: duplicate case_id '{case.case_id}', "
                f"already defined in {seen[case.case_id].name}"
            )
        seen[case.case_id] = path
        cases.append(case)

    for case in cases:
        if not case.fixture.exists():
            raise CorpusError(f"{case.case_id}: fixture not found: {case.data['source']['fixture']}")

    return sorted(cases, key=lambda c: c.case_id)
