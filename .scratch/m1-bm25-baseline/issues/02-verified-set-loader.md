# 02 — Load SWE-bench Verified into Instances

Status: ready-for-agent

## Context

The Verified Set is 500 human-validated instances across 12 Python repos, loaded via the `datasets` library. See ADR-0006 for why this dataset and why the revision is pinned.

Pinned source — these values go in code as constants, not as call-site literals:

| Field | Value |
|---|---|
| ID | `princeton-nlp/SWE-bench_Verified` |
| Config | `default` |
| Split | `test` |
| Revision | `c104f840cc67f8b6eec6f759ebc8b2693d585d4a` |

```python
load_dataset(
    "princeton-nlp/SWE-bench_Verified",
    split="test",
    revision="c104f840cc67f8b6eec6f759ebc8b2693d585d4a",
)
```

Record fields, and how they map onto `Instance`:

| Dataset field | Use |
|---|---|
| `instance_id` | → `instance_id` |
| `repo` | → `repo` |
| `base_commit` | → `base_commit` |
| `problem_statement` | → `issue_text` |
| `patch` | gold patch → changed files → Instance Filter → `ground_truth_files` |
| `test_patch` | **unused** — test files are not ground truth (ADR-0001) |
| `hints_text` | **must not be loaded** — see notes |
| `created_at` | keep; needed to state the set's date range and for the contamination argument |
| `version`, `environment_setup_commit`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `difficulty` | unused — this project does not execute code (ADR-0002) |

The Ground-Truth File Set must be derived from the patch's changed files, then passed through the Instance Filter from issue 01.

## Acceptance criteria

- An `Instance` model (pydantic) with `instance_id`, `repo`, `base_commit`, `issue_text`, `ground_truth_files`
- A loader that yields filtered Instances plus a count of drops per `DropReason`
- Dataset ID, split, and revision are module constants; a test asserts the pinned revision is what gets requested
- Changed-file extraction from the gold patch is unit-tested against at least one real patch fixture committed to the repo
- Loader is cached to disk so repeated runs don't re-download

## Notes

Do not silently discard dropped instances — the counts are the Filter Rate that ADR-0001 requires be published.

`hints_text` holds the issue's comment thread, which frequently names the offending file or quotes the fix. Loading it would leak the answer into the input. It is excluded at the loader, not at the prompt, so no downstream component can reach it by accident.

Instances are Django-heavy (231 of 500). The loader should preserve `repo` so per-repo breakdowns are possible — ADR-0006 requires them.
