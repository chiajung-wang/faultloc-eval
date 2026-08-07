# faultloc-eval

**Given a bug report, which source file must change?**

Fault localization, built as a *measured ladder*: lexical retrieval, dense retrieval, LLM reranking, then a tool-using agent. Each rung must earn its place. Its value is the delta it adds over the rung below, priced in dollars and seconds.

The system is half the deliverable. The evidence is the other half: a reproducible benchmark, a published filter rate, a contamination control, and a calibrated confidence model. That model lets the system abstain instead of guess.

> **Status: M4 complete.** An LLM reranking the candidate list scores **74.2% Top-1** on the dev split, against **45.5%** for free rank fusion below it. That is the first gap in this ladder wider than its own confidence interval. Four model configurations spanning an 11.8x price difference land within 6.6 points of each other, so the model choice is not what produced it. Rung 4, the agent, comes next.

## Why localization and not patch generation

Most LLM work on GitHub issues tries to *write the fix*. In that setting the choice of model decides almost the whole score. Swap the model and the number moves. Change the engineering and it does not.

Localization is the earlier question, and the one that triage blocks on: *where is this, and who owns it?* A human usually writes the fix afterwards. Here system design moves the result, not the choice of model.

## Results

Dev split, 244 instances. Test set untouched until M7.

| Rung | Index unit | Top-1 | Recall@3 | Recall@5 | Cost/instance | Latency |
|---|---|---|---|---|---|---|
| BM25 | whole file | 39.3% (33.4–45.6) | 59.3% | 68.5% | $0.00 | 0.34s |
| BM25 | AST Chunk, no bodies | 39.8% (33.8–46.0) | 52.0% | 61.3% | $0.00 | 0.68s |
| BM25 | AST Chunk | **43.9%** (37.8–50.1) | **60.3%** | 65.7% | $0.00 | 0.91s |
| Embedding retrieval | AST Chunk | 43.0% (37.0–49.3) | 57.9% | 67.8% | $0.00 | 0.14s + 37.6s index |
| Hybrid (rung 2.5) | rank fusion | 45.5% (39.4–51.8) | 65.2% | 73.1% | $0.00 | 1.02s |
| Cross-encoder (rung 2.6) | Evidence Chunk | 26.6% (21.5–32.5) | 42.8% | 52.6% | $0.00 | 15.05s |
| **LLM rerank (rung 3)** | Evidence Chunk | **74.2%** (68.3–79.3) | **81.8%** | **85.3%** | **$0.0016** | 45.84s |
| Agent | — | — | — | — | — | — |

Every number traces to a dataset, split, commit, and date in [`RESULTS.md`](RESULTS.md). The run writes that file. Nobody writes it by hand. Latency is the entry's wall clock divided by 244.

### On Top-1, M3 established nothing

All four intervals overlap pairwise. The best row sits 4.6 points above rung 1, and **the measurement does not show that difference to be real**. At this sample size the Wilson interval is about ±6pp. That is wider than every gap in the column. The table is ordered by point estimate. Do not read that order as a ranking.

Recall figures carry no interval in the log. Read them as direction, not magnitude. The missing interval is a gap, not a feature.

### The three deltas, one per variable

Rung 2 changes two things against rung 1: the matching function *and* the index unit. A single delta could not attribute the result to either one. The three deltas below separate them.

**Chunking alone: no gain, and a real recall cost.** Whole file → AST Chunk moves Top-1 by +0.5pp, which is nothing. Recall@3 falls 59.3 → 52.0 and Recall@5 falls 68.5 → 61.3. A fall that large means ground-truth files stopped being *retrievable*, not merely ranked lower. That is a property of the documents. The change is free, and it made the result worse.

**Indexing bodies: the only change that moved anything.** Recall@3 recovers 52.0 → 60.3, back to parity with whole-file search. Top-1 reaches its highest value. This change is also free. The first chunk definition excluded function bodies, on the theory that mechanical code would swamp the docstring. Measurement put the cost of that theory at 8.3pp of Recall@3. Bug reports quote body tokens constantly: called functions, locals, error strings, and traceback frames.

