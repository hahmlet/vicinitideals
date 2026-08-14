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


# --- the fifth shape: stacked grids ------------------------------------------

# WVDC Table 210-3 as municipal.codes linearises it: a header block of zone
# codes, then each row as its label followed by one value line per zone.
# Carries every hazard the reader must survive: paren footnotes on labels and
# values, "(See ...)" comment cells between label and values, a Corner Lots
# block whose setbacks are variants, and a coverage row after that block.
WOOD_VILLAGE_GRID = """
210.320 Lot Size and Dimensional Standards.

Table 210-3. Development Standards in Light Residential Zones

Standard

LR12

LR7.5

Minimum Lot Size

- Min. lot area(2)

12,000 sq ft

7,500 sq ft

Minimum Setbacks

- Front setback

10 ft(1)

10 ft(1)

- Side setback(2)

10 ft

5 ft

Corner Lots

- Front setback

10 ft

10 ft

- Street side setback(3)

20 ft

10 ft

- Side setback(2)

10 ft

10 ft

Maximum Site Coverage

(See 210.350 and (2), (3) below)

45%

45%
"""

# Milwaukie's Table 19.301.4: one zone, columns are lot-size tiers. Reading
# n positional values under a single zone code is exactly what a tier row
# looks like, so a one-zone header is never read.
MILWAUKIE_TIERS = """
Table 19.301.4

Standard

R-MD

1. Minimum lot width (ft)

20

30

50

60
"""


def _grid(text: str):
    from flats.encode.tables import read_stacked_grids

    return read_stacked_grids(text, path="doc.txt")


def test_each_zone_gets_the_value_in_its_column_position() -> None:
    grids = _grid(WOOD_VILLAGE_GRID)
    lr12 = {c.field: c.value for c in grids["LR12"]}
    lr75 = {c.field: c.value for c in grids["LR7.5"]}

    assert lr12["min_lot_sqft"] == 12000
    assert lr75["min_lot_sqft"] == 7500
    assert lr12["setback_side_ft"] == 10
    assert lr75["setback_side_ft"] == 5


def test_a_paren_footnote_travels_with_the_value_as_a_note() -> None:
    grids = _grid(WOOD_VILLAGE_GRID)
    front = next(c for c in grids["LR7.5"] if c.field == "setback_front_ft")

    assert front.value == 10
    assert front.conditional


def test_a_corner_block_yields_only_the_street_side_setback() -> None:
    # Corner-lot side setbacks are variants of the base standard above them;
    # the street side is the one field whose natural home is the corner block.
    grids = _grid(WOOD_VILLAGE_GRID)
    fields = [c.field for c in grids["LR7.5"]]

    assert fields.count("setback_side_ft") == 1
    assert next(c for c in grids["LR7.5"] if c.field == "setback_street_side_ft").value == 10
    assert next(c for c in grids["LR12"] if c.field == "setback_street_side_ft").value == 20


def test_a_row_after_the_corner_block_is_a_sibling_not_a_member() -> None:
    grids = _grid(WOOD_VILLAGE_GRID)

    assert next(c for c in grids["LR7.5"] if c.field == "max_coverage_pct").value == 45


def test_a_comment_cell_between_label_and_values_is_stepped_over() -> None:
    # "(See 210.350 ...)" sits where a value would; the 45% pair behind it is
    # still positional.
    grids = _grid(WOOD_VILLAGE_GRID)

    assert next(c for c in grids["LR12"] if c.field == "max_coverage_pct").value == 45


def test_a_single_zone_header_is_never_read() -> None:
    # Four tier values under one zone code: claiming any of them for R-MD
    # would encode the smallest lot tier as the zone standard.
    assert _grid(MILWAUKIE_TIERS) == {}


def test_more_values_than_zones_refuses_the_row() -> None:
    text = """
Standard

LR12

LR7.5

- Front setback

10 ft

15 ft

20 ft
"""
    assert _grid(text) == {}


def test_a_grid_quote_points_at_the_zone_s_own_value_line() -> None:
    grids = _grid(WOOD_VILLAGE_GRID)
    lr75_lot = next(c for c in grids["LR7.5"] if c.field == "min_lot_sqft")

    assert WOOD_VILLAGE_GRID.splitlines()[lr75_lot.line - 1].strip() == "7,500 sq ft"
    assert lr75_lot.quote == f"doc.txt#L{lr75_lot.line}"


