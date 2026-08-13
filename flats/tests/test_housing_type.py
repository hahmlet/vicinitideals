"""The housing-type dimension: tables whose rows name who, not what.

Gresham's Table 4.0130 states one standard per group heading ("B. Minimum Lot
Size") and then a row per housing type under it — Duplex, Townhouse, All other
uses. Three cities name this dimension (Gresham, Troutdale's grid family, Wood
Village's MR columns); this file covers the row-level case. The failure modes
are all silent substitutions: a duplex's number corroborating a townhome's
standard, "All other uses" speaking for a quadplex the table lists explicitly,
a glued footnote promoting a conditional height to an unconditional one.

Column geometry mirrors the real chapter PDF: a header of bare zone codes with
no label cell, lettered group headings with no colon, footnote digits fused to
the unit ("35 ft.12").
"""

from __future__ import annotations

from typing import Sequence

import pytest

from flats.encode.corroborate import Verdict, check_zone
from flats.encode.tables import _housing_type, candidates_for, read_tables
from flats.rules.model import Provenance, Value

pytestmark = pytest.mark.unit


def _gline(label: str, cells: Sequence[str] = (), at: Sequence[int] = (40, 58)) -> str:
    out = f"  {label}" if label else ""
    for text, col in zip(cells, at):
        out += " " * (col - len(out)) + text
    return out


GRESHAM_GRID = "\n".join(
    [
        _gline("Table 9: Development Requirements"),
        _gline("", ("R-5", "R-7")),
        _gline("B. Minimum Lot Size2"),
        _gline("Duplex", ("5,000 sq. ft.", "7,000 sq. ft.")),
        _gline("Townhouse", ("None", "None")),
        _gline("All other uses", ("5,000 sq. ft.", "6,000 sq. ft.")),
        _gline("E. Minimum Lot Width"),
        _gline("1. Width at building line: Interior lot"),
        _gline("Duplex, Triplex, Quadplex,", ("35 ft.", "40 ft.")),
        _gline("and Cottage Cluster"),
        _gline("Townhouse", ("16 ft.", "16 ft.")),
        _gline("All other uses", ("99 ft.", "99 ft.")),
        _gline("2. Width at building line: Corner lot"),
        _gline("Townhouse", ("20 ft.", "20 ft.")),
        _gline("H. Maximum Building Height"),
        _gline("Townhouse", ("35 ft.12", "35 ft.")),
        _gline("All other uses", ("35 ft.", "35 ft.")),
    ]
)

CITE = {
    "cite": "GDC Table 4.0130",
    "url": "https://example.test/gdc",
    "retrieved": "2026-08-13",
}


def value(number: float | int, name: str = "min_lot_sqft") -> Value:
    return Value(name=name, value=number, prov=Provenance(**CITE))


def r5() -> list:
    return candidates_for(read_tables(GRESHAM_GRID)[0], "R-5", path="doc.txt")


def for_field(name: str) -> list:
    return [c for c in r5() if c.field == name]


# --- the reader --------------------------------------------------------


def test_a_bare_zone_header_anchors_the_table() -> None:
    # Gresham's header is nothing but district names — no "Standard" cell.
    assert len(read_tables(GRESHAM_GRID)) == 1
    assert for_field("min_lot_sqft")


def test_a_lettered_heading_is_a_group_not_a_row_continuation() -> None:
    # Without the heading branch "B. Minimum Lot Size2" glues onto the row
    # above it and every housing-type row after it keeps the wrong group.
    lots = for_field("min_lot_sqft")

    assert {c.value for c in lots} == {5000}
    assert all(c.housing_type for c in lots)


def test_a_typed_row_carries_its_housing_type() -> None:
    by_type = {c.housing_type: c.value for c in for_field("min_lot_width_ft")}

    assert by_type["townhouse"] == 16
    assert by_type["default"] == 99


def test_a_compound_label_names_every_type_it_lists() -> None:
    assert _housing_type("Duplex, Triplex, Quadplex, and Cottage Cluster") == (
        "duplex+triplex+quadplex+cottage_cluster"
    )


def test_an_except_label_is_refused() -> None:
    # "All uses except X" applies to the pod only if X is not the pod, and
    # that is not decidable from a row label.
    assert _housing_type("All uses except Manufactured Dwelling Parks") is None


def test_a_corner_variant_stays_out_of_an_interior_standard() -> None:
    # The 20 ft. corner-lot width would otherwise sit beside the interior
    # 16 ft. as a bogus second reading of the same field.
    assert 20 not in {c.value for c in for_field("min_lot_width_ft")}


def test_a_glued_footnote_keeps_the_number_conditional() -> None:
    # "35 ft.12" is a superscript that lost its baseline. Reading 35 and
    # dropping the 12 would encode the base case of a conditional standard.
    townhouse = next(
        c for c in for_field("max_height_ft") if c.housing_type == "townhouse"
    )

    assert townhouse.value == 35
    assert townhouse.notes == ("footnote 12 (text not captured)",)


def test_a_none_cell_produces_no_candidate() -> None:
    # Townhouse minimum lot size is "None" — no minimum at all. That is a
    # standard this reader cannot state as a number, not a zero.
    assert not any(c.housing_type == "townhouse" for c in for_field("min_lot_sqft"))


