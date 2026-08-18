# 06 — Two index builds, and rung 2.5's drop across both sets

Status: ready-for-agent

## Parent

[M6 PRD](../PRD.md)

## What to build

The free half of the Contamination estimate.

`AgentRung` defaults to `HybridRung`, so rung 4 warm-starts from bm25 **and** the embedding index. Two indexes do not exist:

- The Verified **test** split. `faultloc index --split dev` never covered it.
- The Fresh Set, which sits on post-2026 commits sharing few blobs with the 2023-era index.

Each takes about 2.5 hours and costs no money. The index is content-keyed by blob SHA, so measure what actually needs embedding before assuming a full rebuild.

Then run rung 2.5 on the Verified test split and on the Fresh Set, and report its drop. **Rung 2.5 runs no model, so its drop prices task difficulty alone.** That is the quantity issue 09 subtracts, and it is what stops a raw gap from being read as memory.

Rung 2.5 acts here as a Rung and as the Candidate Set at once. Every figure names which role it carries, because the two are judged by different metrics: Top-1 at K=1 against hit@K at K=20.

Also report hit@20 on the Fresh Set. It is the hard ceiling on rung 4's Fresh number, and reading rung 4 without it repeats an error M4 and M5 both had to correct for.

## Acceptance criteria

- [ ] The Verified test split is indexed
- [ ] The Fresh Set is indexed
- [ ] Rung 2.5 writes `RESULTS.md` entries for the Verified test split and for the Fresh Set
- [ ] Rung 2.5's drop across the two sets is reported, reweighted, with effective n
- [ ] hit@20 is reported on the Fresh Set
- [ ] Each entry carries per-repo Top-1, cost, and latency, including where cost is $0.00
- [ ] Every run starts from a clean tree

## Notes

**Changing what a chunk contains invalidates every index.** Do not touch the chunker. A window or aggregation change here would make the Verified-to-Fresh delta measure the change rather than the dataset.

**Piping a long-running command through `grep` buffers its progress output.** Track progress another way.

## Blocked by

- [03 — Fresh Set loader and dataset provenance](03-fresh-loader-and-provenance.md)
- [05 — Mix Reweighting and the minimum detectable effect](05-reweighting-and-detectable-effect.md)
