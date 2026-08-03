# 05 — BM25 rung

Status: ready-for-agent

## Context

Rung 1 of the ladder. Lexical retrieval over file contents, no model calls.

**Index unit: the whole file.** One document per source file at the instance's `base_commit`. Chunking belongs to rung 2 (locked design decision #6), and rung 1 exists to establish the floor — the crudest thing that works — so the deltas above it mean something.

Known effect, expected and not a bug: file lengths in these repos are very uneven, and Django's are among the longest. BM25's length normalisation is a generic average-based correction, not one tuned for source code, so it can both under-penalise long files that match everything by vocabulary alone and over-penalise the large core module that genuinely is the answer. A weaker Django result at rung 1 is the predicted outcome, not a defect to chase.

Issue text frequently quotes identifiers, file paths, and stack traces, so lexical matching is a genuinely strong baseline here — that is the point. If later rungs struggle to beat it, that is a finding worth reporting, not a bug.

## Acceptance criteria

- Given an Instance, returns a ranked list of file paths
- Tokenisation splits identifiers sensibly (snake_case, CamelCase, dotted paths)
- Deterministic: same Instance, same ranking, every run
- Returns `no_candidates` rather than an empty list silently
- Exposes a `Prediction` shape that later rungs also produce

## Notes

Keep the rung interface narrow — later rungs must be swappable behind it without touching the harness.
