"""Tests for the Instance model.

Validation happens at construction, which makes this the last point where a
malformed instance can be stopped. Everything downstream assumes these
guarantees hold.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from faultloc.dataset.models import Instance

SHA = "0" * 40


def instance(**overrides: object) -> Instance:
    fields: dict[str, object] = {
        "instance_id": "x",
        "repo": "a/b",
        "base_commit": SHA,
        "issue_text": "t",
        "ground_truth_files": ("a.py",),
    }
    return Instance(**(fields | overrides))  # type: ignore[arg-type]


class TestBaseCommitValidation:
    def test_accepts_a_full_sha(self) -> None:
        assert instance(base_commit="0b0998dc151feb77068e2387c34cc50ef6b356ae")

    def test_rejects_an_abbreviated_sha(self) -> None:
        """Every file read happens at this commit.

        A short SHA still resolves against a local clone, so it fails silently
        rather than loudly -- the repository state would simply not be the one
        the issue was filed against, and every read after it would be wrong
        with nothing raising.
        """
        with pytest.raises(ValidationError):
            instance(base_commit="0b0998dc")

    def test_rejects_a_non_hex_sha(self) -> None:
        with pytest.raises(ValidationError):
            instance(base_commit="z" * 40)

    def test_rejects_an_uppercase_sha(self) -> None:
        """Git prints lowercase; an uppercase SHA means it came from elsewhere."""
        with pytest.raises(ValidationError):
            instance(base_commit="0B0998DC151FEB77068E2387C34CC50EF6B356AE")


class TestRequiredFields:
    def test_rejects_an_empty_ground_truth_set(self) -> None:
        """A kept instance always has at least one file, by ADR-0001."""
        with pytest.raises(ValidationError):
            instance(ground_truth_files=())

    def test_rejects_an_empty_instance_id(self) -> None:
        with pytest.raises(ValidationError):
            instance(instance_id="")

    def test_rejects_an_empty_repo(self) -> None:
        with pytest.raises(ValidationError):
            instance(repo="")


class TestImmutability:
    def test_is_frozen(self) -> None:
        """Instances are loaded once and scored many times.

        A rung that could mutate its input would make results depend on
        evaluation order.
        """
        built = instance()
        with pytest.raises(ValidationError):
            built.repo = "other/repo"

    def test_ground_truth_files_is_a_tuple(self) -> None:
        """A list would be mutable in place, past the frozen check."""
        assert isinstance(instance().ground_truth_files, tuple)