def test_zone_spelling_matches_across_space_and_hyphen() -> None:
    # The GIS layer writes "LR 7.5"; the table header prints "LR7.5".
    from flats.encode.tables import stacked_candidates_for

    grids = _grid(WOOD_VILLAGE_GRID)

    assert stacked_candidates_for(grids, "LR 7.5")
    assert stacked_candidates_for(grids, "lr12")
    assert stacked_candidates_for(grids, "R-5") == []


# Happy Valley's Table 16.22.020-2 family: labels wear glued footnote refs,
# setback rows drop the word "yard" under a "Building setbacks (minimum)6"
# heading, a typed sub-row sits under a heading whose own row-read fails,
# and one column prints "Variable4" where a number would be.
HAPPY_VALLEY_GRID = """
Standard

R-40

R-20

Lot size (minimum): Townhome1

1,500 sq. ft.

1,500 sq. ft.

Lot width (minimum)2,6

100 feet

80 feet

Lot coverage (maximum)3

Duplex, triplex, quadplex, townhome

20%

Variable4

Building setbacks (minimum)6

Front

22 feet

22 feet

Interior side

15/04 feet

10/04 feet

Garage and carport entrances

22 feet

22 feet

Street side (corner lot)

15 feet

15 feet
"""


def _r40(field: str):
    return [c for c in _grid(HAPPY_VALLEY_GRID)["R-40"] if c.field == field]


def test_a_label_wearing_glued_refs_still_reads_and_stays_conditional() -> None:
    # "Lot width (minimum)2,6" is a label with two superscripts fused on.
    # Refusing it for the digits loses the row; reading it clean loses the
    # footnotes. It reads, and the refs ride along as conditions.
    width = _r40("min_lot_width_ft")

    assert [c.value for c in width] == [100]
    assert "footnote 2 (text not captured)" in width[0].notes


def test_a_heading_ref_conditions_every_row_it_scopes() -> None:
    # The 6 on "Building setbacks (minimum)6" belongs to all the setback
    # rows under it, none of which repeat it.
    front = _r40("setback_front_ft")

    assert [c.value for c in front] == [22]
    assert "footnote 6 (text not captured)" in front[0].notes


def test_a_bare_direction_reads_under_a_setbacks_heading() -> None:
    # "Front" with no "yard" — the heading names the standard, the row only
    # the direction.
    assert [c.value for c in _r40("setback_front_ft")] == [22]


def test_an_unmatched_row_does_not_end_the_setbacks_block() -> None:
    # "Garage and carport entrances" over "22 feet" is a row this reader has
    # no field for — not a new block heading. The street-side row after it
    # must still know it is a setback.
    street = _r40("setback_street_side_ft")

    assert [c.value for c in street] == [15]
    assert not any("corner" in n for n in street[0].notes)


def test_a_slashed_cell_refuses_the_whole_row() -> None:
    # "15/04 feet" is a two-tier standard with a glued footnote; no single
    # number is honest, so the interior-side row produces nothing.
    assert _r40("setback_side_ft") == []


def test_a_typed_sub_row_under_a_failed_heading_reads_with_its_types() -> None:
    # "Lot coverage (maximum)3" has no values of its own; the typed rows
    # under it do. The heading's field and ref scope the sub-row.
    coverage = _r40("max_coverage_pct")

    assert [c.value for c in coverage] == [20]
    assert "quadplex" in coverage[0].housing_type.split("+")
    assert "footnote 3 (text not captured)" in coverage[0].notes


def test_a_variable_cell_yields_no_candidate() -> None:
    # The R-20 coverage cell says "Variable4": the standard exists and is
    # not a number. Like a dash, that zone gets nothing — not a neighbour's
    # value shifted into place.
    r20 = [c for c in _grid(HAPPY_VALLEY_GRID)["R-20"] if c.field == "max_coverage_pct"]

    assert r20 == []


