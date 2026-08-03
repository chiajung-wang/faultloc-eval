# 05 — BM25 rung

Status: ready-for-agent

## Context

Rung 1 of the ladder. Lexical retrieval over file contents, no model calls.

Issue text frequently quotes identifiers, file paths, and stack traces, so lexical matching is a genuinely strong baseline here — that is the point. If later rungs struggle to beat it, that is a finding worth reporting, not a bug.

## Acceptance criteria

- Given an Instance, returns a ranked list of file paths
- Tokenisation splits identifiers sensibly (snake_case, CamelCase, dotted paths)
- Deterministic: same Instance, same ranking, every run
- Returns `no_candidates` rather than an empty list silently
- Exposes a `Prediction` shape that later rungs also produce

## Notes

Keep the rung interface narrow — later rungs must be swappable behind it without touching the harness.
