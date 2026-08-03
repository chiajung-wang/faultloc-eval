# 02 — Load SWE-bench Verified into Instances

Status: done

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

## Comments

**Closed 2026-08-03.** Real run against the pinned revision: **500 total, 490 kept, 10 dropped, all from the >3-file cap.** Identical to the throwaway script written during issue 01 — two independent implementations agreeing on real data.

Commits on `m1-bm25-baseline`:

| Commit | What |
|---|---|
| `fbe8d96` | `test: add real gold patch fixtures` |
| `b87a572` | `feat: parse changed files from a gold patch` |
| `e10d5e2` | `feat: add the Instance model` |
| `8181d9c` | `feat: load the Verified Set into instances` |

**Split into three modules by what can fail.** `patches.py` reads a diff and has no opinions — it reports `setup.cfg` rather than skipping it, so a parsing bug and a classification bug fail different tests. `models.py` holds `Instance`. `verified.py` has exactly one impure function, `fetch_rows`; everything above it is pure and tested with no network.

**The revision pin is tested by asserting the request, not the response.** `load_verified_set` takes its row source as an argument, and a spy captures the call. A dataset that silently updates cannot be caught by inspecting what came back — wrong data looks like data. The only observable is what was asked for.

**`base_commit` must be a full 40-character lowercase hex SHA.** An abbreviated SHA still resolves against a local clone, so it fails silently: the repository state would simply not be the one the issue was filed against, and every file read afterwards would be wrong with nothing raising.

**`hints_text` exclusion is pinned by a test**, not just by omission. Fixture rows carry `hints_text: "SECRET_HINT ..."` and the test asserts that string appears nowhere in the serialised Instance — so the exclusion survives `Instance` gaining a field later.

Four real gold patches are committed under `tests/fixtures/patches/`, chosen after counting the shapes that occur across all 500: **1 patch adds a new file, 0 delete, 0 rename.** Rename and space-in-path handling are still tested synthetically, for M6 where Fresh Set PRs will be less tame.

Caveat on the caching criterion: warm runs do not re-download, but `datasets` still makes a Hub metadata request. Fully offline needs `HF_DATASETS_OFFLINE=1`.
