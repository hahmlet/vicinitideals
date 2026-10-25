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


def test_two_table_rows_stay_apart_when_the_second_label_is_lower_case() -> None:
    """Troutdale 3.230 labels its rows in lower case ("when abutting a park").
    A lower-case line read as the rest of the row above, so two rows of the
    setback table printed as one line under the wrong row's numbers."""
    lines = [
        "when abutting a park (regardless of zoning district)            0                    0                   10",
        "when abutting a non-residential zoning district                   0                    0                    0",
    ]
    got = clean(lines)
    assert got.lines == tuple(lines)
    _same(lines, got)
    # a lower-case line under a row that is not itself a row still joins it
    wrapped = ["Front yard                 20                  20 to the front", "porch of a unit."]
    assert len(clean(wrapped).lines) == 1


def test_a_running_head_goes_only_from_a_pages_first_line() -> None:
    """Troutdale prints its running header at the top of the page, so the
    extraction puts it on the page's own first line, not in the band above."""
    head = re.compile(r"^\s*TROUTDALE DEVELOPMENT CODE\s*$")
    lines = ["One sentence here.", "TROUTDALE DEVELOPMENT CODE", "Two sentence here.",
             "TROUTDALE DEVELOPMENT CODE"]
    got = clean(lines, breaks=[2], head=head)
    assert got.removed == (2,)
    assert "TROUTDALE DEVELOPMENT CODE" in got.lines
    _same(lines, got, breaks=[2], head=head)


def test_a_web_prints_note_marker_alone_opens_a_block() -> None:
    """Fairview's web print sets a footnote marker "[2]" on a line of its own;
    joined onto the cell above, it read as part of that cell's number."""
    lines = [LONG, "[2]", "work nearby."]
    got = clean(lines)
    assert got.lines[0] == LONG
    assert "[2]" in got.lines[1]


def test_sub_row_labels_stay_on_their_own_lines() -> None:
    """Troutdale 3.230 sets labels the rows below share ("without alley
    access", "from street") on lines of their own between rows of values.
    Read as the rest of the row above, "from street" printed after the 20s of
    the garage-door row, and the next row joined onto it."""
    lines = [
        "   Front yard:",
        "        without alley access",
        "            to the garage door of units with a driveway                                      20                  20",
        "           from street",
        "            to the front façade of a residential unit                        15                  15",
        "            to the front porch of a residential unit                          10                  10",
    ]
    got = clean(lines)
    assert got.lines == tuple(line.strip() for line in lines)
    _same(lines, got)
    # the last cell of a row still takes the words that wrap under it
    fee = [
        "TYPE I LAND DIVISION                                                    $15.00",
        "                                                   per lot plus actual City Costs",
    ]
    assert clean(fee).lines == ("TYPE I LAND DIVISION                                                    $15.00 per lot plus actual City Costs",)
    # and prose spaced once in the middle is not a row of values (Durham 3.7)
    prose = [
        "3.7.1.4.2         for 3 to 49 dwelling units, 1 two-way at least 30 feet wide or 2 one               -way each at",
        "least 20 feet wide, 5 foot sidewalk required on one side, no curb required;",
    ]
    assert len(clean(prose).lines) == 1


def test_a_web_prints_cells_never_join_on_width() -> None:
    """A web print has no margin: each line is a whole paragraph or a whole
    table cell, however long. Joined because the cell above ran past 80
    characters, Fairview's "10 ft" and West Linn's "CU" printed as the last
    words of the standard beside them, and Gladstone's notes 1-3 as one."""
    cell = "The ground floor commercial space must occupy a minimum of 50 percent of the width of the total street frontage."
    lines = [cell, "10 ft", LONG, "CU", LONG + " to provide", "access to the street."]
    got = clean(lines, margin=False)
    assert got.lines == (cell, "10 ft", LONG, "CU", LONG + " to provide access to the street.")
    _same(lines, got)
    # a PDF line that ran to the margin still carries on
    assert clean([LONG, "CU and more"]).lines == (LONG + " CU and more",)
    # an enumerator alone on its line opens a block in a web print only: in a
    # PDF a sentence can end on a number ("a central angle of" / "14.")
    alone = ["inundation of normally dry land areas from:", "a.", "Overflow of waters."]
    assert clean(alone, margin=False).lines[1] == "a."
    angle = ["THENCE following the arc of a 477.50 foot radius curve to the right, through a central angle of", "14."]
    assert len(clean(angle).lines) == 1


def test_a_lower_case_roman_item_opens_a_block() -> None:
    """Troutdale and King City number items "i.", "ii.", "iii."; "ii." read
    as the end of the item above, so each item began on the line before."""
    lines = ["i.      Face the street; and", "ii.      Be at an angle of up to 45 degrees."]
    got = clean(lines)
    assert got.lines == ("i.      Face the street; and", "ii.      Be at an angle of up to 45 degrees.")
    _same(lines, got)
