# 03 — Rung 3 end to end, one model

Status: done

## Parent

[M4 PRD](../PRD.md)

## What to build

The rung. Take the union candidate list from issue 01, ask the model to reorder it, and return a `Prediction` carrying **real** `cost_usd` and `latency_s`.

End to end: `faultloc evaluate --rung rerank --split dev` prints the metrics and prepends a `RESULTS.md` entry, unchanged in format from every rung before it.

**This is the first rung that spends money.** `Prediction.cost_usd` has existed since M1 and reported `$0.00` through three rungs precisely so nothing would need retrofitting at this moment. Cost is read from the response's usage, per instance, not estimated from a price list.

Whatever issue 02 decided about determinism is implemented here, including the response cache if that is the decision. A cached rerun must be free and byte-identical, and a cache built by a different model or prompt must never be read as if it matched — the same failure `EmbeddingIndex` guards against.

The budget cap is enforced here too: a run that would exceed it stops with a clear message rather than reporting the overspend afterwards.

## Acceptance criteria

- [x] `faultloc evaluate --rung rerank --split dev` runs end to end and emits a `RESULTS.md` entry
- [x] `cost_usd` is read from the model response's token usage, per instance
- [x] `latency_s` measured per instance and reported alongside cost
- [x] The determinism decision from ADR-0008 implemented and pinned by a test
- [x] A cache built by a different model or prompt is refused, not silently reused
- [x] Hard spend cap stops a run before exceeding it
- [x] A malformed or unparseable model response degrades to the input ranking rather than crashing the run, and is counted
- [x] Candidate union identical to issue 01's, so the ceiling measured there still applies
- [x] Tests make no network calls — the model client is injectable, as the encoder is at rung 2
- [x] `uv run pytest` and `uv run ruff check` clean

## Notes

The model can return a file that was not in the candidate list, or return fewer than it was given. Both are hallucination-adjacent and both must be handled explicitly and counted rather than quietly dropped — `CONTEXT.md`'s Path Guardrail is the M5 version of this problem, and the counting here is its first evidence.

Start with `--limit` on a handful of instances to see real cost and a real response before running 244 of them.

Same dev split, same frozen seed. The test split stays untouched until M7.

## Blocked by

- [02 — ADR-0008: rerank design, budget, and determinism](02-rerank-design-adr.md)

## Comments

**Smoke-tested against OpenRouter, 2026-08-05.** Four probe calls, ~$0.0003 total, no repo data sent. Everything below is measured from the responses rather than read off documentation.

### Pin the provider, not just the model

**The most consequential finding, and it changes what the rung must send.** `deepseek/deepseek-v4-pro` is served by twelve upstream providers at $0.435–$1.68 per 1M input — **3.9×** — and the *quantization varies across them*: fp8, fp4, bf16, unknown. `openai/gpt-oss-120b` is the same story, CoreWeave at fp4 against DeepInfra at bf16.

Two of the four probe calls landed on different providers (DigitalOcean, StreamLake) and cost 6× different amounts for the same prompt.

An unpinned call therefore has no fixed price *and no fixed weights precision*. A cross-model table built on that would be comparing routing luck. ADR-0007 established that a model name is not provenance; this is the same lesson one level down, where name **and revision** are still not enough.

Rung 3 must send explicit routing and record what it got:

```json
"provider": {"only": ["deepseek"], "allow_fallbacks": false}
```

**`only`, not `order`, and the value is the endpoint's `tag`** from `/api/v1/models/{id}/endpoints` — not its display name. `{"order": ["DeepSeek"]}` returns a 404 that says nothing about the name being wrong.

The response's `provider` field goes in the `RESULTS.md` entry beside the model ID. Without it the entry names a model that does not determine the number.

**The route decides whether reasoning happens at all.** Same model, same prompt: first-party `deepseek` gave 154 reasoning tokens at default, `streamlake/fp8` gave 131, and `digitalocean` gave **0**. An unpinned run samples a mixture, some of which silently opt out of the variable the ablation measures.

