"""Reading a zoning table without moving a number into another zone's column.

Portland's Table 110-4 is six zones wide. Every test here exists because the
failure mode is invisible: a value read from the wrong column arrives with the
right label, the right units, and a citation to the right line, and screens
every lot in the zone against a standard that was written for its neighbour.

The geometry in these fixtures — column offsets, and the cell that sits twelve
characters left of the header above it — is copied from the real chapter PDF,
not invented.
"""

from __future__ import annotations

from typing import Sequence

import pytest

from flats.encode.tables import (
    ZONES_ACROSS,
    ZONES_DOWN,
    Row,
    candidates_for,
    columns,
    header,
    measure,
    read_table,
    read_tables,
)

pytestmark = pytest.mark.unit

DOC = "or/multnomah/portland/33.110.txt"

#: Where Table 110-4's six zone columns start, as layout extraction reports them.
COLS = (94, 139, 184, 229, 274, 331)
ZONES = ("RF", "R20", "R10", "R7", "R5", "R2.5")


def line(label: str, cells: Sequence[str], at: Sequence[int] = COLS) -> str:
    """One layout line: a label, then each cell starting at its offset."""
    out = label
    for text, offset in zip(cells, at):
        out = out.ljust(offset) + text
    return out


HEADER = line("Standard", ZONES)

TABLE = "\n".join(
    [
        HEADER,
        line("Minimum lot area", ("20,000 sq. ft.", "20,000 sq. ft.", "10,000 sq. ft.",
                                 "7,000 sq. ft.", "5,000 sq. ft.", "3,000 sq. ft.")),
        # The last cell starts twelve characters left of its own header. Read
        # left-to-right it lands on R5 and overwrites R5's own setback.
        line("- Front building", ("20 ft.", "20 ft.", "20 ft.", "15 ft.", "10 ft.", "5 ft."),
             at=(94, 139, 184, 229, 274, 319)),
        line("  setback", ()),
        line("Maximum height", ("30 ft.", "30 ft.", "30 ft.", "30 ft.", "35 ft. [1]", "35 ft.")),
        line("Maximum building coverage", ("NA", "NA", "NA", "40%", "45%", "50%")),
        line("Minimum lot width", ("no limit", "no limit", "50 ft.", "40 ft.", "36 ft.", "36 ft.")),
    ]
)


def rows_of(text: str = TABLE, **kw) -> tuple[Row, ...]:
    return read_table(text, **kw).rows


def row_named(part: str, text: str = TABLE) -> Row:
    return next(r for r in rows_of(text) if part in r.label)


# --- finding the columns ----------------------------------------------


def test_a_header_line_yields_one_column_per_zone() -> None:
    assert [(c.zone, c.offset) for c in columns(HEADER)] == list(zip(ZONES, COLS))


def test_a_line_that_is_not_a_header_yields_nothing() -> None:
    assert columns(line("- Front building", ("20 ft.", "20 ft."))) == ()


def test_a_header_naming_one_zone_is_not_a_table() -> None:
    # One column is a sentence with spaces in it, not a grid.
    assert columns(line("Standard", ("R5",))) == ()


def test_text_with_no_header_has_no_rows() -> None:
    assert read_table("The minimum front setback is 10 feet.\n").rows == ()


# --- putting a cell in the right column --------------------------------


def test_each_cell_lands_under_its_own_zone() -> None:
    row = row_named("Minimum lot area")

    assert row.cells["RF"] == "20,000 sq. ft."
    assert row.cells["R5"] == "5,000 sq. ft."
    assert row.cells["R2.5"] == "3,000 sq. ft."


def test_a_cell_left_of_its_header_still_belongs_to_it() -> None:
    # The defect this module was rewritten for. R2.5's front setback starts
    # twelve characters left of the R2.5 header; claiming it for R5 replaces
    # R5's 10 ft. with 5 ft. and loses R2.5 entirely.
    row = row_named("Front building")

    assert row.cells["R5"] == "10 ft."
    assert row.cells["R2.5"] == "5 ft."
    assert len(row.cells) == len(ZONES)


def test_the_row_label_is_not_read_as_a_value() -> None:
    row = row_named("Minimum lot area")

    assert row.label == "Minimum lot area"
    assert set(row.cells) == set(ZONES)


