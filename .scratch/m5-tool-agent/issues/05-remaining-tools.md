# 05 — The four remaining tools, each honoring the contract

Status: done

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

- [x] All five tools available to the agent, and none of them writes anything
- [x] `search_code` runs a **literal** search at `base_commit` through the bare clones *(this said "literal and regex"; literal is what issue 01 measured and what shipped, and ADR-0009 carries the same correction)*
- [x] `search_code` caps its hits and reports the true match count alongside them
- [x] `semantic_search` accepts a query the agent writes, not the raw issue text
- [x] `find_definition` uses the `ast` module, with no language server and no process to supervise
- [x] Every tool hard-caps its output, and truncation is deterministic
- [x] A test proves every tool produces byte-identical output across two runs
- [x] Per-tool call counts and per-tool contribution to the final answer are logged and printed
- [x] The error split from issue 04 holds for all four new tools
- [x] `faultloc evaluate --rung agent --split dev --limit 3` runs end to end with all five *(3 rather than 5: the tool-surface change invalidated the response cache, so every Instance pays fresh, and 3 is what issue 04 used)*
- [x] Tests make no network calls
- [x] `uv run pytest` and `uv run ruff check` clean

## Notes

**`semantic_search` earns its slot on one repo, named in advance.** `sphinx` has a hit@20 of 63.6%, and all four rung-3 cells score exactly that. Its reports describe rendered output, so `git grep` should fail there by construction: nothing can grep a term the code does not contain. Bridging a phrase like "table renders wrong" to `tabular` needs either sphinx-internals knowledge the agent lacks, or a dense match. The expected size is small, at 22 Instances of 244 and roughly 3.3pp, which sits inside the ±6pp interval. **The contribution log is what decides whether it earned the slot.** Do not decide it in this issue.

Five is a ceiling and not a floor. ADR-0002 says a larger tool surface degrades selection quality and inflates cost per step. At a cap of 8 calls, one wasted call is an eighth of the Instance's Budget.

Determinism is not a preference here. A resumed run replays from the response cache only while each step's prompt stays byte-identical, so a tool that sorts differently on two runs makes a six-hour run pay twice. Sort output, use no timestamps, and never leak an absolute path such as `data/repos/...` into a result.

Read issue 01's findings before choosing what patterns `search_code` should accept. It measured which pattern classes reach a ground-truth file.

## Blocked by

- [04 — Rung 4 end to end, one tool, whole contract](04-agent-end-to-end.md)

## Comments

**Closed 2026-08-11.** Commits `4809d57`, `10fa6fb`, `d192f12`, `8955d3b`, `a1b8ac4`. 631 tests, `ruff` clean, **57 breaks caught with none uncaught**. The smoke run cost about $0.03.

### The smoke run, with all five

`--limit 3` at `a1b8ac4`: 3 of 3 answered, no degrades, $0.0107 per Instance and 58.7s. Every Instance paid fresh, because the tool surface is part of the response cache key.

```
Guardrail: 0 paths rejected as absent, 0 retries. Off-list accepted: 0, of which 0
were never surfaced by a tool. Tool calls: median 8, mean 8.0, cap of 8 reached on
3/3 instances. Tools: read_file 18 calls/3 top-1, search_code 6 calls/0 top-1.
```

### Three of the five tools were never called

`semantic_search`, `file_outline` and `find_definition` recorded **zero calls**. `read_file` took 18 and `search_code` 6, and `read_file` found the Top-1 on all three.

The contribution log did exactly the job ADR-0009 gave it, and it did so on the first run. At n=3, on one repository, this is direction and not magnitude — but the tool whose slot was already in question is the one that went unused.

**`semantic_search`'s case is not yet tested.** It was named in advance for `sphinx`, and none of these three Instances is a sphinx Instance. Issue 06's full run is where that decision belongs, and ADR-0002's roster takes a recorded correction if the log stays empty.

### Rung 4 did not reach past the Candidate Set on any of the three

Zero Off-List Paths, zero hallucinations, zero invented tools. Reaching past the list is the only thing rung 4 adds over rung 3, and here it added nothing.

Read it carefully rather than as a failure: all three Instances were answered correctly, so the agent had no reason to look outside a list that already held the answer. The Instances that matter are the 27 where the list does not, and none of them is in this sample.

### The cap is now reached on 6 of 6 Instances

Three with one tool, three with five. ADR-0009's revisit condition has fired on every Instance run so far, and the median is exactly the cap.

If that holds at scale, **the published number belongs to the cap and not to the agent.** Issue 06 must report the distribution and say so.

### Corrections made while closing

Two statements here overstated what shipped, and both are corrected above rather than quietly dropped. `search_code` is a **literal** search, not "literal and regex" — literal is what issue 01 measured its 59.3% reachability with, and a regex mode would add a failure the agent could only find by spending a step. ADR-0009 carries the same correction. And the smoke ran on 3 Instances rather than 5, because the tool-surface change invalidated the cache and issue 04 used 3.

### What the build found

**Sharing one parser was right, and reusing `chunk_source` was wrong.** `_windowed` drops the signature and the line on purpose and renames pieces to `name#0`, so an outline built on windows lists a long definition as nameless rubbish at line 0. A 3,200-character docstring triggers it. `chunks.definitions` walks without windowing and reuses `_walk`, so the qualified-name and nesting rules — the part that could genuinely drift — stay written once.

**A qualified name never appears literally in the file that defines it.** `find_definition` greps the last segment, and the parse afterwards is what separates a definition from a mention.

**Four tests could not fail**, every one caught by the break harness rather than by reading them: a "mere mention" file that defined nothing, an outline fixture too small to be windowed, a credit test that made no tool calls, and a cost test that ran one Instance where cumulative and per-Instance spend are equal.

**And the harness failed three times in ways worth recording.** A timeout left a patched file in the tree, and a detection grep then called it clean because of unescaped regex metacharacters. An edit to add five breaks was a silent no-op, because a `str.replace` anchor had stopped matching. And a changed `VIRTUAL_ENV` turned pytest's colour on, so every failure line arrived as `\x1b[31mFAILED` and the harness reported all 57 breaks uncaught while the suite was green. It now restores on a kill, asserts each patch applied, and strips control characters.
