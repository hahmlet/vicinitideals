"""Durham 3.7.1.7: measure frontage placement against street intersections."""

from __future__ import annotations

import json

import pytest
import shapely
import pyarrow as pa
import pyarrow.parquet as pq
from shapely.geometry import LineString, box

import flats.geom.durham_apron as durham_apron
from flats.geom.durham_apron import (
    DURHAM_APRON_MIN_CLEARANCE_FT,
    StreetNetwork,
    maximum_clearance_ft,
)
from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.ingest.quadfit import _durham_apron_clearance_column, lot_from_row, screen_lot
from flats.rules.conditions import CONDITIONS
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import flags as flag_plan
from flats.score.screen import DRIVEWAY_NEAR_INTERSECTION_100FT
from flats.score import relief, slack
from flats.score.flags import fact_code
from flats.tests.test_utility_easement import X0, Y0
from flats.tests.test_utility_easement import lot_row as _beaverton_row

pytestmark = pytest.mark.unit

DURHAM = "or/washington/durham"
FACT = "driveway_near_intersection_100ft"
FLAG = fact_code(FACT)
POD = ("multi_story", "attached_wall")


def test_the_fact_is_registered_with_the_100_foot_threshold() -> None:
    defn = CONDITIONS[FACT]
    assert defn.kind == "site_fact"
    assert defn.assume is None
    assert "3.7.1.7" in defn.describe and "100 feet" in defn.describe
    assert "RLIS street-centerline intersections" in defn.evidence


def test_the_apron_is_qualified_with_the_codes_own_words() -> None:
    held = load_rules()[DURHAM].defaults["driveway_approach_max_width_ft"]
    assert held.value == 40
    assert held.qualified_by == FACT
    assert "3.7.1.7" in held.qualified_cite and "100 feet" in held.qualified_cite
    assert held.qualified_quote == "or/washington/durham/3/3.7.txt#L27"
    for zone in ("SDR", "MDR"):
        res = RuleSet(load_rules()).resolve(DURHAM, zone, POD)
        assert FACT in res.unencoded


def test_the_quoted_line_is_the_100_feet() -> None:
    from flats.provenance.store import ProvenanceStore

    text = ProvenanceStore().quote("or/washington/durham/3/3.7.txt#L27")
    assert text.startswith("3.7.1.7")
    assert "100 feet from any street intersection" in text
    assert "curb return" in text


def test_no_other_city_carries_the_fact() -> None:
    for jid, layer in load_rules().items():
        if jid == DURHAM:
            continue
        held = list(layer.defaults.values()) + [
            v for z in layer.zones.values() for v in z.values.values()
        ]
        assert all(v.qualified_by != FACT for v in held), jid


def test_the_flag_reads_in_plain_english() -> None:
    t = flag_plan.registry().types[FLAG]
    assert t.description == (
        "Durham forbids a driveway within 100 ft of a street intersection "
        "(3.7.1.7); not yet checked on this lot"
    )
    assert t.severity >= flag_plan.colour_rules().yellow_at_severity


# --- through the bridge -------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _durham_corner(w: float = 120.0, d: float = 200.0) -> dict[str, object]:
    """A Durham SDR corner lot: streets along its south and west edges."""
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + d, "S"],
        [X0 + w, Y0 + d, X0, Y0 + d, "R"],
        [X0, Y0 + d, X0, Y0, "F"],
    ]
    return _beaverton_row(
        w,
        d,
        TLID="2S113BC00100",
        jurisdiction="durham",
        zone="SDR",
        edges_json=json.dumps(edges),
        front_bearings_json="[0.0, 90.0]",
        frontage_ft=w + d,
        area_sqft=w * d,
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + w, Y0 + d)),
    )


def _durham_midblock(w: float = 300.0, d: float = 200.0) -> dict[str, object]:
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + d, "S"],
        [X0 + w, Y0 + d, X0, Y0 + d, "R"],
        [X0, Y0 + d, X0, Y0, "S"],
    ]
    return _beaverton_row(
        w,
        d,
        TLID="2S113BC00101",
        jurisdiction="durham",
        zone="SDR",
        edges_json=json.dumps(edges),
        front_bearings_json="[0.0]",
        frontage_ft=w,
        area_sqft=w * d,
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + w, Y0 + d)),
    )


