"""Putting a PDF's letter-spaced text back together.

Municode serves Oregon City's Title 17 as a scanned PDF whose OCR text is
letter-spaced: ten thousand square feet arrives as "1 0 , 000 squ are f eet".
Nineteen thousand lines of it, holding the dimensional standards of five zones.

The tests below are mostly about what the repair refuses to do. Joining digits
across a space is exactly what a table of single-digit cells looks like, and a
repair that invents a standard is worse than a document nobody can read.
"""

from __future__ import annotations

import pytest

from flats.encode.despace import repair, repair_text

pytestmark = pytest.mark.unit


def test_a_number_split_by_spaces_is_one_number() -> None:
    assert repair("1 0 , 000 square feet") == "10,000 square feet"


def test_a_percentage_split_by_a_space_is_one_number() -> None:
    assert repair("Maximum coverage 4 0%") == "Maximum coverage 40%"


def test_a_word_is_rejoined_only_into_a_word_this_system_reads() -> None:
    assert repair("1 0 , 000 squ are f eet") == "10,000 square feet"
    assert repair("Maxim um h eight: All") == "Maximum height: All"


def test_a_join_that_spells_nothing_is_left_alone() -> None:
    # "tac h e d" is the tail of "detached", broken across a line break. No
    # vocabulary entry spells it, so it stays broken rather than becoming a
    # word nobody wrote.
    assert repair("tac h e d , duplex") == "tac h e d , duplex"


def test_two_words_are_not_run_together_because_the_result_is_a_term() -> None:
    # Nothing here is short enough to be a fragment, so "single family" stays
    # two words even though joining them spells one.
    assert repair("single family detached") == "single family detached"


def test_clean_text_is_returned_unchanged() -> None:
    clean = "Minimum lot size 10,000 square feet, except 45% coverage."

    assert repair(clean) == clean


def test_the_repair_is_idempotent() -> None:
    once = repair("1 0 , 000 squ are f eet")

    assert repair(once) == once


def test_the_line_count_never_changes() -> None:
    # A quote is a line number into the stored document. A repair that moved
    # lines would re-point every citation in the jurisdiction.
    text = "a b\n1 0 , 000\n\nlast\n"

    assert repair_text(text).count("\n") == text.count("\n")