def test_a_run_of_bare_letters_is_not_a_header() -> None:
    # Lettered list fragments match the zone pattern; a real district run
    # carries a digit somewhere.
    text = """
C

D

Front setback

10 ft

12 ft
"""
    assert _grid(text) == {}


def test_sf_counts_as_square_feet() -> None:
    # Happy Valley's 040-2 prints "5,000 sf".
    assert measure("5,000 sf") == (5000.0, "area_sqft")


def test_a_context_paren_conditions_the_row_it_qualifies() -> None:
    # "Front (street access garage)" and "Front (alley access garage)" are
    # both real front setbacks, conditioned on which way the garage faces.
    # Both read, and neither reads clean.
    text = """
Standard

R-5

MUR-S

Building setbacks (minimum)8

Front (street access garage)

20 feet

20 feet

Front (alley access garage)

10 feet

10 feet
"""
    fronts = [c for c in _grid(text)["R-5"] if c.field == "setback_front_ft"]

    assert sorted(c.value for c in fronts) == [10, 20]
    assert all(any("(row context)" in n for n in c.notes) for c in fronts)


def test_a_bare_direction_pair_is_not_zone_evidence() -> None:
    # Lake Oswego's WLG R-2.5 structure-type table pairs "Front" with
    # "10 ft." under a setbacks heading. A pair has no column geometry to
    # pin a zone, so bare directions stay stacked-grid-only; the yard forms
    # keep working.
    from flats.encode.tables import read_pairs

    text = """
Minimum Setbacks

Front

10 ft

Front yard

15 ft
"""
    fields = [(c.field, c.value) for c in read_pairs(text, path="doc.txt")]

    assert ("setback_front_ft", 10) not in fields
    assert ("setback_front_ft", 15) in fields


# --- digit-less zone families -----------------------------------------------

SPRINGWATER = "\n".join(
    [
        "Table 4.1508:      Development Standards in Springwater Residential Sub-Districts",
        "                                        VLDR-SW                 LDR-SW                  THR-SW",
        "A. Minimum Buildable Lot Size (square feet)",
        "     Townhouse                          None                    None                    1,800 sq. ft.",
        "     All Other Uses                     10,000 sq. ft.          5,000 sq. ft.           None",
    ]
)


def test_a_digit_less_zone_family_is_a_header() -> None:
    # Springwater's sub-districts carry no digits at all — VLDR-SW, LDR-SW,
    # THR-SW. Requiring a digit somewhere in the family refused the header
    # and dropped the whole table to the prose reader, which read the
    # townhouse 1,800 as every zone's lot size.
    kind, cols = header("                    VLDR-SW                 LDR-SW                  THR-SW")

    assert kind == ZONES_ACROSS
    assert tuple(c.zone for c in cols) == ("VLDR-SW", "LDR-SW", "THR-SW")


def test_a_repeated_digit_less_token_is_not_a_header() -> None:
    # A wrapped label row repeats one token; a header names distinct
    # districts.
    assert header("                    MR                 MR") is None


def test_a_row_of_empty_cells_is_still_not_a_header() -> None:
    assert header("                    NA                 NA                  NA") is None


def test_the_springwater_table_reads_the_middle_column() -> None:
    found = candidates_for(read_tables(SPRINGWATER)[0], "LDR-SW", path=DOC)

    got = {(c.field, c.value, c.housing_type) for c in found}
    assert ("min_lot_sqft", 5000, "default") in got
    assert not any(c.value == 1800 for c in found)


def test_the_springwater_table_gives_the_townhouse_row_to_its_zone() -> None:
    found = candidates_for(read_tables(SPRINGWATER)[0], "THR-SW", path=DOC)

    assert ("min_lot_sqft", 1800, "townhouse") in {
        (c.field, c.value, c.housing_type) for c in found
    }


# --- type-column headers: a run of housing types refuses the block ----------

# Wood Village Table 220-3 as municipal.codes linearises it: the header row
# becomes a run of housing-type names, then each row label prints over a
# ragged run of values whose empty cells vanished with the geometry. Flat
# text can no longer say which type a value belongs to.
WOOD_VILLAGE_TYPE_COLUMNS = """220.320 Lot Size and Dimensional Standards.

Townhouse

Detached Single Dwelling

Duplex

Minimum Lot Size

- Min. lot area

1,500 sq ft

10,000 sq ft

Minimum Setbacks

- Front setback

10 ft

20 ft
"""


