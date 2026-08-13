"""Score jachai against the benchmark corpus.

    python -m benchmarks.evaluate            # human-readable
    python -m benchmarks.evaluate --json     # machine-readable

Scoring rules, stated up front because a benchmark that hides its rules can be
made to say anything:

* A case with ``ground_truth.is_bug: true`` is a positive. jachai reporting any
  finding for it is a **detection**; reporting nothing is a **miss**.
* A case with ``ground_truth.is_bug: false`` is a negative control. Reporting
  nothing is a **true negative**; reporting anything is a **false positive**.
* A case jachai declines to check (variadic signature, unconstructable
  argument type) is **unsupported**. Unsupported cases are reported separately
  and are excluded from precision and recall, because scoring a refusal as
  either success or failure would be dishonest.
* A case whose declared expectation and observed result disagree is a
  **surprise** and is listed by name. Surprises do not silently pass.

An empty corpus produces zeroes and a non-zero exit code. Metrics computed over
nothing are worse than no metrics: they look like evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.corpus import BugCase, CorpusError, load_corpus  # noqa: E402
from jachai.cli import check_file  # noqa: E402


@dataclass
class CaseResult:
    case_id: str
    real_or_synthetic: str
    bug_category: str
    is_bug: bool
    expected_outcome: str
    observed_outcome: str  # detect | miss | skip | unsupported | error
    finding_kinds: list[str] = field(default_factory=list)
    surprise: str | None = None
    error: str | None = None


@dataclass
class Scores:
    total_cases: int = 0
    positives: int = 0
    negatives: int = 0
    detected: int = 0
    missed: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    unsupported: int = 0
    errors: int = 0
    real_cases: int = 0
    synthetic_cases: int = 0
    surprises: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        denominator = self.detected + self.false_positives
        return None if denominator == 0 else self.detected / denominator

    @property
    def recall(self) -> float | None:
        denominator = self.detected + self.missed
        return None if denominator == 0 else self.detected / denominator

    @property
    def false_positive_rate(self) -> float | None:
        denominator = self.false_positives + self.true_negatives
        return None if denominator == 0 else self.false_positives / denominator


def run_case(case: BugCase, timeout: float) -> CaseResult:
    result = CaseResult(
        case_id=case.case_id,
        real_or_synthetic=case.data["real_or_synthetic"],
        bug_category=case.data["bug_category"],
        is_bug=case.is_bug,
        expected_outcome=case.expected_outcome,
        observed_outcome="error",
    )

    try:
        reports = check_file(case.fixture, timeout=timeout)
    except BaseException as exc:  # noqa: BLE001 - a crashing fixture is a result, not a stop
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    symbol = case.data["source"].get("symbol")
    relevant = [r for r in reports if symbol is None or r.spec.name == symbol]

    if not relevant:
        result.observed_outcome = "error"
        result.error = f"function {symbol!r} not found in fixture"
        return result

    findings = [f for r in relevant for f in r.findings]
    result.finding_kinds = sorted({f.kind for f in findings})

    if findings:
        result.observed_outcome = "detect"
    elif all(r.skipped_reason for r in relevant):
        result.observed_outcome = "unsupported"
    else:
        result.observed_outcome = "miss" if case.is_bug else "skip"

    if result.observed_outcome != case.expected_outcome:
        result.surprise = f"expected {case.expected_outcome}, observed {result.observed_outcome}"

    return result


def score(results: list[CaseResult]) -> Scores:
    scores = Scores(total_cases=len(results))

    for r in results:
        if r.real_or_synthetic == "real":
            scores.real_cases += 1
        else:
            scores.synthetic_cases += 1

        if r.is_bug:
            scores.positives += 1
        else:
            scores.negatives += 1

        if r.observed_outcome == "error":
            scores.errors += 1
        elif r.observed_outcome == "unsupported":
            scores.unsupported += 1
        elif r.is_bug:
            scores.detected += 1 if r.observed_outcome == "detect" else 0
            scores.missed += 1 if r.observed_outcome != "detect" else 0
        else:
            scores.false_positives += 1 if r.observed_outcome == "detect" else 0
            scores.true_negatives += 1 if r.observed_outcome != "detect" else 0

        if r.surprise:
            scores.surprises.append(f"{r.case_id}: {r.surprise}")

    return scores


def _rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render(scores: Scores, results: list[CaseResult]) -> str:
    lines = [
        "",
        "jachai benchmark",
        f"  cases            {scores.total_cases}  "
        f"({scores.real_cases} real, {scores.synthetic_cases} synthetic)",
        f"  positives        {scores.positives}    negatives {scores.negatives}",
        f"  detected         {scores.detected}",
        f"  missed           {scores.missed}",
        f"  false positives  {scores.false_positives}",
        f"  true negatives   {scores.true_negatives}",
        f"  unsupported      {scores.unsupported}  (excluded from the rates below)",
        f"  errors           {scores.errors}",
        "",
        f"  precision            {_rate(scores.precision)}",
        f"  recall               {_rate(scores.recall)}",
        f"  false-positive rate  {_rate(scores.false_positive_rate)}",
    ]

    if scores.real_cases == 0:
        lines += [
            "",
            "  NOTE: every case in this corpus is synthetic. Synthetic cases show that a"
            " check fires; they say nothing about whether the check matters. Phase 0 is"
            " not complete until real bugs are in here.",
        ]

    if scores.surprises:
        lines += ["", "  surprises (declared expectation did not match observation):"]
        lines += [f"    - {s}" for s in scores.surprises]

    errors = [r for r in results if r.error]
    if errors:
        lines += ["", "  errors:"]
        lines += [f"    - {r.case_id}: {r.error}" for r in errors]

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.evaluate",
        description="Score jachai against the benchmark corpus.",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--timeout", type=float, default=1.0, help="seconds per call")
    parser.add_argument("--cases", type=Path, default=None, help="alternative cases directory")
    args = parser.parse_args(argv)

    try:
        cases = load_corpus(args.cases)
    except CorpusError as exc:
        print(f"benchmark: {exc}", file=sys.stderr)
        return 2

    if not cases:
        print("benchmark: corpus is empty — nothing to measure", file=sys.stderr)
        return 2

    results = [run_case(case, args.timeout) for case in cases]
    scores = score(results)

    if args.json:
        payload = {
            "scores": {
                **{k: v for k, v in asdict(scores).items()},
                "precision": scores.precision,
                "recall": scores.recall,
                "false_positive_rate": scores.false_positive_rate,
            },
            "cases": [asdict(r) for r in results],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render(scores, results))

    if scores.errors or scores.surprises:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
