# Daikon

## What it does
The original work on dynamic invariant detection. Instruments a program, watches
it run, and reports properties that held over every observed execution.

## How it relates to jachai
Same core idea — infer the unwritten rules from execution — with two decades
more research behind it. The differences: Daikon needs an existing test suite or
workload to observe, and reports invariants for a human to read rather than
defects to fix.

## What it can detect
Rich relational invariants across variables and call boundaries that jachai
does not attempt: ordering, linear relationships, containment.

## What it cannot detect
Anything the observed runs never exercise. With no workload, it has nothing to
learn from — which is the same gap jachai fills by generating its own inputs.

## Evaluation procedure
Study the published papers and the invariant taxonomy before running anything.
Chicory/Java tooling makes direct Python comparison awkward; the value here is
conceptual.

## Evidence still missing
Not run. Open question: which Daikon invariant classes could be inferred from
generated rather than observed executions?
