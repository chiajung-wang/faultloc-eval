# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |
| —                          | `done`               | Implemented, verified, and committed     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

`done` is local to this repo — the five canonical roles cover triage and refusal but have no terminal state, so nothing marked the difference between an issue waiting to be picked up and one already shipped. An agent that pulls the next `ready-for-agent` issue would otherwise re-implement finished work.

A `done` issue records its closing commits under `## Comments`, so the file stays as the specification of what was built rather than becoming a stale to-do.

## How labels are applied here

This repo uses the local-markdown issue tracker (see `issue-tracker.md`), so there is no label API. Write the label string on the `Status:` line near the top of the issue file instead:

```markdown
# 03 — Parse the config file

Status: ready-for-agent
```

Changing triage state means editing that line.

Edit the right-hand column of the table above to match whatever vocabulary you actually use.
