# ADR-001 — Hypothesis versus the custom input generator

**Status:** proposed — decision deferred pending benchmark evidence
**Date:** 2026-08-12

## Context

The roadmap's Phase 1 says plainly: lean on Hypothesis for input generation and
do not write our own fuzzer. The shipped code does the opposite. `generate.py`
is a hand-written generator: type-hint parsing, parameter-name heuristics, and a
fixed table of boundary values per type.

This is a real divergence from the plan, and it was not a considered decision at
the time — the tool was built in an environment with no network access, so
`pip install hypothesis` was not available. The design that resulted then
acquired a justification after the fact ("zero dependencies"). That ordering is
worth naming honestly, because a constraint that becomes a principle deserves
more scrutiny than one chosen on purpose.

## What the custom generator actually does

- Parses annotations, including `Optional[X]`, `X | None`, and generics
- Falls back to parameter-name heuristics when there is no annotation
- Emits ordinary values plus boundary values (empty, zero, negative, huge,
  non-ASCII, NaN, infinity)
- Varies one parameter at a time, so every finding names the input that caused it
- Refuses to guess at types it cannot construct, which is where most of its
  false-positive suppression comes from

What it does not do: shrinking, stateful generation, coverage guidance,
heterogeneous containers (`tuple[int, str]` is filled from the first type
only), or multi-type unions (`int | str` collapses to `int`). Hypothesis does
all of this, and does it better than a re-implementation ever will.

## The conflict

Two goals point in opposite directions.

1. **Adoption.** `pip install jachai` pulling in nothing is a genuine advantage
   for a tool people run casually on a file they were just handed. The README
   makes this promise today.
2. **Quality.** Input generation is a solved problem. Every hour spent
   improving our generator is an hour not spent on the part that is actually
   unsolved: deciding which failures are worth a human's attention.

The second goal matters more to the project's thesis. The claimed contribution
is not "we generate inputs"; it is "we decide what to report". If the generator
is the weak link, replacing it is straightforward and correct.

## Options

**A. Keep the custom generator.** Zero dependencies stay. Ceiling on input
quality stays too. Cheap now, pays interest forever.

**B. Depend on Hypothesis outright.** Best inputs, shrinking for free, a mature
project behind it. Loses the zero-dependency promise and its install-friction
argument.

**C. Optional backend.** Keep the current generator as the default; use
Hypothesis when it is importable, behind `pip install jachai[hypothesis]`. Two
code paths to maintain, and two sets of results to explain when they disagree.

**D. Use Hypothesis internally, expose neither.** Vendor nothing, depend
properly, and treat generation as an implementation detail so the checker can
switch later without a user-visible change.

## Recommendation

Defer, and decide with data rather than taste. Concretely:

1. Build the real-bug corpus (Phase 0, in progress).
2. For each missed bug, record *why* it was missed — bad input, or a check that
   does not exist. This is the number that settles the question.
3. If input quality accounts for a meaningful share of misses, take option **C**
   first (optional backend, so the zero-dependency default survives), and
   revisit **B** if the two paths prove not worth maintaining.
4. If input quality accounts for almost none of the misses, keep the custom
   generator and spend the effort on the reporting logic instead.

## Consequence if we get this wrong

Migrating early costs the install-friction advantage for no measured gain.
Migrating late means every benchmark number collected until then was measuring
our generator rather than our checker — which would make the corpus, the one
thing Phase 0 exists to produce, harder to interpret.

That risk is the reason step 2 above is mandatory rather than nice to have.

## Unchanged by this decision

The core rule stands either way: **a model may guess, but only a program may
conclude.** Hypothesis, if adopted, proposes inputs. It does not render
verdicts, and neither does any language model.
