# M1 — BM25 baseline, end to end

## Goal

A real Top-1 number on the Verified Set, printed by `faultloc evaluate --rung bm25`.

No LLM. No embeddings. No agent. The point of M1 is to build the evaluation harness — loader, filter, scorer, results log — which every later rung reuses unchanged, and to prove the pipeline runs end to end.

## Why this first

Per [ADR-0003](../../docs/adr/0003-baseline-ladder.md), the harness is the project's most load-bearing code. Rung 1 needs no model, so it exercises the harness for free and produces an anchoring number in about a day.

## Done when

- `faultloc evaluate --rung bm25 --split dev` prints Top-1, Recall@3, Recall@5, and wall-clock time
- The Instance Filter is unit-tested and its rejection counts are reported per drop reason
- The dev/test split is frozen and committed, and was fixed before any tuning
- One entry exists in `RESULTS.md` recording the number with its dataset, split, commit, and date

## Out of scope

Cost tracking (no model calls yet), the Fresh Set, calibration, the web layer.
