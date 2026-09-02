"""A number can be on the cited line and still be the wrong number.

Gresham Table 4.0130 G.1 prints ``16 ft. / 16 ft. / 16 ft. / None / None /
16 ft. / None`` across seven districts, and 16 had been encoded for all six of
the ones we hold. Every check in the corpus passed, because they all ask
whether the number appears on the quoted line and it appears three times. The
question nobody was asking is which column it appears in.

These tests cover the check that now asks it, and -- more importantly -- cover
the check *itself* going blind. A reader that stops finding rows reports a
clean corpus in exactly the same words as a corpus that is clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.columns import Survey, reach, survey

pytestmark = pytest.mark.unit

#: What the check could read on 2026-09-02. A floor, not a target: encoding
#: more tables should raise it. It dropping is the failure that matters -- it
#: means the reader stopped seeing rows, and a blind reader reports every
#: corpus clean.
#:
#: It has gone blind twice already, both times saying only "0 disagree". The
#: first version read 29 citations, missing Happy Valley entirely because its
#: layer keys R40 where its table prints R-40, and missing every table whose
#: header carries its own row-label cell. The second compared numbers only, so
#: "None" was invisible to it -- it would have walked past the misread it was
#: written for.
REACH = 581

#: Of what it reaches, how much it can actually compare. Well below ``REACH``
#: on purpose: a citation naming a footnote beside the cell is left alone
#: rather than judged against a value the corpus deliberately overrode, and an
#: exemption against a cell printing a figure is handed to the exemption ledger
#: rather than answered here.
JUDGED = 255


@pytest.fixture(scope="module")
def got() -> Survey:
    return survey()


def test_no_encoded_number_sits_in_another_districts_column(got: Survey) -> None:
    assert [str(row) for row in got.mismatches] == []


def test_no_number_is_encoded_where_the_cell_states_no_standard(got: Survey) -> None:
    assert [str(row) for row in got.vacancies] == []


def test_the_check_has_not_gone_blind(got: Survey) -> None:
    # The failure this guards is silence. Change an extractor so its tables no
    # longer print one cell per column, or rename a district so it stops
    # matching its own header, and every assertion above passes on nothing.
    assert got.reached >= REACH, (
        f"the column check now reads {got.reached} citations, down from {REACH}"
    )
    assert got.judged >= JUDGED, (
        f"the column check now judges {got.judged} of them, down from {JUDGED}"
    )


# --- the check against itself -------------------------------------------
#
# A four-line document and a five-line layer. Without these, a passing suite
# proves only that the corpus and a reader that reads nothing are
# indistinguishable.


def _corpus(
    tmp_path: Path,
    row: str,
    encoded: str,
    *,
    spec: str = "L3",
    tail: str = "",
) -> tuple[Path, Path]:
    docroot = tmp_path / "docs"
    configroot = tmp_path / "config"
    doc = docroot / "or" / "x" / "city" / "table.txt"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "  Table 1: Development Requirements\n"
        "                    A-1        B-2        C-3\n"
        f"{row}\n"
        f"{tail}\n",
        encoding="utf-8",
    )
    layer = configroot / "or" / "x" / "city.yaml"
    layer.parent.mkdir(parents=True)
    layer.write_text(
        "zones:\n"
        "  B-2:\n"
        "    min_frontage_ft:\n"
        f"      {encoded}\n"
        f'      quote: "or/x/city/table.txt#{spec}"\n',
        encoding="utf-8",
    )
    return configroot, docroot


TOWNHOUSE = "        Townhouse   16 ft.     None       16 ft."


def _corpus2(tmp_path, header, row, zone, encoded, *, spec="L3"):
    """A four-line document whose header the caller writes, and one value."""
    docroot = tmp_path / "docs"
    configroot = tmp_path / "config"
    doc = docroot / "or" / "x" / "city" / "table.txt"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        f"  Table 1: Development Requirements\n{header}\n{row}\n\n",
        encoding="utf-8",
    )
    layer = configroot / "or" / "x" / "city.yaml"
    layer.parent.mkdir(parents=True)
    layer.write_text(
        "zones:\n"
        f"  {zone}:\n"
        f"    {encoded}\n"
        f'      quote: "or/x/city/table.txt#{spec}"\n',
        encoding="utf-8",
    )
    return configroot, docroot


HEADER_TC = "     Standard      LDR-1     LDR-2     MDR       (TC)      HDR       (TC)"
ROW_TC = "     Lot width     70        60        50        50        N/A       20"


def test_a_header_that_repeats_a_label_is_still_read(tmp_path) -> None:
    # Troutdale heads six columns LDR-1, LDR-2, MDR, (TC), HDR, (TC): the
    # town-centre variants take their district's name from the line above.
    # Rejecting the whole header for the repeat left 64 citations unchecked;
    # the ambiguity is confined to the label that repeats.
    configroot, docroot = _corpus2(
        tmp_path, HEADER_TC, ROW_TC, "MDR", "min_lot_width_ft:\n      value: 99"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert len(found.mismatches) == 1
    assert found.mismatches[0].cell == "50"


def test_a_district_heading_two_columns_is_declined(tmp_path) -> None:
    # Which of the two it came from is the whole question, so the check does
    # not pick the first. Wood Village Table 220-3 heads four housing-type
    # columns "MR4 and MR2", and reading a value out of it would be a guess.
    configroot, docroot = _corpus2(
        tmp_path, HEADER_TC, ROW_TC, "(TC)", "min_lot_width_ft:\n      value: 99"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 0


def test_quoting_the_header_row_is_not_a_reach_past_the_table(tmp_path) -> None:
    # It is the opposite: quoting the header is how the corpus pins which of
    # six columns a number came from. Counting it as a line the check failed
    # to read left Troutdale and Happy Valley almost entirely unjudged.
    configroot, docroot = _corpus2(
        tmp_path,
        HEADER_TC,
        ROW_TC,
        "MDR",
        "min_lot_width_ft:\n      value: 99",
        spec="L2,L3",
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.judged == 1
    assert len(found.mismatches) == 1


def test_an_exemption_against_a_printed_figure_is_not_this_check(tmp_path) -> None:
    """It is ``flats.encode.exemptions``, which reads words rather than cells.

    Happy Valley's density row prints "4.4 du/net acre" and the encoded value
    is exempt, because the row is headed "Townhome maximum density" and a
    quadplex is not a townhouse. No count of columns can see that. What this
    check owns is the other direction -- a number encoded where the column
    states no standard -- because there the number is the thing that may have
    come from somewhere else.
    """
    configroot, docroot = _corpus2(
        tmp_path, HEADER_TC, ROW_TC, "MDR", "min_lot_width_ft:\n      exempt: true"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.judged == 0
    assert found.mismatches == ()


def test_zero_and_none_are_the_same_setback(tmp_path) -> None:
    # Portland writes 0 where Table 130-2 reads "none" for a street lot line,
    # and says so in the file. A setback is subtracted rather than tested, so
    # both readings let the building stand on the line and the number is the
    # one that stays in the arithmetic. The same cell under a minimum lot size
    # is a finding, which is what ``test_it_catches_a_number_taken_from_the_
    # column_next_door`` covers.
    row = "     Front yard    10        none      10        10        10        10"
    configroot, docroot = _corpus2(
        tmp_path, HEADER_TC, row, "LDR-2", "setback_front_ft:\n      value: 0"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.vacancies == ()


def test_it_catches_a_number_taken_from_the_column_next_door(tmp_path: Path) -> None:
    configroot, docroot = _corpus(tmp_path, TOWNHOUSE, "value: 16")
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.mismatches == ()
    assert len(found.vacancies) == 1
    bad = found.vacancies[0]
    assert (bad.zone, bad.encoded, bad.cell) == ("B-2", "16", "None")
    assert "its own column reads 'None'" in str(bad)


def test_it_passes_the_same_row_read_correctly(tmp_path: Path) -> None:
    configroot, docroot = _corpus(tmp_path, TOWNHOUSE, "exempt: true")
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.mismatches == ()
    assert found.vacancies == ()


def test_a_wrong_number_is_a_different_finding_from_an_absent_one(
    tmp_path: Path,
) -> None:
    configroot, docroot = _corpus(
        tmp_path, "        Townhouse   16 ft.     45 ft.     16 ft.", "value: 16"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert len(found.mismatches) == 1
    assert found.vacancies == ()
    assert found.mismatches[0].cell == "45 ft."


def test_a_row_with_dropped_blanks_is_skipped_rather_than_guessed(
    tmp_path: Path,
) -> None:
    # The row prints two cells where the header has three columns, because the
    # extractor dropped an empty one. Which one is gone decides what B-2's
    # number is, and nothing on the line says. Counting from the left here
    # would produce a confident finding out of a coin flip.
    configroot, docroot = _corpus(
        tmp_path, "        Townhouse   16 ft.     16 ft.", "value: 99"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 0
    assert found.mismatches == ()


def test_an_exemption_over_a_printed_figure_belongs_to_the_other_ledger(
    tmp_path: Path,
) -> None:
    """The dangerous direction is real, and this is not the reader for it.

    An exemption encoded where the code states a standard is the one mistake
    in this corpus that produces a false GREEN. But it cannot be caught by
    counting cells, because the innocent version looks identical: Happy
    Valley's density row prints "4.4 du/net acre" in R-40's own column and the
    encoded value is exempt, correctly, because the row is headed "Townhome
    maximum density" and a quadplex is not a townhouse.

    :mod:`flats.encode.exemptions` reads the words instead, and calls both of
    them ``numeric`` -- a citation a reviewer cannot read the exemption out
    of. All seven Happy Valley rows are in its ledger, its count is pinned at
    37 by ``test_exemptions``, and that line of the table is one of its own
    test cases. Answering here as well would mean either duplicating the
    finding or, worse, silencing it with a list of exceptions.
    """
    configroot, docroot = _corpus(
        tmp_path, "        Townhouse   16 ft.     0 ft.      16 ft.", "exempt: true"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.judged == 0
    assert found.mismatches == ()


def test_a_citation_that_reaches_past_the_table_is_left_alone(
    tmp_path: Path,
) -> None:
    """The second line named is usually where the real number is.

    Gresham CC's maximum front setback is "10 feet" in the cell and five feet
    by note 3c on every street class this screen cannot read; Happy Valley's
    lot width is "100 feet" in the cell and exempt by note 2 four hundred lines
    down. Both encodings are right and neither matches its own cell. Judging
    them against the cell reports the footnote as a misreading, so a citation
    that quotes the override is not judged at all -- and what stays judged is
    the citation naming the row and nothing else, which is the shape the
    townhouse frontage misread had.
    """
    configroot, docroot = _corpus(
        tmp_path,
        TOWNHOUSE,
        "value: 5",
        spec="L3,L4",
        tail="        1. Note: five feet where the street is a Collector.",
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.mismatches == ()
    assert found.vacancies == ()


def test_a_wrapped_cell_is_not_judged_on_the_line_it_starts(tmp_path: Path) -> None:
    # Portland prints a density as "1 unit per" / "1,450 sq. ft. of" / "site
    # area" down three lines. The figure is not on the row the citation names,
    # and reading the leading "1" would report every density in the city wrong.
    configroot, docroot = _corpus(
        tmp_path,
        "        Density     1 unit per 2,500   1 unit per     1 unit per 900",
        "value: 1450",
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.reached == 1
    assert found.judged == 0
    assert found.mismatches == ()


def test_a_zone_whose_key_has_a_space_is_its_own_zone(tmp_path: Path) -> None:
    """And the silent half: its fields were being read as the zone above it.

    Wood Village keys four zones ``LR 12``, ``LR 7.5``, ``MR 2`` and ``MR 4``.
    A pattern that stopped at the space did not skip them -- it kept attributing
    their values to whichever zone was declared before, so each was checked
    against another district's columns, found no cell, and passed in silence.
    """
    docroot = tmp_path / "docs"
    configroot = tmp_path / "config"
    doc = docroot / "or" / "x" / "city" / "table.txt"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "  Table 1: Development Requirements\n"
        "     Standard      LR 12     LR 7.5\n"
        "     Lot width     80 ft     60 ft\n\n",
        encoding="utf-8",
    )
    layer = configroot / "or" / "x" / "city.yaml"
    layer.parent.mkdir(parents=True)
    layer.write_text(
        "zones:\n"
        "  TC:\n"
        "    max_height_ft:\n"
        "      value: 35\n"
        '      cite: elsewhere\n'
        "  LR 7.5:\n"
        "    min_lot_width_ft:\n"
        "      value: 80\n"
        '      quote: "or/x/city/table.txt#L3"\n',
        encoding="utf-8",
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert len(found.mismatches) == 1
    assert found.mismatches[0].zone == "LR 7.5"
    assert found.mismatches[0].cell == "60 ft"


def test_a_quoted_caption_is_context_like_a_header(tmp_path: Path) -> None:
    # Wood Village quotes "Table 220-3. Housing Types Allowed" beside the row,
    # the way other cities quote the header. Counting it as a line the check
    # failed to read put the whole city in the reaches-past-the-table bucket.
    configroot, docroot = _corpus(tmp_path, TOWNHOUSE, "exempt: true", spec="L1,L3")
    found = survey(configroot=configroot, docroot=docroot)
    assert found.judged == 1
    assert found.mismatches == ()
    assert found.vacancies == ()


def test_a_decimal_without_its_leading_zero_is_still_that_number(
    tmp_path: Path,
) -> None:
    # Wood Village states LR12's density floor as ".9 (25%)". Read as a whole
    # number that is nine, and the file's correct 0.9 becomes a finding.
    configroot, docroot = _corpus(
        tmp_path, "        Density     .9 (25%)   4.6 (80%)  8.7", "value: 4.6"
    )
    found = survey(configroot=configroot, docroot=docroot)
    assert found.judged == 1
    assert found.mismatches == ()


def test_a_quote_inside_measured_on_is_not_the_values_citation(
    tmp_path: Path,
) -> None:
    """It cites the denominator, which is a different document and a different
    question.

    Happy Valley's maximum density is measured per NET acre, and the block that
    says what a net acre is carries its own quote -- into a land-division
    chapter, four sections away from the density table. Read as the density's
    own citation, a number gets compared against a definition. 103 citations in
    the corpus sit inside such a block, and none of them reaches a dimensional
    table today, which is exactly why this needs a test rather than a count:
    the day one does, it would be a finding invented out of a parser.
    """
    docroot = tmp_path / "docs"
    configroot = tmp_path / "config"
    doc = docroot / "or" / "x" / "city" / "table.txt"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "  Table 1: Development Requirements\n"
        "                    A-1        B-2        C-3\n"
        "        Density     12         18         24\n\n",
        encoding="utf-8",
    )
    layer = configroot / "or" / "x" / "city.yaml"
    layer.parent.mkdir(parents=True)
    layer.write_text(
        "zones:\n"
        "  B-2:\n"
        "    max_density_du_per_acre:\n"
        "      value: 18\n"
        '      quote: "or/x/city/table.txt#L3"\n'
        "      measured_on:\n"
        "        fact: net_developable_area\n"
        '        quote: "or/x/city/table.txt#L3"\n',
        encoding="utf-8",
    )
    found = survey(configroot=configroot, docroot=docroot)
    # One citation, not two: the nested quote is the denominator's.
    assert found.reached == 1
    assert found.judged == 1
    assert found.mismatches == ()


def test_reach_is_the_same_number_the_survey_reports(got: Survey) -> None:
    assert reach() == got.reached
