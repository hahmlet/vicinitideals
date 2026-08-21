"""A footnote we never pulled can only be caught by someone reading the page.

The census exists because that is not a plan. These tests pin the shapes real
codifiers use, the two directions reconciliation has to run in, and the
narrowness that keeps a marker rule from inventing hundreds of markers out of
prose -- each of which was a live defect at some point in the module's first
hour.
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import census, survey

pytestmark = pytest.mark.unit


# --- the shapes a notes block is written in ----------------------------


def test_a_headed_block_with_the_number_on_the_text_line() -> None:
    text = "\n".join(
        [
            "Standard          R-5",
            "Building height   45 feet2",
            "",
            "NOTES:",
            "1 Density is calculated under Section 16.63.020.",
            "2 The maximum is 45 feet at the front elevation.",
            "",
            "(Ord. 389 § 1, 2009)",
        ]
    )
    seen = census(text, doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2"]
    assert seen.bodies[1].text.startswith("The maximum is 45 feet")
    # Note 1 has no marker anywhere above it, which is a finding, not a shrug.
    assert [b.mark for b in seen.unmarked] == ["1"]
    assert not seen.reconciled


def test_the_number_on_its_own_line_is_still_a_note() -> None:
    """Happy Valley's largest block, as an HTML table hands it over: every
    cell its own line, so the number and its text are never on one.

    This shape was invisible at first, and what it hid was footnote 11 -- a
    corner lot's front setback dropping to eight feet on a local street. A
    qualifier that changes the answer, sitting in a block the reader skipped.
    """
    text = "\n".join(
        [
            "Building height (maximum)",
            "45 feet8",
            "",
            "NOTES:",
            "NOTES:",
            "8",
            "Maximum height is 45 feet at the front elevation.",
            "11",
            "On a corner lot, one of the required front yard setbacks may be",
            "reduced to eight feet when abutting a local or connector street.",
            "",
            "D.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["8", "11"]
    assert "eight feet" in seen.bodies[1].text
    assert "local or connector street" in seen.bodies[1].text


def test_a_bracket_run_needs_no_heading() -> None:
    text = "\n".join(
        [
            "Maximum height   30 ft. [3]",
            "",
            "[3] Additional height may be allowed. See 33.110.265.F.",
            "[4] Applies to the R2 zone only.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["3", "4"]
    assert [m.mark for m in seen.markers] == ["3"]
    assert [b.mark for b in seen.unmarked] == ["4"]


def test_a_heading_over_prose_is_not_a_block() -> None:
    """"Notes:" introduces commentary as often as it introduces footnotes, and
    a block that swallows the paragraph under it invents bodies."""
    text = "\n".join(
        [
            "NOTES:",
            "The standards in this table are minimums unless stated otherwise.",
            "",
        ]
    )
    assert census(text, doc="d.txt").blocks == ()


# --- where a marker is allowed to be -----------------------------------


def test_a_marker_belongs_to_the_block_below_it_not_the_one_above() -> None:
    """Numbering restarts under every table, so reconciliation is scoped to
    the run of lines a block governs. Reconciling per document would let the
    second table's note 1 answer the first table's marker 1 and report
    nothing -- which is the direction that hides gaps."""
    text = "\n".join(
        [
            "Lot size    2,000 sq. ft.1",
            "NOTES:",
            "1 The first table's note.",
            "",
            "Height      45 feet2",
            "NOTES:",
            "1 The second table's note.",
            "",
        ]
    )
    seen = census(text, doc="d.txt")
    assert len(seen.blocks) == 2
    # The marker under the first block is answered by the second block's
    # numbering, and 2 is not in it.
    assert [m.mark for m in seen.unbodied] == ["2"]
    assert [b.mark for b in seen.unmarked] == ["1"]


def test_a_marker_below_every_block_has_no_block_at_all() -> None:
    text = "\n".join(
        [
            "NOTES:",
            "1 A note.",
            "",
            "Height   45 feet1",
        ]
    )
    seen = census(text, doc="d.txt")
    assert [m.mark for m in seen.unbodied] == ["1"]


# --- and the narrowness that keeps markers honest ----------------------


def test_a_neighbouring_cell_is_not_a_footnote_marker() -> None:
    """Oregon City's height row arrives with its cells a single space apart:
    "All 65 feet 60 feet 50 feet". An unanchored glued-marker rule reads each
    cell's number as a marker on the cell before it, which invented 76
    markers in that one document."""
    text = "Maximum height   All 65 feet 60 feet 50 feet"
    assert census(text, doc="d.txt").markers == ()


def test_a_glued_marker_at_the_end_of_a_cell_is_read() -> None:
    text = "Front setback     20 feet7,8,9     15 feet"
    seen = census(text, doc="d.txt")
    assert sorted(m.mark for m in seen.markers) == ["7", "8", "9"]


def test_three_letters_of_english_are_not_permission_codes() -> None:
    """"A", "N" and "S" are used as permission codes by somebody, and are also
    words and labels. Gresham's flood definitions name "Zones A, AO, AH,
    A1-30" and its design chapter pairs guideline "G5" with standard "S5":
    268 markers in one document, every one of them imaginary."""
    prose = "\n".join(
        [
            "On the map, Zone A usually is refined into Zones A, AO, AH, A1-30.",
            "A guideline labeled G5 corresponds with standard S5.",
            "Paths are provided in A5.509 of the Design District standards.",
        ]
    )
    assert census(prose, doc="d.txt").markers == ()


def test_a_row_of_permissions_is_read_and_a_sentence_is_not() -> None:
    """A use row states several permissions, which is what tells it from a
    sentence that happens to contain one. Gresham prints the whole row on one
    line with single spaces: "Affordable Housing P/L2 P/L2 P3"."""
    row = "Affordable Housing P/L2 P/L2 P3"
    assert sorted(m.mark for m in census(row, doc="d.txt").markers) == ["2", "3"]

    sentence = "The lot must be platted under C2 of the partition standards."
    assert census(sentence, doc="d.txt").markers == ()


def test_a_label_carries_markers_and_a_zone_code_does_not() -> None:
    text = "\n".join(
        [
            "Lot coverage (maximum)3,6     20%",
            "Table 16.22.020-2 Development Standards for R-40",
            "MUR-M3",
        ]
    )
    seen = census(text, doc="d.txt")
    assert sorted(m.mark for m in seen.markers) == ["3", "6"]


def test_a_note_does_not_mark_itself() -> None:
    """A body carries its own number. Counted as a marker it would reconcile
    every block against itself and the census would report nothing, ever."""
    text = "\n".join(["NOTES:", "1 A note whose number is not a marker.", ""])
    seen = census(text, doc="d.txt")
    assert seen.markers == ()
    assert [b.mark for b in seen.unmarked] == ["1"]


# --- both directions, over the corpus ----------------------------------


@pytest.fixture(scope="module")
def store() -> list:
    return survey()


def test_the_census_covers_every_stored_document(store: list) -> None:
    assert len(store) > 40
    assert all(row.doc.endswith(".txt") for row in store)
    assert all(row.layer and row.doc.startswith(row.layer) for row in store)


def test_reconciliation_is_stated_in_both_directions(store: list) -> None:
    for row in store:
        assert row.reconciled == (not row.unbodied and not row.unmarked)
        for marker in row.unbodied:
            assert marker.quote.startswith(row.doc)
        for body in row.unmarked:
            assert body.quote.startswith(row.doc)


def test_the_corner_lot_qualifier_the_stacked_shape_was_hiding(store: list) -> None:
    """The finding that justified the module, pinned against the real store:
    Happy Valley's note 11 reduces a corner lot's front setback to eight feet
    on a local or connector street. It is in a stacked block, in a document we
    have held all along, and nothing in the encoding knew about it."""
    happy = next(
        row for row in store if row.doc.endswith("happy-valley/16.22.residential.txt")
    )
    eleven = [b for b in happy.bodies if b.mark == "11" and "corner lot" in b.text.lower()]
    assert eleven, "the stacked block is not being read"
    assert "eight feet" in eleven[0].text
    assert "local or connector street" in eleven[0].text


def test_documents_that_lost_their_markers_are_named(store: list) -> None:
    """Bodies and no markers at all is the shape the census exists to make
    visible instead of silent: notes are stated, and nothing on the page says
    which cell they answer. Gresham Butte's two are the last of them -- its
    density table lost its superscripts in extraction. Troutdale's zoning
    chapter used to read the same way and did not deserve to: its markers were
    never lost, they were spelled out in words (see test_page_frame)."""
    butte = next(
        row for row in store if row.doc.endswith("gresham/4.1300.gresham-butte.txt")
    )
    assert butte.bodies and not butte.markers
    assert not butte.reconciled
    assert len(butte.unmarked) == len(butte.bodies)

    troutdale = next(
        row for row in store if row.doc.endswith("troutdale/3.zoning-districts.txt")
    )
    assert troutdale.reconciled


def test_a_lettered_notes_block_is_a_notes_block():
    """Wilsonville's Table 8A runs its notes A through P.

    Every RN value in the corpus is read off that table, and until the census
    could see a letter, sixteen governing sentences were invisible — the
    combined side yards, the cul-de-sac frontage reduction, the quadplex lot
    size. A footnote nobody can see is not a footnote nobody has to read.
    """
    text = "\n".join(
        [
            "R-5 Small Lot 4,000 60' 60% 35 12 15 20",
            "Notes:",
            "A. Minimum lot size may be reduced to 80% of minimum lot size.",
            "B. For townhouses the minimum lot size in all sub-districts is",
            "1,500 square feet.",
            "C. In R-5 and R-7 sub-districts the minimum lot size for",
            "quadplexes is 7,000 square feet.",
        ]
    )

    seen = census(text, doc="d.txt")

    assert [b.mark for b in seen.bodies] == ["A", "B", "C"]
    assert "1,500 square feet" in seen.bodies[1].text


def test_extraction_spacing_does_not_hide_a_lettered_note():
    """Wilsonville prints "F . Front porches may extend" — the space is the
    extractor's, not the codifier's, and the note is note F either way."""
    text = "\n".join(["Notes:", "A. Minimum lot size.", "F . Front porches may extend 5 feet."])

    assert [b.mark for b in census(text, doc="d.txt").bodies] == ["A", "F"]


def test_a_lettered_paragraph_under_a_numbered_block_is_not_note_c():
    """Troutdale's "C. Townhouse dwellings:" heads the next table.

    Read as a note it did two kinds of damage: it invented a footnote nobody
    wrote, and it cut the real note above it short — voiding a ruling somebody
    had already made against the whole sentence. A block keeps one alphabet.
    """
    text = "\n".join(
        [
            "Notes:",
            "1. Front yard setback is 10 feet.",
            "2. Street side yard setback is 20 feet.",
            "C. Townhouse dwellings: Dimensional Standard LDR-1 LDR-2 MDR",
        ]
    )

    seen = census(text, doc="d.txt")

    assert [b.mark for b in seen.bodies] == ["1", "2"]
    assert "Townhouse" not in seen.bodies[-1].text


def test_a_sentence_beginning_with_a_capital_is_not_a_lettered_note():
    """"A minimum lot size of 5,000 square feet" opens a paragraph, not a
    list. Only the punctuation after the letter tells the two apart, which is
    why a letter is held to a stricter rule than a digit."""
    text = "\n".join(["Notes:", "A minimum lot size of 5,000 square feet applies."])

    assert census(text, doc="d.txt").bodies == ()


def test_a_page_break_does_not_end_a_notes_list():
    """Wilsonville's Table 8A runs A through P and breaks pages after L.

    What sits in the gap is the running header and the page stamp. Read as the
    start of the next section they took M, N, O and P with them — the combined
    side yards, the courtyard frontage, one driveway per street, and the garage
    setback from a sidewalk easement.
    """
    text = "\n".join(
        [
            "Notes:",
            "K. Front Setback is measured as the offset of the front lot line.",
            "L. For cottage clusters all setbacks greater than 10 feet are",
            "reduced to 10 feet",
            " � 4.127PLANNING AND LAND DEVELOPMENT",
            "CD4:178.3Supp. No. 5",
            "M. On lots greater than 10,000 SF the minimum combined side yard",
            "setbacks shall total 20 ft. with a minimum of 10 ft.",
        ]
    )

    seen = census(text, doc="d.txt")

    assert [b.mark for b in seen.bodies] == ["K", "L", "M"]
    assert "combined side yard" in seen.bodies[-1].text


def test_a_lettered_note_may_number_its_own_sub_parts():
    """Wilsonville's Table 8B note E numbers three garage setbacks.

    Read as the start of a new numbered list it ended the block, and F, G, H
    and I went with it — including the one that reduces a side setback to 3.5
    feet and the one that maps lot area onto another table's standards. A
    lettered list numbers its sub-parts; a numbered list that letters is the
    next subsection, and only the second ends a block.
    """
    text = "\n".join(
        [
            "Notes:",
            "D. For townhouses maximum lot coverage is calculated for the",
            "combined lots.",
            "E. Setbacks for residential garages are as follows:",
            "1. Front (street loaded): minimum 20 feet.",
            "2. Alley loaded with exterior driveway: minimum 18 feet.",
            "F . For Urban Form Type 1 and 2, side setbacks may be reduced to",
            "3.5 feet.",
        ]
    )

    seen = census(text, doc="d.txt")

    assert [b.mark for b in seen.bodies] == ["D", "E", "F"]
    assert "minimum 20 feet" in seen.bodies[1].text


def test_a_headless_numbered_run_under_a_table_is_a_notes_block():
    """Milwaukie's Table 19.302.4 prints its notes with nothing over them.

    No "Notes:", no brackets — just the number, a column gap and the sentence.
    One of them exempts middle housing from a density maximum that would
    otherwise ask 28,000 sq ft for four units, so the whole zone turns on a
    block the census could not see.
    """
    text = "\n".join(
        [
            "Maximum2, 3                                          32.0",
            "1  Minimum lot size for single detached dwelling applies to lots",
            "created on or after June 3, 2022.",
            "2  Townhouses are allowed at 4 times the maximum density allowed",
            "for single detached dwellings or 25 dwelling units per acre.",
            "3  The density for single room occupancy developments is",
            "calculated as follows: four SRO rooms equal one dwelling unit.",
        ]
    )

    seen = census(text, doc="d.txt")

    assert [b.mark for b in seen.bodies] == ["1", "2", "3"]
    assert "25 dwelling units per acre" in seen.bodies[1].text


def test_a_numbered_paragraph_in_the_code_body_is_not_a_headless_run():
    """"1. The applicant shall" is one space and a period — the shape of an
    ordinary subsection. A codifier's footnote is a number, a column gap and
    no period, and only that shape is read without a heading."""
    text = "\n".join(
        [
            "1. The applicant shall submit a site plan.",
            "2. The director shall review it within 30 days.",
        ]
    )

    assert census(text, doc="d.txt").bodies == ()


def test_a_note_may_cite_the_figure_named_after_it():
    """Lake Oswego's Table 50.04.001-11 note 5 ends "See Figure
    50.04.001-11[5]" — the figure carries the note's own number, glued to it.

    Read as a marker, that bracket says a new table has begun, and the block
    stopped there: note 5 arrived empty and 6 and 7 never arrived. Note 6 puts
    every R-0 and R-3 standard under a per-parcel site-specific check.
    """
    text = "\n".join(
        [
            "Notes:",
            "[4]",
            "Maximum base height across the site shall be 28 ft.",
            "[5]",
            "For any portion of the lot above the Oswego Lake surface",
            "elevation, height shall not exceed 25 ft. See Figure 50.04.001-11[5].",
            "[6]",
            "Site-specific dimensional standards, see LOC 50.02.002.2.c.",
        ]
    )

    seen = census(text, doc="d.txt")

    assert [b.mark for b in seen.bodies] == ["4", "5", "6"]
    assert "Oswego Lake" in seen.bodies[1].text
    assert "Site-specific" in seen.bodies[2].text


def test_a_bracket_glued_to_a_bare_number_is_still_a_marker():
    """"28 – 32[5]" is a table cell wearing its marker, and the forgiveness
    for cross-references must not reach it: the next table starting is what
    the block-ending test exists to catch."""
    text = "\n".join(
        [
            "Notes:",
            "[1]",
            "Net developable area divided by the minimum lot area per unit.",
            "Height, Primary Structure  28 – 32[5]  30 – 34[5]",
        ]
    )

    seen = census(text, doc="d.txt")

    assert [b.mark for b in seen.bodies] == ["1"]
    assert "28" not in seen.bodies[0].text


def test_a_glued_parenthesised_run_under_a_table_is_a_notes_block():
    """Municode prints a table's notes with no heading and the marker welded on.

    Wood Village's whole townhouse standard lives in one of them -- 1,500
    square feet, twenty feet of width, no minimum depth, a zero side setback on
    the attached wall -- and Table 210-3 states none of it. Sixteen notes in
    that city were on the page and invisible until this shape was read.
    """
    text = "\n".join(
        [
            "- Min. lot area(2)                 12,000 sq ft  7,500 sq ft",
            "- Side setback(2)                  10 ft         5 ft",
            "",
            "(1)Garages shall not be closer to the street than the plane of "
            "the street-facing facade.",
            "",
            "(2)For townhouses the minimum lot size is one thousand five "
            "hundred (1,500) square feet with a twenty (20) foot minimum "
            "width, no minimum depth, and zero (0) foot side setback when "
            "attached to another townhouse.",
            "",
            "(3)For cottage housing the rear setback and street side setback "
            "is ten (10) feet.",
        ]
    )

    seen = census(text, doc="d.txt")

    assert [b.mark for b in seen.bodies] == ["1", "2", "3"]
    assert "1,500) square feet" in seen.bodies[1].text
    # And the markers in the table above are what the block answers.
    assert "2" in {m.mark for m in seen.markers}
    assert seen.unbodied == ()


def test_a_numbered_subsection_is_not_a_glued_run():
    """The weld is the whole discriminator.

    A codifier writes "(1) Mixed Use Development Requirement." with a space
    after the bracket and writes its footnote bodies without one. Drop that
    distinction and every numbered paragraph in the code becomes a footnote.
    """
    text = "\n".join(
        [
            "(1) Mixed Use Development Requirement. Residential uses shall be "
            "permitted only when part of a mixed use development.",
            "",
            "(2) Limitation on Street-Level Housing. No more than fifty (50) "
            "percent of the frontage may be ground floor residential.",
        ]
    )

    assert census(text, doc="d.txt").bodies == ()


def test_a_lone_glued_note_is_not_believed():
    """A run is believed from its own note 1, with note 2 behind it.

    Wood Village's Table 250-1 prints "(2)See 250.200 D. Limited Uses per Title
    4" and no note 1 -- the sibling was lost in extraction. Reading it alone
    would let the census claim a block it cannot show; leaving it unbodied
    reports the document as unreconciled, which is the direction that surfaces
    the problem instead of burying it.
    """
    text = "\n".join(
        [
            "Household Living                    N(2)",
            "",
            "(2)See 250.200 D. Limited Uses per Title 4",
        ]
    )

    seen = census(text, doc="d.txt")

    assert seen.bodies == ()
    assert [m.mark for m in seen.unbodied] == ["2"]


def test_a_parenthesised_marker_needs_no_unit_in_front_of_it():
    """Half of Wood Village's Table 230-2 has no unit to anchor to.

    "Minimum Lot Size(1)" is a row label, "None(2)" is a cell with a word in
    it, and the height cell ends in a cross-reference before its marker --
    "45 - 55 feet (see Figure 230-3)(2)". The unit-anchored rule sees none of
    them, and all three carry a footnote that changes what the row means.
    """
    text = "\n".join(
        [
            "Minimum Lot Size(1)",
            "Maximum Height        45 - 55 feet (see Figure 230-3)(2)",
            "- Side setback        None(2)",
            "- Site area           5%(3)",
        ]
    )

    seen = census(text, doc="d.txt")

    assert {m.mark for m in seen.markers} == {"1", "2", "3"}


def test_a_code_citation_ending_in_a_subsection_is_not_a_marker():
    """"Subject to TDC 40.300(4)" is a cross-reference wearing a marker's shape.

    The dotted section number is what tells them apart. Without subtracting it
    the census invents a marker on every use row that points at another
    chapter, and an invented marker is an unbodied one -- a document reported
    unreconciled for a footnote that was never there.
    """
    text = "\n".join(
        [
            "Manufactured Dwelling P Subject to TDC 40.300(4)",
            "Equine Facility - Pursuant to ORS 455.315(2)",
            "Yes, except as provided in Section 8.0117(C)(3)",
        ]
    )

    assert census(text, doc="d.txt").markers == ()


def test_a_design_element_named_in_a_sentence_is_not_a_table_cell():
    """"design element P1" is the use-table cell pattern, in running prose.

    Fairview's TCC height-bonus chapter names its plaza and open-space
    standards P1 and P2 and then talks about them in paragraphs. Read as
    cells they are two footnote markers with no notes under them, and the
    chapter reports UNRECONCILED for footnotes that do not exist -- which is
    worse than useless, because the census exists to say which documents to
    go back and look at.
    """
    text = (
        "Additional Open Space. A development that incorporates a pedestrian "
        "access plaza or outdoor recreation area. The plaza must meet the "
        "minimum standards of design element P1 in Table 19.65.090(B)(2). The "
        "outdoor recreation area must meet the standards of design element P2."
    )

    assert census(text, doc="d.txt").markers == ()


def test_a_table_row_that_lost_its_column_gaps_is_still_a_row():
    """The reach the sentence rule must not cost.

    Gresham's plan district use tables come down from Municode with every
    column single-spaced -- "Single Detached Dwelling P P L1" -- and 53 rows
    across two chapters are read only because a line with more than one
    permission code on it counts as a row without needing a gap. A row has no
    sentence in it, which is what separates the two.
    """
    text = "\n".join(
        [
            "Single Detached Dwelling P P L1",
            "Affordable Housing P/L3 P4 P4",
            "Religious Institutions L/SUR7 SUR SUR",
            "Parks, Open Spaces, Paths, and Trails L/SUR13 L/SUR13 L/SUR13",
        ]
    )

    seen = census(text, doc="d.txt")

    assert {m.mark for m in seen.markers} == {"1", "3", "4", "7", "13"}


def test_a_column_gap_beats_the_sentence_rule():
    """A cell can carry a full stop when the table prints one.

    The sentence test is only ever the tie-breaker for lines with no column
    gap. Where the gap survives extraction it settles the question, and a
    cell whose text ends in a period keeps its marker.
    """
    text = "Accessory Dwelling Units      P3      One per lot. See 19.490."

    assert {m.mark for m in census(text, doc="d.txt").markers} == {"3"}
