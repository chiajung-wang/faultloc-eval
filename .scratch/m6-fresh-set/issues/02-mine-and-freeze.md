# 02 — `faultloc mine`: GitHub to a frozen, content-hashed Fresh Set

Status: ready-for-agent

## Parent

[M6 PRD](../PRD.md)

## What to build

A command that mines post-cutoff Instances from GitHub and writes one frozen, committed artifact.

Source: merged pull requests carrying `linked:issue`, closed on or after **2026-05-01**, across the 12 Verified repos. A probe counted **398 candidates** in that window. `django/django` yields 1, because it runs its issue tracker on Trac. That is expected and it is not a bug to fix here.

Four structural criteria, all mechanical, all published:

1. The pull request closes the issue through GitHub's own link.
2. Exactly one pull request closes that issue.
3. The issue opens before the pull request.
4. The issue body clears a minimum length.

Then the Instance Filter derives the Ground-Truth File Set from the pull request's file list. A 56-PR sample kept **75%**, which puts the set near **295 Instances**.

`base_commit` comes from the pull request's `base.sha`, which lives in the main repository rather than a fork. `RepoStore` raises `CommitUnavailableError` when a clone lacks a commit, so a fork-only SHA would fail loudly rather than silently.

The artifact holds full issue text, not identifiers. GitHub issue text can be edited or deleted, and a published number must not stop reproducing with nothing in the repository showing why. Its **content hash is the Fresh Set's revision**.

The command reports the Filter Rate per drop reason and the count rejected by each structural criterion.

## Acceptance criteria

- [ ] `faultloc mine` writes one JSON artifact of frozen Instances, committed to the repository
- [ ] Every Instance satisfies the four structural criteria and the Instance Filter
- [ ] `base_commit` resolves in the existing bare clone for every Instance
- [ ] The artifact's content hash is computed and recorded
- [ ] The command reports counts rejected per structural criterion and per filter drop reason
- [ ] The GitHub search API is throttled: it allows 30 requests per minute and this repository hit that limit during planning
- [ ] Mining is resumable, because a rate-limit stop must not discard completed work
- [ ] Parsing and criteria logic is unit-tested against fixed API payloads, with no network
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

The set is a control that gets read once, so it carries **no dev/test split**. See [ADR-0010](../../../docs/adr/0010-fresh-set-mining.md).

Target size is 150–300 and it is **not** the binding constraint. The power calculation shows a Fresh Set of 1000 moves the detectable effect by only 1pp. Do not spend effort widening the yield.

## Blocked by

- [01 — Instance Filter: two rules for raw input](01-filter-rules-raw-input.md)