**Routing depends on an account setting outside this repo.** `only: ["deepseek"]` first failed with *"No endpoints available matching your guardrail restrictions and data policy"* — OpenRouter filters providers that may train on prompts. The account toggle was changed deliberately, since this project sends only public issue text and open-source code. A third party cannot reproduce a rung-3 row from this commit alone without the same setting.

### An empty answer is the failure mode that matters

At `max_tokens=50`, `gpt-oss-120b` returned **empty content** — 45 tokens spent reasoning, nothing left to answer with. At 800 it answers and stops.

This is worse than a crash. An empty response degrades to the input ranking, which *is* fusion's order, so a too-small token budget produces a rung-3 run scoring identically to rung 2.5. That reads as "the model didn't help" when the model never answered. **`finish_reason == "length"` must be counted as a failure**, not absorbed into the degrade path, and the count belongs in the entry.

### Cost comes from the response, not a price list

OpenRouter returns actual `cost` per request with `"usage": {"include": true}`. That is better than this issue's acceptance criterion asked for — `cost_usd` is read, not computed, so a price change cannot silently invalidate a published figure. Reasoning tokens arrive under `usage.completion_tokens_details.reasoning_tokens`.

### The reasoning controls are not equivalent, and one is unverified

`gpt-oss-120b` responds to `reasoning: {effort}` — 46 reasoning tokens at `low` against 113 at `high` on an identical trivial prompt. Confirmed working.

`deepseek-v4-pro` looked unmeasurable at first — every unpinned probe returned 0 reasoning tokens, even at default. **That conclusion was wrong**, and wrong because of the routing problem above: those calls were landing on DigitalOcean, whose serve does no reasoning. Pinned to the first-party route the toggle is clean:

| | reasoning tokens | completion | cost |
|---|---|---|---|
| default | 154 | 158 | $0.000154 |
| `reasoning: {enabled: false}` | 0 | 3 | $0.0000196 |

7.9× cost difference. Both models' ablations are measurable, provided the route is pinned.

`minimax-m3` spent 0 reasoning tokens on a trivial prompt despite adaptive thinking being its documented default. Adaptive genuinely decides per prompt, so a "thinking on" row's cost depends on the prompt and not only on the flag.

### Still a guess

ADR-0008's 2,000-reasoning-tokens-per-instance estimate is unchanged by any of this. A trivial prompt drew 113 at high effort; the real prompt is 4,886 tokens with twenty candidates to weigh. The $1.50 per-run cap is what makes the guess safe — measure it on the first batch and replace it.

**Closed 2026-08-07.** Four cells scored on the dev split, n=244 each.

**Spend: $1.95 in published rows, $5.59 on the account.** The gap — **$3.64, nearly two thirds of the total** — went to abandoned runs and the route hunt: $2.25 on a first attempt that completed nothing, $0.63 on a Groq run killed at instance 110, and the rest on probes that established the provider limits. The four numbers below cost $1.95; finding out how to obtain them cost almost twice that.

ADR-0008 set a $5.00 milestone cap and the $2.25 was re-based to setup partway through, by agreement, on the grounds that it produced no number and everything it did produce is now code. Against the re-based budget the milestone spent $3.18 of $5.00. Against the original cap it did not fit, which is the more honest way to read it.

| Row | Top-1 | Recall@3 | Recall@5 | Cost | Wall clock |
|---|---|---|---|---|---|
| `rerank-deepseek-on` | 79.1% (73.6–83.7) | 83.9% | 84.6% | $0.49 | 178m |
| `rerank-deepseek-off` | 75.0% (69.2–80.0) | 82.8% | 85.7% | $0.31 | 22m |
| **`rerank`** — ladder row | **74.2% (68.3–79.3)** | 81.8% | 85.3% | $0.39 | 186m |
| `rerank-gpt-oss-low` | 72.5% (66.6–77.8) | 81.1% | 83.3% | $0.76 | 9m |
| `hybrid` (rung 2.5) | 45.5% (39.4–51.8) | 65.2% | 73.1% | $0.00 | — |

### Every cell beats fusion decisively; none beats another

The four span 72.5–79.1% with intervals overlapping almost entirely, against fusion's 45.5% which none of them touch. **An 11.8× price difference and a reasoning-effort ablation both produce nothing distinguishable at n=244.**

