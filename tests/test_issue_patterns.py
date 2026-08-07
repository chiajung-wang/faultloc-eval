"""Pattern extraction from issue reports.

The measurement in `scripts/grep_reachability.py` runs one `git grep` per
pattern, and its conclusion decides whether rung 4's target is reachable at all.
So the extractor has to be deterministic, and it has to stay crude: an extractor
that collects ordinary English words would report every Instance as reachable,
because a grep for "the" matches everything.
"""

from __future__ import annotations

from faultloc.issue_patterns import (
    DOTTED_NAMES,
    ERROR_STRINGS,
    IDENTIFIERS,
    KINDS,
    TRACEBACK_PATHS,
    patterns,
)

REPORT = """\
Calling `Model.objects.get_or_create` on a proxy model raises:

Traceback (most recent call last):
  File "django/db/models/query.py", line 581, in get_or_create
    return self._create_object_from_params(kwargs, params)
TypeError: cannot convert 'NoneType' object to str

This worked in 1.11.3 but broke after the change to QuerySetManager.
"""


def test_finds_a_pattern_of_every_kind() -> None:
    found = patterns(REPORT)

    assert set(found) == set(KINDS)
    assert "cannot convert 'NoneType' object to str" in found[ERROR_STRINGS]
    assert "Model.objects.get_or_create" in found[DOTTED_NAMES]
    assert "get_or_create" in found[IDENTIFIERS]
    assert "QuerySetManager" in found[IDENTIFIERS]
    assert "django/db/models/query.py" in found[TRACEBACK_PATHS]


def test_pins_the_exact_order_of_every_kind() -> None:
    """The order is the contract, so the test states it rather than compare runs.

    Comparing `patterns(REPORT) == patterns(REPORT)` looked like a determinism
    test and was not one: a set is stable inside a single process, so that
    assertion passes under set-based deduplication. The cap applies after
    ordering, so a reordering changes *which* patterns get searched and moves the
    published number.
    """
    found = patterns(REPORT)

    assert found[ERROR_STRINGS] == ("cannot convert 'NoneType' object to str",)
    assert found[DOTTED_NAMES] == ("Model.objects.get_or_create", "self._create_object_from_params")
    # Snake case first, then camel case. `_create_object_from_params` is absent
    # on purpose: a leading underscore leaves no word boundary for the snake
    # pattern to start at, and the dotted kind already carries it.
    assert found[IDENTIFIERS] == ("get_or_create", "TypeError", "NoneType", "QuerySetManager")
    assert found[TRACEBACK_PATHS] == ("django/db/models/query.py",)


def test_keeps_first_occurrence_order() -> None:
    found = patterns("first_name then second_name then first_name again")

    assert found[IDENTIFIERS] == ("first_name", "second_name")


def test_caps_each_kind_independently() -> None:
    text = " ".join(f"name_{n}" for n in range(50))

    assert len(patterns(text, limit=3)[IDENTIFIERS]) == 3


def test_rejects_plain_english_words() -> None:
    """The whole point of requiring an underscore or an internal capital.

    Without this the extractor would collect "should" and "returns", and a grep
    for either matches most of the repository. Every Instance would look
    reachable and the measurement would say nothing.
    """
    found = patterns("The function should return the correct value when called")

    assert found[IDENTIFIERS] == ()
    assert found[DOTTED_NAMES] == ()


def test_rejects_version_numbers_as_dotted_names() -> None:
    """A grep for `1.11.3` finds changelogs, and never the file that must change.

    The dotted-name pattern does this by requiring each segment to start with a
    letter or an underscore. An explicit digit check also stood in the code, and
    breaking it changed no test, because a matched segment can never be all
    digits. The check is gone and this test now guards the regex that does the
    work.
    """
    found = patterns("This regressed between 1.11.3 and numpy.2 in the release")

    assert found[DOTTED_NAMES] == ()


def test_does_not_report_a_file_path_as_a_dotted_name() -> None:
    """`query.py` matches the dotted-name shape, and it is a path.

    Counting it under both kinds would credit dotted names with a reach that
    traceback paths produced, which is the attribution error the kinds exist to
    prevent.
    """
    found = patterns('File "django/db/models/query.py", line 581')

    assert "django/db/models/query.py" in found[TRACEBACK_PATHS]
    assert not any(name.endswith(".py") for name in found[DOTTED_NAMES])


def test_drops_a_message_too_short_to_locate_anything() -> None:
    assert patterns("ValueError: bad")[ERROR_STRINGS] == ()


def test_handles_a_report_with_nothing_searchable_in_it() -> None:
    found = patterns("It does not work. Please fix.")

    assert all(found[kind] == () for kind in KINDS)