def test_a_wrapped_label_folds_into_the_row_above() -> None:
    # "- Front building" / "setback" is one standard. Half a label names
    # nothing, and the subject matcher would never find "setback" alone.
    assert row_named("Front building").label == "- Front building setback"


def test_a_footnote_marker_is_not_part_of_the_value() -> None:
    assert row_named("Maximum height").cells["R5"] == "35 ft."


def test_line_numbers_follow_the_document_not_the_table() -> None:
    # Quotes point into the stored document, so a table that starts on line
    # 400 has to report 400 — otherwise every citation opens the wrong page.
    row = next(r for r in rows_of(start_line=400) if "Minimum lot area" in r.label)

    assert row.line == 401


# --- refusing an ambiguous row -----------------------------------------


CROWDED = "\n".join(
    [
        HEADER,
        # Two cells nearer R7 than any other column: one on its header, one
        # eleven characters past it. Nothing in the layout says which is R7's.
        line("Minimum lot width", ("50 ft.", "50 ft.", "50 ft.", "40 ft."), at=COLS[:4])
        + " " * 5
        + "70 ft.",
    ]
)


def test_two_cells_in_one_column_produce_no_value_for_it() -> None:
    row = rows_of(CROWDED)[0]

    assert "R7" in row.contested
    assert row.value_for("R7") == ""


def test_a_contested_zone_proposes_nothing() -> None:
    # An ambiguous row is review work. Picking either number is a coin flip
    # that arrives looking like a reading.
    assert candidates_for(rows_of(CROWDED), "R7", path=DOC) == []


def test_a_contested_zone_does_not_spoil_its_neighbours() -> None:
    row = rows_of(CROWDED)[0]

    assert row.value_for("R10") == "50 ft."
    assert [c.value for c in candidates_for(rows_of(CROWDED), "R10", path=DOC)] == [50]


# --- what a cell means -------------------------------------------------


@pytest.mark.parametrize(
    "cell,expected",
    [
        ("20 ft.", (20.0, "length_ft")),
        ("35 feet", (35.0, "length_ft")),
        ("3,000 sq. ft.", (3000.0, "area_sqft")),
        ("5,000 square feet", (5000.0, "area_sqft")),
        ("45 percent", (45.0, "percent")),
        ("45%", (45.0, "percent")),
        ("35 ft. [1]", (35.0, "length_ft")),
    ],
)
def test_a_measurement_reads_as_a_number_and_a_kind(cell: str, expected) -> None:
    assert measure(cell) == expected


@pytest.mark.parametrize(
    "cell",
    [
        "",
        "NA",
        "N/A",
        "None",
        # "no limit" says the standard does not apply here. Encoding it as a
        # large number would make the screen pass lots on a rule that is absent.
        "no limit",
        # A tiered coverage curve is a different encoding job, and the cell
        # says so rather than stating a value.
        "See Table 110-5",
        # A dimension pair, not a quantity — 12 alone means nothing.
        "12 ft. x 12 ft.",
        # A cross-reference, not a standard.
        "33.110.245",
    ],
)
def test_a_cell_that_is_not_a_measurement_is_refused(cell: str) -> None:
    assert measure(cell) is None


# --- proposing values for one zone -------------------------------------


def test_a_zone_gets_only_the_column_written_for_it() -> None:
    got = {c.field: c.value for c in candidates_for(rows_of(), "R5", path=DOC)}

    assert got["min_lot_sqft"] == 5000
    assert got["setback_front_ft"] == 10
    assert got["max_height_ft"] == 35
    assert got["max_coverage_pct"] == 45
    assert got["min_lot_width_ft"] == 36


def test_the_narrow_zone_gets_its_own_numbers() -> None:
    got = {c.field: c.value for c in candidates_for(rows_of(), "R2.5", path=DOC)}

    assert got["min_lot_sqft"] == 3000
    assert got["setback_front_ft"] == 5, "R5's 10 ft. is not R2.5's standard"
    assert got["max_coverage_pct"] == 50


def test_a_cell_that_states_no_limit_proposes_nothing() -> None:
    got = {c.field for c in candidates_for(rows_of(), "RF", path=DOC)}

    assert "min_lot_width_ft" not in got
    assert "max_coverage_pct" not in got, "NA is not a coverage standard"