def test_a_run_of_housing_types_suppresses_all_pairing() -> None:
    # Two values land under one label — whichever pairing the reader guessed,
    # some type's number would corroborate the wrong standard by coincidence.
    # Wood Village's MR block did exactly that: the duplex column's 10,000
    # "agreed" with the encoded SFD minimum.
    assert _pairs(WOOD_VILLAGE_TYPE_COLUMNS) == {}


def test_the_type_column_refusal_ends_at_the_next_section() -> None:
    text = WOOD_VILLAGE_TYPE_COLUMNS + "\n220.330 Fences.\n\nMaximum height\n\n6 ft\n"

    assert _pairs(text) == {"max_height_ft": 6}


def test_one_type_line_is_a_sub_label_not_a_header() -> None:
    # A single housing-type line is a sub-row label (Gladstone's "Detached
    # single household"), not a column header — pairing continues after it.
    text = """220.320 Standards.

Townhouse

Minimum front setback

15 ft
"""

    assert _pairs(text) == {"setback_front_ft": 15}


def test_wood_village_type_spellings_are_recognised() -> None:
    from flats.encode.tables import _housing_type

    assert _housing_type("Detached Single Dwelling") == "single_detached"
    assert _housing_type("Cottage Housing") == "cottage_cluster"


# --- the sixth shape: housing types across the top ---------------------------

# Wood Village Table 220-3 as the table-aware extractor renders it: the columns
# are housing types and no zone is named anywhere in the grid. Which zones it
# speaks for comes from the section it is printed under. Carries the shapes
# that broke the reader: an empty cell (townhouse has no lot depth), a second
# table below it, and a group heading glued to the row above.
WOOD_VILLAGE_TYPES = "\n".join(
    [
        "220.320 Lot Size and Dimensional Standards.",
        "",
        "Table 220-3. Housing Types Allowed",
        "Standard                      Townhouse    Detached Single Dwelling  Duplex Triplex Quadplex",
        "Minimum Lot Size              1,500 sq ft  7,500 sq ft               7,500 sq ft",
        "- Min. lot depth              20 ft                                  80 ft",
        "- Front setback               10 ft        10 ft                     10 ft",
        "Maximum Site Coverage         75%          45%                       45%",
        "",
        "Table 220-4. Development Standards for Multi-Dwelling Structures",
        "Number of Units  Minimum Lot Area  Min. Width",
        "5                16,500 sq ft      60 ft",
    ]
)


def _typed(text: str, path: str = "doc.txt"):
    from flats.encode.tables import read_tables

    return read_tables(text)[0]


def test_a_header_of_housing_types_is_its_own_shape() -> None:
    from flats.encode.tables import TYPES_ACROSS, header

    kind, cols = header(WOOD_VILLAGE_TYPES.splitlines()[3])

    assert kind == TYPES_ACROSS
    assert [c.zone for c in cols] == [
        "townhouse",
        "single_detached",
        "duplex+triplex+quadplex",
    ]


def test_one_type_column_beside_zone_columns_is_not_a_typed_table() -> None:
    # A zone table with a stray type label still has zones in it, and reading
    # it as typed would drop every zone the columns name.
    from flats.encode.tables import ZONES_ACROSS, header

    kind, cols = header("Standard          R-5        R-7        Townhouse")

    assert kind == ZONES_ACROSS
    assert [c.zone for c in cols] == ["R-5", "R-7"]


def test_a_typed_table_keeps_each_type_in_its_own_column() -> None:
    table = _typed(WOOD_VILLAGE_TYPES)

    assert table.typed
    area = next(r for r in table.rows if r.label == "Minimum Lot Size")
    assert area.value_for("townhouse") == "1,500 sq ft"
    assert area.value_for("duplex+triplex+quadplex") == "7,500 sq ft"


