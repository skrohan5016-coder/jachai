# Fuzzing (AFL, libFuzzer, Atheris)

## What it does
Feeds enormous volumes of mutated input into a program, guided by code coverage,
looking for crashes and hangs.

## How it relates to jachai
Same failure modes, opposite economics. Fuzzing spends CPU hours per target and
needs a harness per entry point. jachai spends milliseconds per function and
writes its own calls. Fuzzing goes far deeper on one target; jachai goes
shallowly across every function in a file.

## What it can detect
Deep crash paths, memory-safety failures in native code, and inputs no
hand-written boundary table would ever contain.

## What it cannot detect
Anything that is not a crash: silent argument mutation, a wrong return type, a
shared mutable default. Those are contradictions, not faults.

## Evaluation procedure
Run Atheris on a handful of corpus fixtures with a minimal harness. Record both
detection and setup cost — setup cost is the honest comparison here.

## Evidence still missing
Not run. Expected finding: strictly more crashes, at a per-target cost that
rules it out for casual use.
