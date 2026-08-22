"""The mark welded to a row label, with the row's cells on the same line.

Gresham writes a use row as a label and its permissions::

    Cottage Cluster16                                    P
    Cottage Cluster16 P P P

The first is Table 4.0110's, laid out with column gaps, and `LABEL_MARKER`
finds it because `_markers` splits a gapped line into cells and the label is
one of them. The second is Table 4.1413's, printed single-spaced, so the label
and the permissions arrive as one run of words and the mark sits in the middle
of it -- where a rule anchored to the end of a cell cannot reach.

Eight rows in the corpus are printed that way, all in the Pleasant Valley and
Springwater chapters, and each was a note nobody was seen to point at.
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import _row_label_marks, census
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _chapter(store: ProvenanceStore, name: str):
    doc = f"{GRESHAM}/{name}.txt"
    return census(store.load(doc).text, layer=GRESHAM, doc=doc)


# --- what the shape is -------------------------------------------------------


def test_a_label_with_its_mark_and_its_permissions() -> None:
    assert _row_label_marks("Helliports15 NP NP NP") == ["15"]
    assert _row_label_marks("Cottage Cluster16 P P P") == ["16"]
    assert _row_label_marks("Multi-Family/Shared Housing Facility2 NP P P") == ["2"]
    assert _row_label_marks("Retail7,8 P P") == ["7", "8"]


def test_and_a_row_without_one_stays_without_one() -> None:
    assert _row_label_marks("Quadplex P P P") == []
    assert _row_label_marks("Single Detached Dwelling P P L1") == []


def test_the_digits_have_to_follow_a_lowercase_letter() -> None:
    """Which is what keeps a zone code out. Gresham's dimensional tables put
    "MDR-12" at the head of a row and Happy Valley writes "MUR-M3"; neither is
    a label numbered twelve or three."""
    assert _row_label_marks("MDR-12 P P P") == []
    assert _row_label_marks("MUR-M3 P P") == []


def test_and_the_rest_of_the_line_has_to_be_nothing_but_permissions() -> None:
    """A row states several of them, so one is not enough, and a word that is
    not a permission ends it. That second clause is what keeps prose out: the
    tail of a sentence is almost never two permission codes and nothing else."""
    assert _row_label_marks("Live-Work6 P") == []
    assert _row_label_marks("Landscaping shall be at least L3 L3") == []
    assert _row_label_marks("twenty (20) P P") == []


# --- what it finds in the corpus ---------------------------------------------


def test_the_five_single_spaced_rows_in_pleasant_valley(
    store: ProvenanceStore,
) -> None:
    got = _chapter(store, "4.1400.pleasant-valley")
    found = {(m.line, m.mark) for m in got.markers}
    assert {(140, "16"), (145, "2"), (157, "6"), (203, "15"), (531, "7")} <= found


def test_and_the_three_in_springwater(store: ProvenanceStore) -> None:
    got = _chapter(store, "4.1500.springwater")
    found = {(m.line, m.mark) for m in got.markers}
    assert {(147, "15"), (148, "1"), (208, "14")} <= found


def test_the_gapped_rows_are_read_the_way_they_always_were(
    store: ProvenanceStore,
) -> None:
    """Eighteen of the twenty-six welded row labels in the corpus already had
    their marks, by the column-gap path. This rule is not allowed to change
    them -- "Cottage Cluster16" with a gap before its P still reports one
    marker, numbered sixteen."""
    got = _chapter(store, "4.0100.residential")
    assert [m.mark for m in got.markers if m.line == 136] == ["16"]
    assert [m.mark for m in got.markers if m.line == 138] == ["4"]


def test_what_is_left_unmarked_and_why(store: ProvenanceStore) -> None:
    """Fourteen down to nine, and twelve down to nine. What remains is not this
    shape, and is worth naming because each is its own blindness.

    Notes 1 and 3 through 7 of Table 4.1431 are marked, on rows that read
    "Affordable Housing P1" and "Solar Energy Systems L/SUR3" -- a use table
    with one column, printed single-spaced. `_cell_row` wants either a column
    gap or two permission codes before it will read a line as a row, because
    "P1" in a paragraph is a design element, and a one-column table can offer
    neither.

    Note 1 of Table 4.1421 is marked mid-row: "5 ft. 5 ft. 20 ft.1 5 ft." with
    single spaces, where `GLUED_MARKER` is anchored to the end of a cell and
    there is no gap to split the cells apart by.

    Note 4 of Table 4.1424 is marked on "abutting LDR-PV4", a mark welded to a
    capital -- the shape this module refuses corpus-wide because permission
    codes wear it too."""
    pv = _chapter(store, "4.1400.pleasant-valley")
    assert [(b.line, b.mark) for b in pv.unmarked] == [
        (416, "1"),
        (690, "1"),
        (695, "4"),
        (845, "1"),
        (847, "3"),
        (848, "4"),
        (849, "5"),
        (850, "6"),
        (851, "7"),
    ]
    sw = _chapter(store, "4.1500.springwater")
    assert len(sw.unmarked) == 9
