"""Decide which observed behaviours are worth telling a human about.

This module is the actual product. Generating a crash is easy; knowing that a
particular crash is a *bug* rather than deliberate input validation, or an
artefact of our own bad guess at an argument type, is the hard part.

Every suppression rule below exists because without it the tool cries wolf, and
a checker that cries wolf gets deleted within a week.
"""

from __future__ import annotations

import math
from typing import Any

from .model import Finding, FunctionReport, FunctionSpec, Invocation, Outcome
from .generate import normalise, understood
from .probe import call, call_twice

#: Exceptions that essentially never represent intentional behaviour.
ACCIDENTAL = (
    ZeroDivisionError,
    IndexError,
    AttributeError,
    UnboundLocalError,
    RecursionError,
    StopIteration,
    OverflowError,
    NameError,
)

#: Exceptions a careful author might raise on purpose to reject bad input.
VALIDATION_LIKE = (ValueError, TypeError, AssertionError, NotImplementedError, KeyError)

#: Function-name prefixes that announce "I mutate my argument, that is my job".
INPLACE_PREFIXES = (
    "add", "append", "insert", "update", "set", "push", "extend", "remove",
    "pop", "register", "put", "store", "write", "apply_to", "fill", "clear",
)

COMPARABLE = (int, float, str, bool, bytes, list, dict, tuple, set, frozenset, type(None))


def _exc_name(exc: BaseException) -> str:
    return type(exc).__name__


def _annotation_of(spec: FunctionSpec, param_name: str | None) -> str | None:
    if param_name is None:
        return None
    for p in spec.params:
        if p.name == param_name:
            return p.annotation
    return None


#: What Python raises when you hand a function the wrong kind of object.
#: If we invented that object ourselves, the blame is ours, not the author's.
TYPE_MISMATCH = (TypeError, AttributeError)


def _we_guessed_the_type(spec: FunctionSpec, varied: str | None) -> bool:
    """True if the value that reached the function was our invention.

    For an edge-case call we know exactly which parameter we pushed, so we check
    that one. For the baseline call every parameter is in play, so a single
    unannotated parameter is enough to make the result untrustworthy.
    """
    if varied is not None:
        return not understood(_annotation_of(spec, varied))
    return any(not understood(p.annotation) for p in spec.callable_params)


def _looks_inplace(spec: FunctionSpec) -> bool:
    name = spec.name.lower()
    if name.endswith(("_inplace", "_in_place")) or "mutate" in name:
        return True
    return name.startswith(INPLACE_PREFIXES)


def _declares_no_return(spec: FunctionSpec) -> bool:
    kind, _, optional = normalise(spec.returns)
    return kind == "none" or (spec.returns is None and False) or optional and kind == "none"


# --------------------------------------------------------------------------
# check 1: crashes on edge input
# --------------------------------------------------------------------------


def check_crash(spec: FunctionSpec, outcome: Outcome) -> Finding | None:
    exc = outcome.exception
    if exc is None:
        return None

    where = outcome.invocation.label

    # The author raises this exact exception type on purpose somewhere in the
    # body. Seeing it come out is the design working, not a defect.
    if _exc_name(exc) in spec.raised_names:
        return None

    # Command line entry points end by exiting. That is the contract, not a bug.
    if isinstance(exc, SystemExit):
        return None

    if outcome.timed_out:
        return Finding(
            spec.name, spec.lineno, "hang", "hang",
            f"did not finish on {where}",
            "The call was still running when the time limit expired. "
            "Usually an unbounded loop or runaway recursion.",
            "high",
        )

    # We may have handed the function an object of a type it never advertised.
    # A complaint about that object is a complaint about our own guess.
    if isinstance(exc, TYPE_MISMATCH) and _we_guessed_the_type(spec, outcome.invocation.varied):
        return None

    if isinstance(exc, ACCIDENTAL):
        return Finding(
            spec.name, spec.lineno, "crash", f"crash:{_exc_name(exc)}",
            f"{_exc_name(exc)} on {where}",
            f"{exc or 'no message'} — this exception type is almost never raised "
            f"on purpose, so the input path looks unhandled.",
            "high",
        )

    if isinstance(exc, VALIDATION_LIKE):
        # The author validates their own input somewhere in this function, so a
        # ValueError here is probably the validation firing as designed.
        if spec.raises_explicitly:
            return None
        return Finding(
            spec.name, spec.lineno, "crash", f"crash:{_exc_name(exc)}",
            f"{_exc_name(exc)} on {where}",
            f"{exc or 'no message'} — the function has no raise statement of its own, "
            f"so this came from deeper inside rather than from deliberate validation.",
            "medium",
        )

    return Finding(
        spec.name, spec.lineno, "crash", f"crash:{_exc_name(exc)}",
        f"{_exc_name(exc)} on {where}",
        str(exc) or "no message",
        "medium",
    )


