"""Distance to transit: a per-lot fact, measured once per transit release.

Steph, 2026-09-30: "If we're building it for one, it's worth building it for
all and making it a standard part of our data collection/processing. However,
we don't need to re-run transit distance every single time."

Pinned here:

- **The registry** holds the three TriMet layers as points and a polyline,
  and a point is an ArcGIS layer or nothing.
- **The probe** says when a layer's data was edited, not when it was merely
  republished -- that is the cue to re-measure.
- **The measurement** is from the nearest point of the lot, to existing rail
  stations (MAX only for the light-rail measure), to any stop, and to the
  LINE of a Frequent Service route.
- **The version** is the geometry, not the file: a republish in another
  order is the same transit.
- **The cache** keeps a lot's distances while its shape and the transit
  version are unchanged, and re-measures everything else.
- **The band** on a distance cannot place a lot within the measurement's
  doubt of its edge, and says so.
- **The rules**: Hillsboro's station community heights and densities and
  Beaverton's 400 ft density, read against the measured distance.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import shapely
from shapely.geometry import LineString, Point, box

from flats.geom.transit import MEASURES, build, distances
from flats.ingest.acquire import data_edited, esri_point
from flats.ingest.quadfit import transit_from_row
from flats.ingest.sources import Geometry, Kind, Provides, load_pipeline
from flats.ingest.transit import measure
from flats.rules.loader import load_rules
from flats.rules.model import Band
from flats.rules.resolver import RuleSet
from flats.score.configure import configure
from flats.score.screen import LotFacts

pytestmark = pytest.mark.unit

HILLSBORO = "or/washington/hillsboro"
BEAVERTON = "or/washington/beaverton"


def _feature(geom, **props):
    return {"type": "Feature", "geometry": shapely.geometry.mapping(geom), "properties": props}


def _set(*, stations=(), stops=(), routes=()):
    return build(list(stations), list(stops), list(routes))


# --- the registry, the fetch, the probe ------------------------------------------


def test_the_three_transit_layers_are_registered() -> None:
    pipe = load_pipeline()
    transit = {k: d for k, d in pipe.datasets.items() if d.provides is Provides.transit}

    assert set(transit) == {"transit_rail_stations", "transit_stops", "transit_routes"}
    assert transit["transit_rail_stations"].geometry is Geometry.point
    assert transit["transit_stops"].geometry is Geometry.point
    assert transit["transit_routes"].geometry is Geometry.polyline
    # Planned stations are not stations.
    assert transit["transit_rail_stations"].where == "STATUS = 'Existing'"
    for ds in transit.values():
        assert ds.kind is Kind.arcgis
        assert set(ds.serves) >= {"or/multnomah", "or/clackamas", "or/washington"}


def test_a_point_is_an_arcgis_layer_or_nothing(tmp_path: Path) -> None:
    p = tmp_path / "pipeline.yaml"
    p.write_text(
        """
working_srid: 2913
display_srid: 4326
datasets:
  stops:
    kind: rlis_zip
    label: stops
    provides: transit
    url: https://example.gov/rlis.zip
    member: TRANSIT/stops.shp
    geometry: point
    serves: [or/multnomah]