def test_an_empty_cell_in_a_typed_row_stays_empty() -> None:
    # The reason the extractor renders grids at all: without the gap, the
    # detached column's 80 ft slides one column left and becomes the
    # townhouse's lot depth.
    table = _typed(WOOD_VILLAGE_TYPES)
    depth = next(r for r in table.rows if "lot depth" in r.label)

    assert depth.value_for("single_detached") == ""
    assert depth.value_for("duplex+triplex+quadplex") == "80 ft"


def test_the_next_table_s_caption_ends_this_one() -> None:
    table = _typed(WOOD_VILLAGE_TYPES)

    assert max(r.line for r in table.rows) < 10, "Table 220-4's rows are not in 220-3"


def test_a_reprinted_caption_does_not_end_the_table() -> None:
    # A chapter PDF stamps the same caption at every page break. Treating it
    # as a new table cuts Gresham's grid off at the first page boundary and
    # loses every standard printed after it.
    text = "\n".join(
        [
            "Table 4.0130: Development Requirements",
            "Standard              R-5      R-7",
            "Minimum lot area      5,000    7,000",
            "Table 4.0130: Development Requirements",
            "Minimum front setback  20 ft   20 ft",
        ]
    )
    from flats.encode.tables import read_tables

    rows = read_tables(text)[0].rows

    assert [r.label for r in rows] == ["Minimum lot area", "Minimum front setback"]
    assert rows[-1].value_for("R-5") == "20 ft"


def test_a_typed_table_reads_zone_blind_and_carries_its_section() -> None:
    from flats.encode.extract import extract

    read = extract(
        WOOD_VILLAGE_TYPES, path="doc.txt", jurisdiction="or/multnomah/wood-village", zone="MR 2"
    )
    typed = [c for c in read.candidates if c.source == "typed-table"]

    assert {c.section for c in typed} == {"220.320"}
    assert ("min_lot_sqft", 7500, "duplex+triplex+quadplex") in {
        (c.field, c.value, c.housing_type) for c in typed
    }
    assert ("min_lot_sqft", 1500, "townhouse") in {
        (c.field, c.value, c.housing_type) for c in typed
    }


def test_a_zone_spelled_with_a_space_still_finds_its_column() -> None:
    # The GIS layer writes "LR 7.5" and the header prints "LR7.5". The stacked
    # reader always matched loosely; the column reader had to once a rendered
    # grid replaced the one-code-per-line linearisation.
    from flats.encode.tables import read_tables

    text = "\n".join(
        [
            "Standard              LR12          LR7.5",
            "Minimum lot area      12,000 sq ft  7,500 sq ft",
        ]
    )
    row = read_tables(text)[0].rows[0]

    assert row.value_for("LR 7.5") == "7,500 sq ft"
    assert row.value_for("LR 12") == "12,000 sq ft"
    assert row.value_for("LR 8") == ""


def test_a_capitalised_block_heading_scopes_the_rows_under_it() -> None:
    # Happy Valley's HTML grid heads each block with a label row whose cells
    # are empty — no leading letter, no colon. Without a heading rule that
    # catches it, "Rear" and "Interior side" name a direction and nothing
    # else, and every setback in the chapter goes unread.
    text = "\n".join(
        [
            "Standard                      R-5      MUR-S",
            "Building setbacks (minimum)8",
            "Rear                          20 feet  20 feet",
            "Interior side                 5 feet   5 feet",
        ]
    )
    found = candidates_for(read_tables(text)[0], zone="R-5", path="d.txt")

    assert {(c.field, c.value) for c in found} == {
        ("setback_rear_ft", 20),
        ("setback_side_ft", 5),
    }


def test_the_tail_of_a_wrapped_label_is_not_a_block_heading() -> None:
    # Portland wraps "- Front building setback" across two lines, and its
    # tail says "setback" as loudly as any heading does. Read as one, the
    # heading swallows the row it belongs to and the setback disappears.
    text = "\n".join(
        [
            "Standard              R5       R7",
            "Minimum Setbacks",
            "- Front building      10 ft.   15 ft.",
            " setback",
        ]
    )
    found = candidates_for(read_tables(text)[0], zone="R5", path="d.txt")

    assert [(c.field, c.value) for c in found] == [("setback_front_ft", 10)]


