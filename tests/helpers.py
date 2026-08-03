"""Small builders shared by tests that need an Instance but do not test one."""

from __future__ import annotations

from faultloc.dataset.models import Instance

SHA = "0" * 40


def make_instance(
    instance_id: str = "i-1",
    repo: str = "a/b",
    *truth: str,
) -> Instance:
    return Instance(
        instance_id=instance_id,
        repo=repo,
        base_commit=SHA,
        issue_text="t",
        ground_truth_files=truth or ("pkg/core.py",),
    )