def _measured(row: dict[str, object], roads: list[LineString]) -> dict[str, object]:
    return {
        **row,
        "durham_apron_clearance_ft": maximum_clearance_ft(
            str(row["edges_json"]),
            json.loads(str(row["front_bearings_json"])),
            StreetNetwork.build(roads, ["front", *(f"cross-{i}" for i in range(len(roads) - 1))]),
            30.0,
        ),
    }


def _screen(corpus, policies, lot):
    (s,) = screen_lot(
        lot,
        [load_catalog().latest("pod56x36")],
        rules=corpus,
        policy=policies[0],
        relief=policies[1],
        step_deg=30.0,
    )
    return s


def test_a_midblock_apron_clear_of_intersections_can_be_green(corpus, policies) -> None:
    row = _durham_midblock()
    roads = [
        LineString(((X0 - 500, Y0 - 20), (X0 + 800, Y0 - 20))),
        LineString(((X0 - 200, Y0 - 100), (X0 - 200, Y0 + 100))),
        LineString(((X0 + 500, Y0 - 100), (X0 + 500, Y0 + 100))),
    ]
    row = _measured(row, roads)
    assert row["durham_apron_clearance_ft"] >= DURHAM_APRON_MIN_CLEARANCE_FT
    lot = lot_from_row(row, corpus.layers)
    assert lot.observed[FACT] is False
    cleared = _screen(corpus, policies, lot)
    assert FLAG not in {f.code for f in cleared.signed.flags}
    assert cleared.signed.colour is flag_plan.Colour.green


def test_bridge_measures_from_the_s1_street_file(tmp_path) -> None:
    row = _durham_midblock(w=60.0)
    roads = [
        LineString(((X0 - 500, Y0 - 20), (X0 + 500, Y0 - 20))),
        LineString(((X0 - 20, Y0 - 100), (X0 - 20, Y0 + 100))),
    ]
    path = tmp_path / "s1_streets.parquet"
    pq.write_table(
        pa.table(
            {
                "name": ["front", "cross"],
                "wkb": [shapely.to_wkb(road) for road in roads],
            }
        ),
        path,
    )
    (clearance,) = _durham_apron_clearance_column([row], path)
    assert clearance == pytest.approx(50.0)


def test_bridge_uses_the_measured_cross_street_half_width(tmp_path) -> None:
    row = _durham_midblock(w=170.0)
    row["road_widths_json"] = json.dumps(
        [[X0, Y0, X0, Y0 + 200, 20.0, True, ["cross-0"], {}]]
    )
    roads = [
        LineString(((X0 - 500, Y0 - 20), (X0 + 500, Y0 - 20))),
        LineString(((X0 - 20, Y0 - 100), (X0 - 20, Y0 + 100))),
    ]
    path = tmp_path / "s1_streets.parquet"
    pq.write_table(
        pa.table(
            {
                "name": ["front", "cross-0"],
                "wkb": [shapely.to_wkb(road) for road in roads],
            }
        ),
        path,
    )
    (clearance,) = _durham_apron_clearance_column([row], path)
    assert clearance == pytest.approx(105.0)


def test_a_103_foot_corner_frontage_fails_the_apron_rule(corpus, policies) -> None:
    row = _durham_corner(w=80.0, d=23.0)
    roads = [
        LineString(((X0 - 500, Y0 - 20), (X0 + 500, Y0 - 20))),
        LineString(((X0 - 20, Y0 - 100), (X0 - 20, Y0 + 100))),
    ]
    row = _measured(row, roads)
    assert row["frontage_ft"] == 103.0
    assert row["durham_apron_clearance_ft"] < DURHAM_APRON_MIN_CLEARANCE_FT
    lot = lot_from_row(row, corpus.layers)
    assert lot.observed[FACT] is True
    failed = _screen(corpus, policies, lot)
    assert failed.signed.colour is flag_plan.Colour.red
    assert DRIVEWAY_NEAR_INTERSECTION_100FT in failed.signed.reasons
    apron_check = next(
        c for c in failed.signed.checks if c.check == DRIVEWAY_NEAR_INTERSECTION_100FT
    )
    assert apron_check.verdict.value == "fail"