def test_row_context_on_a_grouped_setback_is_kept_as_a_condition() -> None:
    # "Front (street access garage)" beside "Front (alley access garage)" is
    # one standard with two cases, not two readings. The parenthesis is
    # dropped for the lookup and kept as the note that says which case.
    text = "\n".join(
        [
            "Standard                      R-5      MUR-S",
            "Building setbacks (minimum)",
            "Front (street access garage)  20 feet  20 feet",
            "Front (alley access garage)   10 feet  10 feet",
            "Street side (corner lot)      8 feet   8 feet",
        ]
    )
    found = candidates_for(read_tables(text)[0], zone="R-5", path="d.txt")
    by_value = {c.value: c for c in found}

    assert by_value[20].notes == ("(street access garage) (row context)",)
    assert by_value[10].notes == ("(alley access garage) (row context)",)
    # A corner is the only place a street-side setback exists, so saying so
    # conditions nothing.
    assert by_value[8].notes == ()


def test_a_headed_note_block_gives_a_marked_cell_its_condition() -> None:
    # "35 ft.5" says the standard has an exit. Without the definition the
    # value is conditional on nothing anybody can read, which is unreviewable
    # and unquotable — and a reviewer cannot sign what they cannot see.
    text = "\n".join(
        [
            "Standard              R-5      R-7",
            "Maximum height        35 ft.5  35 ft.5",
            "Table Notes",
            "5. Height may be increased to 45 feet for affordable housing.",
        ]
    )
    found = candidates_for(read_tables(text)[0], zone="R-5", path="d.txt")

    assert [c.notes for c in found] == [
        ("Height may be increased to 45 feet for affordable housing.",)
    ]


def test_a_definition_that_wraps_is_rejoined_across_its_hyphen() -> None:
    # A condition cut in half reads as a different condition, and a PDF breaks
    # words at the margin: "abutting zoning dis-" / "trict." is one word.
    text = "\n".join(
        [
            "Standard              R-5      R-7",
            "Maximum height        35 ft.1  35 ft.1",
            "Table Notes",
            "1. Height is the same height as required by the abutting zoning dis-",
            "trict.",
        ]
    )
    note = candidates_for(read_tables(text)[0], zone="R-5", path="d.txt")[0].notes[0]

    assert note == "Height is the same height as required by the abutting zoning district."


def test_a_page_break_inside_the_note_block_does_not_end_it() -> None:
    # Troutdale prints notes 1-2, breaks the page, reprints the column header
    # — sometimes only its second row — and carries on with notes 3 and up.
    text = "\n".join(
        [
            "Standard              LDR-1    LDR-2",
            "Maximum height        35 ft.3  35 ft.3",
            "Table Notes",
            "1. Front yard setback may be reduced with rear access.",
            "TDC3-7",
            "LDR-1                 LDR-2",
            "3. Rear yard setbacks are 15 feet unless access is from a rear yard",
            "(20 feet).",
        ]
    )
    table = read_tables(text)[0]

    assert table.notes[3] == (
        "Rear yard setbacks are 15 feet unless access is from a rear yard (20 feet)."
    )
    # The page stamp is not the wrap of note 1: a definition's wrap is the
    # line immediately after it, and nothing survives a page break to claim it.
    assert table.notes[1] == "Front yard setback may be reduced with rear access."


def test_each_table_numbers_its_own_notes() -> None:
    # Happy Valley's note 3 exempts cottage clusters from lot coverage under
    # one table and sets a townhouse side setback under the next. One shared
    # dictionary hands a value the wrong condition entirely.
    text = "\n".join(
        [
            "Standard              R-5      R-7",
            "Maximum height        35 ft.1  35 ft.1",
            "Table Notes",
            "1. The first table's condition.",
            "Standard              R-9      R-11",
            "Maximum height        45 ft.1  45 ft.1",
            "Table Notes",
            "1. The second table's condition.",
        ]
    )
    first, second = read_tables(text)[:2]

    assert first.notes[1] == "The first table's condition."
    assert second.notes[1] == "The second table's condition."


