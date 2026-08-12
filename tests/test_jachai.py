"""Tests for jachai.

Written with stdlib unittest so the whole project stays dependency-free and
``python -m unittest`` works on a bare interpreter.

The most important test in this file is ``TestNoFalsePositives``. A checker
that flags correct code is worse than no checker at all, so that class is the
regression guard the rest of the project is built around.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jachai.checks import run_checks  # noqa: E402
from jachai.cli import check_file, main  # noqa: E402
from jachai.discover import discover, module_is_nondeterministic  # noqa: E402
from jachai.generate import cases_for_param, guess_from_name, normalise, plan  # noqa: E402
from jachai.model import Invocation  # noqa: E402
from jachai.probe import call, load_module  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "generated_code.py"


def kinds_for(reports, name):
    for report in reports:
        if report.spec.name == name:
            return {f.kind for f in report.findings}
    raise AssertionError(f"{name} was never checked")


class TestDiscover(unittest.TestCase):
    def test_finds_module_level_functions_only(self):
        specs, _ = discover(
            "def top(): pass\n"
            "class C:\n"
            "    def method(self): pass\n"
            "def outer():\n"
            "    def inner(): pass\n"
        )
        self.assertEqual([s.name for s in specs], ["top", "outer"])

    def test_skips_private_by_default(self):
        specs, _ = discover("def _hidden(): pass\ndef shown(): pass\n")
        self.assertEqual([s.name for s in specs], ["shown"])
        specs, _ = discover("def _hidden(): pass\n", include_private=True)
        self.assertEqual([s.name for s in specs], ["_hidden"])

    def test_detects_explicit_raise(self):
        specs, _ = discover("def a(x):\n    if x: raise ValueError('no')\n    return x\n")
        self.assertTrue(specs[0].raises_explicitly)

    def test_raise_in_nested_function_does_not_count(self):
        specs, _ = discover("def a(x):\n    def inner(): raise ValueError('no')\n    return x\n")
        self.assertFalse(specs[0].raises_explicitly)

    def test_detects_generator(self):
        specs, _ = discover("def g(n):\n    yield n\n")
        self.assertTrue(specs[0].is_generator)

    def test_detects_mutable_defaults(self):
        specs, _ = discover(
            "def f(a=[], b={}, c=set(), d=list(), e=None, g=0, *, h=[]): pass\n"
        )
        mutable = {p.name for p in specs[0].params if p.mutable_default}
        self.assertEqual(mutable, {"a", "b", "c", "d", "h"})

    def test_records_annotations(self):
        specs, _ = discover("def f(x: list[int], y: str = 'a') -> bool: return True\n")
        self.assertEqual(specs[0].params[0].annotation, "list[int]")
        self.assertEqual(specs[0].returns, "bool")
        self.assertTrue(specs[0].params[1].has_default)

    def test_nondeterministic_module_detection(self):
        _, tree = discover("import random\ndef f(): pass\n")
        self.assertTrue(module_is_nondeterministic(tree))
        _, tree = discover("import json\ndef f(): pass\n")
        self.assertFalse(module_is_nondeterministic(tree))


class TestAnnotationParsing(unittest.TestCase):
    def test_plain_types(self):
        self.assertEqual(normalise("int"), ("int", [], False))
        self.assertEqual(normalise("str"), ("str", [], False))

    def test_optional_forms_agree(self):
        for text in ("Optional[int]", "int | None", "Union[int, None]", "typing.Optional[int]"):
            kind, _, optional = normalise(text)
            self.assertEqual((kind, optional), ("int", True), text)

    def test_generic_arguments(self):
        self.assertEqual(normalise("list[str]"), ("list", ["str"], False))
        self.assertEqual(normalise("dict[str, int]"), ("dict", ["str", "int"], False))

    def test_aliases_collapse(self):
        self.assertEqual(normalise("Sequence[int]")[0], "list")
        self.assertEqual(normalise("Mapping[str, int]")[0], "dict")

    def test_unparseable_is_unknown(self):
        self.assertEqual(normalise("!!!")[0], "unknown")
        self.assertEqual(normalise(None)[0], "unknown")


class TestGeneration(unittest.TestCase):
    def test_name_heuristics(self):
        self.assertEqual(guess_from_name("count"), "int")
        self.assertEqual(guess_from_name("text"), "str")
        self.assertEqual(guess_from_name("items"), "list")
        self.assertEqual(guess_from_name("is_ready"), "bool")
        self.assertEqual(guess_from_name("zblorp"), "unknown")

    def test_list_case_is_unsorted(self):
        """Sorting an already sorted list is invisible, so the default must not be sorted."""
        specs, _ = discover("def f(tags: list[str]): pass\n")
        cases = cases_for_param(specs[0].params[0])
        typical = next(c.value for c in cases if not c.edgy)
        self.assertNotEqual(typical, sorted(typical))

    def test_edge_cases_present_for_lists(self):
        specs, _ = discover("def f(values: list[int]): pass\n")
        labels = {c.label for c in cases_for_param(specs[0].params[0])}
        self.assertIn("empty list", labels)

    def test_optional_adds_none(self):
        specs, _ = discover("def f(x: int | None): pass\n")
        self.assertIn(None, [c.value for c in cases_for_param(specs[0].params[0])])

    def test_plan_varies_one_parameter_at_a_time(self):
        specs, _ = discover("def f(a: int, b: str): pass\n")
        plans = plan(specs[0])
        self.assertIsNone(plans[0].varied)
        self.assertTrue(all(p.varied in {"a", "b"} for p in plans[1:]))

    def test_plan_respects_budget(self):
        specs, _ = discover("def f(a: int, b: str, c: list[int], d: float): pass\n")
        self.assertLessEqual(len(plan(specs[0], max_cases=5)), 5)

    def test_zero_argument_function(self):
        specs, _ = discover("def f(): return 1\n")
        self.assertEqual(len(plan(specs[0])), 1)


class TestProbe(unittest.TestCase):
    def test_records_return_value(self):
        outcome = call(lambda x: x * 2, Invocation({"x": 3}, None, "t"))
        self.assertEqual(outcome.returned, 6)
        self.assertFalse(outcome.crashed)

    def test_records_exception(self):
        def boom(x):
            raise ZeroDivisionError("nope")

        outcome = call(boom, Invocation({"x": 1}, None, "t"))
        self.assertIsInstance(outcome.exception, ZeroDivisionError)

    def test_detects_mutation(self):
        def mutate(items):
            items.append(99)
            return items

        outcome = call(mutate, Invocation({"items": [1, 2]}, None, "t"))
        self.assertEqual(outcome.mutated, ("items",))

    def test_caller_arguments_are_not_touched(self):
        original = [1, 2]

        def mutate(items):
            items.append(3)
            return items

        call(mutate, Invocation({"items": original}, None, "t"))
        self.assertEqual(original, [1, 2])

    def test_no_mutation_reported_for_pure_function(self):
        outcome = call(lambda items: list(items) + [1], Invocation({"items": [1]}, None, "t"))
        self.assertEqual(outcome.mutated, ())

    def test_timeout(self):
        def spin():
            while True:
                pass

        outcome = call(spin, Invocation({}, None, "t"), timeout=0.2)
        self.assertTrue(outcome.timed_out)


class TestChecksFire(unittest.TestCase):
    """Each planted bug in the example file must be caught."""

    @classmethod
    def setUpClass(cls):
        cls.reports = check_file(EXAMPLE, timeout=0.4)

    def test_crash_on_empty_input(self):
        self.assertIn("crash", kinds_for(self.reports, "average"))

    def test_argument_mutation(self):
        self.assertIn("mutation", kinds_for(self.reports, "normalise_tags"))

    def test_return_contract_violation(self):
        self.assertIn("contract", kinds_for(self.reports, "find_user"))

    def test_shared_mutable_default(self):
        self.assertIn("shared-default", kinds_for(self.reports, "collect"))

    def test_infinite_loop(self):
        self.assertIn("hang", kinds_for(self.reports, "countdown"))

    def test_findings_are_collapsed_not_repeated(self):
        """One cause must produce one line, however many inputs expose it."""
        for report in self.reports:
            signatures = [f.signature for f in report.findings]
            self.assertEqual(len(signatures), len(set(signatures)), report.spec.name)


class TestNoFalsePositives(unittest.TestCase):
    """The functions in the example file that are correct must stay silent."""

    @classmethod
    def setUpClass(cls):
        cls.reports = check_file(EXAMPLE, timeout=0.4)

    def test_pure_arithmetic_is_clean(self):
        self.assertEqual(kinds_for(self.reports, "add"), set())

    def test_string_handling_is_clean(self):
        self.assertEqual(kinds_for(self.reports, "slugify"), set())

    def test_deliberate_validation_is_not_a_bug(self):
        """safe_divide raises ValueError on purpose. That is correct behaviour."""
        self.assertEqual(kinds_for(self.reports, "safe_divide"), set())

    def test_in_place_helper_returning_none_is_not_a_bug(self):
        self.assertEqual(kinds_for(self.reports, "append_item"), set())

    def test_unannotated_arguments_do_not_produce_type_errors(self):
        """If we guessed the argument type wrong, that is our fault, not the author's."""
        source = "def mystery(zblorp):\n    return zblorp.frobnicate()\n"
        specs, _ = discover(source)
        module = type(sys)("m")
        exec(compile(source, "m", "exec"), module.__dict__)
        report = run_checks(specs[0], module.mystery, plan(specs[0]), timeout=0.4)
        self.assertEqual(report.findings, [])
        self.assertIsNotNone(report.skipped_reason)

    def test_nan_return_is_not_called_nondeterministic(self):
        source = "def f(x: float) -> float:\n    return float('nan')\n"
        specs, _ = discover(source)
        module = type(sys)("m")
        exec(compile(source, "m", "exec"), module.__dict__)
        report = run_checks(specs[0], module.f, plan(specs[0]), timeout=0.4)
        self.assertNotIn("determinism", {f.kind for f in report.findings})

    def test_random_using_module_is_not_called_nondeterministic(self):
        source = "import random\ndef f(n: int) -> int:\n    return random.randint(0, n + 1)\n"
        specs, tree = discover(source)
        module = type(sys)("m")
        exec(compile(source, "m", "exec"), module.__dict__)
        report = run_checks(
            specs[0], module.f, plan(specs[0]), module_is_nondeterministic(tree), timeout=0.4
        )
        self.assertNotIn("determinism", {f.kind for f in report.findings})

    def test_optional_return_may_be_none(self):
        source = "def f(x: int) -> int | None:\n    return None\n"
        specs, _ = discover(source)
        module = type(sys)("m")
        exec(compile(source, "m", "exec"), module.__dict__)
        report = run_checks(specs[0], module.f, plan(specs[0]), timeout=0.4)
        self.assertEqual(report.findings, [])

    def test_int_returned_where_float_declared_is_fine(self):
        source = "def f(x: int) -> float:\n    return x\n"
        specs, _ = discover(source)
        module = type(sys)("m")
        exec(compile(source, "m", "exec"), module.__dict__)
        report = run_checks(specs[0], module.f, plan(specs[0]), timeout=0.4)
        self.assertEqual(report.findings, [])


