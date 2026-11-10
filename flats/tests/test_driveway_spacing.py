"""Driveway spacing from intersections and along busy streets (FOLLOWUPS 169)."""

from __future__ import annotations

import json

import pytest
from shapely.geometry import LineString

from flats.designs.model import load_catalog
from flats.encode.load import load_trusted
from flats.geom import driveway_spacing as ds
from flats.geom.durham_apron import StreetNetwork
from flats.geom.street_class import build
from flats.ingest.quadfit import lot_from_row, screen_lot, with_driveway_spacing
from flats.ingest.sources import load_pipeline
from flats.provenance.store import ProvenanceStore
from flats.score import flags as flag_plan
from flats.score import relief, slack
from flats.score.screen import DRIVEWAY_SPACING_BLOCKED, DRIVEWAY_SPACING_UNREAD
from flats.tests.test_utility_easement import X0, Y0
from flats.tests.test_utility_easement import lot_row as _row

pytestmark = pytest.mark.unit

TIGARD = "or/washington/tigard"


# --- the config ----------------------------------------------------------


def test_every_quote_resolves_and_prints_its_figure() -> None:
    store = ProvenanceStore()
    for layer, rules in ds.load_rules().items():
        for quote, figure, _cite in rules.quotes():
            text = store.quote(quote)
            assert text.strip(), (layer, quote)
            if figure is not None:
                assert f"{figure:g}" in text, (layer, quote, figure)


def test_every_map_is_registered_and_every_class_is_on_it() -> None:
    datasets = load_pipeline().datasets
    for layer, rules in ds.load_rules().items():
        if rules.map is None:
            assert not rules.classes, layer
            continue
        assert rules.map in datasets, rules.map
        # A map borrowed from another place only under a ruling.
        assert layer in datasets[rules.map].serves or rules.map_ruling, (layer, rules.map)
        spec = ds.spec_of(rules.map)
        assert spec is not None, rules.map
        assert set(rules.classes) <= set(spec.rank), layer
        named = {*rules.classes.values(), *([rules.unlisted] if rules.unlisted else [])}
        for word in rules.frontage:
            assert word in named, (layer, word)
        for r in rules.intersections:
            assert r.on <= named and r.cross <= named, (layer, r)


def test_the_spacing_maps_feed_no_other_rule() -> None:
    from flats.geom.street_class import CLASS_MAPS

    assert not set(ds.SPACING_MAPS) & set(CLASS_MAPS)


def test_the_tigard_figures_are_the_printed_ones() -> None:
    tigard = ds.rules_for(TIGARD)
    assert tigard is not None
    assert tigard.frontage["arterial"].figure_ft == 600
    assert tigard.frontage["collector"].figure_ft == 200
    (rule,) = tigard.intersections
    assert rule.figure_ft == 150 and rule.basis == "right_of_way_line"
    assert tigard.class_of_rank(4, ds.spec_of(tigard.map)) == "arterial"  # PCPL Arterial
    assert tigard.class_of_rank(5, ds.spec_of(tigard.map)) is None  # Freeway: unread


def test_durham_keeps_its_own_check() -> None:
    assert ds.rules_for("or/washington/durham") is None


# --- the measurement -----------------------------------------------------


def _tigard_map(front: LineString, cross: LineString, front_rank: int, cross_rank: int):
    return build(
        [TIGARD],
        [front, cross],
        ["", ""],
        ["MAIN ST", "OAK ST"],
        [front, cross],
        ["MAIN ST", "OAK ST"],
        [1500, 1500],
        [front_rank, cross_rank],
        key="street_class_tigard",
        access=False,
        by_name=True,
    )


def _midblock(w: float) -> tuple[str, list[float]]:
    edges = [
        [X0, Y0, X0 + w, Y0, "F"],
        [X0 + w, Y0, X0 + w, Y0 + 200, "S"],
        [X0 + w, Y0 + 200, X0, Y0 + 200, "R"],
        [X0, Y0 + 200, X0, Y0, "S"],
    ]
    return json.dumps(edges), [0.0]


def _roads(w: float) -> tuple[LineString, LineString]:
    # The front street 20 ft south of the lot; a cross street 20 ft west.
    front = LineString(((X0 - 600, Y0 - 20), (X0 + w + 600, Y0 - 20)))
    cross = LineString(((X0 - 20, Y0 - 300), (X0 - 20, Y0 + 300)))
    return front, cross


