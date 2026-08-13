# External tool runs

Raw output from Hypothesis, CrossHair, mutmut and others, one file per
`<tool>-<case_id>-<date>` run, kept as the evidence behind every
`tool_results` entry in `cases/`.

Empty. No external tool has been run against this corpus yet, and the schema
deliberately makes that state distinguishable from "a tool ran and found
nothing": an unrun tool is an absent entry, never `detected: false`.

Running these is the substance of Phase 0 and the single most useful thing
anyone can contribute right now. If Hypothesis and CrossHair already catch
everything in a real corpus, that is the answer, and the roadmap says to stop.
