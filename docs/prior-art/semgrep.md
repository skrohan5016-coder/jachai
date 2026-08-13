# Semgrep

## What it does
Pattern-matching static analysis. Rules are written in the shape of the code
they match, which makes them far more approachable than AST visitors.

## How it relates to jachai
Static where jachai is dynamic, and the better model for the parts of jachai
that need no execution — the mutable-default check is essentially a Semgrep rule
already, and Semgrep would express it more clearly.

## What it can detect
Anything with a syntactic signature: mutable defaults, dangerous calls, missing
error handling, project-specific conventions. Fast, safe, no code execution.

## What it cannot detect
Anything that depends on runtime values: whether a function actually mutates its
argument, whether it terminates, whether it returns what it declares.

## Evaluation procedure
Write Semgrep rules for jachai's static checks; run both over the corpus; record
which findings are reproducible statically. Any check Semgrep matches is a check
jachai should not claim as its own contribution.

## Evidence still missing
Not run. Also worth studying as an adoption model — Semgrep's rule registry is
the clearest example of the ecosystem jachai currently lacks.
