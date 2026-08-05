# faultloc-eval — Domain Language

Terms used consistently across code, issues, ADRs, and results. If a concept isn't here, either it's new language the project doesn't need, or this file has a gap.

## Instance

One evaluable unit: an issue report plus the repository state it was filed against.

Fields: `instance_id`, `repo`, `base_commit` (SHA the repo is pinned to), `issue_text`, `ground_truth_files`.

Sourced from either the **Verified Set** or the **Fresh Set**.

## Verified Set

SWE-bench Verified — 500 human-validated instances across 12 Python repos. Used because published localization numbers exist against it, so results are anchored rather than free-floating.

Pinned to `princeton-nlp/SWE-bench_Verified`, split `test`, revision `c104f840cc67f8b6eec6f759ebc8b2693d585d4a`. Its newest instance dates to 2023-08-07, so it predates current model training cutoffs and is **contaminated** by construction. 231 of the 500 instances are from `django/django`, so results are reported per repo as well as in aggregate. See ADR-0006.

## Fresh Set

Self-mined instances whose issues were closed *after* the evaluated model's training cutoff. Serves as the contamination control. Target size 150–300, drawn from the Verified Set's repositories where possible so a measured gap reflects contamination rather than repo difficulty. See ADR-0006.

## Contamination

The possibility that a model has memorised an issue's fix from training data rather than localising it. Measured as the accuracy gap between the Verified Set and the Fresh Set.

## Ground-Truth File Set

The files an instance's answer is scored against. Derived mechanically: take the PR that closed the issue, keep files it modified, then apply the **Instance Filter**.

Never hand-labelled. A reader must be able to regenerate it from the same inputs.

## Instance Filter

The rule deciding which raw issue/PR pairs become Instances. Drops non-source files (tests, docs, config, lockfiles) from the Ground-Truth File Set, then drops the whole instance if more than 3 source files remain.

Rationale in [ADR-0001](docs/adr/0001-ground-truth-file-set.md).

## Filter Rate

The proportion of raw candidates the Instance Filter rejects, reported per drop reason. Published alongside every result. Unreported filtering makes accuracy numbers unfalsifiable.

## Rung

One system on the ladder that produces a ranked answer for an Instance, measured on the same Instances as every other and reported with its accuracy, cost, and latency.

| # | Rung | What it adds over the rung below |
|---|---|---|
| 1 | **BM25** | lexical retrieval over file contents, no model |
| 2 | **Embedding retrieval** | dense retrieval over AST Chunks |
| 2.5 | **Hybrid** | rank fusion of rungs 1 and 2 — no model, no new signal, just agreement |
| 2.6 | **Cross-encoder rerank** | a model that reads the issue and a candidate *together*, rather than embedding each alone |
| 3 | **LLM rerank** | a model that reasons about the Candidate Set in natural language |
| 4 | **Agent** | a tool-using loop that can go looking for what retrieval missed |

A rung's value is the delta it adds over the rung below, at its cost and latency. That rule is what makes the numbering load-bearing rather than decorative: inserting a system between two rungs changes what the rung above it is being credited with.

**Decimals rather than renumbering.** [ADR-0003](docs/adr/0003-baseline-ladder.md) fixed four rungs before any existed. Rungs 2.5 and 2.6 were inserted afterwards, and renumbering would silently invalidate every reference to "rung 3" and "rung 4" — including two milestone definitions. The decimals are honest about having been added later.

Rung 2.5 arrived by accident: it was built as the Candidate Set's merge step and turned out to score above both rungs it merges.

## Ablation

A system built to isolate one variable, published alongside the Rungs and never shipped. It answers *which half of a change did the work*, which a Rung's own number cannot.

`bm25-chunks` and `bm25-chunks-bodies` differ from rung 1 only in what counts as a document. That is how M3 established that indexing function bodies — not chunking — was what moved the number, and that reporting rung 2's delta over rung 1 alone would have credited a model with a gain a free change produced.

An Ablation appears in `RESULTS.md` with the same provenance as a Rung. It does not appear in the ladder.

