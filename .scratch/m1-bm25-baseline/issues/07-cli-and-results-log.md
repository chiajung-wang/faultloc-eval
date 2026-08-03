# 07 — Wire the CLI and open the results log

Status: ready-for-agent

## Context

Closes M1. `faultloc evaluate --rung bm25 --split dev` runs the whole pipeline and prints the numbers.

`RESULTS.md` starts here and becomes the project's running log. Every number published anywhere in the repo must be traceable to an entry in it.

## Acceptance criteria

- `faultloc evaluate --rung bm25 --split dev [--limit N]` runs end to end
- Prints Top-1, Recall@3, Recall@5, per-repo breakdown, instance count, wall-clock time
- Prints the Filter Rate with per-reason drop counts
- `RESULTS.md` created with the first entry: dataset, split, instance count, filter rate, metrics, commit SHA, date
- README updated with the first real number

## Notes

The results-log format set here is permanent. Design it so a later reader can tell exactly which code produced which number.
