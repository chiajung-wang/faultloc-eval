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
