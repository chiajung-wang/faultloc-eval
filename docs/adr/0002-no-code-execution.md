# ADR-0002: Read-only tools, no code execution

**Status:** Accepted · 2026-07-31

## Context

This project could give a localization agent the power to run tests or execute snippets inside a sandbox. A reproduced failure is strong evidence about where a bug lives.

That choice requires a working environment per instance. Each environment needs the correct Python version, the correct pinned dependencies, and the correct build steps. The project spans roughly twelve repositories at five hundred distinct commits.

## Decision

The agent gets exactly five read-only tools:

`search_code` · `semantic_search` · `read_file(path, start, end)` · `file_outline` · `find_definition`

No test execution. No sandboxed interpreter. No container per instance.

## Rationale

The question here is *"which file is wrong"*, not *"does this fix work"*. Execution is evidence for the second question, and only indirectly for the first.

The cost is not incidental. A project must build and maintain one environment per instance. That work is the single most common reason projects in this space stall. A direct predecessor of this project, `~/dev/archives/triage-rca-agent`, chose a Docker sandbox for test execution in its ADR-0003. Its author abandoned it one day later, at three commits total, with no working output.

Five tools is also a deliberate ceiling. Larger tool surfaces degrade selection quality, inflate token cost per step, and make failures harder to attribute.

## Consequences

- The project runs on any machine with Python and a network connection. No environment matrix to maintain.
- `find_definition` uses the standard-library `ast` module rather than a language server. There is no process to supervise.
- Python-only, which is acceptable: the evaluated benchmark is Python.
- Some instances are unsolvable without code execution. Those become part of the measured ceiling. The failure taxonomy must describe them rather than design around them.

## Alternatives rejected

- **Read-only plus sandbox execution** — strongest signal, but reintroduces exactly the cost that killed the predecessor
- **Search and read only (two tools)** — too thin. The agent cannot traverse structure, and it collapses into a slower version of rung 3
- **Execution plus patch application** — that is patch generation, out of scope, and a space where the underlying model rather than this system's engineering decides the result

## Amended 2026-08-18 — two tools of the five carry the work

This ADR fixed five tools by name and called that "a deliberate ceiling". M5
measured what each one did across 244 Instances, and the roster does not hold up
as written.

| Tool | Calls | Instances where it found the Top-1 |
|---|---|---|
| `read_file` | 811 | 121 |
| `search_code` | 618 | 81 |
| `file_outline` | 89 | 39 |
| `find_definition` | 10 | 1 |
| **`semantic_search`** | **3** | **0** |

**`semantic_search` was called three times in 244 Instances and never surfaced a
path that reached an answer.** [ADR-0009](0009-tool-using-agent.md) named exactly
this as the condition for revisiting the roster, before any of it ran.

**The prediction that justified it failed.** It was kept for `sphinx`, whose
reports describe rendered output in words the code does not contain, so a literal
`git grep` should fail there by construction. Sphinx went from 63.6% to 86.4% at
rung 4 — and `semantic_search` cannot be what did it, because the agent barely
called the tool at all.

**`find_definition` is close behind at ten calls.** It was argued for as the tool
most likely to reach a file the Candidate Set never held, because it follows
structure rather than similarity. Rung 4 reached past the Candidate Set twice in
244 Instances, so that argument was right about the mechanism and wrong about the
scale.

**What this ADR does not do.** It does not drop either tool yet. One agent, one
model, one prompt and one split produced this table, and a tool the agent did not
*choose* is not the same as a tool that does not *work*. The prompt describes five
tools in a fixed order, and `semantic_search` sits second while `read_file` sits
third — so ordering is not the explanation, and something else is.

The measurement stands as the record. A roster of five was asserted here in July
2026 and is now evidence-backed for two, plausible for a third, and unsupported
for two. That is worth knowing before M8 builds a service around it.
