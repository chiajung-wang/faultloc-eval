# faultloc-eval

**Given a bug report, which source file must change?**

Fault localization, built as a *measured ladder*: lexical retrieval, dense retrieval, LLM reranking, then a tool-using agent. Each rung must earn its place. Its value is the delta it adds over the rung below, priced in dollars and seconds.

The system is half the deliverable. The evidence is the other half: a reproducible benchmark, a published filter rate, a contamination control, and a calibrated confidence model. That model lets the system abstain instead of guess.

> **Status: M5 complete.** A tool-using agent scores **88.1% Top-1** on the dev split, the highest number in this ladder. Its own ablation — the same agent with **no tools at all** — scores **84.0%**. The gap between them is the only comparison that isolates the tools, and at **+4.1pp, p=0.087, it is not established**. Most of what separates rung 4 from rung 3 is the loop and the answer format, not the searching.

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
| **LLM rerank (rung 3)** | Evidence Chunk | **75.0%** (69.2–80.0) | **82.8%** | **85.7%** | **$0.0013** | 5.34s |
| Agent, no tools (ablation) | Evidence Chunk | 84.0% (78.9–88.1) | 86.7% | 89.3% | $0.0229 | 41.0s |
| **Agent (rung 4)** | Evidence Chunk + 5 tools | **88.1%** (83.5–91.6) | **94.0%** | **94.8%** | **$0.0213** | 41.5s |

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

### The rung-3 row moved, on cost-effectiveness

The table above now names **`rerank-deepseek-off`** at 75.0%, $0.0013 per instance and 5.34s. The row this project declared in advance was `rerank` at 74.2%, and every number in this section is that row.

ADR-0008 wrote the condition for the move before any number existed: if reasoning bought nothing, the ladder row goes to reasoning off, published as a correction rather than a quiet edit. It bought 4.1pp on DeepSeek, inside the ±6pp interval. The replacement is the only cell that is both cheapest to run and near-fastest — 22 minutes against 178 for its reasoning-on twin.

**The 4.1pp it gives up is not the only cost.** `deepseek-off` named 43 files that were never candidates, against 14 for `deepseek-on`. A reranker discards such a path and barely notices. An agent cannot, which is why [ADR-0009](docs/adr/0009-tool-using-agent.md) pins rung 4 to reasoning **on** while this row moves to reasoning off. The two decisions point opposite ways on purpose, each made against the metric that matters for its own rung.

### The remaining headroom is retrieval, not ranking

The candidate list holds a ground-truth file in its top 20 for **88.9%** of instances. That is the hard ceiling on any reranker, because a reranker reorders and never adds. The declared row reached 74.2%, which is 14.7pp below it. The row that stands now, `deepseek-off`, reaches 75.0%, 13.9pp below. The best configuration reaches 79.1%, 9.8pp below.

`sphinx` shows the shape of what is left. All four configurations score **63.6%** there, which is exactly its share of instances whose answer was in the list at all. Every model picks correctly on every sphinx instance it could. Its remaining loss belongs to retrieval.

### What M4 overturned

**Rung 2.6 was inserted to stop rung 3 taking credit for what reranking-in-general buys. It scored 26.6%, below every free rung.** A cross-encoder reading the issue and one candidate together is worse than rank fusion reading neither. The rung was added on the theory that it would absorb part of rung 3's delta. It did the opposite, and the entry stays in the ladder rather than disappearing.

**This project expected the cheap model to be the weak one.** The cheapest configuration to run scored second of four. The most expensive per run scored last.

### What it cost

The four published rows cost **$1.95**. The account spent **$5.59**. The difference went to abandoned runs and to the search for a provider that could serve the work. One attempt completed nothing at $2.25. Another died at instance 110. The rest went on probes that established the limits. Three providers were rejected on measurement — an undocumented 8,192-token completion cap, an exhausted shared capacity pool, and repeated timeouts.

The first rung with a bill also produced the first rung whose number a reader cannot regenerate from a commit alone. Reproducing it needs an API key and about two dollars.

## M5: the agent is the best row, and the tools are not what made it

**Rung 4 scores 88.1% Top-1 (83.5–91.6)**, above every other row. It is also the
milestone's least interesting number, because a second cell explains most of it.