# --------------------------------------------------------------------------
# check 2: silently mutates an argument
# --------------------------------------------------------------------------


def check_mutation(spec: FunctionSpec, outcome: Outcome) -> list[Finding]:
    if not outcome.mutated or outcome.crashed:
        return []
    # Returning None while changing an argument is the normal in-place idiom.
    if outcome.returned is None:
        return []
    if _looks_inplace(spec):
        return []

    return [
        Finding(
            spec.name, spec.lineno, "mutation", f"mutation:{name}",
            f"modifies its argument '{name}' and also returns a value",
            "The caller's object is changed in place while the function looks pure "
            "from the outside. Callers who reuse that object will see it silently "
            "altered. Copy the argument before modifying it, or return None.",
            "high",
        )
        for name in outcome.mutated
    ]


# --------------------------------------------------------------------------
# check 3: return value contradicts the declared return type
# --------------------------------------------------------------------------

_RUNTIME_TYPES: dict[str, tuple[type, ...]] = {
    "int": (int,),
    "float": (int, float),  # int where float is declared is conventionally fine
    "str": (str,),
    "bool": (bool,),
    "bytes": (bytes, bytearray),
    "list": (list,),
    "dict": (dict,),
    "set": (set, frozenset),
    "tuple": (tuple,),
}


def check_return_contract(spec: FunctionSpec, outcome: Outcome) -> Finding | None:
    if spec.is_generator or outcome.crashed or spec.returns is None:
        return None

    kind, _, optional = normalise(spec.returns)
    if kind in ("unknown", "Any", "object", "none"):
        return None

    value = outcome.returned

    if value is None:
        if optional:
            return None
        return Finding(
            spec.name, spec.lineno, "contract", "contract:none",
            f"declared -> {spec.returns} but returned None on {outcome.invocation.label}",
            "A code path falls off the end of the function without returning. "
            f"Either return a real {spec.returns} or declare the type as optional.",
            "high",
        )

    expected = _RUNTIME_TYPES.get(kind)
    if expected is None:
        return None
    if isinstance(value, expected):
        return None
    if kind == "int" and isinstance(value, bool):
        return None

    return Finding(
        spec.name, spec.lineno, "contract", f"contract:{type(value).__name__}",
        f"declared -> {spec.returns} but returned {type(value).__name__} "
        f"on {outcome.invocation.label}",
        f"Returned value was {value!r}. The annotation and the behaviour disagree; "
        "one of them is wrong.",
        "high",
    )


# --------------------------------------------------------------------------
# check 4: same input, different answer
# --------------------------------------------------------------------------