def test_units_have_to_match_the_field() -> None:
    text = "\n".join([HEADER, line("Minimum lot area", ("35 ft.",) * 6)])

    assert candidates_for(read_table(text), "R5", path=DOC) == []


def test_a_row_naming_no_field_is_left_alone() -> None:
    text = "\n".join([HEADER, line("Minimum landscaped buffer", ("5 ft.",) * 6)])

    assert candidates_for(read_table(text), "R5", path=DOC) == []


def test_every_candidate_quotes_the_line_it_was_read_from() -> None:
    found = candidates_for(rows_of(start_line=400), "R5", path=DOC)
    lines = TABLE.splitlines()
    assert found

    for candidate in found:
        assert candidate.quote == f"{DOC}#L{candidate.line}"
        cell = candidate.text.rsplit(": ", 1)[1].removesuffix(" (R5)")
        assert cell in lines[candidate.line - 400], "the quote has to open the cell"


def test_a_candidate_says_which_zone_it_came_from() -> None:
    # The reviewer is being asked "is this R2.5's number?", so the column has
    # to be on screen beside the value.
    found = candidates_for(rows_of(), "R2.5", path=DOC)

    assert all("(R2.5)" in c.text for c in found)


def test_a_zone_absent_from_the_table_proposes_nothing() -> None:
    assert candidates_for(rows_of(), "RM1", path=DOC) == []


# --- what a real chapter does to a table reader ------------------------
#
# Both cases below were found by running this against Portland's Title 33
# chapter 33.110, not imagined. Each one silently emptied a column.

CHAPTER = "\n".join(
    [
        "Chapter 33.110",
        "Single-Dwelling Zones",
        "33.110.205 Lot Size",
        "The standards of this section apply in the R zones.",
        "Chapter 33.110",
        "Single-Dwelling Zones",
        "Table 110-4",
        HEADER,
        line("Maximum Height", ("30 ft.", "30 ft.", "30 ft.", "30 ft.", "30 ft.", "35 ft.")),
        "(See 33.110.215 and",
        # A wrapped cross-reference. It starts with a section number and is not
        # the end of anything.
        "33.110.260)",
        line("- Front building", ("20 ft.", "20 ft.", "20 ft.", "15 ft.", "10 ft.", "10 ft.")),
        " setback",
        "Chapter 33.110",
        "Single-Dwelling Zones",
        line("- Side building", ("10 ft.", "10 ft.", "10 ft.", "5 ft.", "5 ft.", "5 ft.")),
        " setback",
        line("- Rear building", ("10 ft.", "10 ft.", "10 ft.", "5 ft.", "5 ft.", "5 ft.")),
        " setback",
        "[1] Including any site with a congregate housing facility.",
        "Chapter 33.110",
        "Single-Dwelling Zones",
        "33.110.210 Floor Area Ratios",
        "The maximum floor area ratio is 0.5 to 1 and the height is 30 feet.",
    ]
)


def test_a_repeated_label_is_not_mistaken_for_page_furniture() -> None:
    # "setback" appears once per row, so counting repeats across the whole
    # document calls it decoration and drops it. What is left is three labels
    # naming no field, and every setback in the chapter goes unencoded — a
    # recall failure with no error to notice.
    got = {c.field: c.value for c in candidates_for(read_table(CHAPTER), "R5", path=DOC)}

    assert got["setback_front_ft"] == 10
    assert got["setback_side_ft"] == 5
    assert got["setback_rear_ft"] == 5


def test_page_furniture_between_rows_does_not_reach_a_label() -> None:
    # A page break lands between two rows. Folded into the label it would give
    # "- Side building Chapter 33.110 Single-Dwelling Zones setback", which
    # matches no field.
    labels = [r.label for r in read_table(CHAPTER)]

    assert "- Side building setback" in labels
    assert not any("Single-Dwelling" in label for label in labels)


def test_a_wrapped_cross_reference_does_not_end_the_table() -> None:
    # "33.110.260)" is the tail of "(See 33.110.215 and", not a new section.
    # Reading it as the end truncates the grid two rows in.
    assert len(read_table(CHAPTER)) == 4


def test_the_table_ends_before_the_prose_that_follows_it() -> None:
    # Past the footnotes the reader is looking at sentences, and a sentence
    # with a number in it is not a row of anything.
    rows = read_table(CHAPTER)

    assert all("floor area ratio" not in r.label for r in rows)
    assert max(r.line for r in rows) < CHAPTER.splitlines().index("33.110.210 Floor Area Ratios") + 1


