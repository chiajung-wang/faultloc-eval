# 05 — Publish the rung-2 delta

Status: ready-for-agent

## Parent

[M3 PRD](../PRD.md)

## What to build

Closes M3. The three numbers now exist in `RESULTS.md`; this slice turns them into a stated result.

The README ladder table gains the ablation rows and fills the embedding row, each with cost per instance and latency. The delta is reported **once per variable**, because there are three of them and they answer different questions:

- chunking alone — `bm25-chunks` over `bm25`, at no model cost
- body exclusion within chunking — the issue-06 variant against `bm25-chunks`, also free
- embeddings given whatever chunk definition survived — `embed` over the best lexical chunk row, at its measured price

Reporting only `embed` over `bm25` would attribute the whole movement to the model, which is the overclaim the ablation exists to prevent.

Confidence intervals govern what may be claimed. At ~244 instances the Wilson interval on Top-1 is roughly ±6pp, so two rungs whose intervals overlap have not been shown to differ, and the table must say so rather than let adjacency imply an ordering. A rung that fails to beat the one below it is published as-is: ADR-0003 makes a null result a finding, and this is the first place that commitment costs anything.

Answer the Sphinx question the M1 log left open. `sphinx-doc/sphinx` sat at 4.5% Top-1, truth at median rank 40 of 541 candidates, on the hypothesis that its issues describe rendered output in vocabulary absent from the code. Rung 2 is the test of that hypothesis. State what happened, including if the answer is nothing.

## Acceptance criteria

- [ ] README ladder table carries all three rows with Top-1 + interval, Recall@3, Recall@5, cost per instance, latency
- [ ] Both deltas stated separately, with the variable each isolates named
- [ ] Overlapping intervals called out explicitly wherever a difference is not established
- [ ] Sphinx result stated against the M1 prediction, whichever way it went
- [ ] Every figure in the README traces to a `RESULTS.md` entry — no number typed by hand
- [ ] `docs/milestones.md` updated to close M3 and mark M4 current

## Notes

The M1 pattern holds: predictions that measurement overturned stay on the record rather than being edited away. A wrong written prediction is better evidence of a working method than one that happened to be right.

If the ablation shows chunking did the work and embeddings added little, that is the milestone's result and the README says it plainly. It also sharpens M4 — an LLM reranker over chunk candidates is a different mechanism, and knowing embeddings did not close the gap tells the reader why the next rung exists.

## Blocked by

- [01 — BM25 over AST Chunks](01-bm25-over-chunks.md)
- [06 — Chunks with bodies](06-chunks-with-bodies.md)
- [04 — Rung 2: embedding retrieval end to end](04-embed-rung.md)
