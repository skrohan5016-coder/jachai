# Recorded evaluation snapshots

`python -m benchmarks.evaluate --json > expected/<date>-<commit>.json`

Snapshots are kept so that a change in the checker can be seen as a change in
the numbers. A commit that improves recall while quietly raising the
false-positive rate looks like progress in a changelog and like a regression
here.

Empty until the first snapshot is taken against a corpus containing real bugs.
Snapshots of an all-synthetic corpus would only record that the tool still
agrees with itself.
