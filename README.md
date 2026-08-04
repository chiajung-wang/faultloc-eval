# faultloc-eval

**Given a bug report, which source file must change?**

Fault localization built as a *measured ladder* — lexical retrieval, dense retrieval, LLM reranking, then a tool-using agent — where each rung's value is the delta it adds over the rung below, priced in dollars and seconds.

The system is half the deliverable. The other half is the evidence: a reproducible benchmark, a published filter rate, a contamination control, and a calibrated confidence model that lets the system abstain rather than guess.

> **Status: M1 complete.** Rung 1 (BM25) scores **39.3% Top-1** on the dev split. Rungs 2–4 next.

## Why localization and not patch generation

Most LLM work on GitHub issues tries to *write the fix*. In that setting the score is decided almost entirely by which model was called — swap the model, the number moves; change the engineering, it doesn't.

Localization is the earlier question, and the one triage actually blocks on: *where is this, and who owns it?* A human usually writes the fix afterwards. It is also a setting where system design, not model choice, moves the result.

## Results

Dev split, 244 instances. Test set untouched until M7.

| Rung | Top-1 | Recall@3 | Recall@5 | Cost/instance | Latency |
|---|---|---|---|---|---|
| BM25 | **39.3%** (95% CI 33.4–45.6) | 59.3% | 68.5% | $0.00 | 0.3s |
| Embedding retrieval | — | — | — | — | — |
| LLM rerank | — | — | — | — | — |
| Agent | — | — | — | — | — |

Every number here traces to a dataset, split, commit, and date in [`RESULTS.md`](RESULTS.md), which is written by the run itself rather than by hand.

Top-1 carries a 95% Wilson interval because at this sample size a few points between two rungs is not yet a result. The intervals already earn their place in the per-repo breakdown: `sphinx-doc/sphinx` at 4.5% (0.8–21.8) and `scikit-learn` at 81.2% (57.0–93.4) do not overlap, so that gap is real, while `django` at 38.9% and `sympy` at 36.1% overlap almost entirely and their difference is not.

Sphinx is the sharpest open question. Its reports describe *rendered output* in vocabulary that never appears in the code producing it — precisely the gap lexical matching cannot cross, and the clearest test of whether rung 2 earns its cost.

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
