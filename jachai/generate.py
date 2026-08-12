"""Turn a function signature into concrete arguments worth trying.

Two sources of truth, in priority order:

  1. the type annotation, when there is one;
  2. the parameter *name*, when there is not -- ``count`` is almost always an
     int, ``items`` is almost always a sequence.

The generator is deliberately small and boring. Exotic input generation is a
solved problem (Hypothesis); what is not solved is deciding which of the
resulting failures are worth a human's attention. That judgement lives in
``checks.py``.
"""

from __future__ import annotations

import ast
import math
from typing import Any

from .model import Case, FunctionSpec, Invocation, Param

# --------------------------------------------------------------------------
# annotation parsing
# --------------------------------------------------------------------------

_ALIASES = {
    "Sequence": "list",
    "Iterable": "list",
    "Collection": "list",
    "List": "list",
    "MutableSequence": "list",
    "Mapping": "dict",
    "MutableMapping": "dict",
    "Dict": "dict",
    "Set": "set",
    "FrozenSet": "set",
    "AbstractSet": "set",
    "Tuple": "tuple",
    "Text": "str",
}


def normalise(annotation: str | None) -> tuple[str, list[str], bool]:
    """Return ``(kind, type_args, optional)`` for an annotation string.

    ``Optional[int]``, ``int | None`` and ``Union[int, None]`` all collapse to
    ``("int", [], True)``. Anything we do not understand becomes ``"unknown"``,
    which downstream means "guess from the name and forgive TypeErrors".
    """
    if not annotation:
        return ("unknown", [], False)

    try:
        node = ast.parse(annotation, mode="eval").body
    except SyntaxError:
        return ("unknown", [], False)

    optional = False

    def unwrap(n: ast.expr) -> ast.expr | None:
        nonlocal optional
        # X | None
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
            parts = [n.left, n.right]
            keep = []
            for p in parts:
                if isinstance(p, ast.Constant) and p.value is None:
                    optional = True
                else:
                    keep.append(p)
            return keep[0] if len(keep) == 1 else (keep[0] if keep else None)
        # Optional[X] / Union[X, None]
        if isinstance(n, ast.Subscript):
            base = n.value
            base_name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
            if base_name == "Optional":
                optional = True
                return n.slice
            if base_name == "Union":
                elts = n.slice.elts if isinstance(n.slice, ast.Tuple) else [n.slice]
                keep = []
                for p in elts:
                    if isinstance(p, ast.Constant) and p.value is None:
                        optional = True
                    else:
                        keep.append(p)
                return keep[0] if keep else None
        return n

    node = unwrap(node)
    if node is None:
        return ("none", [], True)

    args: list[str] = []
    if isinstance(node, ast.Subscript):
        slice_node = node.slice
        elts = slice_node.elts if isinstance(slice_node, ast.Tuple) else [slice_node]
        for e in elts:
            try:
                args.append(ast.unparse(e))
            except Exception:
                args.append("unknown")
        node = node.value

    if isinstance(node, ast.Attribute):
        name = node.attr
    elif isinstance(node, ast.Name):
        name = node.id
    elif isinstance(node, ast.Constant) and node.value is None:
        return ("none", [], True)
    else:
        return ("unknown", args, optional)

    return (_ALIASES.get(name, name), args, optional)


# --------------------------------------------------------------------------
# name heuristics, used only when there is no annotation
# --------------------------------------------------------------------------

_NAME_HINTS: list[tuple[frozenset[str], str]] = [
    (frozenset({"n", "i", "j", "k", "count", "num", "size", "length", "len", "index",
                "idx", "total", "amount", "age", "limit", "offset", "depth", "width",
                "height", "port", "year", "steps", "times", "capacity"}), "int"),
    (frozenset({"ratio", "rate", "score", "price", "pct", "percent", "percentage",
                "weight", "factor", "threshold", "temperature", "alpha", "lr"}), "float"),
    (frozenset({"s", "text", "name", "title", "path", "url", "key", "message", "msg",
                "label", "word", "line", "content", "email", "token", "query",
                "prefix", "suffix", "sep", "pattern", "filename"}), "str"),
    (frozenset({"items", "values", "data", "rows", "entries", "elements", "results",
                "nums", "numbers", "seq", "arr", "array", "records", "samples",
                "points", "tokens", "words", "lines", "batch"}), "list"),
    (frozenset({"mapping", "config", "options", "params", "meta", "table", "lookup",
                "counts", "settings", "headers", "attrs"}), "dict"),
    (frozenset({"flag", "verbose", "debug", "active", "enabled", "strict",
                "reverse", "recursive"}), "bool"),
]


def guess_from_name(name: str) -> str:
    lowered = name.lower().lstrip("_")
    for names, kind in _NAME_HINTS:
        if lowered in names:
            return kind
    if lowered.startswith(("is_", "has_", "should_", "can_", "use_", "do_")):
        return "bool"
    for names, kind in _NAME_HINTS:
        if any(token in lowered for token in names if len(token) > 3):
            return kind
    return "unknown"


# --------------------------------------------------------------------------
# candidate values
# --------------------------------------------------------------------------

_LONG_STRING = "x" * 4096


