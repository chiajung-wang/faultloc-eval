# faultloc-eval

Fault localization from issue reports — given a bug report, predict which source file(s) must change. Built as a measured ladder (BM25 → embedding retrieval → LLM rerank → tool-using agent), evaluated against SWE-bench Verified plus a self-mined post-cutoff contamination control.

## Agent skills

### Issue tracker

Issues live as markdown files under `.scratch/<feature-slug>/` in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles use their default strings (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
