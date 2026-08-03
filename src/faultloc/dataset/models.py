"""The evaluable unit shared by every rung and both datasets.

See `CONTEXT.md` for the domain definitions. `Instance` is deliberately
source-agnostic: the Verified Set and the Fresh Set (M6) produce the same shape,
so every rung and the scorer stay unaware of which dataset they are running on.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

SHA1_LENGTH = 40


class Instance(BaseModel):
    """One issue report plus the repository state it was filed against.

    Frozen: instances are loaded once and scored many times, and a rung that
    could mutate its input would make results depend on evaluation order.
    """

    model_config = ConfigDict(frozen=True)

    instance_id: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    base_commit: str
    issue_text: str
    ground_truth_files: tuple[str, ...] = Field(min_length=1)

    @field_validator("base_commit")
    @classmethod
    def _must_be_a_full_sha(cls, value: str) -> str:
        """Reject abbreviated or malformed SHAs at the boundary.

        Every file read happens at this commit. A short SHA would still resolve
        against a local clone while silently failing to pin the repository state
        the issue was filed against.
        """
        if len(value) != SHA1_LENGTH or not all(c in "0123456789abcdef" for c in value):
            raise ValueError(f"base_commit must be a 40-character hex SHA, got {value!r}")
        return value
