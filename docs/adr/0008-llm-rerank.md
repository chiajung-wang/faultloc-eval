# ADR-0008: Rung 3 reranks with a served open-weights model, and stops claiming determinism

**Status:** Accepted · 2026-08-05 · *amended twice the same day: the provider is OpenRouter, both models changed, the reasoning axis is not symmetric, and the upstream serve must be pinned because it varies in quantization. See the [first](#amended-2026-08-05--wrong-provider-and-a-pair-that-could-not-have-told-us-anything), [second](#amended-again-2026-08-05--the-strong-row-is-deepseek-and-a-model-id-does-not-determine-the-number) and [third](#amended-a-third-time-2026-08-06--full-precision-was-the-wrong-reason-to-pin-a-serve) amendments. Nobody has paid for a run yet. Every cost below is an estimate with its assumption named.*

## Context

Issue 01 established what rung 3 is actually for. The Candidate Set holds a ground-truth file in its top 20 for **88.9%** of dev-split Instances, and the best rung picks one correctly **45.5%** of the time. Roughly 45 points of headroom, none of it in retrieval.

So rung 3 is not "search harder". It is: *given a list that usually contains the answer, choose*. Four things needed a decision before anyone spent money. What the model sees. Which model. What a `RESULTS.md` entry asserts when the system is nondeterministic. What it costs.

**Prompt size, measured** by [`scripts/prompt_token_cost.py`](../../scripts/prompt_token_cost.py), dev split, n=244, 2,000 blobs sampled at seed 0, `chars/4` as in `chunk_corpus_stats.py`:

| Payload, per candidate | Tokens/instance at K=20 | Input per run |
|---|---|---|
| paths only | 597 | 0.15 M |
| path + one signature chunk | 1,213 | 0.30 M |
| **path + one body chunk** | **4,886** | **1.19 M** |
| path + all signatures of the file | 18,956 | 4.63 M |
| path + whole file | 135,305 | 33.01 M |

The issue text is the small part: mean 420 tokens, median 299. A path is 9. A body chunk is 214. **The payload decides the bill, not the issue report.**

**Prices**, from Together's own pricing page and serverless model list, checked 2026-08-05. Checked, not recalled. ADR-0007 records what happens when this series writes an external fact from memory.

## Decision

### The provider and the models

| Field | Value |
|---|---|
| Provider | Together, via `init_chat_model(model_provider="together")` |
| Model A | `deepseek-ai/DeepSeek-V4-Flash-0731` — $0.14 / $0.28 per 1M |
| Model B | `MiniMaxAI/MiniMax-M3` — $0.30 / $1.20 per 1M |

Both are open weights on public Hub repositories, served rather than run locally. ADR-0007's amendment named this cell as the one nobody considered: auditable weights without the local throughput wall.

### What the model sees

The issue text, then 20 candidates in Candidate Set order. Each candidate renders as its path plus its **Evidence Chunk**, the chunk the file scored as under Chunk Aggregation. 1.19 M input tokens per run.

### Output

A full reordering of all 20 paths. Roughly 200 output tokens.

### Thinking mode is a measured variable, not a setting

Both models default to reasoning on. Rather than pick one, **this milestone runs all four cells**: two models × thinking {on, off}. One variable moves per pair.

| Run | Input | Output | **Cost** |
|---|---|---|---|
| Flash, thinking off | $0.17 | $0.01 | **$0.18** |
| Flash, thinking on | $0.17 | $0.15 | **$0.32** |
| MiniMax-M3, thinking off | $0.36 | $0.06 | **$0.42** |
| MiniMax-M3, thinking on | $0.36 | $0.64 | **$1.00** |
| | | | **$1.92 total** |

**This ADR declares the ladder's rung-3 row before any number exists: `DeepSeek-V4-Flash-0731`, thinking on.** The cheaper model in its default mode is the configuration a reader would deploy. Naming it in advance stops the ladder's headline from becoming whichever of four runs happened to win. The other three feed the cross-model table (issue 04) and the thinking Ablation.

### What a rung-3 entry asserts

**Not determinism.** `test_is_deterministic` does not extend to rung 3, and the entry states that rather than omit it. A rung-3 row asserts one sampled run, at a pinned model ID, on a pinned dataset revision, from a clean commit. **Run-to-run variance is unmeasured.**

### Budget

Per-run hard cap **$1.50**. The run checks it against accumulated spend and aborts, rather than report the overspend afterwards. Milestone cap $5.00.

## Rationale

**Why body text rather than paths.** Paths-only is 8× cheaper and would have fit every model on the price list, including the ones $1.00/run ruled out. It fails as the *first* thing to measure. Issue 01 sharpened rung 3's job into one question: which of two retrievers was right on this repository? A path carries no evidence about that. `scikit-learn` is where fusion lands *below* both parents, at 68.8% against lexical's 81.2%. Both retrievers ranked plausible-looking paths there, and the discriminating signal sits in the code. Paths-only remains the obvious Ablation if the text fails to earn its 8×.

**Why the Evidence Chunk and not the file.** A file is 6,735 tokens on average. Twenty of them is 33 M tokens per run, or roughly $5–$40 depending on the model, for one row. The chunk the file *scored as* is the one piece of the file the retriever thought matched the issue. It is the retriever's own evidence. Show the model something the retriever never read, and the two rungs disagree about what a candidate even is. Chunk Aggregation already computes the argmax, and rung 3 stops discarding it.

**Why a full reordering.** Every published row since M1 carries Top-1, Recall@3 and Recall@5. A single pick leaves the recall columns undefined for rung 3, or fills them from fusion's order. That would credit a model with a result reciprocal rank fusion produced for free, which is the exact error issue 01 warned about. The reordering costs ~$0.06 more across all four runs.

**Why both thinking modes, given the cost.** Thinking tokens bill as output, so on MiniMax-M3 the mode is 58% of the run's price. That makes it the most expensive single flag in the project. Buy it blind, and the project pays it forever without knowing what it bought. Two runs per model isolate it with one variable moving. That pattern is what made M3's chunking-vs-bodies finding possible.

Thinking-on also *removes* a control. DeepSeek's API documents that thinking mode ignores `temperature`, `top_p`, `presence_penalty` and `frequency_penalty`. Set them and nothing errors, and nothing happens. The thinking-off rows can at least ask for greedy decoding.

**Why this ADR drops the determinism claim rather than design around it.** Two mechanisms were available. The first commits raw responses to the repo at ~100 KB per model. That makes re-scoring free and lets M9's CI gate run rung 3 without spending. But it turns `test_is_deterministic` into a replay test. Such a test proves the scorer is deterministic, which nobody doubted, and says nothing about the model. The second sets `temperature=0`. That narrows sampling but is not determinism either: batch-dependent kernel nondeterminism remains at the server, and thinking-on rows ignore the parameter outright.

Neither buys the property the phrase implies. **An entry that says "variance unmeasured" is worth more than one that says "deterministic" and means "we replayed a cache."**

## Consequences

**Rung 3 is the first row in `RESULTS.md` that a reader cannot regenerate.** Reproduction needs a Together API key and roughly $1.92. Every rung below is free and reproducible from a commit alone. The project loses a real property it has held since M1. That is the price of the rung existing at all.

**Variance is unmeasured, and that is a named gap rather than an oversight.** The budget holds no repeat runs. The gap has a specific shape. At n=244, Top-1 carries a ±6pp Wilson interval, so run-to-run variance smaller than about 2pp stays invisible against sampling noise. That is a reason to expect an uninformative measurement, not a reason to assume the variance is small. If rung 3's delta over rung 2.5 lands inside a few points, this gap becomes load-bearing and the project must buy repeats. It joins Recall@k's missing interval as the second known measurement gap.

**The $1.50 cap above supersedes the PRD's $0.50 per-run budget.** The PRD wrote that number before anyone measured the payload, and before either model's default reasoning behavior was known.

**Thinking-on latency is 10–60s per instance**, so a sequential dev-split run takes hours. Concurrency becomes a requirement for issue 03, not a refinement. The latency column reports wall-clock per instance rather than per run, so the two modes stay comparable.

**The 2,000-thinking-token estimate is the weakest number in this ADR.** Every cost in the table above moves with it. It is a guess, labeled as one. The first run replaces it with a measurement, and the $1.50 cap is what makes the guess safe rather than expensive.

**Two providers now serve the same open weights at different prices.** Fireworks lists Model B at the same $0.30/$1.20 and offers batch inference at 50%. This ADR rejects batch. It would halve the bill and destroy the latency figure that sits beside every accuracy number in this project.

## Revisit condition

**If rung 3 lands at or near the 88.9% ceiling**, K=20 binds the result rather than the model, and K=50 becomes worth its 2.5× tokens. Issue 01 states this, and this ADR inherits it.

**If the thinking Ablation shows the mode buys nothing**, the ladder row moves to thinking-off. That is 44% cheaper on Model A and 58% on Model B. Publish the move as a correction rather than a quiet edit.

**If rung 3 fails to beat rung 2.5**, the interesting question is no longer which model. It is whether the *format* is wrong. Twenty candidates in one prompt asks the model to hold 20 code fragments at once. Rung 2.6, a cross-encoder that scores one candidate at a time, sits in the numbering for exactly this outcome.

**Model IDs here will go stale.** Both models shipped within four months of this ADR. Select by criteria at the time: open weights on a public repository, a pinnable identifier, a per-token price reported in the row, and served rather than local. A vendor's benchmark claim decides which model is worth one run. It never decides what the number is.

## Alternatives rejected

- **Paths-only payload** — 8× cheaper, and it fits every model on the price list. Rejected as the first measurement, kept as the Ablation that prices what the text bought
- **Whole file per candidate** — 33 M tokens/run, $5–$40 for one row, to show the model 20 files it will read ~2% of
- **All signatures of each file** — 4.63 M tokens/run. The mean of 918 tokens/file hides a p90 of 2,807, so it needs a truncation constant that no measurement would justify
- **Single pick rather than a reordering** — saves ~$0.06 total and costs rung 3 its Recall@3 and Recall@5 columns
- **Raw responses committed to the repo for a replay test** — makes re-scoring free and CI cheap, but it licenses a "deterministic" claim the system does not support. Worth a second look at M9 on its own merits, where the CI gate is the real motivation, and without the determinism framing
- **Groq** — fastest serving of the three checked, but its self-serve catalog holds Llama 3.x, GPT-OSS and Qwen3.6-27B. Those cannot supply a cross-model table at two price tiers
- **Fireworks batch inference at 50% off** — halves the bill, invalidates the latency column
- **A proprietary frontier model as the ceiling row** — ADR-0007's amendment puts the open-weights gap at a size this project cannot resolve at n=244, and the ±6pp interval would swallow it. Measure it later as an extra row with its price, never as the ladder's rung-3 entry

## Amended 2026-08-05 — wrong provider, and a pair that could not have told us anything

Two errors, of different kinds. This record stays rather than disappear into an edit, as ADR-0007's amendments do. The decisions below stand corrected. The reasoning that produced them is the thing worth keeping.

### Nobody asked which account exists before choosing the provider

Together won on two grounds. It carried every model on the shortlist with published IDs and prices, and `langchain-together` is an `init_chat_model` provider. Both true, and both beside the point. **The account that will pay for these runs is an OpenRouter account.** No comparison of Together against Fireworks against Groq could surface that, because it was never a question about providers.

The decision is now **OpenRouter**. The original comparison was wasted work rather than wrong work.

A check confirmed `init_chat_model(model_provider="openrouter")` rather than assume it. LangChain's own forum carries a report of it raising, and that report turns out to be stale. On `langchain` 1.3.14 / `langchain-core` 1.5.3 / `langchain-openrouter` 0.2.7 it returns a `ChatOpenRouter`. [ADR-0005](0005-langgraph.md)'s commitment therefore survives intact, and rung 3 needs no bespoke client.

### The two models were 1.5pp apart against a ±6pp interval

The worse error, because it repeats one this series already records.

This ADR paired `DeepSeek-V4-Flash-0731` and `MiniMax-M3` as "cheap" and "strong". On the SWE-bench Verified figures circulating for them, they sit at roughly **79% and 80.5%**. That is 1.5 percentage points apart, for 3.3× the input price. **This project's Top-1 interval at n=244 is ±6pp.** The cross-model table therefore had "indistinguishable" as its most likely outcome. That is exactly the failure the top of `CLAUDE.md` describes: a capability ranking asserted at a size smaller than the project's own confidence interval.

The new pair spans a price range the measurement can resolve:

| Role | Model | in / out per 1M | context | license |
|---|---|---|---|---|
| cheap | `openai/gpt-oss-120b` | **$0.037 / $0.17** | 131,072 | Apache-2.0 |
| strong | `minimax/minimax-m3` | $0.30 / $1.20 | 1,048,576 | — |

**8.1× on input, 7.1× on output.** The question the table now asks is one a null result would still answer: *does paying eight times more buy anything here at all?*

`gpt-oss-120b` is pinned at Hub revision `b5c939de8f754692c1647ca79fbf85e8c1e70f8a`.

**`qwen/qwen3.7-flash` was the cheaper candidate at $0.030/$0.13, and this ADR's own criterion rejects it.** It has no Hugging Face repository. "Flash" is Alibaba's hosted service tier, not a weights release. This ADR inherited open weights as a decision from ADR-0007's amendment. A model that nobody can pin to a published artifact fails that test whatever its price.

### The reasoning axis is no longer symmetric, and the ablation is weaker for it

The original design ran two models × thinking {on, off}: one variable per pair, four cells. That worked because both models had an off switch.

**`gpt-oss-120b` has no off.** It exposes `reasoning_effort` at `low` / `medium` / `high` and defaults to medium. No documented setting disables reasoning entirely. So the four cells are now:

| Run | Setting | Est. cost |
|---|---|---|
| `gpt-oss-120b`, low effort | `reasoning_effort="low"` | **$0.06** |
| `gpt-oss-120b`, high effort | `reasoning_effort="high"` | **$0.14** |
| `minimax-m3`, thinking off | `thinking: {type: disabled}` | **$0.42** |
| `minimax-m3`, thinking on | adaptive, the default | **$1.00** |
| | | **$1.62 total** |

**Name what this costs.** The axis is now "the least and most reasoning each model permits". That is a *model-specific* quantity rather than one shared variable. Within each pair one variable still moves, so each ablation is clean on its own terms. Across the pair it is not. "Reasoning helped gpt-oss more than MiniMax" would compare low-vs-high against off-vs-on, and this ADR does not license that sentence. Read the two ablations separately or not at all.

### Consequences that move

**This amendment re-declares the ladder's rung-3 row, still in advance of any number: `openai/gpt-oss-120b` at `reasoning_effort="high"`.** The original declaration named the cheaper model in its default mode. "Default mode" no longer picks out a cell that this milestone runs, so the higher-reasoning setting takes its place. That matches what "thinking on" meant for the original pin. The declaration comes before the runs, for the same reason as the first time: the headline cannot become whichever of four cells happens to win.

**Total falls from $1.92 to about $1.62.** The per-run hard cap of $1.50 does not move. It was set to clear the most expensive cell, which is still MiniMax-M3 at an estimated $1.00.

**The prompt, the payload, K=20, the full reordering, and the dropped determinism claim all survive unchanged.** None of them depended on the provider or on which two models this ADR named.

**One thing this amendment does not fix.** Both models' headline scores come from SWE-bench Verified, the benchmark this project evaluates on. A model that advertises 80% there has been measured against the dev split's instances, and plausibly tuned near them. That is not evidence about rung 3, and it is not independent of the number this milestone will publish. `CONTEXT.md` names Contamination, and M6's Fresh Set exists for exactly this. Until then, a rung-3 result on this split carries the asterisk.

## Amended again 2026-08-05 — the strong row is DeepSeek, and a model ID does not determine the number

Two changes, one of them affecting every future entry in this project that calls a hosted model.

### MiniMax-M3 out, DeepSeek-V4-Pro in

Directed after the first amendment, and it holds up on this ADR's own criteria. `deepseek-ai/DeepSeek-V4-Pro` is **MIT**, weights published, Hub revision `b5968e9190ef`. Against `openai/gpt-oss-120b` at $0.037 it spans **11.8×** on input. That is wider than the MiniMax pairing it replaces, so the cross-model table keeps the property the first amendment bought it.

| Role | Model | in / out per 1M | license | context |
|---|---|---|---|---|
| cheap | `openai/gpt-oss-120b` | $0.037 / $0.17 | Apache-2.0 | 131,072 |
| strong | `deepseek/deepseek-v4-pro` | $0.435 / $0.87 | MIT | 1,048,576 |

Routes pinned: `deepinfra/bf16` for gpt-oss (full precision, and the endpoint whose price this table quotes), `deepseek` first-party for DeepSeek. A check confirmed that both answer, and that both honor their reasoning controls, before this ADR budgeted any run.

The original ADR pinned `deepseek/deepseek-v4-flash-0731`. This amendment reconsidered it for the strong row and rejected it at $0.090. That is only 2.4× gpt-oss, which is the narrow-pair mistake the first amendment exists to correct.

Estimated total moves from $1.62 to **$1.75**: gpt-oss $0.06 low / $0.14 high, DeepSeek $0.56 off / $0.99 on. The $1.50 per-run cap still clears the most expensive cell.

### The provider must be pinned, and the entry must record it

**This is the part that outlives the model choice.** Smoke testing found that twelve upstream providers serve `deepseek/deepseek-v4-pro`, priced $0.435–$1.68 per 1M input. **The quantization differs between them**: fp8, fp4, bf16, unknown. `gpt-oss-120b` is the same. CoreWeave serves fp4, DeepInfra serves bf16, and the $0.037 this ADR quotes is DeepInfra's.

Two of four probe calls landed on different providers and differed 6× in cost for one prompt.

So an unpinned request has neither a fixed price nor fixed weights precision. **A rung-3 row identified only by model ID would name something that does not determine the number it reports.** ADR-0007 concluded that a model name is not provenance, and pinned a revision in response. This is the same failure one level lower, where name *and* revision are still not enough, because the serve is a third variable.

The decision: rung 3 sends explicit routing and records what it received.

```json
"provider": {"only": ["deepseek"], "allow_fallbacks": false}
```

Use `only` rather than `order`. The value is the endpoint's **`tag`** from `/api/v1/models/{id}/endpoints`, not its display name. `{"order": ["DeepSeek"]}` returns a 404 that never says the provider name was the problem. That is a cheap mistake to make and an expensive one to make silently.

The `RESULTS.md` entry carries the response's `provider` field beside the model ID and revision. Rung 3 disables fallbacks rather than order them. A silent reroute mid-run would mix two serves inside one number, which is worse than a failed run.

**The route also decides whether reasoning happens at all.** That finding makes the pin necessary rather than tidy. On the same model and the same prompt:

| Route | quant | reasoning tokens, default | cost |
|---|---|---|---|
| `deepseek` (first-party) | unknown | **154** | $0.000154 |
| `streamlake/fp8` | fp8 | **131** | $0.000203 |
| `digitalocean` | unknown | **0** | $0.000041 |

DigitalOcean's serve does no reasoning, even with reasoning left at its default. An unpinned run would therefore sample a mixture of serves. Some of them silently opt out of the variable the ablation measures. The result would be a "reasoning does not help" finding that is an artifact of routing.

**Consequence worth stating.** This narrows what "reproducible" means for rung 3 further than the original ADR admitted. The entry already said variance is unmeasured. It must now also say *which serve produced it*. A reader who routes to a different provider gets different weights, not merely a different sample.

### A wrong conclusion, and what corrected it

An earlier draft of this amendment recorded `deepseek-v4-pro`'s reasoning toggle as **unverifiable**. Every unpinned probe reported zero reasoning tokens, including at its default, so the ablation looked unmeasurable on one side.

That was wrong, and wrong for the reason this amendment is about. The unpinned probes were landing on DigitalOcean's serve, which does no reasoning. Pinned to the first-party route, the toggle is unambiguous:

| | reasoning tokens | completion | cost |
|---|---|---|---|
| default | **154** | 158 | $0.000154 |
| `reasoning: {enabled: false}` | **0** | 3 | $0.0000196 |

A 7.9× cost difference and a clean on/off. The ablation is fully measurable.

This record stays rather than disappear, because the mistake is the argument. A conclusion about a *model* was really a property of an unpinned *route*. Only a pinned provider could tell the two apart. That is the same confusion in miniature that this amendment exists to prevent at the scale of a published number.

### The first-party route required an account change

`{"only": ["deepseek"]}` first failed with *"No endpoints available matching your guardrail restrictions and data policy"*. OpenRouter filters routing by an account-level toggle for providers that may train on prompts, and DeepSeek's first-party endpoint falls outside the default. This project changed the setting deliberately, because it sends only SWE-bench issue text and code from public repositories.

Worth a record, because it is a **reproducibility precondition that lives outside the repository**. A third party holding the pinned model, revision, provider tag and this commit still cannot reproduce a rung-3 row without the matching account setting. No pin inside the codebase can express that.

## Amended a third time 2026-08-06 — "full precision" was the wrong reason to pin a serve

The second amendment pinned `openai/gpt-oss-120b` to `deepinfra/bf16` and called it the full-precision endpoint. **That justification does not hold for this model.**

`gpt-oss-120b` ships *natively* in MXFP4. OpenAI post-trained it with the MoE weights quantized to 4.25 bits, and those weights are over 90% of its parameters. The remaining tensors stay in BF16. So a bf16 endpoint **upcasts weights that were already 4-bit**. It does not serve a higher-fidelity copy. No full-precision serve of this model exists to pin, and bf16 bought nothing it was chosen for.

Measured on one prompt at high reasoning effort:

| tag | quantization | in / out per 1M | throughput | est. dev run |
|---|---|---|---|---|
| `deepinfra/bf16` | bf16 | $0.037 / $0.17 | 40 tok/s | 7.0 h · $0.24 |
| `coreweave/fp4` | fp4 | $0.030 / $0.17 | 34 tok/s | ~8 h · $0.20 |
| `groq` | unknown | $0.150 / $0.60 | 198 tok/s | ~2 h · $0.88 |
| **`cerebras/fp16`** | **fp16** | $0.350 / $0.75 | **723 tok/s** | **~34 min · $1.46** |

**The fp4 endpoint is the slowest thing measured.** Hardware sets the speed here, not precision: wafer-scale and LPU parts against GPUs. The quantization-versus-latency trade this table was expected to show does not exist. Cerebras serves at fp16, the same 16-bit class as the incumbent, and runs 18× faster.

**Decision: gpt-oss routes to `cerebras/fp16`.** Declared before any accuracy number exists, on stated grounds of throughput at an equal precision class. A check confirmed it end to end through the rung at 25s for three instances, against 5m11s on DeepInfra.

**The per-run cap rises from $1.50 to $2.00.** Ten times the speed costs roughly five times the price per token. That puts this cell at **$1.46** measured, and the old cap would have aborted it on ordinary variance. The milestone cap of $5.00 does not move, and it still clears the four cells at an estimated $3.30 total.

**What this does not settle.** Nobody has measured whether serving precision moves *accuracy* on this task, and nothing here claims otherwise. It is simply no longer a question a route choice must answer, because the fast option is not the low-precision one. If a rung-3 result ever turns on it, the ablation is one model, two serves, one variable.

**This record stays rather than disappear into an edit**, as with the second amendment. The error was to reason from a general belief, that bf16 means full precision, without a check on what this particular model is. That is the same failure mode as a model named from memory, one level further in.

## Budget note, 2026-08-06 — the first attempt is charged to setup, not to measurement

M4's first full-run attempt spent **$2.25 and completed nothing**. Four cells launched in parallel. One died at seven minutes on an unretried 429. The rest died once the per-instance cost estimates proved ~45% low.

This ADR records that spend as **setup rather than measurement**, and counts the $5.00 milestone cap from here. The reasoning: none of it produced a number, and all of it bought things the milestone needed anyway. It bought a working client, the provider-routing discovery, the account policy fix, the rate-limit gap, and a per-instance cost figure grounded in 20 instances instead of three.

Stated rather than quietly rebased, because a cap that resets whenever it is inconvenient is not a cap. Spend charges to setup under two conditions. It produced no publishable number, **and** what it did produce now sits in the repository as code or as a decision. Both hold here.

**Re-measured on 20 instances** (`--limit 20`, which refuses to write an entry, so it counts as a measurement and not a truncated run):

| | 3-instance estimate | 20-instance measurement |
|---|---|---|
| ladder row, cost | $1.46 | **$1.34** |
| ladder row, wall clock | 34 min | **20 min** |

Both estimates ran high because only three instances absorbed the fixed startup cost. That startup loads the benchmark, the splits, and the retriever's encoder. The overrun on the first attempt came from the other three cells. Their estimates rested on two-instance samples, and nobody has re-measured them.

## Amended a fourth time 2026-08-10 — the ladder's rung-3 row moves to reasoning off

This ADR wrote the condition for this move before any number existed:

> **If the thinking Ablation shows the mode buys nothing**, the ladder row moves to thinking-off. That is 44% cheaper on Model A and 58% on Model B. Publish the move as a correction rather than a quiet edit.

The condition holds, so the row moves. **The ladder's rung-3 row is now `rerank-deepseek-off`.**

| Cell | Top-1 | Cost | Wall clock |
|---|---|---|---|
| `rerank-deepseek-on` | 79.1% (73.6-83.7) | $0.49 | 178m |
| **`rerank-deepseek-off`** | **75.0% (69.2-80.0)** | **$0.31** | **22m** |
| `rerank` — the old row, gpt-oss-high | 74.2% (68.3-79.3) | $0.39 | 186m |
| `rerank-gpt-oss-low` | 72.5% (66.6-77.8) | $0.76 | 9m |

`rerank-deepseek-off` is the only cell that breaks the trade between cost and speed. It is the cheapest to run and the second fastest, and it scores second of the four. Reasoning buys 4.1pp on this model, and that sits inside the ±6pp interval this project reports at n=244.

**What moves.** The row a reader should deploy, and the row the README's ladder table names.

**What does not move.** M4's published entries all stay exactly as they are. The old row, `rerank` at 74.2%, was declared in advance and it stays on the record as the row this ADR originally named. A number is not withdrawn because a cheaper configuration turned out to be as good.

**The 4.1pp this gives up is stated rather than hidden.** `deepseek-off` also produced **43 Off-List Paths** against `deepseek-on`'s 14. That is the worst hallucination rate of the four cells. It costs a reranker very little, because a reranker discards a path that was never a candidate. It would cost an agent a great deal, which is why [ADR-0009](0009-tool-using-agent.md) pins rung 4 to reasoning **on** while this row moves to reasoning off. The two decisions point in opposite directions on purpose, and each one is made against the metric that matters for its own rung.

**Consequence for M5.** The ladder's rung-3 row and rung 4's attributable baseline are now different cells. ADR-0009 therefore reports three deltas rather than one, and it says which licenses which claim.

## Provenance note, 2026-08-07 — the first-party DeepSeek serve is fp8

The second amendment's route table lists the quantization of the `deepseek` first-party route as **unknown**. It is **fp8**.

A probe for M5 returned `system_fingerprint` as `fp_9954b31ca7_prod0820_fp8_kvcache_20260402`. That table stays as written, and this note sits beside it.

**This changes no decision.** The route was never pinned on precision, and the third amendment already established that precision is not the trade it appears to be.

**It fills a gap in the provenance record.** Two of M4's four published rows ran on this route. Each entry names a model, a revision and a provider tag. Neither states the precision that produced the number, and nobody could state it before now. A reader who routes elsewhere gets different weights, and this note is what makes that comparison possible for these two rows.

**It does not fill the other gap.** Nobody has measured whether serving precision moves *accuracy* on this task. The third amendment says so, and that still holds.
