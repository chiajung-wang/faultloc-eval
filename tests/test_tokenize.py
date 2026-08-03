"""Tests for tokenisation.

The query and the document must agree on what a word is, or the strongest
signal in the dataset -- a bug report quoting a real identifier -- never scores
at all.
"""

from __future__ import annotations

import pytest

from faultloc.rungs.tokenize import tokenize, tokenize_path


class TestSplitting:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("separability_matrix", {"separability", "matrix", "separability_matrix"}),
            ("HttpRequest", {"http", "request", "httprequest"}),
            ("django.db.models", {"django", "db", "models"}),
            ("astropy/modeling/separable.py", {"astropy", "modeling", "separable", "py"}),
        ],
    )
    def test_identifiers_split_into_parts(self, text: str, expected: set[str]) -> None:
        assert expected <= set(tokenize(text))

    def test_acronyms_stay_whole(self) -> None:
        """`HTTPServer` is HTTP + Server, not H, T, T, P, Server."""
        assert "http" in tokenize("HTTPServer")
        assert "server" in tokenize("HTTPServer")

    def test_compound_is_kept_alongside_its_parts(self) -> None:
        """The whole identifier is far rarer than either part.

        BM25 weights rare terms heavily, so keeping the compound is what makes
        an exact quote of an identifier outrank a coincidental part match.
        """
        tokens = tokenize("get_user_name")
        assert tokens.count("get_user_name") == 1
        assert {"get", "user", "name"} <= set(tokens)

    def test_single_characters_are_dropped(self) -> None:
        """Loop variables appear everywhere and carry no signal."""
        assert tokenize("for i in x") == ["for", "in"]

    def test_is_lowercased(self) -> None:
        assert tokenize("Foo") == tokenize("foo") == ["foo"]

    def test_empty_text_yields_nothing(self) -> None:
        assert tokenize("") == []


class TestQueryMatchesCode:
    def test_prose_matches_an_identifier(self) -> None:
        """The case the whole module exists for."""
        report = set(tokenize("separability matrix is wrong for nested models"))
        code = set(tokenize("def separability_matrix(transform):"))
        assert report & code >= {"separability", "matrix"}

    def test_exact_quote_matches_the_compound(self) -> None:
        report = set(tokenize("`separability_matrix` crashes"))
        code = set(tokenize("def separability_matrix(t):"))
        assert "separability_matrix" in report & code


class TestTokenizePath:
    def test_keeps_the_whole_path_as_a_token(self) -> None:
        """Tracebacks quote paths verbatim; an exact match should outrank a
        coincidental directory-name match."""
        tokens = tokenize_path("astropy/modeling/separable.py")
        assert "astropy/modeling/separable.py" in tokens

    def test_also_yields_the_parts(self) -> None:
        assert {"astropy", "modeling", "separable"} <= set(
            tokenize_path("astropy/modeling/separable.py")
        )
