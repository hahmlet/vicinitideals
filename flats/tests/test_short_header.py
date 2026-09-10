"""A table whose header lost a column, and the cell that pays for it.

``ragged.py`` asks whether a use table's body rows agree with each other. It
cannot see the failure here, because they do: every row of Clackamas ZDO Table
510-2 prints eleven cells, and it is the *header* that prints ten. Subsection
510.02 names eleven urban commercial and mixed-use districts; the stored header
runs NC, C-2, RCC, RTL, CC, C-3, PMU, OA, OC, RCO, having dropped Station
Community Mixed Use from between PMU and OA.

Counting into that header does not fail loudly. It reads the eighth cell of
each row -- SCMU's -- as OA's, the ninth as OC's, and so on to the end of the
row, and each of those values arrives with the right field, the right units and
a citation pointing at exactly the line it was taken from. The minimum street
frontage row is the one that shows: ten of its eleven cells say "None" and the
eighth says "100 feet", so the reader claimed a 100-foot frontage minimum for a
district whose own cell is blank.

The refusal that was supposed to catch this asked only whether the line after a
row's last cell parses as a *measurement*. A row one number too long and a row
one "None" too long are the same failure, and only the first was being caught.

Table 315-4 in the same chapter is the same shape from the opposite cause: it
is seven districts wide and the seventh is RCHDR, which the zone-code pattern
could not spell -- it allowed four capitals and this one has five. The header
came up six wide against seven-cell rows, and VA's 45-foot height limit read
correctly only because the column that went missing was the last one.
"""

from __future__ import annotations

import pytest

from flats.encode.tables import _ZONE, read_stacked_grids
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"
ZDO_510 = f"{CLACKAMAS}/zdo.510.txt"
ZDO_315 = f"{CLACKAMAS}/zdo.315.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def read(store: ProvenanceStore, path: str) -> dict[str, list]:
    text = store.text_path(path).read_text(encoding="utf-8")
    return read_stacked_grids(text, path=path)


# --- the shape, in the small ---------------------------------------------


HEADER_SHORT = "\n".join(
    [
        "Standard",
        "R-1",
        "R-2",
        "R-3",
        "Minimum Lot Size",
        "5,000 square feet",
        "4,000 square feet",
        "3,000 square feet",
        "2,000 square feet",
        "Minimum Front Setback",
        "20 feet",
        "15 feet",
        "10 feet",
        "5 feet",
        "",
    ]
)


def test_a_row_wider_than_its_header_is_refused_rather_than_shifted() -> None:
    """Four cells under three column heads is a header that lost one."""
    out = read_stacked_grids(HEADER_SHORT, path="x/y.txt")
    assert out == {}


def test_the_same_table_reads_once_its_header_names_every_column() -> None:
    """The refusal is about the mismatch, not about the rows themselves."""
    whole = HEADER_SHORT.replace("R-3\n", "R-3\nR-4\n")
    out = read_stacked_grids(whole, path="x/y.txt")
    assert {z: [(c.field, c.value) for c in cs] for z, cs in sorted(out.items())} == {
        "R-1": [("min_lot_sqft", 5000), ("setback_front_ft", 20)],
        "R-2": [("min_lot_sqft", 4000), ("setback_front_ft", 15)],
        "R-3": [("min_lot_sqft", 3000), ("setback_front_ft", 10)],
        "R-4": [("min_lot_sqft", 2000), ("setback_front_ft", 5)],
    }


def test_a_word_that_is_not_a_number_still_counts_as_a_cell() -> None:
    """"None" is an answer for a column, so a spare one is still an overrun.

    This is the case the old refusal missed. Every extra cell here says
    "None", so nothing about the row looks like a measurement out of place.
    """
    blanks = HEADER_SHORT.replace("2,000 square feet", "None").replace("5 feet\n", "None\n")
    assert read_stacked_grids(blanks, path="x/y.txt") == {}


# --- and in the corpus that found it --------------------------------------


def test_scmu_s_frontage_minimum_is_not_read_as_the_office_district_s(
    store: ProvenanceStore,
) -> None:
    """Table 510-2's eighth column is SCMU, and the header does not say so."""
    out = read(store, ZDO_510)
    assert not [c for c in out.get("OA", []) if c.field == "min_frontage_ft"]
    # Nor may it be quietly re-filed under the district the header dropped:
    # a header that lost a column cannot be counted into at all.
    assert "SCMU" not in out


def test_the_district_the_header_dropped_is_named_by_the_applicability_clause(
    store: ProvenanceStore,
) -> None:
    """So the loss is a fact about the document, not a guess about the table."""
    text = store.text_path(ZDO_510).read_text(encoding="utf-8")
    applies = next(line for line in text.splitlines() if line.startswith("Section 510 applies"))
    assert "Station Community Mixed Use (SCMU)" in applies
    header = text.splitlines()[1314:1324]
    assert header == ["NC", "C-2", "RCC", "RTL", "CC", "C-3", "PMU", "OA", "OC", "RCO"]


# --- a district code five letters long ------------------------------------


def test_a_five_letter_district_code_is_a_district_code() -> None:
    """RCHDR is a real Clackamas district and was unspellable to the reader."""
    assert _ZONE.match("RCHDR")
    assert _ZONE.match("SCMU")


def test_va_keeps_its_height_now_that_the_column_beside_it_is_countable(
    store: ProvenanceStore,
) -> None:
    """Table 315-4 is seven wide; six of the seven cells are "None"."""
    out = read(store, ZDO_315)
    heights = [(c.value, c.line) for c in out.get("VA", []) if c.field == "max_height_ft"]
    assert heights == [(45, 1523)]
