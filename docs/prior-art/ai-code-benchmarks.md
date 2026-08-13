# AI-code benchmarks (SWE-bench, HumanEval, Aider benchmarks)

## What it does
Measures how well models write or repair code, usually by running a reference
test suite against generated patches.

## How it relates to jachai
These benchmarks assume a test suite exists to grade against. jachai's premise
is the situation where none does. But the generated-code artefacts they collect
are a plausible source of *real* bug cases — code a model actually produced,
with a known-correct reference to compare against.

## What it can detect
Whether generated code passes its reference tests. Not whether it is safe,
maintainable, or correct outside those tests.

## What it cannot detect
Everything the reference suite does not cover — which includes most of what
jachai looks for: argument mutation, shared defaults, contract drift.

## Evaluation procedure
Mine failing SWE-bench or HumanEval submissions for defects in jachai's
categories. Each one that reproduces becomes a corpus case labelled `real`,
because the code was genuinely generated rather than authored to demonstrate a
bug.

## Evidence still missing
Not mined. This is the most promising route to real cases that does not depend
on waiting for bugs to occur naturally, and it should be tried before the
30-case Phase 0 gate is declared unreachable.
