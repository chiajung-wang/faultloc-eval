# 02 — Pick the embedding model, record ADR-0007

Status: ready-for-human

## Parent

[M3 PRD](../PRD.md)

## What to build

A decision, priced, written as `docs/adr/0007-embedding-model.md`, plus whatever pinning the choice implies (model identifier, revision, dimensionality, normalisation) so a reader can regenerate the index from the same inputs.

Two open questions from `docs/PRD.md` are settled here:

**Local or hosted.** A local sentence-transformers model costs nothing per run, keeps every number reproducible offline, and makes the cost column honestly `$0.00` at rung 2 — which weakens the ladder's cost story precisely where it was supposed to start biting. A hosted code-specialised model is likely stronger on identifier-dense text, but prices every full-corpus index, pins the project to an API whose weights can change under a stable name, and puts a paid dependency in the CI gate planned for M9.

**Index-cache strategy across ~500 base commits and ~12 repos.** Blob SHA is a content hash, so a chunk embedding keyed by it is never wrong and is shared across every instance and repository holding that content. Confirm this is the key, and state the expected distinct-blob count and what a cold build costs in dollars and wall-clock at the chosen model.

The ADR must state the rejected option and the condition under which the decision would be revisited.

## Acceptance criteria

- [ ] `docs/adr/0007-embedding-model.md` written in the existing ADR format, with rationale and rejected alternatives
- [ ] Model pinned by identifier *and* revision; embedding dimensionality and any normalisation stated
- [ ] Cold-index cost estimated in dollars and wall-clock, with the distinct-blob count it assumes
- [ ] Cache key stated, with the reason it cannot go stale
- [ ] Reproducibility consequence stated explicitly — whether a third party can regenerate the numbers without an API key
- [ ] `CONTEXT.md` updated if the decision introduces or renames domain language

## Notes

HITL because it spends the user's money and constrains M9's CI gate. It is unblocked, so it can be decided while issue 01 runs.

A hosted model chosen here does not have to be the only one measured — but any comparison of two embedding models is a rung-2 variant row, not a replacement for the ablation in issue 01.

## Blocked by

None — can start immediately, in parallel with issue 01.
