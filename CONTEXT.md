# faultloc-eval — Domain Language

Terms used consistently across code, issues, ADRs, and results. If a concept isn't here, either it's new language the project doesn't need, or this file has a gap.

## Instance

One evaluable unit: an issue report plus the repository state it was filed against.

Fields: `instance_id`, `repo`, `base_commit` (SHA the repo is pinned to), `issue_text`, `ground_truth_files`.

Sourced from either the **Verified Set** or the **Fresh Set**.

## Verified Set

SWE-bench Verified — 500 human-validated instances. Used because published localization numbers exist against it, so results are anchored rather than free-floating.

Its instances predate current model training cutoffs, so it is **contaminated** by construction.

## Fresh Set

Self-mined instances whose issues were closed *after* the evaluated model's training cutoff. Serves as the contamination control. Target size 150–300.

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

One system on the ladder, each measured independently on the same Instances:

1. **BM25** — lexical retrieval over file contents, no LLM
2. **Embedding retrieval** — dense retrieval over AST Chunks
3. **LLM rerank** — model reorders rung-2 candidates
4. **Agent** — tool-using loop over the repository

A rung's value is the delta it adds over the rung below, at its cost and latency.

## AST Chunk

The indexed unit at rung 2: one function or class, embedded as its signature, docstring, and file path. Chosen because docstrings carry natural language, partially bridging the gap between prose issue text and code.

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
