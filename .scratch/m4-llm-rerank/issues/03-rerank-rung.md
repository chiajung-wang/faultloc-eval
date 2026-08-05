# 03 — Rung 3 end to end, one model

Status: ready-for-agent

## Parent

[M4 PRD](../PRD.md)

## What to build

The rung. Take the union candidate list from issue 01, ask the model to reorder it, and return a `Prediction` carrying **real** `cost_usd` and `latency_s`.

End to end: `faultloc evaluate --rung rerank --split dev` prints the metrics and prepends a `RESULTS.md` entry, unchanged in format from every rung before it.

**This is the first rung that spends money.** `Prediction.cost_usd` has existed since M1 and reported `$0.00` through three rungs precisely so nothing would need retrofitting at this moment. Cost is read from the response's usage, per instance, not estimated from a price list.

Whatever issue 02 decided about determinism is implemented here, including the response cache if that is the decision. A cached rerun must be free and byte-identical, and a cache built by a different model or prompt must never be read as if it matched — the same failure `EmbeddingIndex` guards against.

The budget cap is enforced here too: a run that would exceed it stops with a clear message rather than reporting the overspend afterwards.

## Acceptance criteria

- [ ] `faultloc evaluate --rung rerank --split dev` runs end to end and emits a `RESULTS.md` entry
- [ ] `cost_usd` is read from the model response's token usage, per instance
- [ ] `latency_s` measured per instance and reported alongside cost
- [ ] The determinism decision from ADR-0008 implemented and pinned by a test
- [ ] A cache built by a different model or prompt is refused, not silently reused
- [ ] Hard spend cap stops a run before exceeding it
- [ ] A malformed or unparseable model response degrades to the input ranking rather than crashing the run, and is counted
- [ ] Candidate union identical to issue 01's, so the ceiling measured there still applies
- [ ] Tests make no network calls — the model client is injectable, as the encoder is at rung 2
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

The model can return a file that was not in the candidate list, or return fewer than it was given. Both are hallucination-adjacent and both must be handled explicitly and counted rather than quietly dropped — `CONTEXT.md`'s Path Guardrail is the M5 version of this problem, and the counting here is its first evidence.

Start with `--limit` on a handful of instances to see real cost and a real response before running 244 of them.

Same dev split, same frozen seed. The test split stays untouched until M7.

## Blocked by

- [02 — ADR-0008: rerank design, budget, and determinism](02-rerank-design-adr.md)
