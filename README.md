# faultloc-eval

**Given a bug report, which source file must change?**

Fault localization built as a *measured ladder* — lexical retrieval, dense retrieval, LLM reranking, then a tool-using agent — where each rung's value is the delta it adds over the rung below, priced in dollars and seconds.

The system is half the deliverable. The other half is the evidence: a reproducible benchmark, a published filter rate, a contamination control, and a calibrated confidence model that lets the system abstain rather than guess.

> **Status: M3 complete.** Rung 1 (BM25) scores **39.3% Top-1** on the dev split; rung 2 (embeddings) scores **43.0%**, and the intervals overlap — dense retrieval matched lexical retrieval rather than beating it. The gain that did appear came from a free change to what gets indexed, not from the model. Rungs 3–4 next.

## Why localization and not patch generation

Most LLM work on GitHub issues tries to *write the fix*. In that setting the score is decided almost entirely by which model was called — swap the model, the number moves; change the engineering, it doesn't.

Localization is the earlier question, and the one triage actually blocks on: *where is this, and who owns it?* A human usually writes the fix afterwards. It is also a setting where system design, not model choice, moves the result.

## Results

Dev split, 244 instances. Test set untouched until M7.

| Rung | Index unit | Top-1 | Recall@3 | Recall@5 | Cost/instance | Latency |
|---|---|---|---|---|---|---|
| BM25 | whole file | 39.3% (33.4–45.6) | 59.3% | 68.5% | $0.00 | 0.34s |
| BM25 | AST Chunk, no bodies | 39.8% (33.8–46.0) | 52.0% | 61.3% | $0.00 | 0.68s |
| BM25 | AST Chunk | **43.9%** (37.8–50.1) | **60.3%** | 65.7% | $0.00 | 0.91s |
| Embedding retrieval | AST Chunk | 43.0% (37.0–49.3) | 57.9% | 67.8% | $0.00 | 0.14s + 37.6s index |
| LLM rerank | — | — | — | — | — | — |
| Agent | — | — | — | — | — | — |

Every number traces to a dataset, split, commit, and date in [`RESULTS.md`](RESULTS.md), which is written by the run itself rather than by hand. Latency is that entry's wall clock divided by 244.

### On Top-1, M3 established nothing

All four intervals overlap pairwise. The best row is 4.6 points above rung 1 and **that difference is not shown to be real** — at this sample size the Wilson interval is about ±6pp, which is wider than every gap in the column. The table is ordered by point estimate and the ordering should not be read as a ranking.

Recall figures carry no interval in the log at all, so read them as direction rather than magnitude. Fixing that is a gap, not a feature.

### The three deltas, one per variable

Rung 2 changes two things against rung 1 — matching function *and* index unit — so a single delta would be unattributable. Splitting them:

**Chunking alone: no gain, and a real recall cost.** Whole file → AST Chunk moves Top-1 by +0.5pp (nothing) while Recall@3 falls 59.3 → 52.0 and Recall@5 falls 68.5 → 61.3. Recall dropping that far means ground-truth files stopped being *retrievable*, not merely ranked lower — a property of the documents. Cost: free, and it made things worse.

**Indexing bodies: the only change that moved anything.** Recall@3 recovers 52.0 → 60.3, back to parity with whole-file search, and Top-1 reaches its highest value. Also free. The original chunk definition excluded function bodies on the theory that mechanical code would swamp the docstring; measured, that theory cost 8.3pp of Recall@3, because bug reports quote body tokens constantly — called functions, locals, error strings, traceback frames.

**Embeddings, given that chunk definition: nothing.** 43.9% → 43.0%, intervals almost identical. After a model, a 1.56 GB index, and 153 minutes of build time, dense retrieval **matched lexical retrieval and did not exceed it**.

Reporting only `embed` over `bm25` would have credited the model with a gain that came entirely from a free change to what gets indexed. That is the overclaim the ablation exists to prevent.

### The aggregate hides a real redistribution

Embeddings against the best lexical row, per repo:

