# 05 — Publish the rung-2 delta

Status: done

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

## Comments

**Closed 2026-08-04. M3 is complete, and its result is a null one.**

The README ladder table now carries four rows with intervals, recall, cost, and latency; `docs/milestones.md` closes M3 and marks M4 current.

### The headline the table had to be honest about

All four Top-1 intervals overlap pairwise. The best row sits 4.6pp above rung 1 and **that is not shown to be real** — the Wilson interval at n=244 is about ±6pp, wider than every gap in the column. The README says so directly and warns that the table is ordered by point estimate, not by established ranking.

It would have been easy to write "43.9% vs 39.3%, a 4.6-point gain" and let the reader supply the significance. The whole reason Top-1 carries an interval in this project is to make that sentence unwriteable.

### Three deltas, and the free one won

- **chunking alone** — +0.5pp Top-1 (nothing), Recall@5 68.5 → 61.3. Free, and it made things worse.
- **indexing bodies** — Recall@3 52.0 → 60.3, back to whole-file parity; the highest Top-1 of any row. Also free.
- **embeddings on top** — 43.9% → 43.0%. A model, a 1.56 GB index, and 153 minutes bought nothing measurable.

Stating it as one `embed`-over-`bm25` delta would have credited the model with a gain that came entirely from changing what gets indexed. That specific overclaim is what the ablation was built to prevent, and it would have been the natural thing to write.

### Sphinx, as the issue required

M1 predicted it as the sharpest test of embeddings. **4.5% → 0.0% → 18.2% → 27.3%.** Right about the repo, wrong about the mechanism: its vocabulary is in the code, in the bodies rather than the signatures. The prediction stays on the record.

### A gap this exposed

**Recall@k carries no confidence interval in the results log.** Top-1 does, and the whole M3 write-up leans on intervals to say what is and isn't established — then quotes recall differences with nothing to bound them. The README labels them as direction rather than magnitude, which is a mitigation, not a fix. Worth an issue when recall is load-bearing for a claim; it is not yet.

### Verification

Every figure in the README was checked against `RESULTS.md` by string match rather than by eye — four Top-1 values with their intervals, four Recall@3 values, and the wall clocks the latency column divides. That caught one error: the bodies row's latency was computed from a superseded run's 3m38s instead of the clean rerun's 3m42s.
