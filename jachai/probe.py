"""Run the function under test and record exactly what happened.

Three things matter here and nothing else:

  * the call must not be able to hang the whole run (timeout);
  * arguments must be deep-copied so one call cannot poison the next;
  * we must notice if the function *changed* its arguments, because silently
    mutating a caller's list is one of the most common real bugs in generated
    code and one of the easiest to miss by reading.

WARNING: importing a target module executes its top-level code, and the calls
happen inside this process. That makes jachai unsafe to point at untrusted
code -- see the README. Process isolation is the next milestone.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import signal
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from .model import Invocation, Outcome

DEFAULT_TIMEOUT = 2.0


class _Timeout(BaseException):
    """Deliberately not an Exception.

    Target code is full of ``except Exception: pass``. If our timeout inherited
    from Exception, the very functions most likely to loop forever would be the
    ones best equipped to swallow the alarm and keep looping.
    """


def _raise_timeout(signum, frame):  # pragma: no cover - signal path
    raise _Timeout()


class time_limit:
    """Best-effort wall-clock limit. Silently no-ops where signals are unavailable."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.active = False

    def __enter__(self) -> "time_limit":
        try:
            self._previous = signal.signal(signal.SIGALRM, _raise_timeout)
            signal.setitimer(signal.ITIMER_REAL, self.seconds)
            self.active = True
        except (ValueError, AttributeError):
            self.active = False
        return self

    def __exit__(self, *exc_info) -> bool:
        if self.active:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self._previous)
        return False


def package_path(path: Path) -> tuple[Path, str] | None:
    """Work out the dotted name of *path* if it lives inside a package.

    A file that says ``from .model import Finding`` cannot be loaded as a
    standalone module -- Python needs to know which package it belongs to.
    Most real code lives in packages, so getting this right is the difference
    between a tool that works on toy files and one that works on a repository.

    Returns ``(sys.path entry, dotted name)`` or None for a plain script.
    """
    path = path.resolve()
    if not (path.parent / "__init__.py").exists():
        return None

    # A package's __init__.py *is* the package. Importing it as
    # ``pkg.__init__`` would execute the initialiser a second time, under a
    # second name, with whatever side effects that entails.
    parts = [] if path.stem == "__init__" else [path.stem]
    directory = path.parent
    while (directory / "__init__.py").exists():
        parts.append(directory.name)
        directory = directory.parent

    if not parts:
        return None
    return directory, ".".join(reversed(parts))


def load_module(path: str | Path, name: str = "jachai_target") -> ModuleType:
    """Import a file as a module. Raises whatever the module's import raises."""
    path = Path(path)

    located = package_path(path)
    if located is not None:
        root, dotted = located
        inserted = str(root) not in sys.path
        if inserted:
            sys.path.insert(0, str(root))
        try:
            return importlib.import_module(dotted)
        except ImportError:
            if inserted:
                sys.path.remove(str(root))
            # fall through to the standalone path below

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _same(before: Any, after: Any) -> bool:
    """Equality that never raises and never reports a false difference."""
    try:
        result = before == after
        if isinstance(result, bool):
            return result
        return bool(getattr(result, "all", lambda: True)())
    except Exception:
        try:
            return repr(before) == repr(after)
        except Exception:
            return True


MUTABLE = (list, dict, set, bytearray)

#: Never swallow these. If the user presses Ctrl-C mid-run they mean it, and a
#: probe harness that eats the interrupt is a harness nobody can stop.
PASS_THROUGH = (KeyboardInterrupt, GeneratorExit, MemoryError)


@contextlib.contextmanager
def _muted():
    """Swallow anything the function under test prints.

    Target code was not written to be probed, and a chatty function would bury
    the report under its own output.
    """
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        yield sink


def call(fn: Any, invocation: Invocation, timeout: float = DEFAULT_TIMEOUT) -> Outcome:
    """Invoke *fn* once and describe the result, including argument mutation."""
    try:
        args = {k: copy.deepcopy(v) for k, v in invocation.args.items()}
    except Exception:
        args = dict(invocation.args)

    watched = {k: v for k, v in args.items() if isinstance(v, MUTABLE)}
    try:
        pristine = {k: copy.deepcopy(v) for k, v in watched.items()}
    except Exception:
        pristine = {}

    positional = [args.pop(name) for name in invocation.positional_only if name in args]

    outcome = Outcome(invocation=invocation)
    try:
        with _muted(), time_limit(timeout):
            outcome.returned = fn(*positional, **args)
    except _Timeout:
        outcome.timed_out = True
        outcome.exception = TimeoutError(f"no result within {timeout:g}s")
        return outcome
    except PASS_THROUGH:
        raise
    except BaseException as exc:  # noqa: BLE001 - recording is the whole point
        outcome.exception = exc
        return outcome

    seen = dict(zip(invocation.positional_only, positional))
    seen.update(args)
    outcome.mutated = tuple(
        name for name, original in pristine.items()
        if name in seen and not _same(original, seen[name])
    )
    return outcome


def call_twice(fn: Any, invocation: Invocation, timeout: float = DEFAULT_TIMEOUT) -> tuple[Outcome, Outcome]:
    """Two independent calls with identical inputs, for determinism checking."""
    return call(fn, invocation, timeout), call(fn, invocation, timeout)
