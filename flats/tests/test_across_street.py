"""Portland's street setback across a local street from a residential zone.

33.130.215.B.1.b: CM2, CM3, CE and CX state no street setback except 10 ft
on a Map 130-1 corridor and 5 ft (a building entirely in residential use)
"from a street lot line facing an RF through RM2 or RMP zone" across a local
service street. The screen holds the 5 on every street line and gives the
plain "none" row (``setback_street_across_nonresidential_ft``) back only to a
street line off the corridor whose five rays across the street all found a
Portland lot in a zone the sentence does not name.

These tests pin the per-line reading (:func:`street_lines_clear`), the edge
flag the envelope reads, the bridge that joins them, and one real corner --
1S2E18CD 07200, SE Woodstock Blvd at SE 50th Ave, CM2 across Woodstock and
RM2 across 50th -- at its own coordinates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapely
from shapely.geometry import LineString

from flats.geom.corridor import CorridorMap
from flats.geom.edges import Edge, EdgeClass
from flats.geom.envelope import Setbacks
from flats.geom.neighbour import observed_neighbours, street_lines_clear
from flats.ingest.quadfit import envelope_for, lot_from_row, setbacks_for
from flats.rules.conditions import ACROSS_STREET_CONDITIONS, CONDITIONS, NEIGHBOUR_ZONE_CONDITIONS
from flats.rules.model import NeighbourRule

pytestmark = pytest.mark.unit

PDX = "or/multnomah/portland"
FACT = "faces_residential_zone_across_street"
FIELD = "setback_street_across_nonresidential_ft"
OFF = "setback_street_off_corridor_ft"
FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "Lot Analysis"
    / "quadfit"
    / "tests"
    / "fixtures"
    / "street_across_1S2E18CD_07200.json"
)

RULE = NeighbourRule(
    condition=FACT,
    true_for=("RF", "R5", "R2.5", "RM1", "RM2", "RMP"),
    false_for=("RM3", "CM2", "CE", "EG1"),
    quote="x",
    note="y",
)


def same(_juris: str, raw: str) -> str | None:
    return raw


def ray(*zones: tuple[str, str], split: int = 0, none: int = 0, near: int = 0) -> dict[str, object]:
    return {"z": [list(z) for z in zones], "split": split, "none": none, "near": near}


@pytest.fixture(scope="module")
def corpus() -> dict:
    from flats.rules.loader import load_rules

    return load_rules()


@pytest.fixture(scope="module")
def pdx_rules(corpus: dict):
    from flats.rules.resolver import RuleSet

    return RuleSet(corpus)


# -- the per-line reading ---------------------------------------------------


def test_a_line_is_clear_only_when_every_ray_found_a_listed_nonresidential_zone() -> None:
    pdx = ("portland", "CM2")
    across = [
        None,  # not a street line
        ray(pdx, ("portland", "CE")),  # every ray read, none residential
        ray(pdx, ("portland", "R5")),  # one residential ray settles it
        ray(pdx, split=1),  # a split-zone lot the ray could not place
        ray(pdx, none=1),  # nothing within reach
        ray(pdx, near=1),  # a lot nearer than a street's width
        ray(pdx, ("gresham", "CM2")),  # another city's lot: on neither list
        ray(pdx, ("portland", "XX")),  # a code on neither list
        ray(),  # no zone at all
    ]
    assert street_lines_clear(across, RULE, "portland", same) == (
        False,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    )


def test_no_rule_answers_nothing_and_a_code_the_normaliser_cannot_place_stays_tight() -> None:
    across = [ray(("portland", "CM2"))]
    assert street_lines_clear(across, None, "portland", same) == (False,)
    assert street_lines_clear(across, RULE, "portland", lambda j, r: None) == (False,)
    # The normaliser's spelling is the one compared: "cm2" read as CM2.
    lower = [ray(("portland", "cm2"))]
    assert street_lines_clear(lower, RULE, "portland", lambda j, r: r.upper()) == (True,)


# -- the edge flag and the setbacks -----------------------------------------


def edge(cls: EdgeClass, *, off: bool, clear: bool) -> Edge:
    return Edge(0, 0, 1, 0, 1.0, 90.0, cls, off_corridor=off, across_clear=clear)


def test_the_plain_row_reaches_only_a_street_line_off_the_corridor_and_read_clear() -> None:
    s = Setbacks(front_ft=5, side_ft=0, rear_ft=0, street_off_corridor_ft=5, street_clear_ft=0)
    assert s.for_edge(edge(EdgeClass.front, off=True, clear=True)) == 0
    assert s.for_edge(edge(EdgeClass.street_side, off=True, clear=True)) == 0
    # Clear across the street but on (or not surely off) a corridor: the
    # corridor's number.
    assert s.for_edge(edge(EdgeClass.front, off=False, clear=True)) == 5
    # Off the corridor, nothing read across: the across-the-street 5.
    assert s.for_edge(edge(EdgeClass.front, off=True, clear=False)) == 5
    # The flag means nothing off a street line.
    side = Setbacks(front_ft=5, side_ft=7, rear_ft=9, street_off_corridor_ft=5, street_clear_ft=0)
    assert side.for_edge(edge(EdgeClass.side, off=True, clear=True)) == 7
    assert side.for_edge(edge(EdgeClass.rear, off=True, clear=True)) == 9
    # A zone that states no plain row keeps the off-corridor number.
    none = Setbacks(front_ft=5, side_ft=0, rear_ft=0, street_off_corridor_ft=5)
    assert none.for_edge(edge(EdgeClass.front, off=True, clear=True)) == 5


class _Rules:
    def __init__(self, **values: object) -> None:
        self.values, self.exempted = values, ()

    def get(self, name: str) -> object:
        return self.values.get(name)


def test_the_plain_row_is_passed_only_on_the_off_corridor_numbers_terms() -> None:
    yards = {"setback_front_ft": 5, "setback_side_ft": 0, "setback_rear_ft": 0}
    both = setbacks_for(_Rules(**yards, **{OFF: 5, FIELD: 0}))  # type: ignore[arg-type]
    assert both.street_off_corridor_ft == 5 and both.street_clear_ft == 0
    # Without an off-corridor number there is nothing for it to refine.
    alone = setbacks_for(_Rules(**yards, **{FIELD: 0}))  # type: ignore[arg-type]
    assert alone.street_clear_ft is None
    # A zone with its own street-side number drops both.
    side = setbacks_for(_Rules(**yards, setback_street_side_ft=8, **{OFF: 5, FIELD: 0}))  # type: ignore[arg-type]
    assert side.street_off_corridor_ft is None and side.street_clear_ft is None


# -- the corpus ---------------------------------------------------------------


def test_the_fact_is_a_registered_site_fact_read_per_line_only() -> None:
    assert FACT in ACROSS_STREET_CONDITIONS and FACT in CONDITIONS
    assert FACT not in NEIGHBOUR_ZONE_CONDITIONS
    assert CONDITIONS[FACT].assume is None


def test_portlands_list_is_rf_through_rm2_and_rmp(corpus: dict) -> None:
    r = corpus[PDX].neighbours[FACT]
    assert set(r.true_for) == {"RF", "R20", "R10", "R7", "R5", "R2.5", "RM1", "RM2", "RMP"}
    assert {"RM3", "RM4", "RX", "IR", "OS", "CM2", "CX", "EG1", "IH"} <= set(r.false_for)
    assert not set(r.true_for) & set(r.false_for)


def test_the_lot_level_reader_never_answers_it(corpus: dict) -> None:
    from flats.geom.neighbour import Line

    lines = [Line(zones=(("portland", "R5"),), unresolved=0)]
    got = observed_neighbours(lines, corpus[PDX].neighbours, "portland")
    assert FACT not in got
    walled = observed_neighbours([], corpus[PDX].neighbours, "portland", all_street=True)
    assert FACT not in walled


@pytest.mark.parametrize("zone", ["CM2", "CM3", "CE", "CX"])
def test_the_four_zones_hold_five_on_every_street_line_and_none_only_per_line(
    corpus: dict, zone: str
) -> None:
    values = corpus[PDX].zones[zone].values
    assert values[OFF].value == 5
    assert values[FIELD].value == 0 and not values[FIELD].variants


@pytest.mark.parametrize("zone", ["CR", "CM1"])
def test_the_zones_the_rule_does_not_name_keep_none_everywhere(corpus: dict, zone: str) -> None:
    values = corpus[PDX].zones[zone].values
    assert values[OFF].value == 0
    assert FIELD not in values


# -- a real corner --------------------------------------------------------------


def _fixture_row(fx: dict, *, across: bool = True) -> dict[str, object]:
    lot = shapely.from_wkt(fx["lot"])
    row: dict[str, object] = {
        "TLID": fx["tlid"],
        "jurisdiction": "portland",
        "zone": fx["zone"],
        "tier": "B",
        "area_sqft": lot.area,
        "frontage_ft": 200.0,
        "lot_width_ft": 100.0,
        "lot_depth_ft": 100.0,
        "edges_json": json.dumps(fx["edges"]),
        "front_bearings_json": json.dumps(fx["front_bearings"]),
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "lot_wkb": shapely.to_wkb(lot),
        "wkb": shapely.to_wkb(lot),
    }
    if across:
        row["street_across_json"] = json.dumps(fx["street_across"])
    return row


def test_a_real_corner_gives_back_the_woodstock_line_and_keeps_five_on_50th(
    corpus: dict, pdx_rules
) -> None:
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # A corridor drawn far away: both street lines surely off it, so the
    # across-the-street reading is the only thing left to decide them.
    far = LineString([(7_650_000.0, 600_000.0), (7_651_000.0, 600_000.0)])
    cm = CorridorMap.from_lines("civic_corridor_setback", [PDX], [far])
    woodstock = LineString([fx["edges"][2][:2], fx["edges"][2][2:4]])
    fiftieth = LineString([fx["edges"][3][:2], fx["edges"][3][2:4]])

    lot = lot_from_row(_fixture_row(fx), corridors=[cm], layers=corpus)
    assert [e.off_corridor for e in lot.edges.edges] == [False, False, True, True]
    assert [e.across_clear for e in lot.edges.edges] == [False, False, True, False]
    assert FACT not in lot.observed
    got = pdx_rules.resolve(PDX, "CM2")
    env = envelope_for(lot, got)
    assert env.setbacks.street_off_corridor_ft == 5 and env.setbacks.street_clear_ft == 0
    # CM2 across Woodstock: the plain none; RM2 across 50th: the 5.
    assert env.geom.distance(woodstock) == pytest.approx(0, abs=0.2)
    assert env.geom.distance(fiftieth) == pytest.approx(5, abs=0.2)

    # A stage file older than the column reads nothing across the street,
    # and both lines keep the 5.
    bare = lot_from_row(_fixture_row(fx, across=False), corridors=[cm], layers=corpus)
    assert not any(e.across_clear for e in bare.edges.edges)
    tight = envelope_for(bare, got).geom
    assert tight.distance(woodstock) == pytest.approx(5, abs=0.2)
    assert tight.distance(fiftieth) == pytest.approx(5, abs=0.2)
    assert tight.within(env.geom.buffer(0.01))
    # So does a lot whose rays the corpus is not handed.
    blind = lot_from_row(_fixture_row(fx), corridors=[cm])
    assert not any(e.across_clear for e in blind.edges.edges)