**Embeddings, given that chunk definition: nothing.** 43.9% → 43.0%, intervals almost identical. After a model, a 1.56 GB index, and 153 minutes of build time, dense retrieval **matched lexical retrieval and did not exceed it**.

A report of `embed` over `bm25` alone would have credited the model with a gain that a free change produced. The ablation exists to prevent that overclaim.

### The aggregate hides a real redistribution

Embeddings against the best lexical row, per repo:

| Gains | | Losses | |
|---|---|---|---|
| `psf/requests` (n=4) | +25.0 | `scikit-learn` (n=16) | −25.0 |
| `matplotlib` (n=17) | +11.8 | `pylint` (n=4) | −25.0 |
| `sphinx` (n=22) | +9.1 | `astropy` (n=10) | −20.0 |
| `xarray` (n=11) | +9.0 | `pytest` (n=10) | −10.0 |

Embeddings gain where lexical matching fails, and lose where it already works. `scikit-learn` reports quote identifiers directly, and BM25 scored 81% there. `sphinx` reports describe rendered output, and BM25 scored 4.5% there. The aggregate is flat because the two effects cancel.

The per-repo counts are small. Treat them as direction, not magnitude. The pattern is still consistent enough to show that the two methods are **complementary, and that neither one dominates**. That is the argument for rung 3 to rerank a *union* of candidates instead of rung 2's list alone.

### Sphinx: the M1 prediction was right about the repo, wrong about the mechanism

M1 flagged `sphinx-doc/sphinx` at 4.5% as the sharpest test of whether embeddings earn their cost. The theory was that its reports describe rendered output in vocabulary that the code does not contain.

**4.5% → 0.0% (chunked, no bodies) → 18.2% (bodies) → 27.3% (embedded)** — six times the rung-1 number.

Its vocabulary *is* in the code. It sits in the function bodies rather than the signatures and docstrings. Bodies did most of the work. Embeddings added the rest. The prediction stays on the record. A written prediction that measurement overturned is better evidence of a working method than one that happened to be right.

### What this said about M4, and what M4 answered

M3 argued that the useful list to rerank is the union of both retrievers, because the two fail on different repositories. M4 tested that and the argument held. Fusion of the two lists scores 45.5%, above both rungs it merges.

## M4: the first established result

**An LLM reranking twenty candidates scores 74.2% Top-1 (68.3–79.3).** Fusion below it scores 45.5% (39.4–51.8). The intervals do not touch. Every earlier comparison in this ladder sat inside the ±6pp noise, which is why M3 established nothing. This one does not.

The deltas, each against a named row:

| Against | Its Top-1 | Delta |
|---|---|---|
| Rung 2.6, cross-encoder | 26.6% | **+47.6pp** |
| Rung 2.5, rank fusion | 45.5% | **+28.7pp** |
| Rung 2, embeddings | 43.0% | **+31.2pp** |
| Best lexical row, BM25 over AST Chunks | 43.9% | **+30.3pp** |

The ladder's rule credits a rung against the rung directly below it, which is 2.6. That number is the largest and the least useful, because rung 2.6 scored *below* everything. Fusion at +28.7pp is the honest comparison.

### The model is not what produced it

Four configurations ran on the same candidate lists and the same prompt:

| Configuration | Top-1 | Cost |
|---|---|---|
| `deepseek-v4-pro`, reasoning on | 79.1% (73.6–83.7) | $0.49 |
| `deepseek-v4-pro`, reasoning off | 75.0% (69.2–80.0) | $0.31 |
| `gpt-oss-120b`, effort high | 74.2% (68.3–79.3) | $0.39 |
| `gpt-oss-120b`, effort low | 72.5% (66.6–77.8) | $0.76 |

They span an 11.8x difference in price per token and land within 6.6 points of each other, with intervals overlapping almost entirely. **No ordering among them is established.** Both reasoning ablations point the same way. More reasoning bought 4.1pp on one model and 1.7pp on the other. Both gaps sit inside the interval.