`agent-no-tools` is the same agent with the tool-call cap set to zero. Same model,
same route, same reasoning setting, same warm-start prompt, same loop, same
`submit_ranking` answer format. The only difference is that it cannot look at a
single file. **It scores 84.0%.**

ADR-0009 declared that ablation before either cell ran, and it earned its $5.59.

### The two deltas, and only one of them is about tools

| Comparison | Delta | Paired p | What moves |
|---|---|---|---|
| **agent vs agent-no-tools** | **+4.1pp** | **0.087** | **tools, and nothing else** |
| agent vs rung 3 (`rerank`) | +13.9pp | 1.2e-06 | model, route, reasoning, loop, format, tools |

The second is decisive and it is not the agent's achievement. Six things move at
once, and the ablation already attributes about ten of those points to the loop
and the answer format alone. Publishing +13.9pp as what an agent buys would be
the same overclaim M3 caught when a free chunking change nearly took credit that
a paid embedding model was about to receive.

**So the honest headline is +4.1pp, and the measurement cannot separate it from
chance.** Nineteen instances won, nine lost, twenty-eight discordant.

### Why the tools bought so little

Rung 4's one structural advantage over any reranker is that it can name a file
the Candidate Set never contained. That is the only route above the 88.9%
retrieval ceiling.

**It did so twice in 244 instances.** Both were surfaced by a tool rather than
recalled, which the Tool-Reached check confirms. Two paths cannot move a Top-1
number, and that is the most direct explanation of the small delta.

### The roster was measured, and it does not hold up

| Tool | Calls | Instances where it found the Top-1 |
|---|---|---|
| `read_file` | 811 | 121 |
| `search_code` | 618 | 81 |
| `file_outline` | 89 | 39 |
| `find_definition` | 10 | 1 |
| `semantic_search` | **3** | **0** |

`semantic_search` was called three times across 244 instances and never surfaced
an answer. [ADR-0002](docs/adr/0002-no-code-execution.md) fixed five tools by
name; ADR-0009 named this exact outcome as the condition for revisiting that, and
the roster now takes a recorded correction rather than a quiet edit.

`find_definition` at ten calls is close behind. Two tools out of five carry the
work.

### The cap binds, so part of this number is the cap's

The Instance Budget allows eight tool calls. **The agent reached it on 141 of 244
instances**, with a median of exactly eight. It is still working when it is cut
off, so 88.1% is a lower bound on what this design does with more room, and
ADR-0009's revisit condition has fired.

### What the agent fixed for free

The ablation truncated **58 of 244** replies. The agent truncated **3**. A cell
with no tools must emit a whole twenty-path ranking in one reply, and one instance
in four this model could not. An agent spreads the same work across steps.

`sphinx` also moved, from the 63.6% where all four rung-3 cells sat — exactly its
Candidate Set ceiling — to **86.4%**.

### What M5 cost, and what it could not buy

$11 across three runs and the setup that found four real bugs: a client with no
request timeout, runaway reasoning that spent an entire 16,000-token budget
without answering, a timeout inherited from rung 3 that made eight retries take
two hours, and a `request_timeout` fix that was itself the cause of a later hang.

One planned comparison was dropped. Rung 4 had to be pinned to bounded reasoning
to stop the runaway, which left M4's unbounded 79.1% cell no longer matched.
Re-running it cost seventeen times M4's measured figure and would have breached
rung 3's budget at instance 57. ADR-0009 records the drop and the reason.


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
| [ADR-0009](docs/adr/0009-tool-using-agent.md) | Rung 4 starts from rung 3's payload and goes looking for what retrieval missed |
| [ADR-0010](docs/adr/0010-fresh-set-mining.md) | The Fresh Set mines GitHub after 2026-05-01, and contamination is a difference of two drops |

## Evaluation

- **Verified Set** — SWE-bench Verified, 500 human-validated instances. Published localization numbers exist against it, so results are anchored.
- **Fresh Set** — self-mined issues whose fix merged *after* the evaluated model's training cutoff. Contamination is rung 4's drop across the two sets **minus** the drop a model-free rung shows on the same pair, because a raw gap mixes memory with task difficulty (ADR-0010).
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