def _scalar_cases(kind: str) -> list[Case]:
    """Ordinary values first, then boundary values.

    The ordinary values are deliberately listed in *descending* order, so that a
    container built from the first two is unsorted. Without that, a function
    that sorts its argument in place looks innocent, because sorting an already
    sorted list changes nothing.
    """
    if kind == "int":
        return [
            Case(3, "3", False),
            Case(1, "1", False),
            Case(0, "zero", True),
            Case(-1, "negative", True),
            Case(10**18, "very large", True),
        ]
    if kind == "float":
        return [
            Case(2.5, "2.5", False),
            Case(1.25, "1.25", False),
            Case(0.0, "zero", True),
            Case(-1.5, "negative", True),
            Case(math.inf, "infinity", True),
            Case(math.nan, "NaN", True),
        ]
    if kind == "str":
        return [
            Case("hello", '"hello"', False),
            Case("beta", '"beta"', False),
            Case("", "empty string", True),
            Case("   ", "whitespace only", True),
            Case("0", '"0"', True),
            Case("héllo ✓", "non-ASCII text", True),
            Case(_LONG_STRING, "4096-character string", True),
        ]
    if kind == "bool":
        return [Case(True, "True", False), Case(False, "False", False)]
    if kind == "bytes":
        return [
            Case(b"data", 'b"data"', False),
            Case(b"beta", 'b"beta"', False),
            Case(b"", "empty bytes", True),
        ]
    if kind == "none":
        return [Case(None, "None", True)]
    return []


def cases_for(kind: str, type_args: list[str], optional: bool, depth: int = 0) -> list[Case]:
    """All values worth trying for one parameter of the given type."""
    cases = _scalar_cases(kind)

    if not cases and kind in ("list", "set", "tuple", "dict"):
        inner_kind, inner_args, inner_opt = normalise(type_args[0]) if type_args else ("int", [], False)
        inner = cases_for(inner_kind, inner_args, inner_opt, depth + 1) if depth < 2 else _scalar_cases("int")
        typical = next((c.value for c in inner if not c.edgy), 1)
        second = next((c.value for c in inner if not c.edgy and c.value != typical), typical)

        if kind == "list":
            cases = [
                Case([typical, second], "2-element list", False),
                Case([], "empty list", True),
                Case([typical], "single-element list", True),
                Case([typical, typical], "list with duplicates", True),
                Case([typical] * 500, "500-element list", True),
            ]
        elif kind == "set":
            try:
                cases = [
                    Case({typical, second}, "2-element set", False),
                    Case(set(), "empty set", True),
                ]
            except TypeError:
                cases = [Case(set(), "empty set", True)]
        elif kind == "tuple":
            cases = [
                Case((typical, second), "2-element tuple", False),
                Case((), "empty tuple", True),
            ]
        else:  # dict
            val_kind, val_args, val_opt = normalise(type_args[1]) if len(type_args) > 1 else ("int", [], False)
            val_inner = cases_for(val_kind, val_args, val_opt, depth + 1) if depth < 2 else _scalar_cases("int")
            val = next((c.value for c in val_inner if not c.edgy), 1)
            key = typical if isinstance(typical, (str, int, float, bool, tuple)) else "k"
            cases = [
                Case({key: val}, "1-entry dict", False),
                Case({}, "empty dict", True),
            ]

    if not cases:  # unknown type -- try a spread and forgive the TypeErrors
        cases = [
            Case(3, "3", False),
            Case("hello", '"hello"', False),
            Case(0, "zero", True),
            Case("", "empty string", True),
            Case([], "empty list", True),
        ]

    if optional:
        cases = cases + [Case(None, "None", True)]
    return cases


#: Kinds for which we can build a value that genuinely satisfies the annotation.
SUPPORTED_KINDS = frozenset(
    {"int", "float", "str", "bool", "bytes", "list", "dict", "set", "tuple", "none"}
)


_SCALAR_KINDS = frozenset({"int", "float", "str", "bool", "bytes", "none"})
_CONTAINER_KINDS = frozenset({"list", "dict", "set", "tuple"})


def understood(annotation: str | None) -> bool:
    """True if we can produce a value that actually matches this annotation.

    ``list[int]`` yes; ``Path``, ``UserRecord`` and ``list[UserRecord]`` no. The
    check is recursive on purpose: filling a ``list[UserRecord]`` with integers
    is exactly as wrong as passing an integer for a ``UserRecord``, and it fails
    one call deeper where the mistake is harder to spot.

    A bare ``list`` also counts as not understood, because the element type is
    unconstrained and any element we invent is a guess.
    """
    if annotation is None:
        return False
    kind, args, _ = normalise(annotation)
    if kind in _SCALAR_KINDS:
        return True
    if kind in _CONTAINER_KINDS:
        return bool(args) and all(understood(arg) for arg in args)
    return False


def cases_for_param(param: Param) -> list[Case]:
    kind, args, optional = normalise(param.annotation)
    if kind == "unknown" and not args:
        kind = guess_from_name(param.name)
        if kind == "unknown":
            return cases_for("unknown", [], optional)
    return cases_for(kind, args, optional)


# --------------------------------------------------------------------------
# invocation planning
# --------------------------------------------------------------------------


def plan(spec: FunctionSpec, max_cases: int = 60) -> list[Invocation]:
    """One baseline call, then one call per edge value, varying a single param.

    Varying one parameter at a time keeps every report line attributable: we can
    always say *which* input caused the failure. A full cartesian product would
    be exponentially larger and no more informative.
    """
    params = spec.callable_params
    if not params:
        return [Invocation({}, None, "no arguments")]

    pool = {p.name: cases_for_param(p) for p in params}
    baseline: dict[str, Any] = {}
    for p in params:
        typical = next((c for c in pool[p.name] if not c.edgy), pool[p.name][0])
        baseline[p.name] = typical.value

    plans = [Invocation(dict(baseline), None, "typical values")]

    for p in params:
        for case in pool[p.name]:
            if not case.edgy:
                continue
            args = dict(baseline)
            args[p.name] = case.value
            plans.append(Invocation(args, p.name, f"{p.name}={case.label}"))
            if len(plans) >= max_cases:
                return plans

    return plans