That null result is informative rather than empty. The pair was chosen to be 11.8x apart on price precisely so the measurement could show a difference if one existed. It did not.

### The remaining headroom is retrieval, not ranking

The candidate list holds a ground-truth file in its top 20 for **88.9%** of instances. That is the hard ceiling on any reranker, because a reranker reorders and never adds. The ladder row reaches 74.2%, which is 14.7pp below it. The best configuration reaches 79.1%, 9.8pp below.

`sphinx` shows the shape of what is left. All four configurations score **63.6%** there, which is exactly its share of instances whose answer was in the list at all. Every model picks correctly on every sphinx instance it could. Its remaining loss belongs to retrieval.

### What M4 overturned

**Rung 2.6 was inserted to stop rung 3 taking credit for what reranking-in-general buys. It scored 26.6%, below every free rung.** A cross-encoder reading the issue and one candidate together is worse than rank fusion reading neither. The rung was added on the theory that it would absorb part of rung 3's delta. It did the opposite, and the entry stays in the ladder rather than disappearing.

**This project expected the cheap model to be the weak one.** The cheapest configuration to run scored second of four. The most expensive per run scored last.

### What it cost

The four published rows cost **$1.95**. The account spent **$5.59**. The difference went to abandoned runs and to the search for a provider that could serve the work. One attempt completed nothing at $2.25. Another died at instance 110. The rest went on probes that established the limits. Three providers were rejected on measurement — an undocumented 8,192-token completion cap, an exhausted shared capacity pool, and repeated timeouts.

The first rung with a bill also produced the first rung whose number a reader cannot regenerate from a commit alone. Reproducing it needs an API key and about two dollars.

## Design

Each decision carries a stated rationale and its rejected alternatives:

| Doc | Covers |
|---|---|
| [`CONTEXT.md`](CONTEXT.md) | Domain language — Instance, Ground-Truth File Set, Rung, Coverage, Stop Condition |
| [`docs/PRD.md`](docs/PRD.md) | Problem, scope, success criteria, open questions |
| [`docs/milestones.md`](docs/milestones.md) | M1–M9 |
| [ADR-0001](docs/adr/0001-ground-truth-file-set.md) | Ground truth = source files in the fixing PR, capped at three |
| [ADR-0002](docs/adr/0002-no-code-execution.md) | Read-only tools, no execution, no per-instance containers |
| [ADR-0003](docs/adr/0003-baseline-ladder.md) | Build a measured ladder, not the top rung |
| [ADR-0004](docs/adr/0004-calibrated-confidence.md) | Confidence from a calibrator, not model self-report |
| [ADR-0005](docs/adr/0005-langgraph.md) | LangGraph for the agent loop |
| [ADR-0006](docs/adr/0006-datasets.md) | SWE-bench Verified as the anchor, a self-mined Fresh Set as the control |
| [ADR-0007](docs/adr/0007-embedding-model.md) | A local embedding model, pinned by revision |
| [ADR-0008](docs/adr/0008-llm-rerank.md) | Rung 3 reranks with a served open-weights model, and stops claiming determinism |

## Evaluation

- **Verified Set** — SWE-bench Verified, 500 human-validated instances. Published localization numbers exist against it, so results are anchored.
- **Fresh Set** — self-mined issues closed *after* the evaluated model's training cutoff. The accuracy gap between the two sets measures contamination.
- **Filter rate published.** A stated rule drops instances (ADR-0001). The rejection rate and the per-reason counts ship with every result. Unreported filtering makes a benchmark unfalsifiable.
- **Abstention measured, not asserted.** A calibrated confidence model produces the accuracy-vs-coverage curve. The report includes ECE and a reliability diagram.

A null result is a reportable finding. The agent may fail to beat retrieval, or no contamination gap may appear.

## Quickstart

```bash
uv sync
uv run pytest
uv run faultloc --help
```

## Stack

Python 3.12 · LangChain + LangGraph · FastAPI + Jinja + htmx · SQLite · Langfuse · Docker

## License

TBD