""",
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="points are fetched from an ArcGIS layer only"):
        load_pipeline(p)


def test_an_esri_point_becomes_geojson_and_an_empty_one_nothing() -> None:
    assert esri_point({"x": 7_650_000.5, "y": 680_000.25}) == {
        "type": "Point",
        "coordinates": [7_650_000.5, 680_000.25],
    }
    assert esri_point({"x": None, "y": None}) is None
    assert esri_point(None) is None


def test_the_data_edit_date_is_read_and_an_absent_one_is_none() -> None:
    assert data_edited({"editingInfo": {"dataLastEditDate": 1_780_000_000_000}}) == 1_780_000_000_000
    assert data_edited({"editingInfo": {}}) is None
    assert data_edited({}) is None


def test_the_probe_says_a_layer_whose_data_was_edited_is_a_new_release() -> None:
    import httpx

    from flats.ingest.acquire import _spec_sha
    from flats.ingest.probe import probe

    pipe = load_pipeline()
    ds = pipe.datasets["transit_stops"]
    only = pipe.model_copy(update={"datasets": {"transit_stops": ds}})
    then, now = 1_780_000_000_000, 1_790_000_000_000

    def county(request: httpx.Request) -> httpx.Response:
        if str(request.url).split("?", 1)[0].endswith("/query"):
            return httpx.Response(200, json={"count": 7_735})
        fields = [{"name": n} for n in ("OBJECTID", *ds.fields)]
        return httpx.Response(200, json={"fields": fields, "editingInfo": {"dataLastEditDate": now}})

    entry = {"status": "acquired", "features": 7_735, "spec_sha256": _spec_sha(ds), "data_edited": then}
    client = httpx.Client(transport=httpx.MockTransport(county))

    found = probe(only, {"datasets": {"transit_stops": entry}}, client)
    assert [f.finding for f in found] == ["new_release"]
    assert not found[0].changed  # soft: new data is not wrong data

    same = probe(only, {"datasets": {"transit_stops": {**entry, "data_edited": now}}}, client)
    assert [f.finding for f in same] == ["ok"]


# --- the measurement ---------------------------------------------------------------


def test_distance_is_from_the_nearest_point_of_the_lot() -> None:
    lot = box(0, 0, 100, 100)
    transit = _set(
        stations=[_feature(Point(400, 50), STATUS="Existing", TYPE="MAX")],
        stops=[_feature(Point(150, 50), RTE="12")],
        routes=[_feature(LineString([(0, 180), (500, 180)]), FREQUENT="True")],
    )

    got = distances([lot], transit)

    assert got["rail_stop_ft"] == [300.0]  # to the lot's east edge, not its middle
    assert got["lrt_station_ft"] == [300.0]
    assert got["transit_stop_ft"] == [50.0]
    assert got["frequent_route_ft"] == [80.0]


def test_a_lot_holding_the_stop_is_zero_and_a_missing_lot_is_none() -> None:
    transit = _set(
        stations=[_feature(Point(50, 50), STATUS="Existing", TYPE="MAX")],
        stops=[_feature(Point(50, 50))],
        routes=[_feature(LineString([(0, 50), (500, 50)]), FREQUENT="True")],
    )

    got = distances([box(0, 0, 100, 100), None], transit)

    for m in MEASURES:
        assert got[m] == [0.0, None], m


def test_streetcar_is_rail_but_not_light_rail_and_planned_is_nothing() -> None:
    transit = _set(
        stations=[
            _feature(Point(200, 0), STATUS="Existing", TYPE="Street Car"),
            _feature(Point(900, 0), STATUS="Existing", TYPE="MAX"),
            _feature(Point(100, 0), STATUS="Planned", TYPE="MAX"),
        ],
        stops=[_feature(Point(5_000, 0))],
        routes=[],
    )

    got = distances([Point(0, 0)], transit)

    assert got["rail_stop_ft"] == [200.0]
    assert got["lrt_station_ft"] == [900.0]
    # No frequent line at all: the distance is not measured, not zero.
    assert got["frequent_route_ft"] == [None]


def test_only_a_frequent_line_is_a_frequent_corridor() -> None:
    transit = _set(
        stations=[],
        stops=[_feature(Point(0, 0))],
        routes=[
            _feature(LineString([(0, 100), (500, 100)]), FREQUENT="False"),
            _feature(LineString([(0, 700), (500, 700)]), FREQUENT="True"),
        ],
    )

    assert distances([Point(10, 0)], transit)["frequent_route_ft"] == [700.0]


def test_a_stop_on_three_routes_is_one_stop() -> None:
    stops = [_feature(Point(10, 10), RTE=r) for r in ("4", "8", "44")]

    assert len(_set(stops=stops).stops) == 1


def test_the_version_is_the_geometry_not_the_order_it_was_published_in() -> None:
    a = [_feature(Point(0, 0)), _feature(Point(100, 0))]
    b = list(reversed(a))

    assert _set(stops=a).version == _set(stops=b).version
    assert _set(stops=a).version != _set(stops=[*a, _feature(Point(200, 0))]).version


def test_the_cache_keeps_an_unchanged_lot_and_measures_a_changed_one() -> None:
    transit = _set(stops=[_feature(Point(0, 0))])
    lots = pd.DataFrame(
        {"TLID": ["A", "B"], "wkb": [shapely.to_wkb(box(100, 0, 110, 10)), shapely.to_wkb(box(200, 0, 210, 10))]}
    )
    first, stats = measure(lots, transit)
    assert stats == {"lots": 2, "reused": 0, "measured": 2}
    assert list(first["transit_stop_ft"]) == [100.0, 200.0]

    # B's shape changed: only B is measured again.
    moved = lots.assign(wkb=[lots["wkb"][0], shapely.to_wkb(box(300, 0, 310, 10))])
    second, stats = measure(moved, transit, reuse=first, reuse_version=transit.version)
    assert stats == {"lots": 2, "reused": 1, "measured": 1}
    assert list(second["transit_stop_ft"]) == [100.0, 300.0]

    # New stops move everybody: nothing is reused across versions.
    newer = _set(stops=[_feature(Point(0, 0)), _feature(Point(95, 0))])
    third, stats = measure(lots, newer, reuse=first, reuse_version=transit.version)
    assert stats["reused"] == 0
    assert list(third["transit_stop_ft"]) == [5.0, 105.0]


# --- the band, the lot, the screen -------------------------------------------------


def test_a_band_on_a_station_distance_does_not_place_a_lot_inside_its_doubt() -> None:
    beyond = Band(measure="lrt_station_ft", more_than=800)
    within = Band(measure="lrt_station_ft", at_most=800)

    # The station point sits mid-platform; the platform may be 100 ft nearer.
    assert beyond.holds({"lrt_station_ft": 950}) is True
    assert beyond.holds({"lrt_station_ft": 850}) is None
    assert beyond.holds({"lrt_station_ft": 650}) is False
    assert within.holds({"lrt_station_ft": 650}) is True
    assert within.holds({"lrt_station_ft": 850}) is None
    assert within.holds({"lrt_station_ft": 950}) is False
    assert within.holds({}) is None


def test_a_band_on_lot_area_has_no_doubt() -> None:
    band = Band(measure="lot_sqft", at_least=5000)

    assert band.holds({"lot_sqft": 4999}) is False
    assert band.holds({"lot_sqft": 5000}) is True


def test_the_row_carries_its_distances_and_zero_is_a_distance() -> None:
    row = {"rail_stop_ft": 0.0, "lrt_station_ft": 1200.5, "transit_stop_ft": None}

    assert transit_from_row(row) == (("rail_stop_ft", 0.0), ("lrt_station_ft", 1200.5))
    assert transit_from_row({}) == ()


def test_configure_keeps_a_zero_distance() -> None:
    from flats.designs.model import load_catalog

    design = next(iter(load_catalog()))
    lot = LotFacts(lot_sqft=8000, transit_ft=(("transit_stop_ft", 0.0), ("lrt_station_ft", 900.0)))

    measures = configure(lot, design).measures

    assert measures["transit_stop_ft"] == 0.0
    assert measures["lrt_station_ft"] == 900.0
    assert "rail_stop_ft" not in measures


# --- the rules ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def _at(ft: float | None, **more: float) -> dict[str, float]:
    lot = {"lot_sqft": 10_000.0, **more}
    if ft is not None:
        lot["lrt_station_ft"] = ft
    return lot


def test_hillsboro_scc_sc_height_minimum_holds_only_near_a_station(rules: RuleSet) -> None:
    near = rules.resolve(HILLSBORO, "SCC-SC", lot=_at(300))
    far = rules.resolve(HILLSBORO, "SCC-SC", lot=_at(2_000))
    edge = rules.resolve(HILLSBORO, "SCC-SC", lot=_at(850))
    unmeasured = rules.resolve(HILLSBORO, "SCC-SC", lot=_at(None))

    assert near.values["min_building_height_ft"].value == 30
    assert "min_building_height_ft" in far.exempted
    assert "min_building_height_ft" in edge.ambiguous
    assert "min_building_height_ft" in unmeasured.ambiguous


def test_hillsboro_station_densities_follow_the_distance(rules: RuleSet) -> None:
    near = rules.resolve(HILLSBORO, "SCC-SC", lot=_at(300))
    far = rules.resolve(HILLSBORO, "SCC-SC", lot=_at(2_000))
    assert near.values["min_density_du_per_acre"].value == 30
    assert far.values["min_density_du_per_acre"].value == 24
    # The ceiling is the state's to remove for a quadplex (OAR
    # 660-046-0220(2)(b)), near a station or not.
    assert "max_density_du_per_acre" in near.exempted
    assert "max_density_du_per_acre" in far.exempted

    assert rules.resolve(HILLSBORO, "SCR-DNC", lot=_at(300)).values["min_density_du_per_acre"].value == 15
    assert rules.resolve(HILLSBORO, "SCR-DNC", lot=_at(2_000)).values["min_density_du_per_acre"].value == 9

    village = {ft: rules.resolve(HILLSBORO, "SCR-V", lot=_at(ft)).values["min_density_du_per_acre"].value
               for ft in (500, 2_000, 4_000)}
    assert village == {500: 24, 2_000: 15, 4_000: 7}


def test_beaverton_station_community_density_steps_down_beyond_400_ft(rules: RuleSet) -> None:
    for zone in ("SC-MU", "SC-HDR", "SC-S"):
        assert rules.resolve(BEAVERTON, zone, lot=_at(200)).values["min_density_du_per_acre"].value == 30, zone
        assert rules.resolve(BEAVERTON, zone, lot=_at(1_000)).values["min_density_du_per_acre"].value == 24, zone
        assert "min_density_du_per_acre" in rules.resolve(BEAVERTON, zone, lot=_at(450)).ambiguous, zone


# --- the state parking reform's reach, shown on the lot page ------------------------


def test_the_parking_reform_reach_is_yes_no_or_cannot_say() -> None:
    from flats.geom.transit import parking_reform_reach

    assert parking_reform_reach(3_900.0, None) is True  # inside 3/4 mile of rail
    assert parking_reform_reach(None, 2_600.0) is True  # inside 1/2 mile of a frequent line
    assert parking_reform_reach(9_000.0, 5_000.0) is False
    # The station point may be 100 ft from the platform's end: no "no" there.
    assert parking_reform_reach(4_000.0, 5_000.0) is None
    assert parking_reform_reach(9_000.0, None) is None


def test_every_lot_of_the_copy_can_be_measured_from_the_normalized_table(tmp_path: Path) -> None:
    from flats.ingest.transit import read_lots

    path = tmp_path / "lots.parquet"
    pd.DataFrame({"tlid": ["1S1E01AA  -00100  "], "wkb": [shapely.to_wkb(box(0, 0, 10, 10))]}).to_parquet(path)

    lots = read_lots(path)

    assert list(lots.columns) == ["TLID", "wkb"]
    assert list(lots["TLID"]) == ["1S1E01AA  -00100"]
