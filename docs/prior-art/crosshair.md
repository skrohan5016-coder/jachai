# CrossHair

## What it does
Symbolic execution for Python. Analyses code paths against contracts and
docstring conditions, using an SMT solver to find inputs that violate them.

## How it relates to jachai
The most direct competitor for the "find the input that breaks this" job, and
substantially deeper. CrossHair reasons about paths; jachai pokes at boundary
values and watches. Where CrossHair applies, it should find strictly more.

## What it can detect
Contract violations, unreachable branches, and inputs that break stated
postconditions — including inputs no boundary-value table would contain.

## What it cannot detect
Behaviour it cannot model symbolically: C extensions, heavy I/O, unbounded
loops, and much third-party code. Coverage varies sharply by codebase.

## Evaluation procedure
Install; run `crosshair check` on each corpus fixture; record detections,
runtime, and cases it cannot analyse at all.

## Evidence still missing
Not run. The decisive question is coverage: if CrossHair analyses most real code
successfully, jachai's niche narrows to the code it cannot handle.