# --- selection ---------------------------------------------------------


def verdicts(values: dict[str, Value]) -> dict:
    found = check_zone(
        GRESHAM_GRID,
        layer="or/multnomah/gresham",
        zone="R-5",
        values=values,
        path="doc.txt",
    )
    return {f.field: f for f in found}


def test_the_default_row_speaks_while_quadplexes_are_unnamed() -> None:
    # Minimum lot size lists Duplex, Townhouse, All other uses. A quadplex is
    # in "other" implicitly, so the 5,000 corroborates the encoded 5,000 —
    # and the duplex row's identical number is not what did it.
    found = verdicts({"min_lot_sqft": value(5000)})["min_lot_sqft"]

    assert found.verdict is Verdict.agrees
    assert found.found == (5000,)


def test_an_explicit_quadplex_row_silences_the_default() -> None:
    # Lot width names quadplexes outright, so "All other uses" provably
    # excludes them: its 99 must not appear as evidence.
    found = verdicts({"min_lot_width_ft": value(16, "min_lot_width_ft")})[
        "min_lot_width_ft"
    ]

    assert 99 not in found.found


def test_both_pod_classifications_survive_to_disagree() -> None:
    # Townhouse says 16, the quadplex compound says 35. Which one is the
    # pod's is a plat-path decision; the field reads as multi-value and
    # attach refuses, rather than either number being picked silently.
    found = verdicts({"min_lot_width_ft": value(16, "min_lot_width_ft")})[
        "min_lot_width_ft"
    ]

    assert found.found == (16, 35)


def test_rows_for_other_types_alone_are_no_evidence() -> None:
    text = "\n".join(
        [
            _gline("", ("R-5", "R-7")),
            _gline("B. Minimum Lot Size"),
            _gline("Duplex", ("5,000 sq. ft.", "7,000 sq. ft.")),
        ]
    )

    found = check_zone(
        text,
        layer="or/multnomah/gresham",
        zone="R-5",
        values={"min_lot_sqft": value(5000)},
        path="doc.txt",
    )

    assert {f.field: f.verdict for f in found}["min_lot_sqft"] is Verdict.unsupported


# --- table-level: one grid per type (Troutdale's family) ---------------


def _tline(label: str, cells: Sequence[str] = (), at: Sequence[int] = (38, 50)) -> str:
    out = label
    for text, col in zip(cells, at):
        out += " " * (col - len(out)) + text
    return out


TROUTDALE_BLOCKS = "\n".join(
    [
        _tline("       A.     Single-family detached and duplex dwellings:"),
        _tline(""),
        _tline("Dimensional Standard", ("R-5", "R-7")),
        _tline("Setbacks (ft):"),
        _tline("   Front yard", ("20", "20")),
        _tline("   Side yard", ("10", "7.5")),
        _tline(""),
        _tline("       C.     Townhouse dwellings:"),
        _tline(""),
        _tline("Dimensional Standard", ("R-5", "R-7")),
        _tline("Setbacks (ft):"),
        _tline("   Front yard see note 1", ("10", "10")),
        _tline("   Side yard", ("5", "5")),
    ]
)


def test_the_grid_inherits_the_type_heading_above_its_header() -> None:
    # "C. Townhouse dwellings:" is printed above the header line — outside
    # the table's own span. Every row of the grid below it is a townhouse row.
    tables = read_tables(TROUTDALE_BLOCKS)
    typed = {
        c.housing_type
        for t in tables
        for c in candidates_for(t, "R-5", path="doc.txt")
    }

    assert "single_detached+duplex" in typed
    assert "townhouse" in typed
    assert "" not in typed


def test_a_glued_note_ref_conditions_the_row_it_lost_its_cell_in() -> None:
    # "Front yard see note 1" is a label wearing another column's note
    # pointer. The row still reads as the front setback, and every value in
    # it carries the ref as a condition — the direction that refuses a quote
    # rather than quoting a conditional number clean.
    tables = read_tables(TROUTDALE_BLOCKS)
    fronts = [
        c
        for t in tables
        for c in candidates_for(t, "R-5", path="doc.txt")
        if c.field == "setback_front_ft" and c.housing_type == "townhouse"
    ]

    assert [c.value for c in fronts] == [10]
    assert fronts[0].notes == ("see note 1 (text not captured)",)


def test_selection_reads_the_townhouse_grid_not_the_detached_one() -> None:
    # The detached/duplex grid says 5 or 10; the townhouse grid says 5. The
    # encoded 5 corroborates against the pod's own grid only.
    found = check_zone(
        TROUTDALE_BLOCKS,
        layer="or/multnomah/troutdale",
        zone="R-5",
        values={"setback_side_ft": value(5, "setback_side_ft")},
        path="doc.txt",
    )
    side = {f.field: f for f in found}["setback_side_ft"]

    assert side.verdict is Verdict.agrees
    assert side.found == (5,)


def test_a_lot_context_sub_label_is_not_a_default_row() -> None:
    # Happy Valley's frontage rows sub-label by lot context. "All other
    # lots" must not read as the pod's "all other uses" row: it is a tier
    # of lots, and every housing type is in it.
    assert _housing_type("All other lots") is None
    assert _housing_type("All other uses") == "default"
