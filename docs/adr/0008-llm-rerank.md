# ADR-0008: Rung 3 reranks with a served open-weights model, and stops claiming determinism

**Status:** Accepted · 2026-08-05 · *no run has been paid for yet; every cost below is an estimate with its assumption named*

## Context

Issue 01 established what rung 3 is actually for. The Candidate Set holds a ground-truth file in its top 20 for **88.9%** of dev-split Instances, and the best rung picks one correctly **45.5%** of the time. Roughly 45 points of headroom, none of it in retrieval.

So rung 3 is not "search harder". It is: *given a list that usually contains the answer, choose*. Four things had to be settled before any money was spent — what the model sees, which model, what a `RESULTS.md` entry asserts when the system is nondeterministic, and what it costs.

**Prompt size, measured** by [`scripts/prompt_token_cost.py`](../../scripts/prompt_token_cost.py), dev split, n=244, 2,000 blobs sampled at seed 0, `chars/4` as in `chunk_corpus_stats.py`:

| Payload, per candidate | Tokens/instance at K=20 | Input per run |
|---|---|---|
| paths only | 597 | 0.15 M |
| path + one signature chunk | 1,213 | 0.30 M |
| **path + one body chunk** | **4,886** | **1.19 M** |
| path + all signatures of the file | 18,956 | 4.63 M |
| path + whole file | 135,305 | 33.01 M |

The issue text is the small part: mean 420 tokens, median 299. A path is 9. A body chunk is 214. **The payload decides the bill, not the issue report.**

**Prices**, from Together's own pricing page and serverless model list, checked 2026-08-05. Not recalled — ADR-0007 records what happens when an external fact in this series is written from memory.

## Decision

### The provider and the models

| Field | Value |
|---|---|
| Provider | Together, via `init_chat_model(model_provider="together")` |
| Model A | `deepseek-ai/DeepSeek-V4-Flash-0731` — $0.14 / $0.28 per 1M |
| Model B | `MiniMaxAI/MiniMax-M3` — $0.30 / $1.20 per 1M |

Both are open weights on public Hub repositories, served rather than run locally. This is the cell ADR-0007's amendment identified as never having been considered: auditable weights without the local throughput wall.

### What the model sees

The issue text, then 20 candidates in Candidate Set order, each rendered as its path plus its **Evidence Chunk** — the chunk the file scored as under Chunk Aggregation. 1.19 M input tokens per run.

### Output

A full reordering of all 20 paths. Roughly 200 output tokens.

### Thinking mode is a measured variable, not a setting

Both models default to reasoning on. Rather than pick, **all four cells are run**: two models × thinking {on, off}. One variable moves per pair.

| Run | Input | Output | **Cost** |
|---|---|---|---|
| Flash, thinking off | $0.17 | $0.01 | **$0.18** |
| Flash, thinking on | $0.17 | $0.15 | **$0.32** |
| MiniMax-M3, thinking off | $0.36 | $0.06 | **$0.42** |
| MiniMax-M3, thinking on | $0.36 | $0.64 | **$1.00** |
| | | | **$1.92 total** |

**The ladder's rung-3 row is declared here, before any number exists: `DeepSeek-V4-Flash-0731`, thinking on.** The cheaper model in its default mode is the configuration a reader would actually deploy, and naming it in advance is what stops the ladder's headline from being whichever of four runs happened to win. The other three are the cross-model table (issue 04) and the thinking Ablation.

### What a rung-3 entry asserts

**Not determinism.** `test_is_deterministic` does not extend to rung 3, and the entry says so rather than omitting it. A rung-3 row asserts: one sampled run, at a pinned model ID, on a pinned dataset revision, from a clean commit. **Run-to-run variance is unmeasured.**

### Budget

Per-run hard cap **$1.50**, checked against accumulated spend and aborting the run rather than reporting the overspend afterwards. Milestone cap $5.00.

## Rationale

**Why body text rather than paths.** Paths-only is 8× cheaper and would have fit every model on the price list, including ones ruled out at $1.00/run. It was rejected as the *first* thing to measure because rung 3's job, sharpened by issue 01, is to decide which of two retrievers was right on this repository — and a path carries no evidence about that. `scikit-learn` is where fusion lands *below* both parents (68.8% against lexical's 81.2%): both retrievers ranked plausible-looking paths, and the discriminating signal is in the code. Paths-only remains the obvious Ablation if the text turns out not to earn its 8×.

**Why the Evidence Chunk and not the file.** A file is 6,735 tokens on average; twenty of them is 33 M tokens per run, roughly $5–$40 depending on the model, for one row. The chunk the file *scored as* is the one piece of the file the retriever thought matched the issue — it is the retriever's own evidence, and showing the model something the retriever never looked at would make the two rungs disagree about what a candidate even is. Chunk Aggregation already computes the argmax; rung 3 stops discarding it.

**Why a full reordering.** Every published row since M1 carries Top-1, Recall@3 and Recall@5. A single pick makes the recall columns undefined for rung 3, or fills them from fusion's order — which would credit a model with a result reciprocal rank fusion produced for free. That is the exact error issue 01 warned about. The reordering costs ~$0.06 more across all four runs.