def _comparable(value: Any, depth: int = 0) -> bool:
    """True only if two of these can be meaningfully compared for equality.

    Descends into containers: a tuple holding a plain object is no more
    comparable than the object itself. Without this, any function returning
    ``(data, some_object)`` looks nondeterministic, because the default repr of
    an object embeds its memory address and that address changes every call.
    """
    if depth > 3:
        return False
    if isinstance(value, (int, float, str, bool, bytes, type(None))):
        return True
    if isinstance(value, (list, tuple, set, frozenset)):
        return all(_comparable(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return all(
            _comparable(k, depth + 1) and _comparable(v, depth + 1) for k, v in value.items()
        )
    return False


def _stable(a: Any, b: Any) -> bool:
    if not _comparable(a) or not _comparable(b):
        return True  # cannot compare meaningfully; stay quiet
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    try:
        if a == b:
            return True
    except Exception:
        return True
    try:
        return repr(a) == repr(b)
    except Exception:
        return True


def check_determinism(
    spec: FunctionSpec, fn: Any, invocation: Invocation, module_nondeterministic: bool, timeout: float
) -> Finding | None:
    if module_nondeterministic:
        return None

    first, second = call_twice(fn, invocation, timeout)
    if first.crashed or second.crashed:
        return None
    if _stable(first.returned, second.returned):
        return None

    return Finding(
        spec.name, spec.lineno, "determinism", "determinism",
        "returns a different value for the same input",
        f"Two identical calls returned {first.returned!r} and then {second.returned!r}. "
        "The module imports no clock or random source, so this points at hidden shared "
        "state — a mutable default argument, a module-level cache, or a global.",
        "high",
    )


# --------------------------------------------------------------------------
# check 5: mutable default argument (static -- no execution needed)
# --------------------------------------------------------------------------


def check_mutable_default(spec: FunctionSpec) -> list[Finding]:
    """A default like ``x=[]`` is created once and shared by every call forever.

    This is the one check that needs no execution at all, and it has no
    plausible false positive: there is no situation in which a shared mutable
    default is what the author meant.
    """
    return [
        Finding(
            spec.name, spec.lineno, "shared-default", f"shared-default:{p.name}",
            f"parameter '{p.name}' has a mutable default that is shared by every call",
            "The default object is created once when the function is defined, not "
            "once per call, so anything written into it leaks into the next caller. "
            f"Use '{p.name}=None' and build a fresh one inside the function.",
            "high",
        )
        for p in spec.params
        if p.mutable_default
    ]


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------


def run_checks(
    spec: FunctionSpec,
    fn: Any,
    invocations: list[Invocation],
    module_nondeterministic: bool = False,
    timeout: float = 2.0,
) -> FunctionReport:
    """Execute every planned invocation and collect the findings worth showing."""
    report = FunctionReport(spec=spec)
    static_findings = check_mutable_default(spec)

    # A *args/**kwargs-only signature tells us nothing about what a valid call
    # looks like. Guessing produces a TypeError that says more about us than it.
    if not spec.callable_params and any(
        p.kind in ("var_positional", "var_keyword") for p in spec.params
    ):
        report.findings.extend(static_findings)
        report.skipped_reason = "variadic signature: no way to infer a valid call"
        return report

    if not invocations:
        report.findings.extend(static_findings)
        report.skipped_reason = None if static_findings else "no arguments could be generated"
        return report

    baseline = call(fn, invocations[0], timeout)
    report.calls = 1

    # If we cannot even call the function with ordinary-looking values, we have
    # misunderstood its signature. Reporting anything now would be noise.
    if isinstance(baseline.exception, TYPE_MISMATCH) and any(
        not understood(p.annotation) for p in spec.callable_params
    ):
        report.findings.extend(static_findings)
        report.skipped_reason = "could not infer argument types (add type hints for a deeper check)"
        return report

    seen: dict[str, Finding] = {}
    for finding in static_findings:
        seen[finding.signature] = finding
        report.findings.append(finding)

    def add(finding: Finding | None) -> None:
        if finding is None:
            return
        existing = seen.get(finding.signature)
        if existing is not None:
            existing.occurrences += 1
            return
        seen[finding.signature] = finding
        report.findings.append(finding)

    for outcome in [baseline] + [call(fn, inv, timeout) for inv in invocations[1:]]:
        if outcome is not baseline:
            report.calls += 1
        add(check_crash(spec, outcome))
        for f in check_mutation(spec, outcome):
            add(f)
        add(check_return_contract(spec, outcome))

    add(check_determinism(spec, fn, invocations[0], module_nondeterministic, timeout))
    report.calls += 2

    report.findings.sort(key=Finding.sort_key)
    return report
