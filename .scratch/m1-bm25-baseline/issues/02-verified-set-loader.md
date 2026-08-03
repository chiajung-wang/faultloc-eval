# 02 — Load SWE-bench Verified into Instances

Status: ready-for-agent

## Context

The Verified Set is 500 human-validated instances, available via the `datasets` library. Each record carries the repo, base commit, issue text, and the gold patch.

The Ground-Truth File Set must be derived from the patch's changed files, then passed through the Instance Filter from issue 01.

## Acceptance criteria

- An `Instance` model (pydantic) with `instance_id`, `repo`, `base_commit`, `issue_text`, `ground_truth_files`
- A loader that yields filtered Instances plus a count of drops per `DropReason`
- Changed-file extraction from the gold patch is unit-tested against at least one real patch fixture committed to the repo
- Loader is cached to disk so repeated runs don't re-download

## Notes

Do not silently discard dropped instances — the counts are the Filter Rate that ADR-0001 requires be published.
