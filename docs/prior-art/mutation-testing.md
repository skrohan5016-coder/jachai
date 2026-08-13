# Mutation testing (mutmut, Cosmic Ray)

## What it does
Introduces small deliberate faults into the source and checks whether the test
suite notices. A surviving mutant marks a gap in the tests.

## How it relates to jachai
Complementary rather than competing. Mutation testing measures the quality of
tests that exist; jachai runs where no tests exist yet. The roadmap places
mutation testing in Phase 3 as a way to grade jachai itself.

## What it can detect
Weak assertions, untested branches, and tests that pass regardless of behaviour.

## What it cannot detect
Bugs in code with no test suite at all — with nothing to kill the mutants, every
mutant survives and the signal is meaningless.

## Evaluation procedure
Run mutmut against jachai's own tests and record the surviving mutants. Each
survivor is a claim the suite does not actually check.

## Evidence still missing
Not run. Applying it to jachai's own tests would be the sharpest available
critique of this project's central claim about false positives.
