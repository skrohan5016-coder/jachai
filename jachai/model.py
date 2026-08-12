"""Shared data model for jachai.

Everything that crosses a module boundary is defined here so the pipeline
stages (discover -> generate -> probe -> check -> report) stay decoupled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Param:
    """One parameter of a discovered function."""

    name: str
    annotation: str | None
    has_default: bool
    kind: str  # "positional" | "keyword_only" | "var_positional" | "var_keyword"
    mutable_default: bool = False


@dataclass(frozen=True)
class FunctionSpec:
    """A module-level function found by static analysis, before it is ever run."""

    name: str
    lineno: int
    params: tuple[Param, ...]
    returns: str | None
    raises_explicitly: bool
    is_generator: bool
    raised_names: frozenset[str] = frozenset()
    doc: str | None = None

    @property
    def callable_params(self) -> tuple[Param, ...]:
        return tuple(p for p in self.params if p.kind in ("positional", "keyword_only"))


@dataclass(frozen=True)
class Case:
    """One candidate value for one parameter, with a human label.

    The label is what shows up in the report, so it must read like something a
    person would say out loud: "empty list", not "list[]".
    """

    value: Any
    label: str
    edgy: bool = False  # True for boundary values, False for ordinary ones


@dataclass(frozen=True)
class Invocation:
    """A concrete set of arguments plus why we chose them."""

    args: dict[str, Any]
    varied: str | None  # which param was pushed to an edge, if any
    label: str


@dataclass
class Outcome:
    """What actually happened when we called the function."""

    invocation: Invocation
    returned: Any = None
    exception: BaseException | None = None
    mutated: tuple[str, ...] = ()
    timed_out: bool = False

    @property
    def crashed(self) -> bool:
        return self.exception is not None


@dataclass
class Finding:
    """One reported problem.

    ``signature`` identifies the underlying *cause* and deliberately excludes the
    triggering input, so twenty inputs that expose the same missing return
    statement collapse into one line instead of twenty. That collapsing is the
    difference between a report a person reads and a report a person mutes.
    """

    func: str
    lineno: int
    kind: str
    signature: str
    headline: str
    detail: str
    confidence: str  # "high" | "medium"
    occurrences: int = 1

    def sort_key(self) -> tuple[int, int, str]:
        return (self.lineno, 0 if self.confidence == "high" else 1, self.kind)


@dataclass
class FunctionReport:
    """Everything learned about one function."""

    spec: FunctionSpec
    findings: list[Finding] = field(default_factory=list)
    calls: int = 0
    skipped_reason: str | None = None

    @property
    def clean(self) -> bool:
        return not self.findings and self.skipped_reason is None
