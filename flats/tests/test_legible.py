"""Rendering a code document better without editing it.

The one thing these tests exist to hold is that the stored bytes and the line
numbering come out the other side untouched. Every rule in FLATS is a citation
to a line number; a cleanup that dropped a blank line or joined two wrapped
ones would move six hundred citations by one and there would be nothing on
screen to say so.

The second thing is that a table row is not prose. Its runs of spaces are the
only surviving evidence of which column a number sat in, and squeezing them
produces something that reads better and means less.
"""

from __future__ import annotations

import pytest

from flats.encode.legible import Line, is_grid, legible, marker, read

pytestmark = pytest.mark.unit


# --- the line numbering, which is what everything else cites --------------


def test_every_line_keeps_its_number_including_the_blank_ones():
    """A dropped blank line moves every citation below it by one."""
    text = "19.30.030 Dimensional standards.\n\n\nA. The minimum side yard is 10 feet.\n"

    got = read(text)

    assert [x.n for x in got] == [1, 2, 3, 4]
    assert got[3].shown.startswith("A. The minimum side yard")


def test_a_window_carries_the_numbering_it_was_cut_from():
    """A card shows lines 340-360 of a chapter. They are still 340-360."""
    got = read("first shown line\nsecond shown line", first=340)

    assert [x.n for x in got] == [340, 341]


def test_the_stored_bytes_are_returned_untouched_beside_the_shown_ones():
    """`raw` is the audit trail. A reviewer who suspects the cleanup can see
    through it without leaving the page."""
    got = read("   A.  The minimum  side yard is 10 feet.  ")

    assert got[0].raw == "   A.  The minimum  side yard is 10 feet.  "
    assert got[0].shown == "A. The minimum side yard is 10 feet."


# --- prose, where horizontal position means nothing -----------------------


def test_justification_spacing_is_squeezed():
    assert legible("The  minimum   lot   area is 7,000  square feet.") == (
        "The minimum lot area is 7,000 square feet."
    )


def test_a_hyphen_the_extractor_left_hanging_is_not_guessed_at():
    """Oregon code PDFs are full of "street- side" and "require- ments". The
    first wants joining, the second wants the hyphen gone, and nothing short of
    a dictionary tells them apart -- so neither is touched. Printing a word the
    code does not contain, on the one screen whose job is showing a reviewer
    what the code says, is worse than printing an ugly one."""
    assert legible("0 feet front and street- side; 15 feet rear.") == (
        "0 feet front and street- side; 15 feet rear."
    )
    assert legible("Low Density Residential-  7") == "Low Density Residential- 7"


def test_leading_indentation_is_dropped_from_prose():
    assert legible("          B. Lot Dimensions. All lots shall have") == (
        "B. Lot Dimensions. All lots shall have"
    )


# --- grids, where horizontal position is the only thing that means anything


def test_a_table_row_is_left_exactly_as_it_is():
    """This is Lake Oswego's R-5 setback row. The gaps are the columns, and the
    columns are the only evidence of which zone each number belongs to."""
    row = (
        "Attached Dwellings, Including Duplexes, Triplexes, Quadplexes  10"
        "        10 - Exterior Wall 0 - Attached Wall          10"
    )

    got = read(row)[0]

    assert got.kind == "grid"
    assert got.shown == row.rstrip(), "not one space of the column geometry moved"


def test_a_line_with_one_wide_gap_is_a_grid_not_a_sentence():
    """Biased toward calling it a grid. Squeezing a table loses information;
    leaving a sentence wide loses nothing but a little tidiness."""
    assert is_grid("Front (ft.)                    20")
    assert not is_grid("The minimum interior side yard is 10 feet.")
    # And a prose line that happens to carry a wide gap is read as a grid, on
    # purpose. It comes out a little wide; nothing is lost.
    assert is_grid("A.   Lot Size.  All VSF lots shall be no less than 4,000 sq ft.")


def test_a_blank_line_is_neither():
    got = read("\n")[0]

    assert got.kind == "blank"
    assert got.shown == ""


def test_the_grid_threshold_matches_the_review_card():
    """The card flags a card as table-derived on three or more spaces. If this
    module disagreed, a line would be squeezed here and then flagged there as a
    table the reviewer should read closely -- worse than either alone."""
    from app.api.routers.ui_flats import _GRID  # noqa: PLC0415 — read at assert time

    row = "Front (ft.)   20"
    assert bool(_GRID.match(row.strip())) is is_grid(row)


# --- navigation ----------------------------------------------------------


@pytest.mark.parametrize(
    "line,found",
    [
        ("B. Lot Dimensions. All lots in the VSF zone", "B."),
        ("   (2) Additional Setback Standards.", "(2)"),
        ("iv. Corner Lots.", "iv."),
        ("6. Maximum Lot Depth", "6."),
        ("The minimum lot area is 7,000 square feet.", ""),
    ],
)
def test_the_subsection_marker_is_pulled_out(line: str, found: str):
    assert marker(line) == found


def test_a_line_is_frozen():
    """It is shown to a reviewer and quoted into a feedback bundle. Nothing
    downstream may edit what was on screen after the fact."""
    got = Line(1, "raw", "shown", "prose")

    with pytest.raises(Exception):
        got.shown = "something else"  # type: ignore[misc]
