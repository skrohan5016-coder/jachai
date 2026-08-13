# Hypothesis

## What it does
Property-based testing for Python. You state a property that should hold for all
inputs; it generates inputs trying to falsify it, then shrinks any counterexample
to the smallest form that still fails.

## How it relates to jachai
The closest neighbour, and the more mature tool by a wide margin. The difference
is what the user must supply. Hypothesis needs you to know and write the
property. jachai infers weak properties on its own and runs on a file you were
handed thirty seconds ago. Where you can write the property, write it there.

## What it can detect
Anything expressible as a property, with far better input generation than ours:
shrinking, stateful testing, targeted search, composable strategies.

## What it cannot detect
Nothing you have not thought to assert. A codebase with no Hypothesis tests gets
no benefit from it, which is exactly the situation after a model writes 500 lines.

## Evaluation procedure
Install; write the obvious properties for each corpus fixture; record whether it
finds the planted bug and how much human effort each property cost.

## Evidence still missing
Not run. The critical unknown: on a real corpus, how many bugs does jachai find
that a reasonable engineer's Hypothesis properties would have caught anyway?
If the answer is "almost none", the roadmap's Phase 0 stop condition applies.