| Gains | | Losses | |
|---|---|---|---|
| `psf/requests` (n=4) | +25.0 | `scikit-learn` (n=16) | −25.0 |
| `matplotlib` (n=17) | +11.8 | `pylint` (n=4) | −25.0 |
| `sphinx` (n=22) | +9.1 | `astropy` (n=10) | −20.0 |
| `xarray` (n=11) | +9.0 | `pytest` (n=10) | −10.0 |

Embeddings gain where lexical matching fails and lose where it already works. `scikit-learn` reports quote identifiers directly and BM25 was at 81%; `sphinx` reports describe rendered output and BM25 was at 4.5%. The aggregate is flat because the two effects cancel.

Small per-repo counts — treat these as direction, not magnitude. But the pattern is consistent enough to say the two methods are **complementary rather than one dominating**, which is an argument for rung 3 reranking a *union* of candidates rather than reordering rung 2's alone.

### Sphinx: the M1 prediction was right about the repo, wrong about the mechanism

M1 flagged `sphinx-doc/sphinx` at 4.5% as the sharpest test of whether embeddings earn their cost, on the theory that its reports describe rendered output in vocabulary absent from the code.

**4.5% → 0.0% (chunked, no bodies) → 18.2% (bodies) → 27.3% (embedded)** — six times the rung-1 number.

Its vocabulary *is* in the code, in the function bodies rather than the signatures and docstrings. Bodies did most of the work; embeddings added the rest. The prediction stays on the record rather than being edited away — a written prediction that measurement overturned is better evidence of a working method than one that happened to be right.

### What this says about M4

The next rung is an LLM reranker, and it now has a specific job rather than a hopeful one. Dense retrieval did not beat lexical, but the two fail on different repositories — so the useful thing to rerank is the union of both candidate lists, and the question M4 answers is whether a model can pick between two retrievers that are each right about different things.

## Design

Each decision carries a stated rationale and its rejected alternatives:

| Doc | Covers |
|---|---|
| [`CONTEXT.md`](CONTEXT.md) | Domain language — Instance, Ground-Truth File Set, Rung, Coverage, Stop Condition |
| [`docs/PRD.md`](docs/PRD.md) | Problem, scope, success criteria, open questions |
| [`docs/milestones.md`](docs/milestones.md) | M1–M9 |
| [ADR-0001](docs/adr/0001-ground-truth-file-set.md) | Ground truth = source files in the fixing PR, capped at three |
| [ADR-0002](docs/adr/0002-no-code-execution.md) | Read-only tools; no execution, no per-instance containers |
| [ADR-0003](docs/adr/0003-baseline-ladder.md) | Build a measured ladder, not the top rung |
| [ADR-0004](docs/adr/0004-calibrated-confidence.md) | Confidence from a calibrator, not model self-report |
| [ADR-0005](docs/adr/0005-langgraph.md) | LangGraph for the agent loop |
| [ADR-0006](docs/adr/0006-datasets.md) | SWE-bench Verified as the anchor, a self-mined Fresh Set as the control |
| [ADR-0007](docs/adr/0007-embedding-model.md) | A local embedding model, pinned by revision |

## Evaluation

- **Verified Set** — SWE-bench Verified, 500 human-validated instances. Published localization numbers exist against it, so results are anchored.
- **Fresh Set** — self-mined issues closed *after* the evaluated model's training cutoff. The accuracy gap between the two sets measures contamination.
- **Filter rate published.** Instances are dropped by a stated rule (ADR-0001); the rejection rate and per-reason counts ship with every result. Unreported filtering makes a benchmark unfalsifiable.
- **Abstention measured, not asserted.** A calibrated confidence model produces the accuracy-vs-coverage curve, reported with ECE and a reliability diagram.

A null result — the agent failing to beat retrieval, or no contamination gap — is a reportable finding.

## Quickstart

```bash
uv sync
uv run pytest
uv run faultloc --help
```

## Stack

Python 3.12 · LangChain + LangGraph · FastAPI + Jinja + htmx · SQLite · Langfuse · Docker

## Licence

TBD