def test_a_flowed_note_block_defines_the_markers_above_it() -> None:
    # Where the grid was too wide to align, every cell is its own line — and
    # so is every footnote marker, with its text on the line after.
    text = "\n".join(
        [
            "R-5",
            "R-7",
            "Lot size (minimum)",
            "2,000 sf9",
            "3,000 sf",
            "NOTES:",
            "9",
            "Each townhouse lot shall have a minimum size of 2,000 square feet.",
        ]
    )
    sfa = next(c for c in _grid(text)["R-5"] if c.field == "min_lot_sqft")

    assert sfa.value == 2000
    assert sfa.notes == (
        "Each townhouse lot shall have a minimum size of 2,000 square feet.",
    )


# --- columns that are not zones ---------------------------------------


FAIRVIEW_GRID = """
Table 19.30.030.A Dimensional Standards for Residential Districts
R-6
R-7.5
R-10
Townhouse Overlay
Residential Medium (RM)
Additional Standards and Exceptions
1. Minimum Lot Size (sq. ft.)
a. Single Unit
6,000
7,500
10,000
Existing only
NA
d. Quadplex
6,000
7,500
10,000
NA
2,500 per unit
3. Minimum Net Density (units/acre)
a. Single Unit
5.8
4.6
3.5
NA
NA
7. Front Yard Setback Minimum
10 feet
11 feet
12 feet
13 feet
14 feet
19.30.030(B)(1)(b)
8. Front Yard Setback Maximum
30 feet
30 feet
30 feet
30 feet
30 feet
"""


def test_a_named_column_that_is_not_a_zone_still_holds_its_place() -> None:
    # Three zone codes, then "Townhouse Overlay" — counting only the codes
    # makes a five-value row look three wide, and the overrun refusal then
    # throws the row away. Thirty-six Fairview values sat behind that.
    grids = _grid(FAIRVIEW_GRID)

    assert [c.value for c in grids["R-6"] if c.field == "setback_front_ft"] == [10]
    assert [c.value for c in grids["R-7.5"] if c.field == "setback_front_ft"] == [11]
    assert [c.value for c in grids["R-10"] if c.field == "setback_front_ft"] == [12]


def test_a_column_naming_no_zone_files_nothing() -> None:
    grids = _grid(FAIRVIEW_GRID)

    # The Townhouse Overlay column's 13 feet belongs to no zone in the file
    # and is filed under none, while the RM column's 14 feet is filed under RM.
    assert 13 not in [c.value for zone in grids for c in grids[zone]]
    assert [c.value for c in grids["RM"] if c.field == "setback_front_ft"] == [14]


def test_a_maximum_row_is_not_the_minimum_field() -> None:
    # "8. Front Yard Setback Maximum" is a build-to line printed on the next
    # row of the same table. Read as the minimum it becomes a second number
    # for one field — a disagreement the document never states.
    grids = _grid(FAIRVIEW_GRID)

    assert [c.value for c in grids["R-6"] if c.field == "setback_front_ft"] == [10]


def test_the_row_label_may_carry_its_enumerator() -> None:
    assert any(c.field == "setback_front_ft" for c in _grid(FAIRVIEW_GRID)["R-6"])


def test_a_typed_sub_row_takes_its_unit_from_the_heading_above_it() -> None:
    # "d. Quadplex" says nothing about square feet; "1. Minimum Lot Size
    # (sq. ft.)" does. Without the heading the bare 6,000 parses as nothing.
    quad = [c for c in _grid(FAIRVIEW_GRID)["R-6"] if c.housing_type == "quadplex"]

    assert [(c.field, c.value) for c in quad] == [("min_lot_sqft", 6000)]


def test_a_new_numbered_standard_ends_the_one_above_it() -> None:
    # Density is numbered like lot size and is not lot size. Letting the block
    # survive filed 5.8 units per acre as a 5.8 square foot minimum lot.
    assert 5.8 not in [c.value for c in _grid(FAIRVIEW_GRID)["R-6"]]


def test_a_cell_stating_another_basis_does_not_refuse_the_row() -> None:
    # "2,500 per unit" under the RM column is a standard on a different basis:
    # nothing may be filed from it, and breaking on it would discard the three
    # plain lot sizes printed beside it.
    assert [c.value for c in _grid(FAIRVIEW_GRID)["R-10"] if c.field == "min_lot_sqft"] == [10000]
