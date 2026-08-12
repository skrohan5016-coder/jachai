"""Render results for a human reading a terminal at the end of a long day.

Rules of thumb applied here:
  * the finding comes first, the explanation second;
  * every finding says what to do about it, not just what is wrong;
  * clean functions are shown too, so silence never looks like a crash.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from .model import FunctionReport

_COLOURS = {
    "red": "\033[31m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "grey": "\033[90m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}

_MARKS = {"high": "!", "medium": "?"}


def _paint(text: str, colour: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{_COLOURS[colour]}{text}{_COLOURS['reset']}"


def _wrap(text: str, width: int, indent: str) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if current and len(current) + len(word) + 1 > width:
            lines.append(indent + current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(indent + current)
    return lines


def render(
    path: str,
    reports: list[FunctionReport],
    elapsed: float,
    colour: bool | None = None,
    show_clean: bool = True,
    width: int = 78,
) -> str:
    if colour is None:
        colour = sys.stdout.isatty()

    out: list[str] = ["", _paint(path, "bold", colour)]
    total_findings = 0
    total_calls = 0

    for report in reports:
        total_calls += report.calls
        spec = report.spec
        location = _paint(f"  line {spec.lineno:<4}", "grey", colour)
        signature = f"{spec.name}({', '.join(p.name for p in spec.callable_params)})"

        if report.skipped_reason:
            out.append(f"{location} {signature}")
            out.append(_paint(f"    -  skipped: {report.skipped_reason}", "grey", colour))
            out.append("")
            continue

        if report.clean:
            if show_clean:
                out.append(f"{location} {signature}")
                out.append(
                    _paint(f"    ok  nothing broke across {report.calls} inputs", "green", colour)
                )
                out.append("")
            continue

        out.append(f"{location} {signature}")
        for finding in report.findings:
            total_findings += 1
            mark = _MARKS.get(finding.confidence, "?")
            colour_name = "red" if finding.confidence == "high" else "yellow"
            headline = finding.headline
            if finding.occurrences > 1:
                headline += f"  (+{finding.occurrences - 1} more inputs)"
            out.append(_paint(f"    {mark}  {headline}", colour_name, colour))
            out.extend(_paint(line, "grey", colour) for line in _wrap(finding.detail, width - 7, "       "))
        out.append("")

    high = sum(1 for r in reports for f in r.findings if f.confidence == "high")
    medium = total_findings - high
    checked = sum(1 for r in reports if not r.skipped_reason)

    summary = (
        f"  {checked} function(s) checked · {total_calls} calls · "
        f"{high} likely bug(s), {medium} worth a look · {elapsed:.2f}s"
    )
    out.append(_paint(summary, "bold", colour))
    out.append("")
    return "\n".join(out)


def render_json(path: str, reports: list[FunctionReport], elapsed: float) -> str:
    payload = {
        "file": path,
        "elapsed_seconds": round(elapsed, 3),
        "functions": [
            {
                "name": r.spec.name,
                "line": r.spec.lineno,
                "calls": r.calls,
                "skipped": r.skipped_reason,
                "findings": [asdict(f) for f in r.findings],
            }
            for r in reports
        ],
    }
    return json.dumps(payload, indent=2)