def test_a_zone_column_survives_the_whole_chapter() -> None:
    got = {c.field: c.value for c in candidates_for(read_table(CHAPTER), "R2.5", path=DOC)}

    assert got["max_height_ft"] == 35, "R5's 30 ft. is not R2.5's height"


# --- the other layout: zones down the side ----------------------------
#
# Portland's Table 110-7 states the triplex/fourplex minimum lot area with the
# zones running down the rows. It is the gate that decides whether a pod is
# permitted on the lot at all, so a reader that only knows one layout leaves
# the most consequential standard in the chapter unencoded.

TRANSPOSED = "\n".join(
    [
        "Table 110-7",
        "Triplex and Fourplex Minimum Lot Area Standard",
        "Zone                    Minimum Lot Area",
        "R20                     12,000 sq. ft.",
        "R10                     6,000 sq. ft.",
        "R7                      4,200 sq. ft.",
        "R5                      3,000 sq. ft.",
        "R2.5                    1,500 sq. ft.",
    ]
)


def test_the_two_layouts_are_told_apart() -> None:
    assert header(HEADER)[0] == ZONES_ACROSS
    assert header("Zone                    Minimum Lot Area")[0] == ZONES_DOWN


def test_a_transposed_table_gives_each_zone_its_own_value() -> None:
    row = read_table(TRANSPOSED)[0]

    assert row.label == "Minimum Lot Area"
    assert row.value_for("R5") == "3,000 sq. ft."
    assert row.value_for("R2.5") == "1,500 sq. ft."


def test_a_transposed_row_quotes_the_line_its_zone_sits_on() -> None:
    # Every value in this table is on a different line, so one line number for
    # the row would send a reviewer to another zone's number.
    row = read_table(TRANSPOSED)[0]
    lines = TRANSPOSED.splitlines()

    assert "3,000" in lines[row.line_for("R5") - 1]
    assert "1,500" in lines[row.line_for("R2.5") - 1]


def test_a_transposed_table_proposes_per_zone_values() -> None:
    rows = read_table(TRANSPOSED)

    assert [(c.field, c.value) for c in candidates_for(rows, "R5", path=DOC)] == [
        ("min_lot_sqft", 3000)
    ]
    assert [c.value for c in candidates_for(rows, "R20", path=DOC)] == [12000]


def test_a_transposed_candidate_quotes_its_own_row() -> None:
    found = candidates_for(read_table(TRANSPOSED), "R7", path=DOC)[0]
    line = int(found.quote.rsplit("#L", 1)[1])

    assert "4,200" in TRANSPOSED.splitlines()[line - 1]


def test_a_heading_naming_no_field_is_not_a_table() -> None:
    # "Zone / Comment" is a two-column list, not a table of standards, and
    # reading its second column as values invents numbers from prose.
    listing = "Zone            Comment\nR5              See the map.\n"

    assert read_table(listing).rows == ()


def test_a_zone_row_that_is_not_a_zone_is_skipped() -> None:
    text = TRANSPOSED + "\nTotal                   99,000 sq. ft."

    assert read_table(text)[0].value_for("Total") == ""


def test_both_layouts_in_one_document_are_both_read() -> None:
    # Exactly the shape of chapter 33.110: setbacks in one grid, the fourplex
    # lot-size gate in another with the axes swapped.
    document = TABLE + "\n\n" + TRANSPOSED
    found = {}
    for rows in read_tables(document):
        found.update({c.field: c.value for c in candidates_for(rows, "R5", path=DOC)})

    assert found["setback_front_ft"] == 10
    assert found["min_lot_sqft"] == 3000


# --- footnotes: the other half of the standard -------------------------
#
# Portland's Table 110-4 states "30 ft. [3]" and prints "[3] Additional FAR and
# height may be allowed" beneath it. Reading the 30 and dropping the 3 encodes a
# ceiling the code does not impose — and being wrong in that direction turns a
# buildable lot RED, where nobody ever looks at it again.