class TestDogfoodRegressions(unittest.TestCase):
    """Every false positive this tool once produced against its own source.

    Each of these was a real report that would have wasted a real person's time.
    They stay here so they cannot come back.
    """

    def _report(self, source, name=None, timeout=0.4):
        specs, tree = discover(source)
        spec = specs[0] if name is None else next(s for s in specs if s.name == name)
        module = type(sys)("m")
        exec(compile(source, "m", "exec"), module.__dict__)
        return run_checks(
            spec,
            getattr(module, spec.name),
            plan(spec),
            module_is_nondeterministic(tree),
            timeout,
        )

    def test_returning_an_object_is_not_nondeterminism(self):
        """Default reprs embed a memory address that changes every call."""
        source = (
            "class Thing:\n    pass\n\n"
            "def build(n: int) -> tuple:\n    return ([], Thing())\n"
        )
        report = self._report(source, "build")
        self.assertNotIn("determinism", {f.kind for f in report.findings})

    def test_variadic_only_signature_is_skipped(self):
        report = self._report("def wrapper(*args, **kwargs):\n    return args[0]\n")
        self.assertEqual(report.findings, [])
        self.assertIn("variadic", report.skipped_reason)

    def test_custom_class_annotation_is_skipped(self):
        source = (
            "class Record:\n    def total(self): return 1\n\n"
            "def summarise(record: Record) -> int:\n    return record.total()\n"
        )
        report = self._report(source, "summarise")
        self.assertEqual(report.findings, [])

    def test_list_of_custom_class_is_skipped(self):
        """Filling list[Record] with integers is as wrong as passing an integer."""
        source = (
            "class Record:\n    def total(self): return 1\n\n"
            "def total_all(records: list[Record]) -> int:\n"
            "    return sum(r.total() for r in records)\n"
        )
        report = self._report(source, "total_all")
        self.assertEqual(report.findings, [])

    def test_explicitly_raised_type_is_not_a_bug(self):
        source = (
            "def load(name: str) -> str:\n"
            "    if not name:\n"
            "        raise ImportError('no name')\n"
            "    return name\n"
        )
        report = self._report(source)
        self.assertEqual(report.findings, [])

    def test_system_exit_is_not_a_bug(self):
        source = "import sys\ndef quit_now(code: int) -> int:\n    sys.exit(code)\n"
        report = self._report(source)
        self.assertEqual([f for f in report.findings if f.kind == "crash"], [])

    def test_target_output_is_muted(self):
        """A chatty function must not bury the report under its own printing."""
        import contextlib
        import io

        source = "def noisy(n: int) -> int:\n    print('hello ' * 3)\n    return n\n"
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self._report(source)
        self.assertEqual(buffer.getvalue(), "")

    def test_keyboard_interrupt_is_not_swallowed(self):
        def impatient(x):
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            call(impatient, Invocation({"x": 1}, None, "t"))