def _read(w: float, front_rank: int, cross_rank: int) -> tuple[str, str]:
    front, cross = _roads(w)
    edges, bearings = _midblock(w)
    network = StreetNetwork.build([front, cross], ["MAIN ST", "OAK ST"])
    cmap = _tigard_map(front, cross, front_rank, cross_rank)
    return ds.read_lot(edges, bearings, network, cmap, ds.rules_for(TIGARD))


def test_a_long_local_frontage_clears_a_collector_intersection() -> None:
    answer, why = _read(400.0, 0, 2)
    assert answer == ds.CLEAR, why


def test_a_short_local_frontage_by_a_collector_is_blocked() -> None:
    # 120 ft of frontage, the collector's centreline 20 ft off its end: no
    # placement reaches 150 ft even centreline to centreline.
    answer, why = _read(120.0, 0, 2)
    assert answer == ds.BLOCKED, why


def test_between_the_bounds_is_unread() -> None:
    # 180 ft: a centreline 150 ft from the collector's fits, but not 150 ft
    # from its right-of-way line with the apron's width.
    answer, why = _read(180.0, 0, 2)
    assert answer == ds.UNREAD, why


def test_a_local_cross_street_holds_nothing_in_tigard() -> None:
    answer, why = _read(60.0, 0, 0)
    assert answer == ds.CLEAR, why


def test_an_arterial_frontage_is_blocked_whatever_its_length() -> None:
    answer, why = _read(2000.0, 4, 0)
    assert answer == ds.BLOCKED, why


def test_a_freeway_frontage_is_unread() -> None:
    answer, _ = _read(400.0, 5, 0)
    assert answer == ds.UNREAD


def test_no_map_is_unread() -> None:
    edges, bearings = _midblock(400.0)
    front, cross = _roads(400.0)
    network = StreetNetwork.build([front, cross], ["MAIN ST", "OAK ST"])
    answer, _ = ds.read_lot(edges, bearings, network, None, ds.rules_for(TIGARD))
    assert answer == ds.UNREAD


def test_an_unread_cross_street_is_the_strictest_for_a_pass_only() -> None:
    tualatin = ds.rules_for("or/clackamas/tualatin")
    assert tualatin is not None
    # 300 ft of local frontage, an unread street at station 0: 200 ft from
    # it fits (apron 205..225 by 5 ft inset end at 295).
    assert ds.chain_answer(300.0, [(0.0, 30.0, None)], "local", tualatin) == ds.CLEAR
    # 150 ft: an unread street never fails a lot, so the answer is unread.
    assert ds.chain_answer(150.0, [(0.0, 30.0, None)], "local", tualatin) == ds.UNREAD
    # A known arterial there fails it.
    assert ds.chain_answer(150.0, [(0.0, 30.0, "arterial")], "local", tualatin) == ds.BLOCKED


def test_washington_county_reaches_only_a_lot_with_every_frontage_busy(monkeypatch) -> None:
    county = ds.rules_for("or/washington/_unincorporated")
    assert county is not None
    corner = json.dumps(
        [
            [X0, Y0, X0 + 100, Y0, "F"],
            [X0 + 100, Y0, X0 + 100, Y0 + 100, "S"],
            [X0 + 100, Y0 + 100, X0, Y0 + 100, "R"],
            [X0, Y0 + 100, X0, Y0, "F"],
        ]
    )
    midblock, bearings = _midblock(100.0)
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: "collector")
    assert ds.read_lot(midblock, bearings, None, None, county)[0] == ds.CLEAR
    assert ds.read_lot(corner, [0.0, 90.0], None, None, county)[0] == ds.BLOCKED
    monkeypatch.setattr(ds, "chain_class", lambda chain, cmap, rules: None)
    assert ds.read_lot(corner, [0.0, 90.0], None, None, county)[0] == ds.UNREAD


# --- Cornelius on the county map (Steph 2026-11-10) ----------------------


def test_cornelius_reads_the_county_map_as_the_county_does() -> None:
    cornelius = ds.rules_for("or/washington/cornelius")
    assert cornelius is not None
    assert cornelius.map == "street_class_washington"
    assert cornelius.map_ruling == "2026-11-10-cornelius-county-street-map"
    spec = ds.spec_of(cornelius.map)
    assert cornelius.class_of_rank(2, spec) == "collector"
    assert cornelius.class_of_rank(3, spec) == "arterial"
    assert cornelius.class_of_rank(4, spec) == "arterial"  # Principal Arterial
    assert cornelius.class_of_rank(1, spec) == "local"  # Neighborhood Route
    assert cornelius.class_of_rank(0, spec) == "local"  # undrawn, Metro + OSM local
    assert cornelius.class_of_rank(5, spec) is None  # Freeway: unread
    # The county map is not registered to serve Cornelius, so no other
    # reader (corner lots, dedication, local street) takes it up there.
    assert "or/washington/cornelius" not in load_pipeline().datasets[cornelius.map].serves


