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
    """Troutdale's zoning chapter states seventeen notes and not one marker
    survived extraction -- the superscripts are simply gone. That is the
    failure the census exists to make visible instead of silent."""
    troutdale = next(
        row for row in store if row.doc.endswith("troutdale/3.zoning-districts.txt")
    )
    assert troutdale.bodies and not troutdale.markers
    assert not troutdale.reconciled
    assert len(troutdale.unmarked) == len(troutdale.bodies)


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