## Candidate Set

The ranked, truncated list of files a downstream rung is handed. Infrastructure, not a rung — it produces no answer of its own.

Judged by **hit@K**: the share of Instances whose list contains at least one Ground-Truth File. That is the hard ceiling on any system reranking it, since a reranker reorders and never adds.

Distinct from Recall@k, which is the *share* of an Instance's ground-truth files found. hit@K bounds Top-1; Recall@k bounds Recall@k.

The same code produces rung 2.5 and the Candidate Set, and the two are judged by different metrics — Top-1 at K=1 against hit@K at K=20. Tuning for one does not necessarily help the other, so the roles are named separately.

## AST Chunk

The indexed unit at rung 2: one function or class, embedded as its signature, docstring, **body**, and file path.

The body was originally excluded, on the theory that mechanical code would swamp the docstring — the one place in source code where a human wrote English about intent. Measured, that cost 8.3pp of Recall@3: bug reports quote body tokens constantly, and a token that was never indexed cannot be retrieved by any similarity function. A definition carries its *own* source only, not that of definitions nested inside it, which are chunks in their own right.

A file that yields no definitions — unparseable, non-Python, or simply a module of constants — falls back to a whole-file chunk. A file with no chunks would be absent from the candidate set entirely, which caps accuracy in a way indistinguishable from weak ranking.

## Window

The bound on a chunk's length: 2,048 characters, split on line boundaries, no overlap.

Whole-file fallbacks average 16,296 characters against 191 for a function chunk — 1.6% of chunks carrying 55% of the corpus. Handed whole to an embedding model with a 512-token limit, everything past the limit is discarded silently, and a longer context does not fix it at any acceptable cost (ADR-0007). Splitting preserves the text instead.

The same window applies to every chunk-indexed system. Two rungs windowing differently would make the delta between them measure the window rather than the variable under test.

## Chunk Aggregation

The rule turning many chunk scores into one file score: **a file scores as its best chunk**. `sum` would reward length, `mean` would dilute a real match with irrelevant siblings.

Every chunk-indexed system shares this rule. Two of them aggregating differently would make the delta between them measure aggregation rather than the variable under test.

## Evidence Chunk

The chunk a file scored as under Chunk Aggregation, shown to a model as that candidate's evidence.

Chunk Aggregation already computes it and then discards it, keeping only the score. Naming it is what lets rung 3 show a model *why* a file is in the Candidate Set, rather than a fresh excerpt the retriever never looked at — two rungs disagreeing about what a candidate is would make their delta unreadable.

Mean 214 tokens against 6,735 for the whole file (ADR-0008), which is the difference between a rung that costs a dollar and one that costs forty.

## Prediction

A rung's output for one Instance: a ranked list of file paths plus a **Confidence**.

## Confidence

A calibrated probability that the top-ranked file is in the Ground-Truth File Set. Produced by the **Calibrator**, not self-reported by a model.

## Calibrator

A logistic regression mapping cheap features — retrieval margin, model self-report, tool-call count, top-k hit, two-sample agreement — to a probability. Fit on the dev split only.

Quality reported as **ECE** (expected calibration error) and a reliability diagram.

## Coverage

The proportion of Instances a system chooses to answer rather than escalate, at a given Confidence threshold. Sweeping the threshold produces the accuracy-vs-coverage curve.

A system permitted to abstain should beat one forced to guess. That claim is measured here, not asserted.

## Escalation

The `low_confidence` outcome: the system declines to answer and routes the Instance to a human.

## Stop Condition

The single terminal state every run ends in, always logged:

| State | Meaning |
|---|---|
| `answered` | Prediction produced above the Confidence threshold |
| `low_confidence` | Escalated |
| `budget_exceeded` | Cost or tool-call cap hit |
| `timeout` | Wall-clock cap hit |
| `no_candidates` | Retrieval returned nothing |

## Path Guardrail

A deterministic check that every predicted path exists in the repo at the Instance's `base_commit`. A path that doesn't exist is a hallucination; the run rejects it, retries once, then fails. Catch rate is reported.
