"""Portland's Scenic Resource overlay "s" (PCC 33.480; FOLLOWUPS 204 item 1).

Two halves. The scenic corridor setback of 33.480.040.B.2.a "applies along
street lot lines that abut the Scenic Corridor", so it is a number about ONE
street line: read per line off the city's Scenic Corridors layer and applied
to that line as the larger of it and the zone's own. Everything else in the
chapter is unmeasured, so a lot the overlay touches is a closer look whether
or not the pod clears the setback (flats/rules/resource_overlays.py
``pdx_scenic``).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from shapely.geometry import LineString, mapping

from flats.geom.corridor import (
    CORRIDOR_FACTS,
    LINE_MAPS,
    LINE_ONLY,
    TIGHTENS,
    CorridorMap,
    load_maps,
    observed_corridors,
    off_corridor_lines,
    on_line_maps,
)
from flats.geom.edges import Edge, EdgeClass
from flats.geom.envelope import Setbacks
from flats.ingest.quadfit import S5O_COLUMNS, SCENIC_COLUMN, envelope_for, lot_from_row
from flats.ingest.sources import load_pipeline
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import close_entailed
from flats.rules.resource_overlays import BY_KEY
from flats.score import flags as flag_plan
from flats.score.screen import CLOSER_LOOK_RESOURCE, Triage
from flats.tests.test_corridor import ALONG, CORNER, CROSS, EDGES, FRONT, PDX, X0, Y0, _cut
from flats.tests.test_screen import LOT, run

pytestmark = pytest.mark.unit

SCENIC = "scenic_corridor"
FIELD = "setback_scenic_corridor_ft"


def drive(*lines: LineString) -> CorridorMap:
    """The scenic drives, as the city draws them: lines with no street name."""
    return CorridorMap.from_lines(SCENIC, [PDX], lines or (ALONG,))


@pytest.fixture(scope="module")
def pdx_rules():
    from flats.rules.loader import load_rules
    from flats.rules.resolver import RuleSet

    return RuleSet(load_rules())


def _envelope(pdx_rules, zone: str, edges: list, maps: list, **over: object):
    lot = lot_from_row(_cut(edges, zone=zone, **over), corridors=maps)
    held = [name for name, value in close_entailed(lot.observed).items() if value]
    return lot, envelope_for(lot, pdx_rules.resolve(PDX, zone, conditions=held))


# --- the map ---------------------------------------------------------------


def test_the_scenic_map_marks_lines_and_answers_no_fact() -> None:
    """A per-line map: never a lot-level fact, never a relief, and nothing
    the Map 130-1 off-corridor reading counts."""
    assert LINE_MAPS == {"scenic_corridors_pdx": SCENIC}
    assert SCENIC in LINE_ONLY and SCENIC not in TIGHTENS and SCENIC not in CORRIDOR_FACTS
    assert observed_corridors(EDGES, PDX, [drive()]) == {}
    assert off_corridor_lines(CORNER, PDX, [drive()]) == (False,) * 4


def test_only_the_street_line_on_the_drive_is_on_it() -> None:
    # Interior lot: the front line; a corner on the drive: the front, not the
    # cross street's line.
    assert on_line_maps(EDGES, PDX, [drive()], SCENIC) == (True, False, False, False)
    assert on_line_maps(CORNER, PDX, [drive()], SCENIC) == (True, False, False, False)
    # A drive along the cross street instead marks that line alone.
    assert on_line_maps(CORNER, PDX, [drive(CROSS)], SCENIC) == (False, False, False, True)
    # A drive a block away marks none.
    far = LineString([(X0 - 500, Y0 - 400), (X0 + 500, Y0 - 400)])
    assert on_line_maps(EDGES, PDX, [drive(far)], SCENIC) == (False,) * 4


def test_a_lot_outside_portland_is_never_read() -> None:
    assert on_line_maps(EDGES, "or/multnomah/gresham", [drive()], SCENIC) == (False,) * 4
    assert on_line_maps(EDGES, "or/clackamas/oregon-city", [drive()], SCENIC) == (False,) * 4
    # Nor is another map's name answered off this one.
    assert on_line_maps(EDGES, PDX, [drive()], "civic_corridor_setback") == (False,) * 4


def test_load_maps_keeps_the_drives_and_drops_the_waterways_and_trails(tmp_path: Path) -> None:
    def feature(line: LineString, subtype: str) -> dict:
        return {"type": "Feature", "properties": {"Subtype": subtype}, "geometry": mapping(line)}

    river = LineString([(X0 - 500, Y0 + 130), (X0 + 500, Y0 + 130)])
    fc = {
        "type": "FeatureCollection",
        "features": [
            feature(ALONG, "Scenic Drive"),
            feature(river, "Scenic Waterway"),
            feature(river, "Scenic Trail/Path"),
        ],
    }
    (tmp_path / "scenic_corridors_pdx.geojson").write_text(json.dumps(fc), encoding="utf-8")
    (held,) = load_maps(tmp_path)
    assert held.condition == SCENIC and held.covers(PDX)
    assert len(held.corridor.lines) == 1
    assert on_line_maps(EDGES, PDX, [held], SCENIC) == (True, False, False, False)
    ds = load_pipeline().datasets["scenic_corridors_pdx"]
    assert ds.url.endswith("/BPS_Zoning_Code_Layers/MapServer/89")
    assert list(ds.serves) == [PDX]


# --- the number ------------------------------------------------------------


def _edge(cls: EdgeClass, **over: object) -> Edge:
    return Edge(0.0, 0.0, 50.0, 0.0, length_ft=50.0, bearing_deg=90.0, cls=cls, **over)


def test_a_scenic_line_takes_the_larger_of_the_two_setbacks() -> None:
    held = Setbacks(front_ft=10, side_ft=5, rear_ft=5, scenic_corridor_ft=20)
    assert held.for_edge(_edge(EdgeClass.front, on_scenic=True)) == 20
    # The same lot's other lines, and a street line off the drive, keep theirs.
    assert held.for_edge(_edge(EdgeClass.front)) == 10
    assert held.for_edge(_edge(EdgeClass.side)) == 5
    assert held.for_edge(_edge(EdgeClass.rear)) == 5
    # A through lot's far street line is flagged whatever its class.
    assert held.for_edge(_edge(EdgeClass.rear, on_scenic=True)) == 20
    # Table 480-1 note [1]: a larger setback supersedes; a smaller scenic
    # number (RM2's 3 ft) never shrinks the zone's own.
    assert replace(held, front_ft=25).for_edge(_edge(EdgeClass.front, on_scenic=True)) == 25
    assert replace(held, scenic_corridor_ft=3).for_edge(_edge(EdgeClass.front, on_scenic=True)) == 10
    # A code that states no scenic setback adds nothing to a flagged line.
    assert replace(held, scenic_corridor_ft=None).for_edge(_edge(EdgeClass.front, on_scenic=True)) == 10
    # Right-of-way given up is still added on top.
    assert held.for_edge(_edge(EdgeClass.front, on_scenic=True, dedication_ft=4.0)) == 24


@pytest.mark.parametrize("zone", ["RF", "R20", "R10", "R7", "R5", "R2.5", "RM1", "CM2", "CE", "CI1"])
def test_all_other_base_zones_take_twenty(pdx_rules, zone: str) -> None:
    value = pdx_rules.resolve(PDX, zone).values[FIELD]
    assert value.value == 20
    text = ProvenanceStore().quote(value.prov.quote)
    assert "applies along" in text and "abut the Scenic Corridor" in text
    assert "All other base zones 20" in text


def test_rm2_takes_its_own_row(pdx_rules) -> None:
    value = pdx_rules.resolve(PDX, "RM2").values[FIELD]
    assert value.value == 3
    assert "RM2 3" in ProvenanceStore().quote(value.prov.quote)


# --- the lot ---------------------------------------------------------------


def test_a_lot_on_a_scenic_drive_gives_up_twenty_feet_along_it(pdx_rules) -> None:
    """Setback violated before: R5's front setback is 10 ft, so a pod drawn
    in the first 20 ft stood inside the scenic corridor setback."""
    lot, env = _envelope(pdx_rules, "R5", EDGES, [drive()], ovl_pdx_scenic=True)
    assert [e.on_scenic for e in lot.edges.edges] == [True, False, False, False]
    assert env.source == "flats" and env.setbacks.scenic_corridor_ft == 20
    # 50 x 100, 5 ft sides and rear: 40 wide, 100 - 20 - 5 deep.
    assert env.sqft == pytest.approx(40 * 75)
    # Setback met: nothing of the envelope lies in the first 20 ft.
    assert env.geom.bounds[1] == pytest.approx(Y0 + 20)


def test_a_lot_off_the_drive_or_outside_the_overlay_keeps_its_front_setback(pdx_rules) -> None:
    # The overlay touches the lot, but the drive is a block away: no line is on it.
    far = LineString([(X0 - 500, Y0 - 400), (X0 + 500, Y0 - 400)])
    lot, env = _envelope(pdx_rules, "R5", EDGES, [drive(far)], ovl_pdx_scenic=True)
    assert not any(e.on_scenic for e in lot.edges.edges)
    assert env.sqft == pytest.approx(40 * 85)
    # On the drive, but s5o answered the lot clear of the Scenic Resource
    # zone: the chapter reaches development "within the Scenic Resource zone".
    lot, env = _envelope(pdx_rules, "R5", EDGES, [drive()], ovl_pdx_scenic=False)
    assert not any(e.on_scenic for e in lot.edges.edges)
    assert env.sqft == pytest.approx(40 * 85)
    # Without the maps in hand nothing is read per line.
    lot, env = _envelope(pdx_rules, "R5", EDGES, [], ovl_pdx_scenic=True)
    assert not any(e.on_scenic for e in lot.edges.edges)


def test_a_row_with_no_overlay_answer_keeps_the_setback(pdx_rules) -> None:
    # An s5o written before the layer existed says nothing: the tight side.
    lot, env = _envelope(pdx_rules, "R5", EDGES, [drive()])
    assert [e.on_scenic for e in lot.edges.edges] == [True, False, False, False]
    assert env.sqft == pytest.approx(40 * 75)
    assert SCENIC_COLUMN in S5O_COLUMNS


def test_a_corner_lot_gives_it_up_along_the_drive_only(pdx_rules) -> None:
    lot, env = _envelope(pdx_rules, "R5", CORNER, [drive()], ovl_pdx_scenic=True)
    assert [e.on_scenic for e in lot.edges.edges] == [True, False, False, False]
    plain, base = _envelope(pdx_rules, "R5", CORNER, [], ovl_pdx_scenic=True)
    # Only the depth off the drive changes: 10 ft more along the south line.
    width = base.geom.bounds[2] - base.geom.bounds[0]
    assert env.geom.bounds[1] == pytest.approx(Y0 + 20)
    assert base.sqft - env.sqft == pytest.approx(10 * width)


def test_rm2_on_a_scenic_drive_keeps_its_ten(pdx_rules) -> None:
    lot, env = _envelope(pdx_rules, "RM2", EDGES, [drive()], ovl_pdx_scenic=True)
    assert lot.edges.edges[0].on_scenic and env.setbacks.scenic_corridor_ft == 3
    _, bare = _envelope(pdx_rules, "RM2", EDGES, [], ovl_pdx_scenic=True)
    assert env.sqft == pytest.approx(bare.sqft)


def test_a_gresham_lot_on_the_same_line_is_untouched(pdx_rules) -> None:
    lot = lot_from_row(_cut(EDGES, jurisdiction="gresham", zone="LDR-5"), corridors=[drive()])
    assert not any(e.on_scenic for e in lot.edges.edges)
    assert on_line_maps([FRONT], "or/multnomah/gresham", [drive()], SCENIC) == (False,)


# --- the closer look -------------------------------------------------------


def test_a_lot_the_scenic_overlay_touches_is_a_closer_look() -> None:
    """Whether or not the pod clears the setback: the chapter's structure
    length, landscaped setback, trees and view-corridor heights are not
    measured, so no lot in the overlay ends GREEN."""
    area = BY_KEY["pdx_scenic"]
    assert "33.480" in area.cite and area.column == SCENIC_COLUMN
    inside = lot_from_row(_cut(EDGES, zone="R5", ovl_pdx_scenic=True)).facts
    assert inside.resource_permits == ("pdx_scenic",)
    got = run(lot=replace(LOT, resource_permits=inside.resource_permits))
    assert got.triage is Triage.yellow and got.colour is flag_plan.Colour.yellow
    assert got.reasons == (CLOSER_LOOK_RESOURCE,)
    # Clear of the overlay, and a row written before the layer: nothing said.
    assert lot_from_row(_cut(EDGES, zone="R5", ovl_pdx_scenic=False)).facts.resource_permits == ()
    assert lot_from_row(_cut(EDGES, zone="R5")).facts.resource_permits == ()
