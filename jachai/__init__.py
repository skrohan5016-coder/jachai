"""jachai — find the inputs that break generated Python code.

The problem this exists for is old and has a name: the *test oracle problem*.
Running code is easy; knowing whether its output is correct is the hard part.
Machines now write code faster than people can convince themselves it works,
and that gap is what jachai chips away at.

Design rule, and the reason this is not just another wrapper around an LLM:
**a model may guess, but only a program may conclude.** Everything reported here
was observed by actually running the function, never asserted by a language model.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .model import Finding, FunctionReport, FunctionSpec  # noqa: E402

__all__ = ["Finding", "FunctionReport", "FunctionSpec", "__version__", "check_file"]


def check_file(*args, **kwargs):
    """Lazy re-export of :func:`jachai.cli.check_file` (keeps import cost low)."""
    from .cli import check_file as _check_file

    return _check_file(*args, **kwargs)