FOOTNOTED = "\n".join(
    [
        HEADER,
        line("Maximum height", ("30 ft.", "30 ft.", "30 ft.", "30 ft. [3]", "30 ft. [3]",
                               "35 ft.")),
        line("- Front building", ("20 ft.", "20 ft.", "20 ft.", "15 ft.", "10 ft.", "10 ft.")),
        " setback",
        "[1] Including any site with a congregate housing facility.",
        "[3] Additional FAR and height may be allowed. See 33.110.265.F.",
        "33.110.210 Floor Area Ratios",
        "The maximum floor area ratio is stated in Table 110-4.",
    ]
)


def test_the_footnote_block_is_read_with_the_table() -> None:
    table = read_table(FOOTNOTED)

    assert table.notes[3] == "Additional FAR and height may be allowed. See 33.110.265.F."
    assert set(table.notes) == {1, 3}


def test_a_footnote_is_quotable_like_a_value() -> None:
    # A condition has to be readable by whoever signs it, same as a number.
    table = read_table(FOOTNOTED)

    assert "[3]" in FOOTNOTED.splitlines()[table.note_lines[3] - 1]


def test_a_marker_does_not_become_part_of_the_number() -> None:
    table = read_table(FOOTNOTED)
    row = next(r for r in table.rows if "height" in r.label)

    assert row.value_for("R5") == "30 ft."
    assert measure(row.value_for("R5")) == (30.0, "length_ft")


def test_a_marker_is_kept_against_the_zone_that_carries_it() -> None:
    row = next(r for r in read_table(FOOTNOTED).rows if "height" in r.label)

    assert row.marks_for("R5") == (3,)
    assert row.marks_for("R2.5") == (), "R2.5 states 35 ft. with no exit"


def test_a_footnoted_value_is_proposed_as_conditional() -> None:
    table = read_table(FOOTNOTED)
    height = next(c for c in candidates_for(table, "R5", path=DOC) if c.field == "max_height_ft")

    assert height.value == 30
    assert height.conditional
    assert height.notes == ("Additional FAR and height may be allowed. See 33.110.265.F.",)


def test_an_unfootnoted_value_stays_unconditional() -> None:
    table = read_table(FOOTNOTED)
    front = next(c for c in candidates_for(table, "R5", path=DOC) if c.field == "setback_front_ft")

    assert not front.conditional


def test_the_footnote_block_still_ends_the_rows() -> None:
    # Notes are part of the table and are not rows of it. A note read as a row
    # puts its sentence in a label and its numbers in a column.
    labels = [r.label for r in read_table(FOOTNOTED).rows]

    assert not any("congregate" in label for label in labels)
    assert not any("floor area ratio" in label for label in labels)


# --- the Troutdale grid: bare digits, drifting alignment, sub-columns --


def test_a_grid_of_bare_digits_splits_into_cells_not_pairs() -> None:
    # The real bug: with a greedy quantifier, a one-character cell reached
    # across its own gap and glued itself to the next cell, so "5    5    5"
    # read as two cells. Portland never showed it — "20 ft." stops at its own
    # word end either way.
    from flats.encode.tables import _cells

    found = _cells("   Side yard        5               5               5")

    assert [text for _, text in found] == ["Side yard", "5", "5", "5"]


TROUTDALE = "\n".join(
    [
        # The header carries "(TC)" sub-columns between zones, and each data
        # row right-aligns its numbers to their own width — drifting further
        # than the column pitch, so nearest-offset reads 70 as LDR-2's.
        "Dimensional Standard              LDR-1       LDR-2        MDR         (TC)          HDR",
        "Minimum lot size (sq. ft.)              10,000       7,000        5,000        5,000         N/A",
        "Minimum lot width (ft.)                  70             60             50             50            N/A",
    ]
)


def test_a_structurally_complete_row_is_placed_by_position_not_offset() -> None:
    from flats.encode.tables import read_tables

    table = read_tables(TROUTDALE)[0]
    width = table.rows[1]

    assert width.value_for("LDR-1") == "70"
    assert width.value_for("LDR-2") == "60"
    assert width.value_for("MDR") == "50"


def test_a_sub_column_s_number_is_not_claimed_for_the_zone_beside_it() -> None:
    # "(TC)" is a real column that is not a zone. Dropping it from the count
    # makes the fifth cell look like the fifth zone, and the town-center
    # variant's number ends up wearing the base zone's citation.
    from flats.encode.tables import read_tables

    table = read_tables(TROUTDALE)[0]

    assert table.rows[0].value_for("HDR") == "N/A"
    assert table.rows[0].value_for("MDR") == "5,000"


