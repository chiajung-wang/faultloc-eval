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

Self-mined Instances whose fixing pull request merged on or after **2026-05-01**. That date clears the April 2026 training cutoff of `deepseek/deepseek-v4-pro`, which rung 4 pins, with one month of margin. The cutoff is unofficial, so the margin is the whole defense.

This set is the Contamination control. It carries **no dev/test split**, because it is read once and nobody tunes against it. A committed JSON file holds the frozen Instances, and its content hash is the revision that every `RESULTS.md` entry stamps.

**It holds almost no django.** django/django runs its issue tracker on Trac, so GitHub issue linkage finds 1 candidate against django's 231 Instances in the Verified Set. [Mix Reweighting](#mix-reweighting) exists because of that. See ADR-0006.

## Contamination

The possibility that a model memorized an issue's fix from training data instead of localizing it.

**The estimate is a difference of two drops.** Take rung 4's accuracy drop from the Verified Set to the Fresh Set. Then subtract the drop that rung 2.5 shows across the same two sets. Rung 2.5 runs no model, so its drop prices task difficulty alone. What remains is the Contamination estimate.

A single rung's drop is not the estimate. It mixes memory with difficulty, and nothing inside it separates the two.

## Mix Reweighting

The rule that makes a Verified number comparable to a Fresh number. Compute the Verified aggregate as a per-repo average, weighted by the **Fresh Set's** repo proportions.

The two sets have opposite shapes. django is 46% of the Verified Set and near zero in the Fresh Set. Post-cutoff activity concentrates in scikit-learn, pytest, astropy, matplotlib and pylint, and those repos hold few Verified Instances each. An unweighted comparison would move the headline by repo mix alone, by more than any Contamination effect anyone expects.

**Reweighting costs power, and every reweighted figure publishes the cost.** Effective sample size on the Verified side falls from 244 to 66 on the dev split, and to 141 across the full set. A larger Fresh Set does not recover it, because the Verified side is the binding constraint.

## Ground-Truth File Set

The files an instance's answer is scored against. Derived mechanically: take the PR that closed the issue, keep the files it modified, then apply the **Instance Filter**.

Nobody labels it by hand. A reader must be able to regenerate it from the same inputs.

## Instance Filter

The rule that decides which raw issue/PR pairs become Instances. It drops non-source files (tests, docs, config, lockfiles) from the Ground-Truth File Set. It then drops the whole instance if more than 3 source files remain.

Two more rules cover raw pull request file lists, which the Fresh Set introduces. The filter drops a file whose basename carries no extension, such as `AUTHORS` or `.mailmap`. It also drops test infrastructure, such as `_testing.py` and `conftest.py`. Both rules change no Verified Instance, and somebody measured that before ADR-0001 accepted them. M6 implements them.

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

## Budget

A cap on what a system may spend. Three scopes carry the name, and the word *run* alone does not say which one applies.

| Scope | Name | Caps | Rung 4 |
|---|---|---|---|
| one Instance | **Instance Budget** | tool calls, wall clock | 8 calls, 600s |
| one evaluation of a split | **Evaluation Budget** | dollars | $12 |
| one milestone | **Milestone Budget** | dollars | $20 |

Every scope is checked against spend already incurred, and the run stops before it breaks a cap. A run that reports an overspend afterwards is a run that already spent the money.

The Instance Budget holds no dollar cap, because rung 4's cost per Instance is bounded by its structure. Eight tool calls, each with a capped result, cannot reach $0.05. A tunable cap under a structural bound could only fire on a bug, and it would hide that bug.

## Stop Condition

The single terminal state every run ends in, always logged:

| State | Meaning |
|---|---|
| `answered` | Prediction produced above the Confidence threshold |
| `low_confidence` | Escalated |
| `budget_exceeded` | A Budget cap is reached. At rung 4 this is the tool-call cap |
| `timeout` | Wall-clock cap hit |
| `no_candidates` | Retrieval returned nothing |

## Off-List Path

A path that a model names and that the Candidate Set does not hold.

Rung 3 discards one, because a reranker reorders and never adds. Rung 4 keeps one that exists, because a reach past the list is the thing rung 4 adds. One event, two dispositions. Every rung counts it.

An Off-List Path is not a hallucination. The Path Guardrail answers that question, and it is a different question.

## Path Guardrail

A deterministic check that every predicted path exists in the repo at the Instance's `base_commit`. A path that does not exist is a hallucination. The run rejects it. The run then asks the model one more time, and it names the rejected paths. The report states the catch rate.

**At rung 4 a total failure cannot happen.** The answer keeps the Candidate Set behind the model's own order, and every candidate exists at the commit. So the run stamps `answered` and it counts the event. The count is the only honest record, because a silent fall back to Candidate Set order looks healthy in every metric except the one that says whether the model answered.

**The check asks about existence, not about membership.** It never asks whether the Candidate Set held the path. M4 counted 92 Off-List Paths across four configurations. Nobody split that count into paths that exist and paths that do not, so it does not size this guardrail yet.

## Tool-Reached

Whether a tool call surfaced a predicted path during the run that named it.

The Verified Set predates the model training cutoff, so a model can name a real path from memory. Such a path passes the Path Guardrail, and it is not localization. This flag separates search from recall. The run logs it as a diagnostic. It never rejects a path.
