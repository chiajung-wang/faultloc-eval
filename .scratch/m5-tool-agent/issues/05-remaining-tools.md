# 05 — The four remaining tools, each honoring the contract

Status: ready-for-agent

## Parent

[M5 PRD](../PRD.md)

## What to build

The other four tools of [ADR-0002](../../../docs/adr/0002-no-code-execution.md), and the logging that makes the roster a measurement rather than an assertion.

Issue 04 proved the tool contract on `read_file`. These four inherit all of it: a model-caused error returns to the agent, an infrastructure error fails the Instance, output is hard-capped, and truncation is deterministic.

**`search_code` — `git grep`.** Literal and regex search over source files at `base_commit`, through the bare clones `RepoStore` already holds. Not BM25 over the same AST Chunks. BM25 is the signal that already built half the Candidate Set, so it would add nothing the warm start did not run. A literal search finds what a tokenizer smears: quoted error strings, traceback frames, exact identifiers. M3 established that bug reports quote body tokens constantly.

The tool returns at most N hits **and it reports the true match count.** A silently truncated result is a biased slice that the agent cannot know about. A stated count of 847 with 30 shown drives a refinement instead.

**`semantic_search`.** Dense retrieval over the same index rung 2 uses, on a query the agent writes. Its new power is the rewritten query, because the warm start ran both retrievers on raw issue text alone.

**`file_outline`.** The definitions in a file, without their bodies.

**`find_definition`.** Where a symbol is defined. ADR-0002 fixed the mechanism: the standard-library `ast` module, and no language server. This is the tool most likely to reach a file the Candidate Set never held, because it follows structure rather than similarity.

**Per-tool contribution logging.** For each tool, record how many times the agent called it, and how often a call surfaced a path that reached the final answer. Q2's Tool-Reached already maps a path to the tool that found it, so this is nearly free, and it turns the roster into a finding.

## Acceptance criteria

- [ ] All five tools available to the agent, and none of them writes anything
- [ ] `search_code` runs literal and regex search at `base_commit` through the bare clones
- [ ] `search_code` caps its hits and reports the true match count alongside them
- [ ] `semantic_search` accepts a query the agent writes, not the raw issue text
- [ ] `find_definition` uses the `ast` module, with no language server and no process to supervise
- [ ] Every tool hard-caps its output, and truncation is deterministic
- [ ] A test proves every tool produces byte-identical output across two runs
- [ ] Per-tool call counts and per-tool contribution to the final answer are logged and printed
- [ ] The error split from issue 04 holds for all four new tools
- [ ] `faultloc evaluate --rung agent --split dev --limit 5` runs end to end with all five
- [ ] Tests make no network calls
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

**`semantic_search` earns its slot on one repo, named in advance.** `sphinx` has a hit@20 of 63.6%, and all four rung-3 cells score exactly that. Its reports describe rendered output, so `git grep` should fail there by construction: nothing can grep a term the code does not contain. Bridging a phrase like "table renders wrong" to `tabular` needs either sphinx-internals knowledge the agent lacks, or a dense match. The expected size is small, at 22 Instances of 244 and roughly 3.3pp, which sits inside the ±6pp interval. **The contribution log is what decides whether it earned the slot.** Do not decide it in this issue.

Five is a ceiling and not a floor. ADR-0002 says a larger tool surface degrades selection quality and inflates cost per step. At a cap of 8 calls, one wasted call is an eighth of the Instance's Budget.

Determinism is not a preference here. A resumed run replays from the response cache only while each step's prompt stays byte-identical, so a tool that sorts differently on two runs makes a six-hour run pay twice. Sort output, use no timestamps, and never leak an absolute path such as `data/repos/...` into a result.

Read issue 01's findings before choosing what patterns `search_code` should accept. It measured which pattern classes reach a ground-truth file.

## Blocked by

- [04 — Rung 4 end to end, one tool, whole contract](04-agent-end-to-end.md)