# --- the fourth shape: stacked label/value pairs -----------------------------

# A Code Publishing HTML chapter linearised by html_to_text: one table cell
# per line. Direct-subject labels (Gladstone), grouped labels under a setback
# heading (West Linn), a note line after a value, a two-tier value line, and
# a sub-labelled lot-area stack that must produce nothing.
GLADSTONE_PAIRS = '''
17.10.050 Dimensional standards.

Minimum Lot Area

Detached single household

7,200 sf

Minimum Setbacks

Front setback

20 ft

Except that a front porch may project a maximum of five feet into it.

Side setback

7.5 ft or 5 ft due to irregular shaped lots

Interior side setback

5 ft

Rear setback

15 ft

Maximum Building Height

35 ft
'''

WEST_LINN_PAIRS = '''
12.070 DIMENSIONAL REQUIREMENTS

Minimum yard dimensions or minimum building setbacks

Front yard

20 ft

Except for steeply sloped lots where the provisions of CDC 41.010 shall apply

Interior side yard

7.5 ft

Street side yard

15 ft

Rear yard

20 ft

Maximum building height

35 ft

Maximum lot coverage

35%
'''


def _pairs(text: str) -> dict[str, float]:
    from flats.encode.tables import read_pairs

    return {c.field: c.value for c in read_pairs(text, path="doc.txt")}


def test_a_direct_subject_label_pairs_with_the_measure_below_it() -> None:
    found = _pairs(GLADSTONE_PAIRS)

    assert found["setback_front_ft"] == 20
    assert found["setback_rear_ft"] == 15
    assert found["max_height_ft"] == 35


def test_a_note_line_after_the_value_does_not_poison_the_pair() -> None:
    # Joined into one clause, "Except that a front porch..." tags the whole
    # stack an exception and the 20 ft base disappears. The pair reader works
    # on the unjoined lines, where the note is just the next cell.
    assert _pairs(GLADSTONE_PAIRS)["setback_front_ft"] == 20


def test_a_two_tier_value_line_is_refused_whole() -> None:
    # "7.5 ft or 5 ft due to irregular shaped lots" starts with a measurement
    # and does not state one. measure() would read the prefix; the pair
    # reader must consume the whole line or nothing — the interior-side row
    # below it is what fills the field.
    assert _pairs(GLADSTONE_PAIRS)["setback_side_ft"] == 5


def test_a_sub_labelled_stack_produces_nothing() -> None:
    # "Minimum Lot Area" over "Detached single household" over "7,200 sf" is
    # a housing-type row. The line under the label is not a measurement, and
    # whose 7,200 it is is not this reader's call.
    assert "min_lot_sqft" not in _pairs(GLADSTONE_PAIRS)


def test_a_grouped_label_reads_through_the_setback_heading() -> None:
    found = _pairs(WEST_LINN_PAIRS)

    assert found["setback_front_ft"] == 20
    assert found["setback_side_ft"] == 7.5
    assert found["setback_street_side_ft"] == 15
    assert found["setback_rear_ft"] == 20
    assert found["max_coverage_pct"] == 35


def test_a_repeated_value_line_is_not_page_furniture() -> None:
    # "20 ft" prints once per row it governs and "35 ft" once per standard.
    # Frequency-based furniture detection would eat them — West Linn's whole
    # setback block vanished before values were exempted.
    found = _pairs(WEST_LINN_PAIRS)

    assert found["setback_front_ft"] == 20
    assert found["setback_rear_ft"] == 20
    assert found["max_height_ft"] == 35


def test_a_pair_carries_the_section_it_was_read_under() -> None:
    from flats.encode.tables import read_pairs

    sections = {c.field: c.section for c in read_pairs(WEST_LINN_PAIRS, path="doc.txt")}

    assert sections["setback_front_ft"] == "12.070"


def test_a_pair_quotes_the_line_the_number_is_on() -> None:
    from flats.encode.tables import read_pairs

    front = next(
        c for c in read_pairs(GLADSTONE_PAIRS, path="doc.txt") if c.field == "setback_front_ft"
    )

    assert front.quote == f"doc.txt#L{front.line}"
    assert GLADSTONE_PAIRS.splitlines()[front.line - 1].strip() == "20 ft"
