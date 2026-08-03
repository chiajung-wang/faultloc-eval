# ADR-0002: The agent gets read-only tools; no code execution

**Status:** Accepted · 2026-07-31

## Context

A localization agent could be given the ability to run tests or execute snippets inside a sandbox. Reproducing a failure is genuinely strong evidence about where a bug lives.

Doing so requires a working environment per instance: correct Python version, correct pinned dependencies, correct build steps — across roughly twelve repositories at five hundred distinct commits.

## Decision

The agent gets exactly five read-only tools:

`search_code` · `semantic_search` · `read_file(path, start, end)` · `file_outline` · `find_definition`

No test execution. No sandboxed interpreter. No container per instance.

## Rationale

The question being answered is *"which file is wrong"*, not *"does this fix work"*. Execution is evidence for the second question, and only indirectly for the first.

The cost is not incidental. Building and maintaining per-instance environments is the single most common reason projects in this space stall. A direct predecessor of this project — `~/dev/archives/triage-rca-agent` — chose a Docker sandbox for test execution in its ADR-0003 and was abandoned one day later, at three commits total, with no working output.

Five tools is also a deliberate ceiling. Larger tool surfaces degrade selection quality, inflate token cost per step, and make failures harder to attribute.

## Consequences

- The project runs on any machine with Python and a network connection. No environment matrix to maintain.
- `find_definition` is implemented with the standard-library `ast` module rather than a language server — no process to supervise.
- Python-only, which is acceptable: the evaluated benchmark is Python.
- Some instances are genuinely unsolvable without running code. Those become part of the measured ceiling and should be characterised in the failure taxonomy, not engineered around.

## Alternatives rejected

- **Read-only plus sandbox execution** — strongest signal, but reintroduces exactly the cost that killed the predecessor
- **Search and read only (two tools)** — too thin; the agent cannot traverse structure and collapses into a slower version of rung 3
- **Execution plus patch application** — that is patch generation, out of scope, and a space where the underlying model rather than this system's engineering decides the result
