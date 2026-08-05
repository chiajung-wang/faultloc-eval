# 06 — Rung 2.6, a cross-encoder between fusion and the LLM

Status: ready-for-agent

## Parent

[M4 PRD](../PRD.md)

## What to build

Rung 2.6: a cross-encoder that scores each `(issue text, Evidence Chunk)` pair jointly and reorders the Candidate Set by that score. No API, no prompt, no money.

**This exists to stop rung 3 being credited with a gain a free local model produces.** `CONTEXT.md` states the rule plainly — *a rung's value is the delta it adds over the rung below*, and inserting a system between two rungs changes what the rung above is credited with. Rung 3's delta is currently measured against rung 2.5 at 45.5% Top-1. If a cross-encoder lands at 60%, then rung 3's honest delta is over *that*, and roughly all of the LLM's apparent gain was reranking-in-general rather than reasoning-in-natural-language.

The mechanism is genuinely different, which is why it earned its own number rather than an Ablation. Rung 2 embeds the issue and the chunk separately and compares vectors — the chunk's encoding cannot depend on the query. A cross-encoder reads both together in one forward pass, so a chunk can be scored as relevant *to this issue specifically*. Rung 3 also reads both together, but through natural-language reasoning over all 20 candidates at once. Three distinct mechanisms, one metric.

**Same payload as rung 3, so the two rungs differ by mechanism alone.** ADR-0008 fixed what a candidate is shown as: its path plus its Evidence Chunk, K=20, in Candidate Set order. Rung 2.6 uses exactly that. A rung that scored different text would make the 2.6-to-3 delta measure the payload rather than the mechanism.

**Local execution is the right default here, and ADR-0007's 487-hour wall does not apply.** That number came from embedding 1,013,340 chunks. This scores 244 instances × 20 candidates = **4,880 pairs**, once, and nothing is cached across runs because the pair depends on the issue. Even at 10 pairs/second that is eight minutes. The asymmetry is worth stating in the issue's own writeup, because "local was too slow last time" is exactly the kind of conclusion that survives past the conditions that produced it.

**Candidate models are to be selected at the time, not taken from this file.** As of writing, the families worth checking are `BAAI/bge-reranker-v2-*` and `Qwen/Qwen3-Reranker-*` (0.6B / 4B / 8B), plus whatever `sentence-transformers` currently lists under pretrained cross-encoders. Two of these were named from a search on 2026-08-05 and will be stale; re-check rather than trust them. ADR-0007's revisit condition has the criteria this project selects models by.

**One criterion dominates and must be checked first: input length.** The pair is the issue text plus the chunk. Measured (`scripts/prompt_token_cost.py`): issue text mean 420 tokens, p90 937; Evidence Chunk mean 214, p90 508. So a p90 pair is roughly **1,450 tokens**, and the classic 512-token cross-encoders would truncate most of the issue report before the model saw the code. ADR-0007 documented a 512-token cap as an accepted consequence and it later turned out to be discarding 59% of the corpus. **Do not repeat that**: measure the truncation rate before pinning anything, and report it.

Licence matters too — at least one widely-recommended reranker family is CC-BY-NC, which this project cannot use without a commercial arrangement. Check before benchmarking, not after.

## Acceptance criteria

- [ ] `faultloc evaluate --rung cross-encoder --split dev` runs end to end and emits a `RESULTS.md` entry with `cost_usd` of `$0.00` and a real `latency_s`
- [ ] Candidate Set identical to issue 01's, so the 88.9% hit@20 ceiling still applies unchanged
- [ ] Pair text is the Evidence Chunk, matching ADR-0008's payload exactly
- [ ] Model pinned by identifier **and** revision, as ADR-0007 pins rung 2's
- [ ] **Truncation rate measured and reported** — the share of pairs exceeding the model's input limit, and what is lost when they do
- [ ] Licence of the pinned model recorded, and confirmed usable
- [ ] At least two candidate models compared, on Top-1, truncation rate, and throughput — a single model chosen without a comparison is the failure ADR-0007 records
- [ ] `test_is_deterministic` holds — this rung runs locally with fixed weights and has no excuse not to
- [ ] Behind the `embed` extra, like rung 2; rung 1 stays runnable without torch
- [ ] Tests make no network calls and download no weights — the scorer is injectable, as the encoder is at rung 2
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

**This blocks issue 05, not issue 03.** Rung 3 can be built and scored in parallel; what cannot happen is *publishing* rung 3's delta before the row beneath it exists. Issue 05's "delta reported against both rung 2 and the best lexical row" needs a third comparator, and its README table gains a row.

The interesting outcome is not the good one. If rung 2.6 lands near rung 3, that is the most useful finding M4 could produce — a free local model matching a paid API one — and it reframes M5 harder than another win would. If it lands at rung 2.5, then joint encoding buys nothing on this data and the gap really is about reasoning.

Worth a check while the pairs are being scored: **does the cross-encoder's score correlate with correctness?** M7 needs a Confidence signal and ADR-0004 has no source for one yet. A cross-encoder emits a calibrated-ish relevance score for free, which is a better candidate than anything rung 1 or 2 produces. Record the observation; do not build the calibrator here.

Sphinx caps at 63.6% hit@20 and has been the outlier at every rung for three distinct reasons. Expect it to be one again; report per-repo as every rung does.

No ADR is required unless the model choice turns out to be contested — the pin, the revision, the truncation rate and the licence go in this issue's closing comment, which is where issue 01's numbers live. If rung 2.6 ships as a permanent ladder row, fold a short ADR-0009 in at that point.

## Blocked by

- [01 — The union candidate set and its recall ceiling](01-union-recall-ceiling.md) — done; supplies the Candidate Set and the ceiling
- [02 — ADR-0008: rerank design, budget, and determinism](02-rerank-design-adr.md) — done; fixes the payload so 2.6 and 3 differ by mechanism only
