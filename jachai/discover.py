"""Static pass: read a Python file and describe its functions without running it.

We deliberately learn two things here that later stages need in order to keep
false positives down:

  * ``raises_explicitly`` -- does the function contain a ``raise`` statement?
    If it does, a ValueError coming out of it is probably deliberate input
    validation, not an accident.
  * ``nondeterministic_imports`` -- does the module import random/time/etc?
    If so, we must not accuse it of being nondeterministic.
"""

from __future__ import annotations

import ast

from .model import FunctionSpec, Param

#: Modules whose presence makes "same input, different output" expected.
NONDETERMINISTIC_MODULES = frozenset(
    {"random", "time", "datetime", "os", "secrets", "uuid", "socket", "tempfile"}
)


def _annotation_text(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node).strip()
    except Exception:  # pragma: no cover - unparse is very reliable on 3.9+
        return None


#: Constructors whose result is a fresh mutable object shared across calls
#: when used as a default argument.
_MUTABLE_CALLS = frozenset({"list", "dict", "set", "bytearray", "defaultdict",
                            "OrderedDict", "Counter", "deque"})


def _is_mutable_default(node: ast.expr | None) -> bool:
    """True for defaults evaluated once and then shared by every call."""
    if node is None:
        return False
    if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        return name in _MUTABLE_CALLS
    return False


def _params_of(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[Param, ...]:
    a = node.args
    out: list[Param] = []

    positional = list(a.posonlyargs) + list(a.args)
    defaults_start = len(positional) - len(a.defaults)
    for i, arg in enumerate(positional):
        default = a.defaults[i - defaults_start] if i >= defaults_start else None
        out.append(
            Param(
                name=arg.arg,
                annotation=_annotation_text(arg.annotation),
                has_default=i >= defaults_start,
                kind="positional",
                mutable_default=_is_mutable_default(default),
            )
        )

    if a.vararg is not None:
        out.append(
            Param(a.vararg.arg, _annotation_text(a.vararg.annotation), True, "var_positional")
        )

    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        out.append(
            Param(
                name=arg.arg,
                annotation=_annotation_text(arg.annotation),
                has_default=default is not None,
                kind="keyword_only",
                mutable_default=_is_mutable_default(default),
            )
        )

    if a.kwarg is not None:
        out.append(
            Param(a.kwarg.arg, _annotation_text(a.kwarg.annotation), True, "var_keyword")
        )

    return tuple(out)


def _contains_raise(node: ast.AST) -> bool:
    """True if the function body raises anywhere -- including inside nested ifs.

    We do not descend into nested function definitions: a raise inside an inner
    helper says nothing about the outer function's own validation habits.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Raise):
            return True
        if _contains_raise(child):
            return True
    return False


def _raised_names(node: ast.AST, found: set[str] | None = None) -> set[str]:
    """Names of exception types the function raises on purpose, e.g. {"ValueError"}.

    If a function says ``raise ImportError(...)`` then an ImportError coming out
    of it is the design, not a defect. Matching on the exact type is far safer
    than a blanket "this function raises something, trust it".
    """
    found = set() if found is None else found
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Raise) and child.exc is not None:
            exc = child.exc
            target = exc.func if isinstance(exc, ast.Call) else exc
            if isinstance(target, ast.Name):
                found.add(target.id)
            elif isinstance(target, ast.Attribute):
                found.add(target.attr)
        _raised_names(child, found)
    return found


def _is_generator(node: ast.AST) -> bool:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, (ast.Yield, ast.YieldFrom)):
            return True
        if _is_generator(child):
            return True
    return False


def imported_modules(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def module_is_nondeterministic(tree: ast.Module) -> bool:
    return bool(imported_modules(tree) & NONDETERMINISTIC_MODULES)


def discover(source: str, include_private: bool = False) -> tuple[list[FunctionSpec], ast.Module]:
    """Return module-level functions in *source*, plus the parsed tree.

    Methods and nested functions are out of scope for v0.1 on purpose: they
    usually need an instance or a closure to call, and guessing at those is
    exactly how a checker starts producing noise.
    """
    tree = ast.parse(source)
    specs: list[FunctionSpec] = []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name.startswith("_") and not include_private:
            continue
        specs.append(
            FunctionSpec(
                name=node.name,
                lineno=node.lineno,
                params=_params_of(node),
                returns=_annotation_text(node.returns),
                raises_explicitly=_contains_raise(node),
                is_generator=_is_generator(node),
                raised_names=frozenset(_raised_names(node)),
                doc=ast.get_docstring(node),
            )
        )

    return specs, tree