def test_centerline_only_clearance_between_bounds_keeps_the_flag(
    corpus, policies
) -> None:
    row = _durham_midblock(w=170.0)
    roads = [
        LineString(((X0 - 500, Y0 - 20), (X0 + 500, Y0 - 20))),
        LineString(((X0 - 20, Y0 - 100), (X0 - 20, Y0 + 100))),
    ]
    row = _measured(row, roads)
    assert row["durham_apron_clearance_ft"] is None
    lot = lot_from_row(row, corpus.layers)
    assert FACT not in lot.observed
    held = _screen(corpus, policies, lot)
    assert FLAG in {f.code for f in held.signed.flags}
    assert held.signed.colour is flag_plan.Colour.yellow


def test_a_short_jog_does_not_make_a_phantom_nearby_junction() -> None:
    edges = [
        [X0, Y0, X0, Y0 + 3, "F"],
        [X0, Y0 + 3, X0 + 197, Y0 + 3, "F"],
        [X0 + 197, Y0 + 3, X0 + 197, Y0 + 100, "R"],
        [X0 + 197, Y0 + 100, X0, Y0 + 100, "R"],
        [X0, Y0 + 100, X0, Y0, "R"],
    ]
    streets = StreetNetwork.build(
        [
            LineString(((X0 - 500, Y0), (X0 + 500, Y0))),
            LineString(((X0 + 186, Y0 - 100), (X0 + 186, Y0 + 100))),
        ],
        ["front", "cross"],
    )

    clearance = maximum_clearance_ft(edges, [0.0], streets, 30.0)

    assert clearance is None


def test_a_backtracking_frontage_jog_keeps_the_junction_station(monkeypatch) -> None:
    edges = [
        [X0 + 3.5, Y0, X0, Y0, "F"],
        [X0, Y0, X0 + 3.5, Y0 + 0.1, "F"],
        [X0 + 3.5, Y0 + 0.1, X0 + 196.5, Y0 + 0.1, "F"],
        [X0 + 196.5, Y0 + 0.1, X0 + 196.5, Y0 + 100, "R"],
        [X0 + 196.5, Y0 + 100, X0, Y0 + 100, "R"],
        [X0, Y0 + 100, X0 + 3.5, Y0, "R"],
    ]
    streets = StreetNetwork.build(
        [
            LineString(((X0 - 500, Y0 - 20), (X0 + 500, Y0 - 20))),
            LineString(((X0 + 191.5, Y0 - 100), (X0 + 191.5, Y0 + 100))),
        ],
        ["front", "cross"],
    )
    stations: list[float] = []
    best_clearance = durham_apron._best_clearance

    def capture_station(length: float, events: list[float], width: float) -> float:
        stations.extend(events)
        return best_clearance(length, events, width)

    monkeypatch.setattr(durham_apron, "_best_clearance", capture_station)

    clearance = maximum_clearance_ft(edges, [0.0], streets, 30.0)

    assert stations == pytest.approx([195.0], abs=1.0)
    assert clearance is None


def test_a_split_frontage_street_includes_junctions_on_later_segments() -> None:
    edges = [
        [X0, Y0, X0 + 200, Y0, "F"],
        [X0 + 200, Y0, X0 + 200, Y0 + 100, "R"],
        [X0 + 200, Y0 + 100, X0, Y0 + 100, "R"],
        [X0, Y0 + 100, X0, Y0, "R"],
    ]
    streets = StreetNetwork.build(
        [
            LineString(((X0 + 80, Y0 - 20), (X0 + 120, Y0 - 20))),
            LineString(((X0 + 140, Y0 - 20), (X0 + 240, Y0 - 20))),
            LineString(((X0 + 180, Y0 - 100), (X0 + 180, Y0 + 100))),
        ],
        ["front", "front", "cross"],
    )

    clearance = maximum_clearance_ft(edges, [0.0], streets, 30.0)

    assert clearance is None


def test_unmeasurable_intersection_geometry_keeps_the_flag(corpus, policies) -> None:
    lot = lot_from_row(_durham_corner(), corpus.layers)
    assert FACT not in lot.observed
    held = _screen(corpus, policies, lot)
    flags = {f.code: f for f in held.signed.flags}
    assert FLAG in flags
    assert held.signed.colour is not flag_plan.Colour.green
    assert held.signed.colour is flag_plan.Colour.yellow
