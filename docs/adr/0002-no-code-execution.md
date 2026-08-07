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
