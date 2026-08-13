# jachai benchmark corpus

This directory answers the only question that decides whether jachai is worth
continuing: **does it find bugs that existing tools miss, and at what
false-positive cost?**

Until that has a number attached, every claim about the checker is an opinion.

## Run it

```bash
python -m benchmarks.evaluate            # human-readable
python -m benchmarks.evaluate --json     # machine-readable
```

Exit codes: `0` all cases behaved as declared, `1` a surprise or an error,
`2` the corpus could not be loaded.

## Current status — read this before quoting any number

The corpus today contains **7 synthetic cases and 0 real ones**. Synthetic
cases prove that a check fires. They say nothing about whether the check
matters to anyone. The roadmap's Phase 0 requires 30 real bugs collected from
actual work, and that gate has not been met.

The reported precision of 1.000 on this corpus is therefore not evidence of
anything except internal consistency, and the runner says so in its own output.

## Adding a case

One JSON file per case in `cases/`, validated against
`schema/bug-case.schema.json`. The fixture goes in `fixtures/valid/` and should
hold one function, so that a case scores exactly one thing.

Two fields carry most of the weight:

- **`real_or_synthetic`** — `real` means the bug was hit during actual work.
  Code written to demonstrate a bug class is `synthetic`, however realistic it
  looks. Mislabelling here corrupts the only number that matters.
- **`ground_truth.verified_by`** — who confirmed it, and how. Placeholders
  (`unverified`, `TBD`, empty) are rejected by the loader. A case nobody has
  verified cannot be scored, so it is an error rather than a skipped row.

Negative controls — correct code that must not be flagged — are as important as
bugs. Set `ground_truth.is_bug: false` and `jachai_expected.outcome: "skip"`.

## Scoring rules

| Ground truth | jachai reports something | jachai reports nothing |
|---|---|---|
| `is_bug: true` | detection | miss |
| `is_bug: false` | **false positive** | true negative |

Cases jachai declines to check (variadic signature, unconstructable argument
type) are counted as `unsupported` and excluded from precision and recall.
Scoring a refusal as either success or failure would be dishonest.

Rates over an empty denominator report `n/a`, never `0.0`. A zero reads like a
measurement; `n/a` reads like the absence of one.

## Layout

```
schema/     the published contract for a case
cases/      one JSON file per case
fixtures/   the code under test (valid/ and invalid/)
expected/   recorded evaluation snapshots, for spotting drift between runs
tools/      raw output from external tools, kept as evidence
```
