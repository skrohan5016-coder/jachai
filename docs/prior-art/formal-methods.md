# Formal methods (Dafny, TLA+, Lean)

## What it does
Proves that a program or specification satisfies stated properties, for all
inputs, mathematically rather than by sampling.

## How it relates to jachai
The opposite end of the rigour spectrum, and a standing reminder of the tradeoff.
Formal methods give certainty at the cost of a specification most engineers will
never write. jachai gives weak evidence at zero cost. The roadmap is explicit
that the interesting lesson is *why* most developers do not use these tools.

## What it can detect
Whole classes of defect, exhaustively, with a proof rather than a sample.

## What it cannot detect
Anything outside the specification — and writing the specification is the work.
An unspecified property is unverified no matter how strong the prover.

## Evaluation procedure
No direct comparison is meaningful. The useful study is adoption: where formal
methods succeed in industry (protocols, kernels, cryptography) and where they do
not (ordinary application code), and why.

## Evidence still missing
Not attempted. The relevant question is one of positioning, not detection:
jachai's honest claim can never be more than "these specific promises were not
visibly broken".
