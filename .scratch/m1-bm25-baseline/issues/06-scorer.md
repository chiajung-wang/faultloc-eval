# 06 — Scorer

Status: ready-for-agent

## Context

Turns Predictions plus Ground-Truth File Sets into the metrics locked in the design: Top-1, Recall@3, Recall@5.

Like the Instance Filter, this is a pure function whose silent failure would invalidate every number the project publishes. Test it first.

## Acceptance criteria

- Top-1: the rank-1 path is in the Ground-Truth File Set
- Recall@k: proportion of ground-truth files appearing in the top k
- Path comparison is normalised — no false negatives from leading `./` or separator differences
- Unit-tested including the multi-file ground-truth case and the empty-prediction case
- Aggregation reports per-repo breakdown alongside the overall figure

## Notes

Cost and latency fields exist in the output shape from the start, even though rung 1 has no model cost. Later rungs fill them without a schema change.