def _county_map(front: LineString, rank: int | None, osm: str = "residential"):
    if rank is None:
        return build(
            ["or/washington/_unincorporated"], [], [], [], [front], [""], [1500],
            unlisted=0, osm=[front], osm_classes=[osm],
            key="street_class_washington",
        )
    return build(
        ["or/washington/_unincorporated"], [front], [""], [""], [front], [""], [1400], [rank],
        unlisted=0, key="street_class_washington",
    )


def test_a_cornelius_lot_on_a_county_arterial_is_blocked() -> None:
    cornelius = ds.rules_for("or/washington/cornelius")
    edges, bearings = _midblock(400.0)
    front, cross = _roads(400.0)
    network = StreetNetwork.build([front, cross], ["ADAIR ST", "OAK ST"])
    # Busy is busy whatever the zoning says (none read here).
    answer, why = ds.read_lot(edges, bearings, network, _county_map(front, 3), cornelius)
    assert answer == ds.BLOCKED, why


def _no_industry(network: StreetNetwork) -> ds.IndustrialReach:
    return ds.industrial_reach(network, [], 60.0)


def test_a_cornelius_local_street_clears_away_from_corners() -> None:
    cornelius = ds.rules_for("or/washington/cornelius")
    edges, bearings = _midblock(400.0)
    front, cross = _roads(400.0)
    network = StreetNetwork.build([front, cross], ["MAIN ST", "OAK ST"])
    # Undrawn, and Metro and OpenStreetMap both call it residential: local,
    # as on county lots. 400 ft of frontage clears 100 ft from any street's
    # right-of-way (the cross street unread, so taken as the strictest).
    # No industrial district near either street.
    answer, why = ds.read_lot(
        edges, bearings, network, _county_map(front, None), cornelius, None, _no_industry(network)
    )
    assert answer == ds.CLEAR, why


def test_a_cornelius_local_street_that_touches_an_industrial_district_is_unread() -> None:
    from shapely.geometry import box

    cornelius = ds.rules_for("or/washington/cornelius")
    edges, bearings = _midblock(400.0)
    front, cross = _roads(400.0)
    # A far stretch of MAIN ST, past the block, runs beside an M-1 district.
    far = LineString(((X0 + 1500, Y0 - 20), (X0 + 2500, Y0 - 20)))
    network = StreetNetwork.build([front, cross, far], ["MAIN ST", "OAK ST", "MAIN ST"])
    district = box(X0 + 1600, Y0, X0 + 2000, Y0 + 400)
    reach = ds.industrial_reach(network, [district], cornelius.industrial.reach_ft)
    assert reach.may_be(network, (0,)) and not reach.may_be(network, (1,))
    answer, why = ds.read_lot(
        edges, bearings, network, _county_map(front, None), cornelius, None, reach
    )
    assert answer == ds.UNREAD, why
    assert "industrial" in why


def test_a_cornelius_local_street_with_no_zoning_read_is_unread() -> None:
    cornelius = ds.rules_for("or/washington/cornelius")
    edges, bearings = _midblock(400.0)
    front, cross = _roads(400.0)
    network = StreetNetwork.build([front, cross], ["MAIN ST", "OAK ST"])
    for reach in (None, ds.industrial_reach(network, None, 60.0)):
        got = ds.read_lot(edges, bearings, network, _county_map(front, None), cornelius, None, reach)
        assert got[0] == ds.UNREAD, got[1]


def test_cornelius_industrial_districts_are_read_off_the_zoning_map(tmp_path) -> None:
    def square(x: float) -> dict:
        ring = [[x, 0.0], [x + 10, 0.0], [x + 10, 10.0], [x, 10.0], [x, 0.0]]
        return {"type": "Polygon", "coordinates": [ring]}

    def feature(city: str, zone: str, x: float) -> dict:
        return {"type": "Feature", "properties": {"CITY": city, "ZONE": zone}, "geometry": square(x)}

    spec = ds.rules_for("or/washington/cornelius").industrial
    assert spec is not None
    path = tmp_path / f"{spec.zoning}.geojson"
    features = [
        feature("Cornelius", "M1", 0),  # M-1 on the map
        feature("Cornelius", "LI", 20),
        feature("Cornelius", "R7", 40),  # residential
        feature("Cornelius", "FD-20", 60),  # a county sliver, ruled
        feature("Cornelius", "QQ", 80),  # a code the layer cannot spell: may be industrial
        feature("Hillsboro", "M1", 100),  # another city's
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    got = ds.industrial_polygons(tmp_path, "or/washington/cornelius", spec)
    assert got is not None
    assert sorted(round(g.bounds[0]) for g in got) == [0, 20, 80]
    # A map that draws nothing of the city is unread, not "no industry".
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features[-1:]}), encoding="utf-8"
    )
    assert ds.industrial_polygons(tmp_path, "or/washington/cornelius", spec) is None
    assert ds.industrial_polygons(tmp_path / "none", "or/washington/cornelius", spec) is None