That is the outcome ADR-0008's first amendment was designed to make readable: the original model pair sat 1.5pp apart on a benchmark, against this project's ±6pp interval, so the table could only ever have said "indistinguishable" without anyone being able to tell whether that meant anything. Widening the price span to 11.8× means the null result is now informative — paying more does not buy accuracy *here*, and the measurement was capable of showing otherwise.

**High reasoning effort lost on cost-effectiveness to its own model at low effort**: 74.2% for $0.39 against 72.5% for $0.76 — 1.7pp inside a ±6pp interval, for roughly 7,000 extra reasoning tokens per instance. The ladder row was declared in advance and stays the ladder row; it simply did not earn its reasoning.

### Sphinx sits on its ceiling in all four

63.6% in every cell — exactly the union Candidate Set's hit@20 for sphinx from issue 01. Four models, three providers, one number. Every one of them picks correctly on **every sphinx instance where the answer was retrievable at all**; its remaining loss is entirely retrieval's, not ranking's.

Rung 2.6 is the contrast that makes the point: the cross-encoder scored **18.2%** on sphinx, well under the same ceiling. Sphinx is not simply "the repo where the ceiling binds" — it is a repo where reading twenty candidates together in language solves what scoring them one at a time does not.

### Three disclosures that belong beside these numbers

**The ladder row fell back to fusion on 7% of instances.** 17 of 244 replies were unparseable, nearly all empty content — some flagged `finish=length`, but four returned empty with `finish=stop`, which the truncation check cannot see. Those instances kept fusion's ranking, so the published 74.2% is depressed by a serving quirk rather than by the model. Cached responses make this recoverable later without re-paying for the other 227.

**The low-vs-high ablation moves three variables, not one.** `rerank-gpt-oss-low` ran at `72ed477` on Cerebras; `rerank` at `6fad58d` on DeepInfra. Route, commit and effort all differ, so the 1.7pp gap cannot be attributed to effort. Accepted deliberately rather than re-run.

**`rerank-deepseek-on` stamps a commit made during its run.** It loaded `3418386` and stamps `b46e55c`; `src/` changed between them. Checked rather than assumed: its model spec, `MAX_TOKENS` and `_parse` are byte-identical across those commits, and the changes were the response cache, retry patience and the gpt-oss route — none of which touch this cell. The number reproduces; the entry's claim is imprecise, not wrong.

### What the runs cost in engineering, and what that bought

Four cells, four routes, three genuine bugs found by the degrade counters rather than by tests:

- **Cerebras enforces an 8,192-token completion limit while advertising 40,960.** High effort needs 7,300–8,200, so it truncated a third of replies. Caught at instance 40 of a run that would have published a plausible number produced entirely by fusion.
- **`MAX_TOKENS` was sized from a toy prompt.** 4,000 was chosen because 50 was too few; the real prompt needs four times that.
- **Retries watched only one of three places a failure arrives.** HTTP status, then a `504` inside a `200` body, then transport-level disconnects and read timeouts — each one killed a run before being handled. The last is still open as a follow-up.

The counters earned their existence. Every one of these failures produces *a ranking*, so a run that hit them looked healthy in every metric except the one that says how often the model actually answered.

### For M5

**92 off-list paths across the four cells** — files named that were never candidates: 6 for gpt-oss at high effort, 14 for DeepSeek reasoning, 29 for gpt-oss at low effort, and 43 for DeepSeek with reasoning disabled. That is the first sizing evidence for the Path Guardrail, and the spread is the interesting part: **the two configurations that reason least hallucinate most**, by roughly seven to one over the most deliberate one.

**Recall@5 barely exceeds Recall@3 in every cell** (85.3% against 81.8% for the ladder row, with Top-1 at 74.2%). These models are decisive: when they are right, they are right at rank 1. An escalation strategy assuming the answer is "somewhere near the top" has less to work with than the ceiling suggests.

**The remaining headroom is retrieval, not ranking.** Issue 01's ceiling is 88.9%; the best cell reaches 79.1%. Sphinx demonstrates the shape of what is left — the answer has to be *in the list* before any amount of reasoning helps.
