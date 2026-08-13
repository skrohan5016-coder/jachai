"""Tests for the benchmark corpus and evaluation harness.

The harness exists to produce numbers that decide whether the project continues.
That makes its own correctness load-bearing: a loader that silently drops the
cases it does not understand would report perfect precision on an empty corpus.
Most of these tests are about refusing to score things.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks import evaluate  # noqa: E402
from benchmarks.corpus import (  # noqa: E402
    BENCHMARK_ROOT,
    SCHEMA_PATH,
    CorpusError,
    load_case,
    load_corpus,
    validate,
)

VALID_CASE = {
    "case_id": "example-case",
    "source": {"origin": "authored-for-benchmark", "fixture": "fixtures/valid/empty_average.py",
               "symbol": "average"},
    "language": "python",
    "bug_category": "crash",
    "real_or_synthetic": "synthetic",
    "input": "values=[]",
    "expected_behavior": "return 0.0 or raise a documented error",
    "observed_behavior": "ZeroDivisionError",
    "ground_truth": {"is_bug": True, "verified_by": "maintainer, by running it",
                     "verified_on": "2026-08-12"},
    "jachai_expected": {"outcome": "detect", "kind": "crash"},
    "tool_results": [],
}


def written(tmp: Path, name: str, payload) -> Path:
    path = tmp / name
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    return path


class TestValidation(unittest.TestCase):
    def test_a_complete_case_validates(self):
        validate(VALID_CASE, "example")  # must not raise

    def test_missing_ground_truth_is_rejected(self):
        broken = {k: v for k, v in VALID_CASE.items() if k != "ground_truth"}
        with self.assertRaises(CorpusError) as ctx:
            validate(broken, "example")
        self.assertIn("ground_truth", str(ctx.exception))

    def test_unverified_ground_truth_is_rejected(self):
        """'unverified' is the word people write when they have not checked."""
        for placeholder in ("unverified", "TBD", "", "n/a"):
            case = json.loads(json.dumps(VALID_CASE))
            case["ground_truth"]["verified_by"] = placeholder
            with self.assertRaises(CorpusError, msg=placeholder):
                validate(case, "example")

    def test_missing_is_bug_verdict_is_rejected(self):
        case = json.loads(json.dumps(VALID_CASE))
        del case["ground_truth"]["is_bug"]
        with self.assertRaises(CorpusError):
            validate(case, "example")

    def test_negative_control_cannot_expect_a_detection(self):
        case = json.loads(json.dumps(VALID_CASE))
        case["ground_truth"]["is_bug"] = False
        with self.assertRaises(CorpusError):
            validate(case, "example")

    def test_detect_requires_a_kind(self):
        case = json.loads(json.dumps(VALID_CASE))
        del case["jachai_expected"]["kind"]
        with self.assertRaises(CorpusError):
            validate(case, "example")

    def test_bad_case_id_is_rejected(self):
        for bad in ("Has-Capitals", "sp ace", "x", "under_score"):
            case = json.loads(json.dumps(VALID_CASE))
            case["case_id"] = bad
            with self.assertRaises(CorpusError, msg=bad):
                validate(case, "example")

    def test_real_or_synthetic_must_be_declared(self):
        case = json.loads(json.dumps(VALID_CASE))
        case["real_or_synthetic"] = "realistic"
        with self.assertRaises(CorpusError):
            validate(case, "example")

    def test_tool_result_without_a_command_is_rejected(self):
        """An unrun tool must be omitted, never recorded as a guess."""
        case = json.loads(json.dumps(VALID_CASE))
        case["tool_results"] = [{"tool": "hypothesis", "version": "6.0", "detected": False,
                                 "run_on": "2026-08-12"}]
        with self.assertRaises(CorpusError):
            validate(case, "example")

    def test_fixture_path_cannot_escape_the_benchmark_directory(self):
        case = json.loads(json.dumps(VALID_CASE))
        case["source"]["fixture"] = "../../etc/passwd"
        with self.assertRaises(CorpusError):
            validate(case, "example")


class TestLoading(unittest.TestCase):
    def test_malformed_json_fails_closed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = written(Path(tmp), "broken.json", "{not json")
            with self.assertRaises(CorpusError):
                load_case(path)

    def test_duplicate_case_ids_are_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            written(Path(tmp), "a.json", VALID_CASE)
            written(Path(tmp), "b.json", VALID_CASE)
            with self.assertRaises(CorpusError) as ctx:
                load_corpus(Path(tmp))
            self.assertIn("duplicate", str(ctx.exception))

    def test_missing_fixture_is_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            case = json.loads(json.dumps(VALID_CASE))
            case["source"]["fixture"] = "fixtures/valid/does_not_exist.py"
            written(Path(tmp), "a.json", case)
            with self.assertRaises(CorpusError):
                load_corpus(Path(tmp))

    def test_empty_corpus_loads_as_empty_rather_than_failing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_corpus(Path(tmp)), [])

    def test_shipped_corpus_is_valid(self):
        cases = load_corpus()
        self.assertTrue(cases)
        self.assertEqual(len({c.case_id for c in cases}), len(cases))

    def test_shipped_corpus_is_labelled_synthetic_until_real_bugs_arrive(self):
        """Synthetic cases must never be quietly presented as real ones."""
        for case in load_corpus():
            self.assertIn(case.data["real_or_synthetic"], {"real", "synthetic"})
            if case.data["source"]["origin"] == "authored-for-benchmark":
                self.assertFalse(case.is_real, case.case_id)

    def test_schema_and_validator_agree_on_required_fields(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        for field in schema["required"]:
            case = {k: v for k, v in VALID_CASE.items() if k != field}
            with self.assertRaises(CorpusError, msg=field):
                validate(case, "example")


class TestScoring(unittest.TestCase):
    def _result(self, **kwargs):
        base = dict(
            case_id="c", real_or_synthetic="synthetic", bug_category="crash",
            is_bug=True, expected_outcome="detect", observed_outcome="detect",
        )
        base.update(kwargs)
        return evaluate.CaseResult(**base)

    def test_precision_recall_and_fpr(self):
        results = [
            self._result(case_id="tp1"),
            self._result(case_id="tp2"),
            self._result(case_id="fn1", observed_outcome="miss"),
            self._result(case_id="fp1", is_bug=False, expected_outcome="skip"),
            self._result(case_id="tn1", is_bug=False, expected_outcome="skip",
                         observed_outcome="skip"),
        ]
        scores = evaluate.score(results)
        self.assertEqual((scores.detected, scores.missed), (2, 1))
        self.assertEqual((scores.false_positives, scores.true_negatives), (1, 1))
        self.assertAlmostEqual(scores.precision, 2 / 3)
        self.assertAlmostEqual(scores.recall, 2 / 3)
        self.assertAlmostEqual(scores.false_positive_rate, 0.5)

    def test_rates_are_none_rather_than_zero_when_undefined(self):
        """0.0 reads as a measured result. None reads as 'not measured'."""
        scores = evaluate.score([])
        self.assertIsNone(scores.precision)
        self.assertIsNone(scores.recall)
        self.assertIsNone(scores.false_positive_rate)

    def test_unsupported_cases_are_excluded_from_the_rates(self):
        results = [
            self._result(case_id="tp"),
            self._result(case_id="un", observed_outcome="unsupported",
                         expected_outcome="unsupported"),
        ]
        scores = evaluate.score(results)
        self.assertEqual(scores.unsupported, 1)
        self.assertEqual(scores.recall, 1.0)  # the refusal is not counted as a miss

    def test_disagreement_with_the_declared_expectation_is_surfaced(self):
        results = [self._result(case_id="odd", observed_outcome="miss",
                                surprise="expected detect, observed miss")]
        self.assertEqual(len(evaluate.score(results).surprises), 1)


class TestRunner(unittest.TestCase):
    def test_end_to_end_run_is_deterministic(self):
        first = evaluate.main(["--json", "--timeout", "0.4"])
        second = evaluate.main(["--json", "--timeout", "0.4"])
        self.assertEqual(first, second)

    def test_shipped_corpus_scores_without_surprises(self):
        cases = load_corpus()
        results = [evaluate.run_case(c, timeout=0.4) for c in cases]
        scores = evaluate.score(results)
        self.assertEqual(scores.errors, 0)
        self.assertEqual(scores.surprises, [])
        self.assertEqual(scores.false_positives, 0)

    def test_empty_corpus_exits_non_zero(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(evaluate.main(["--cases", tmp]), 2)

    def test_malformed_corpus_exits_non_zero(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            written(Path(tmp), "bad.json", "{not json")
            self.assertEqual(evaluate.main(["--cases", tmp]), 2)

    def test_benchmark_root_is_the_package_directory(self):
        self.assertTrue((BENCHMARK_ROOT / "cases").is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
