"""Tests for `.env` loading.

`.env.sample` documents two variables, so loading only one of them makes the
sample file a lie -- which is how HF_TOKEN came to be set and ignored.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faultloc.env import load_env


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text)
    return path


class TestLoadEnv:
    def test_loads_every_name_not_just_the_one_it_was_written_for(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("HF_TOKEN", raising=False)

        load_env(write(tmp_path, "OPENROUTER_API_KEY=sk-or-1\nHF_TOKEN=hf-2\n"))

        import os

        assert os.environ["OPENROUTER_API_KEY"] == "sk-or-1"
        assert os.environ["HF_TOKEN"] == "hf-2"

    def test_the_environment_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A key exported for one run must not be overridden by a stale file."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "from-shell")
        load_env(write(tmp_path, "OPENROUTER_API_KEY=from-file\n"))

        import os

        assert os.environ["OPENROUTER_API_KEY"] == "from-shell"

    def test_ignores_comments_blanks_and_quotes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HF_TOKEN", raising=False)
        load_env(write(tmp_path, "# a comment\n\n  HF_TOKEN = 'hf-quoted'  \n"))

        import os

        assert os.environ["HF_TOKEN"] == "hf-quoted"

    def test_a_missing_file_is_not_an_error(self, tmp_path: Path) -> None:
        """Rungs 1 through 2.6 need no keys at all, so no `.env` is the normal
        case for most of this project."""
        load_env(tmp_path / "absent")
