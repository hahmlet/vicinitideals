"""Readable code text, and the proof that it is still the extraction's words.

The order is PDF, readable authoritative text, cited encoding (Steph,
2026-10-23). These hold :func:`clean` to what it may do -- take off page
furniture, mend kerning and margin hyphens, join wrapped lines, cut one
sentence to a line -- and :func:`prove` and :func:`align` to catching
anything else.
"""

from __future__ import annotations

import re

from flats.provenance.readable import Readable, align, clean, prove, vocabulary

FURNITURE = re.compile(r"^\s*TOWN CODE page \d+$")
LONG = "The purpose of this zone is to provide housing for the people who live in the town and"


def _same(lines, got: Readable, **kw) -> None:
    assert prove(lines, got, **kw) == []


def test_kerning_is_mended_when_the_code_spells_the_word_whole() -> None:
    lines = ["T able 40-1 sets the yards."]
    got = clean(lines, words={"table": 5, "able": 1})
    assert got.lines == ("Table 40-1 sets the yards.",)
    _same(lines, got)
    # a word the code does not print whole is left as it was printed
    assert clean(["T able 40-1"], words={}).lines == ("T able 40-1",)


def test_a_margin_hyphen_goes_and_a_words_own_hyphen_stays() -> None:
    words = vocabulary(["subject subject subject single-family single-family"])
    lines = ["Every lot is sub-", "ject to these single-", "family standards."]
    got = clean(lines, words=words)
    assert got.lines == ("Every lot is subject to these single-family standards.",)
    assert got.sources == ((1, 2, 3),)
    _same(lines, got)


def test_furniture_goes_only_from_just_above_a_page_start() -> None:
    lines = ["One sentence here.", "TOWN CODE page 2", "Two sentence here.", "TOWN CODE page 9"]
    got = clean(lines, breaks=[3], furniture=FURNITURE)
    # line 2 sits above the page that starts on line 3; line 4 above no page
    assert got.removed == (2,)
    assert "TOWN CODE page 9" in got.lines
    _same(lines, got, breaks=[3], furniture=FURNITURE)
    # and removing a line that is not furniture fails the proof
    forged = Readable(("One sentence here.", "Two sentence here."), ((1,), (3,)), (2, 4))
    assert any("not page furniture" in p for p in prove(lines, forged, breaks=[3], furniture=FURNITURE))


def test_no_line_is_joined_across_a_page() -> None:
    lines = [LONG, "work nearby."]
    assert clean(lines).lines == (f"{LONG} work nearby.",)
    split_by_page = clean(lines, breaks=[2])
    assert split_by_page.lines == (LONG, "work nearby.")
    _same(lines, split_by_page, breaks=[2])


def test_one_sentence_to_a_line() -> None:
    lines = ["The first standard applies here. The second standard applies there."]
    got = clean(lines)
    assert got.lines == ("The first standard applies here.", "The second standard applies there.")
    assert got.sources == ((1,), (1,))
    # an abbreviation and a label are not the end of a sentence
    assert len(clean(["Setbacks are 5 ft. Minimum, as in Sec. 40.300 applies."]).lines) == 1


def test_a_run_in_heading_keeps_its_text() -> None:
    for line in ("(1) Food Stores. Food stores must be under 5,000 square feet.",
                 "Multi-Use Path (Trail). A path for walking and cycling."):
        assert clean([line]).lines == (line,)


def test_a_new_block_is_never_joined_to_the_line_above() -> None:
    lines = [LONG, "(a) The lot shall front a street."]
    assert len(clean(lines).lines) == 2


def test_prove_catches_a_changed_word() -> None:
    lines = ["Quadplexes are permitted outright."]
    forged = Readable(("Quadplexes are prohibited outright.",), ((1,),), ())
    assert prove(lines, forged)


def test_align_walks_a_stored_text_back_to_its_printed_lines() -> None:
    lines = ["TDC 40.100. Purpose.", LONG, "work nearby.", "TOWN CODE page 2", "Next page."]
    stored = ["TDC 40.100. Purpose.", f"{LONG} work nearby.", "Next page."]
    assert align(lines, stored, breaks=[5], furniture=FURNITURE) == ((1,), (2, 3), (5,))
    # the printed lines themselves align too: any cleaning of the same words does
    assert align(lines, [lines[0], lines[1], lines[2], lines[4]], breaks=[5], furniture=FURNITURE)
    # a word that is not the extraction's, or a word left out, does not
    assert align(lines, ["TDC 40.100. Purpose.", "Something else."], breaks=[5], furniture=FURNITURE) is None
    assert align(lines, stored[:2], breaks=[5], furniture=FURNITURE) is None


def test_nothing_joins_onto_an_empty_printed_line() -> None:
    """Durham 5.5: a lower-case line after a blank one was joined onto the
    blank paragraph, and its words printed as an empty line."""
    lines = ["5.5 Trees.", "", "and the trees shall be kept."]
    got = clean(lines)
    assert got.lines[-1] == "and the trees shall be kept."
    _same(lines, got)


def test_rows_of_a_space_set_table_are_never_joined() -> None:
    """Estacada 16.116.030 and Durham 9.10 print tables as columns set apart
    by spaces. A row runs to the margin because its columns do; joining on
    width made one line of a whole table."""
    lines = [
        "Major collector (standard)                2 (12' each)             600 ft             200 ft",
        "Minor collector (standard)                2 (11' each)             300 ft             100 ft",
    ]
    got = clean(lines)
    assert got.lines == tuple(lines)
    _same(lines, got)


def test_a_numbered_item_spaced_off_its_text_still_wraps() -> None:
    """Durham sets a subsection number apart from its text with spaces. That
    is not a table: the item still joins the line it wraps onto."""
    lines = [
        "10.3.5           As to the conditions of approval, the city may require that the applicant of",
        "Durham record the decision.",
    ]
    got = clean(lines)
    assert len(got.lines) == 1
    _same(lines, got)