**Why both thinking modes, given the cost.** Thinking tokens bill as output, so on MiniMax-M3 the mode is 58% of the run's price. That makes it the most expensive single flag in the project, and buying it blind would mean paying it forever without knowing what it bought. Two runs per model isolates it with one variable moving — the pattern that made M3's chunking-vs-bodies finding possible.

Thinking-on also *removes* a control: DeepSeek's API documents that thinking mode ignores `temperature`, `top_p`, `presence_penalty` and `frequency_penalty` — set them and nothing errors and nothing happens. The thinking-off rows can at least ask for greedy decoding.

**Why the determinism claim is dropped rather than engineered around.** Two mechanisms were available. Committing raw responses to the repo (~100 KB/model) makes re-scoring free and lets M9's CI gate run rung 3 without spending, but it turns `test_is_deterministic` into a replay test — it proves the scorer is deterministic, which was never in doubt, and says nothing about the model. Setting `temperature=0` narrows sampling but is not determinism either: batch-dependent kernel nondeterminism at the server remains, and on thinking-on rows the parameter is ignored outright.

Neither buys the property the phrase implies. **An entry that says "variance unmeasured" is worth more than one that says "deterministic" and means "we replayed a cache."**

## Consequences

**Rung 3 is the first row in `RESULTS.md` that a reader cannot regenerate.** Reproducing it needs a Together API key and roughly $1.92. Every rung below is free and reproducible from a commit alone. This is a genuine loss of a property the project has held since M1, and it is the price of the rung existing at all.

**Variance is unmeasured, and that is a named gap rather than an oversight.** No repeat runs are budgeted. The gap has a specific shape: at n=244 Top-1 carries a ±6pp Wilson interval, so run-to-run variance smaller than about 2pp would be invisible against sampling noise anyway — but that is an argument for expecting the measurement to be uninformative, not for assuming the variance is small. If rung 3's delta over rung 2.5 lands inside a few points, this gap becomes load-bearing and repeats have to be bought. It joins Recall@k's missing interval as the second known measurement gap in the project.

**The PRD's $0.50 per-run budget is superseded** by the $1.50 cap above. The PRD number was written before the payload was measured and before either model's default reasoning behaviour was known.

**Thinking-on latency is 10–60s per instance**, so a sequential dev-split run is hours. Concurrency becomes a requirement for issue 03, not a refinement, and the latency column reports wall-clock per instance rather than per run so the two modes stay comparable.

**The 2,000-thinking-token estimate is the weakest number in this ADR.** Every cost in the table above moves with it. It is a guess, labelled as one; the first run replaces it with a measurement, and the $1.50 cap is what makes guessing safe rather than expensive.

**Two providers now serve the same open weights at different prices.** Fireworks lists Model B at the same $0.30/$1.20 and offers batch inference at 50%. Batch was not taken: it would halve the bill and destroy the latency figure that sits beside every accuracy number in this project.

## Revisit condition

**If rung 3 lands at or near the 88.9% ceiling**, K=20 is the binding constraint rather than the model, and K=50 becomes worth its 2.5× tokens — stated in issue 01 and inherited here.

**If the thinking Ablation shows the mode buys nothing**, the ladder row moves to thinking-off, which is 44% cheaper on Model A and 58% on Model B, and the move is published as a correction rather than a quiet edit.

**If rung 3 fails to beat rung 2.5**, the interesting question is no longer which model but whether the *format* is wrong — 20 candidates in one prompt asks the model to hold 20 code fragments at once. Rung 2.6, a cross-encoder scoring one candidate at a time, exists in the numbering for exactly this outcome.

**Model IDs here will go stale.** Both were released within four months of this ADR. Select by criteria at the time: open weights on a public repository, a pinnable identifier, priced per token with the price reported in the row, and served rather than local. A vendor's benchmark claim decides which model is worth one run, never what the number is.

## Alternatives rejected

- **Paths-only payload** — 8× cheaper and fits every model on the price list. Rejected as the first measurement, kept as the Ablation that prices what the text bought
- **Whole file per candidate** — 33 M tokens/run, $5–$40 for one row, to show the model 20 files it will read ~2% of
- **All signatures of each file** — 4.63 M tokens/run, and the mean of 918 tokens/file hides a p90 of 2,807, so it needs a truncation constant that no measurement would justify
- **Single pick rather than a reordering** — saves ~$0.06 total and costs rung 3 its Recall@3 and Recall@5 columns
- **Committing responses to the repo for a replay test** — makes re-scoring free and CI cheap, but licenses a "deterministic" claim the system does not support. Worth revisiting on its own merits at M9, where the CI gate is the actual motivation, and without the determinism framing
- **Groq** — fastest serving of the three checked, but its self-serve catalogue is Llama 3.x, GPT-OSS and Qwen3.6-27B, which cannot supply a cross-model table at two price tiers
- **Fireworks batch inference at 50% off** — halves the bill, invalidates the latency column
- **A proprietary frontier model as the ceiling row** — ADR-0007's amendment puts the open-weights gap at a size this project cannot resolve at n=244, and the ±6pp interval would swallow it. If it is measured later it is an additional row with its price, never the ladder's rung-3 entry
