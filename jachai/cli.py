"""Command line entry point: ``jachai check <path>``."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__
from .checks import run_checks
from .discover import discover, module_is_nondeterministic
from .generate import plan
from .model import FunctionReport
from .probe import load_module
from .report import render, render_json


def check_file(
    path: Path, max_cases: int = 60, timeout: float = 2.0, include_private: bool = False
) -> list[FunctionReport]:
    source = path.read_text(encoding="utf-8")
    specs, tree = discover(source, include_private=include_private)
    nondeterministic = module_is_nondeterministic(tree)

    module = load_module(path)
    reports: list[FunctionReport] = []

    for spec in specs:
        fn = getattr(module, spec.name, None)
        if fn is None or not callable(fn):
            continue
        invocations = plan(spec, max_cases=max_cases)
        reports.append(run_checks(spec, fn, invocations, nondeterministic, timeout))

    return reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jachai",
        description="Find the inputs that break generated Python code.",
    )
    parser.add_argument("--version", action="version", version=f"jachai {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="check one or more Python files")
    check.add_argument("paths", nargs="+", type=Path)
    check.add_argument("--json", action="store_true", help="machine-readable output")
    check.add_argument("--quiet", action="store_true", help="hide functions with no findings")
    check.add_argument("--max-cases", type=int, default=60, help="input budget per function")
    check.add_argument("--timeout", type=float, default=2.0, help="seconds per call")
    check.add_argument("--include-private", action="store_true", help="also check _private functions")
    check.add_argument(
        "--fail-on",
        choices=["never", "high", "any"],
        default="high",
        help="exit non-zero when findings at this level exist (default: high)",
    )
    check.set_defaults(func=_run_check)
    return parser


def _run_check(args: argparse.Namespace) -> int:
    exit_code = 0

    for path in args.paths:
        if not path.exists():
            print(f"jachai: no such file: {path}", file=sys.stderr)
            exit_code = max(exit_code, 2)
            continue

        started = time.perf_counter()
        try:
            reports = check_file(
                path,
                max_cases=args.max_cases,
                timeout=args.timeout,
                include_private=args.include_private,
            )
        except SyntaxError as exc:
            print(f"jachai: {path} does not parse: {exc}", file=sys.stderr)
            exit_code = max(exit_code, 2)
            continue
        except BaseException as exc:  # noqa: BLE001 - importing user code can do anything
            print(f"jachai: could not import {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            exit_code = max(exit_code, 2)
            continue
        elapsed = time.perf_counter() - started

        if args.json:
            print(render_json(str(path), reports, elapsed))
        else:
            print(render(str(path), reports, elapsed, show_clean=not args.quiet))

        high = sum(1 for r in reports for f in r.findings if f.confidence == "high")
        total = sum(len(r.findings) for r in reports)
        if args.fail_on == "high" and high:
            exit_code = max(exit_code, 1)
        elif args.fail_on == "any" and total:
            exit_code = max(exit_code, 1)

    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
