"""A column of the same planting standard, wrapped onto its own line.

Portland's dimensional table carries "Landscape Buffer Abutting an RF - RM4 or
RMP Zoned Lot (see 33.130.215.B)" with six columns of "10 ft. @ L3". The row
wraps, and the columns that did not fit land on the second line with nothing in
front of them -- "L3    L3    L3    L3" -- where the guard that already knows an
L-number is a planting standard has no word or "@" to recognise it by. All four
read as a limited use carrying note 3, and Chapter 33.130 reported an orphan
asking somebody to go and find a note that was never written.

The repeat on its own proves nothing. Gresham writes "L1  L1  L1" across a use
table's zone columns and means a limited use carrying note 1 in each of them,
which is exactly what a marker is; planting every repeat cost thirteen real
markers in five documents. What earns the reading is the line above.
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import LANDSCAPE_RUN, census
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

DOC = "or/multnomah/portland/33.130.txt"


@pytest.fixture(scope="module")
def chapter():
    return census(
        ProvenanceStore().load(DOC).text, layer="or/multnomah/portland", doc=DOC
    )


# --- what the pattern is and is not -----------------------------------------


def test_the_run_needs_the_same_code_twice() -> None:
    assert LANDSCAPE_RUN.search("L3    L3    L3    L3").group("code") == "L3"
    assert LANDSCAPE_RUN.search("F2 F2").group("code") == "F2"
    assert LANDSCAPE_RUN.search("L3") is None
    assert LANDSCAPE_RUN.search("L1    L2    L3") is None


# --- what the line above decides --------------------------------------------


def test_the_wrap_of_a_planted_row_is_stepped_over() -> None:
    seen = census(
        "\n".join(
            [
                "Landscape Buffer    10 ft. @ L3    10 ft. @ L3    10 ft. @ L3",
                "(see 33.130.215.B)  L3             L3             L3",
            ]
        ),
        doc="d.txt",
    )
    assert seen.unbodied == ()


def test_but_a_use_tables_repeated_permission_is_still_a_marker() -> None:
    """Same shape, no planted line above it. Three zones, one limited use,
    one note -- and the note is what the marker is asking for."""
    seen = census(
        "\n".join(
            [
                "Household Living    L1    L1    L1",
                "Group Living        L1    L1    L1",
            ]
        ),
        doc="d.txt",
    )
    # One per row, because a marker is counted where it is written.
    assert [(m.line, m.mark) for m in seen.unbodied] == [(1, "1"), (2, "1")]


# --- what Chapter 33.130 says now -------------------------------------------


def test_the_dimensional_table_stops_asking_for_a_note_three(chapter) -> None:
    assert chapter.unbodied == ()
    assert [b.head for b in chapter.blocks] == [667, 736, 219]


def test_the_note_the_table_really_does_carry_is_untouched(chapter) -> None:
    """Note [1] caps Household Living density on sites with no Retail Sales
    And Service or Office use. It is the chapter's one real footnote and it is
    still answered."""
    first = next(b for b in chapter.bodies if b.line == 668)
    assert "maximum density for Household Living" in first.text