def test_the_cornelius_zoning_map_is_registered_and_its_districts_held() -> None:
    from flats.rules.loader import load_rules as load_layers

    spec = ds.rules_for("or/washington/cornelius").industrial
    assert spec is not None
    dataset = load_pipeline().datasets[spec.zoning]
    assert "or/washington/cornelius" in dataset.serves
    layer = load_layers()["or/washington/cornelius"]
    assert all(layer.holds(z) == z for z in spec.zones)


def test_a_cornelius_street_with_no_reading_stays_unread() -> None:
    cornelius = ds.rules_for("or/washington/cornelius")
    edges, bearings = _midblock(400.0)
    front, cross = _roads(400.0)
    network = StreetNetwork.build([front, cross], ["MAIN ST", "OAK ST"])
    # OpenStreetMap disagrees with Metro: no reading, as on county lots.
    got = ds.read_lot(edges, bearings, network, _county_map(front, None, "secondary"), cornelius)
    assert got[0] == ds.UNREAD, got[1]


# --- the screen ----------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


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


def _lot_2s110db01500(**over: object) -> dict[str, object]:
    """2S110DB01500's shape: a Tigard RES-E lot whose only frontage, 323 ft,
    is Highway 99W (TSP Principal Arterial), Naeve St 270 ft along it."""
    return _row(
        323.0,
        260.0,
        TLID="2S110DB01500",
        jurisdiction="tigard",
        zone="RES-E",
        **over,
    )


def test_2s110db01500_is_not_green(corpus, policies) -> None:
    w = 323.0
    front = LineString(((X0 - 600, Y0 - 50), (X0 + w + 600, Y0 - 50)))
    naeve = LineString(((X0 + w + 270, Y0 - 300), (X0 + w + 270, Y0 - 50)))
    edges, bearings = _midblock(w)
    network = StreetNetwork.build([front, naeve], ["PACIFIC HWY", "NAEVE ST"])
    cmap = build(
        [TIGARD], [front, naeve], ["", ""], ["PACIFIC HWY", "NAEVE ST"],
        [front, naeve], ["PACIFIC HWY", "NAEVE ST"], [1200, 1500], [4, 0],
        key="street_class_tigard", access=False, by_name=True,
    )
    answer, why = ds.read_lot(edges, bearings, network, cmap, ds.rules_for(TIGARD))
    assert answer == ds.BLOCKED, why
    row = _lot_2s110db01500(driveway_spacing=answer, driveway_spacing_why=why)
    got = _screen(corpus, policies, lot_from_row(row, corpus.layers))
    assert got.signed.colour is not flag_plan.Colour.green
    assert DRIVEWAY_SPACING_BLOCKED in got.signed.reasons
    assert "ACCESS-DRIVEWAY-SPACING" in {f.code for f in got.signed.flags}


def test_a_tigard_lot_nothing_read_is_held(corpus, policies) -> None:
    got = _screen(corpus, policies, lot_from_row(_lot_2s110db01500(), corpus.layers))
    assert got.signed.colour is not flag_plan.Colour.green
    assert DRIVEWAY_SPACING_UNREAD in got.signed.reasons


def test_a_clear_reading_adds_no_reason(corpus, policies) -> None:
    row = _lot_2s110db01500(driveway_spacing=ds.CLEAR)
    got = _screen(corpus, policies, lot_from_row(row, corpus.layers))
    assert DRIVEWAY_SPACING_BLOCKED not in got.signed.reasons
    assert DRIVEWAY_SPACING_UNREAD not in got.signed.reasons


def test_the_bridge_without_a_snapshot_leaves_tigard_unread(tmp_path) -> None:
    rows = [_lot_2s110db01500(), _row(100.0, 200.0)]
    assert with_driveway_spacing(rows, None, tmp_path / "none.parquet") == 1
    assert rows[0]["driveway_spacing"] == ds.UNREAD
    assert "driveway_spacing" not in rows[1]
