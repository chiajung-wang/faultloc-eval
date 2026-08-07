# faultloc-eval — Domain Language

This project uses these terms consistently across code, issues, ADRs, and results. If a concept is not here, it is either new language that the project does not need, or a gap in this file.

## Instance

One evaluable unit: an issue report plus the repository state it was filed against.

Fields: `instance_id`, `repo`, `base_commit` (SHA the repo is pinned to), `issue_text`, `ground_truth_files`.

Sourced from either the **Verified Set** or the **Fresh Set**.

## Verified Set

SWE-bench Verified — 500 human-validated instances across 12 Python repos. This project uses it because published localization numbers exist against it. Results are therefore anchored rather than free-floating.

Pinned to `princeton-nlp/SWE-bench_Verified`, split `test`, revision `c104f840cc67f8b6eec6f759ebc8b2693d585d4a`. Its newest instance dates to 2023-08-07. It therefore predates current model training cutoffs and is **contaminated** by construction. 231 of the 500 instances come from `django/django`, so every result is reported per repo as well as in aggregate. See ADR-0006.

## Fresh Set

Self-mined instances whose issues closed *after* the evaluated model's training cutoff. This set is the contamination control. Target size is 150–300. Draw them from the Verified Set's repositories where possible, so that a measured gap reflects contamination rather than repo difficulty. See ADR-0006.

## Contamination

The possibility that a model memorized an issue's fix from training data instead of localizing it. The accuracy gap between the Verified Set and the Fresh Set measures it.

## Ground-Truth File Set

The files an instance's answer is scored against. Derived mechanically: take the PR that closed the issue, keep the files it modified, then apply the **Instance Filter**.

Nobody labels it by hand. A reader must be able to regenerate it from the same inputs.

## Instance Filter

The rule that decides which raw issue/PR pairs become Instances. It drops non-source files (tests, docs, config, lockfiles) from the Ground-Truth File Set. It then drops the whole instance if more than 3 source files remain.

Rationale in [ADR-0001](docs/adr/0001-ground-truth-file-set.md).

## Filter Rate

The proportion of raw candidates that the Instance Filter rejects, reported per drop reason. Every result publishes it. Unreported filtering makes accuracy numbers unfalsifiable.

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

A rung's value is the delta it adds over the rung below, at its cost and latency. That rule makes the numbering load-bearing rather than decorative. A system inserted between two rungs changes what the rung above it earns credit for.

**Decimals rather than renumbering.** [ADR-0003](docs/adr/0003-baseline-ladder.md) fixed four rungs before any of them existed. Rungs 2.5 and 2.6 came afterwards. A renumber would silently invalidate every reference to "rung 3" and "rung 4", including two milestone definitions. The decimals are honest about the later arrival.

Rung 2.5 arrived by accident. It started as the Candidate Set's merge step, and it scored above both rungs that it merges.

## Ablation

A system that isolates one variable. It appears alongside the Rungs and never ships. It answers *which half of a change did the work*, and a Rung's own number cannot answer that.

`bm25-chunks` and `bm25-chunks-bodies` differ from rung 1 only in what counts as a document. That is how M3 established which change moved the number: indexed function bodies, not chunking. It also showed that rung 2's delta over rung 1 alone would have credited a model with a gain that a free change produced.

An Ablation appears in `RESULTS.md` with the same provenance as a Rung. It does not appear in the ladder.

## Candidate Set

The ranked, truncated list of files that a downstream rung receives. It is infrastructure, not a rung. It produces no answer of its own.

**hit@K** judges it: the share of Instances whose list contains at least one Ground-Truth File. That share is the hard ceiling on any system that reranks the list, because a reranker reorders and never adds.

This differs from Recall@k, which is the *share* of an Instance's ground-truth files found. hit@K bounds Top-1. Recall@k bounds Recall@k.

The same code produces rung 2.5 and the Candidate Set. Different metrics judge the two: Top-1 at K=1 against hit@K at K=20. A change that helps one does not always help the other, so the two roles carry separate names.

## AST Chunk

The indexed unit at rung 2: one function or class, embedded as its signature, docstring, **body**, and file path.

The first design excluded the body, on the theory that mechanical code would swamp the docstring. The docstring is the one place in source code where a human wrote English about intent. Measurement put the cost of that choice at 8.3pp of Recall@3. Bug reports quote body tokens constantly, and no similarity function can retrieve a token that nothing indexed. A definition carries its *own* source only. Definitions nested inside it are chunks in their own right.

A file that yields no definitions falls back to a whole-file chunk. Such a file is unparseable, non-Python, or simply a module of constants. A file with no chunks would be absent from the candidate set entirely, which caps accuracy in a way that looks the same as weak ranking.

## Window

The bound on a chunk's length: 2,048 characters, split on line boundaries, no overlap.

Whole-file fallbacks average 16,296 characters against 191 for a function chunk. They are 1.6% of chunks and carry 55% of the corpus. An embedding model with a 512-token limit discards everything past the limit, and it does so silently. A longer context does not fix this at any acceptable cost (ADR-0007). A split preserves the text instead.

The same window applies to every chunk-indexed system. Two rungs that windowed differently would make the delta between them measure the window rather than the variable under test.

## Chunk Aggregation

The rule that turns many chunk scores into one file score: **a file scores as its best chunk**. `sum` would reward length. `mean` would dilute a real match with irrelevant siblings.

Every chunk-indexed system shares this rule. Two systems that aggregated differently would make the delta between them measure aggregation rather than the variable under test.

## Evidence Chunk

The chunk that a file scored as under Chunk Aggregation. A model receives it as that candidate's evidence.

Chunk Aggregation already computes it and then discards it, and keeps only the score. This name lets rung 3 show a model *why* a file is in the Candidate Set. The alternative is a fresh excerpt that the retriever never looked at, and two rungs that disagreed about what a candidate is would make their delta unreadable.

Mean size is 214 tokens against 6,735 for the whole file (ADR-0008). That is the difference between a rung that costs a dollar and one that costs forty.

## Prediction

A rung's output for one Instance: a ranked list of file paths plus a **Confidence**.

## Confidence

A calibrated probability that the top-ranked file is in the Ground-Truth File Set. The **Calibrator** produces it. A model does not self-report it.

## Calibrator

A logistic regression that maps cheap features to a probability. The features are retrieval margin, model self-report, tool-call count, top-k hit, and two-sample agreement. It is fit on the dev split only.

The report states quality as **ECE** (expected calibration error) and a reliability diagram.

## Coverage

The proportion of Instances that a system answers instead of escalates, at a given Confidence threshold. A sweep of the threshold produces the accuracy-vs-coverage curve.

A system that can abstain should beat one that must guess. This project measures that claim rather than asserts it.

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

A deterministic check that every predicted path exists in the repo at the Instance's `base_commit`. A path that does not exist is a hallucination. The run rejects it, retries once, then fails. The report states the catch rate.