class TestDeterminismCheck(unittest.TestCase):
    def test_hidden_global_state_is_caught(self):
        source = (
            "_calls = 0\n"
            "def counter(x: int) -> int:\n"
            "    global _calls\n"
            "    _calls += 1\n"
            "    return x + _calls\n"
        )
        specs, tree = discover(source)
        module = type(sys)("m")
        exec(compile(source, "m", "exec"), module.__dict__)
        report = run_checks(
            specs[0], module.counter, plan(specs[0]), module_is_nondeterministic(tree), timeout=0.4
        )
        self.assertIn("determinism", {f.kind for f in report.findings})


class TestCLI(unittest.TestCase):
    def test_exit_code_is_one_when_bugs_found(self):
        self.assertEqual(main(["check", str(EXAMPLE), "--timeout", "0.3", "--json"]), 1)

    def test_exit_code_is_zero_on_clean_file(self):
        clean = EXAMPLE.parent / "_clean_tmp.py"
        clean.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")
        try:
            self.assertEqual(main(["check", str(clean), "--quiet"]), 0)
        finally:
            clean.unlink()

    def test_missing_file_exits_two(self):
        self.assertEqual(main(["check", "does_not_exist.py"]), 2)

    def test_syntax_error_exits_two(self):
        bad = EXAMPLE.parent / "_bad_tmp.py"
        bad.write_text("def broken(:\n")
        try:
            self.assertEqual(main(["check", str(bad)]), 2)
        finally:
            bad.unlink()

    def test_fail_on_never_always_exits_zero(self):
        self.assertEqual(
            main(["check", str(EXAMPLE), "--timeout", "0.3", "--json", "--fail-on", "never"]), 0
        )

    def test_load_module_executes_file(self):
        module = load_module(EXAMPLE, name="example_target")
        self.assertEqual(module.add(2, 3), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
