"""Institutional land is RED and never scanned (Steph RULED 2026-10-06, FOLLOWUPS 47).

Schools, hospitals, municipal sites, parks, utilities, airports, marinas,
transit hubs, rail, public pools and plazas, malls -- read off OpenStreetMap
and Metro's ORCA by the share of the lot they cover. Churches and charities
stay screened.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("shapely")
pd = pytest.importorskip("pandas")

import shapely  # noqa: E402
from shapely.geometry import box, mapping  # noqa: E402

from flats.geom import institutional as inst  # noqa: E402
from flats.ingest import assign as az  # noqa: E402
from flats.ingest import institutional as step  # noqa: E402
from flats.ingest.sources import load_pipeline  # noqa: E402

pytestmark = pytest.mark.unit


def osm(geom: Any, osm_id: str = "way/1", **tags: str) -> dict[str, Any]:
    return {"type": "Feature", "properties": {"osm": osm_id, **tags}, "geometry": mapping(geom)}


def orca(geom: Any, unit: str = "Park", owner: str = "Local", site: str = "A Park") -> dict[str, Any]:
    return {"type": "Feature", "properties": {"UNITTYPE": unit, "OWNLEV1": owner, "SITENAME": site}, "geometry": mapping(geom)}


LOT = box(0, 0, 100, 100)


def read(lots: list[Any], osm_feats: list[dict[str, Any]] = (), orca_feats: list[dict[str, Any]] = ()) -> list[Any]:  # type: ignore[assignment]
    return inst.classify(lots, inst.build(osm_feats, orca_feats))


# --- the ruling, as the config holds it -------------------------------------


def test_every_category_steph_named_is_held() -> None:
    rules = inst.load_rules()
    assert {c.key for c in rules.categories} == {
        "school", "hospital", "municipal", "park", "utility", "airport",
        "marina", "transit", "rail", "pool_plaza", "mall",
    }
    assert rules.min_share == 0.5


def test_no_category_reads_a_church_or_a_charity() -> None:
    """Steph 2026-10-06: "Churches and charities should still be checked
    because churches do divest of land for charitable purposes"."""
    rules = inst.load_rules()
    for c in rules.categories:
        for m in c.osm:
            assert "religion" not in m and "place_of_worship" not in m.get("amenity", frozenset())
    assert "Non-Profits" not in rules.orca_owners and "Private" not in rules.orca_owners
    assert rules.osm_category({"amenity": "place_of_worship", "religion": "christian"}) is None
    # ...but a church's school is a school (Steph 2026-10-06).
    assert rules.osm_category({"amenity": "school", "religion": "christian", "name": "Central Catholic"}) == "school"


def test_every_tag_the_config_reads_is_one_the_extract_fetches() -> None:
    """The extract is the superset: a category matcher the query never asks
    for would read nothing, silently."""
    query = str(load_pipeline().datasets["osm_land_use"].query)
    selectors = re.findall(r'\["(\w+)"(?:=|~)"\^?\(?([^"]+?)\)?\$?"\]', query)
    fetched = {(k, v) for k, vals in selectors for v in vals.split("|")}
    kept = set(load_pipeline().datasets["osm_land_use"].fields)
    for c in inst.load_rules().categories:
        for m in c.unless:
            assert set(m) <= kept, (c.key, set(m) - kept)
        for m in c.osm:
            assert set(m) <= kept, (c.key, set(m) - kept)
            # At least one of the pair's tags is a selector the query asks for.
            assert any((k, v) in fetched for k, vals in m.items() for v in vals), (c.key, dict(m))


def test_a_yes_value_must_be_quoted(tmp_path: Path) -> None:
    p = tmp_path / "i.yaml"
    p.write_text("min_share: 0.5\nline_half_width_ft: 10\ncategories:\n  t:\n    osm:\n      - {park_ride: [yes]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="quote yes/no"):
        inst.load_rules(p)


# --- the reading ------------------------------------------------------------


def test_a_lot_inside_a_school_outline_is_a_school_lot() -> None:
    got = read([LOT], [osm(box(-50, -50, 300, 300), amenity="school", name="Westview")])[0]
    assert got is not None and got.category == "school" and got.share == pytest.approx(1.0)
    assert (got.source, got.name) == ("osm:way/1", "Westview")


def test_a_house_a_park_brushes_is_not_a_park() -> None:
    assert read([LOT], [osm(box(60, 0, 200, 100), leisure="park", name="Gates Park")]) == [None]  # 40% covered
    got = read([LOT], [osm(box(40, 0, 200, 100), leisure="park", name="Gates Park")])[0]  # 60%
    assert got is not None and got.category == "park" and got.share == pytest.approx(0.6)


def test_a_park_two_maps_draw_counts_once() -> None:
    """OpenStreetMap's park and Metro's park over the same 30% are 30%, not 60%."""
    strip = box(0, 0, 30, 100)
    assert read([LOT], [osm(strip, leisure="park", name="A Park")], [orca(strip)]) == [None]


def test_a_private_or_nonprofit_orca_unit_is_not_read() -> None:
    assert read([LOT], [], [orca(LOT, owner="Private")]) == [None]
    assert read([LOT], [], [orca(LOT, owner="Non-Profits", unit="Natural Area")]) == [None]
    assert read([LOT], [], [orca(LOT, unit="Golf Course")]) == [None]
    got = read([LOT], [], [orca(LOT, unit="School Land", owner="Special District", site="Westview HS")])[0]
    assert got is not None and (got.category, got.source, got.name) == ("school", "orca:School Land", "Westview HS")


def test_a_railway_line_is_widened_and_claims_only_a_lot_that_is_mostly_track() -> None:
    track = shapely.LineString([(-50, 50), (500, 50)])
    row_lot = box(0, 40, 400, 60)  # a 20 ft right-of-way strip
    got = read([row_lot, LOT], [osm(track, railway="rail")])
    assert got[0] is not None and got[0].category == "rail"
    assert got[1] is None  # 20 of 100 ft is track


def test_only_a_named_open_park_is_a_park() -> None:
    """Measured 2026-10-06: a nature reserve's outline can be a national
    forest's proclamation boundary around private land; an unnamed or gated
    "park" a retirement home's lawn. Metro's ORCA holds the public ones."""
    assert read([LOT], [osm(LOT, leisure="nature_reserve", name="Mount Hood National Forest")]) == [None]
    assert read([LOT], [osm(LOT, leisure="park")]) == [None]
    assert read([LOT], [osm(LOT, leisure="park", name="", access="yes")]) == [None]
    assert read([LOT], [osm(LOT, leisure="park", name="Grounds", access="private")]) == [None]
    got = read([LOT], [osm(LOT, leisure="park", name="Gates Park", access="yes")])[0]
    assert got is not None and got.category == "park"
    got = read([LOT], [], [orca(LOT, unit="Natural Area", owner="Federal", site="Mount Hood NF")])[0]
    assert got is not None and got.category == "park"


def test_a_tunnel_or_a_solar_array_is_not_institutional() -> None:
    track = shapely.LineString([(-50, 50), (500, 50)])
    row_lot = box(0, 40, 400, 60)
    assert read([row_lot], [osm(track, railway="light_rail", tunnel="yes")]) == [None]
    assert read([LOT], [osm(LOT, power="plant", **{"plant:source": "solar"})]) == [None]
    got = read([LOT], [osm(LOT, power="substation", name="Harmony Substation")])[0]
    assert got is not None and got.category == "utility"


def test_a_lone_point_claims_nothing() -> None:
    """A police desk drawn as a point in a strip mall is not the mall."""
    assert read([LOT], [osm(shapely.Point(50, 50), amenity="police")]) == [None]


def test_the_category_covering_most_of_the_lot_wins() -> None:
    got = read(
        [LOT],
        [osm(box(0, 0, 100, 55), amenity="school"), osm(box(0, 55, 100, 100), "way/2", leisure="park", name="A Park")],
    )[0]
    assert got is not None and got.category == "school"


def test_a_lot_with_no_shape_is_not_read() -> None:
    assert read([None, shapely.Polygon()], [osm(LOT, amenity="hospital")]) == [None, None]


# --- the step: one file per snapshot ----------------------------------------


def _lots(tmp_path: Path, rows: list[tuple[str, str, Any]]) -> Path:
    path = tmp_path / "lots.parquet"
    pd.DataFrame({"county": [c for c, _t, _g in rows], "tlid": [t for _c, t, _g in rows], "wkb": [shapely.to_wkb(g) for *_x, g in rows]}).to_parquet(path, index=False)
    return path


def _snapshot(tmp_path: Path, osm_feats: list[dict[str, Any]], orca_feats: list[dict[str, Any]]) -> Path:
    src = tmp_path / "sources"
    src.mkdir()
    for key, feats in (("osm_land_use", osm_feats), ("rlis_orca", orca_feats)):
        (src / f"{key}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    return src


def test_the_step_writes_one_row_per_institutional_lot(tmp_path: Path) -> None:
    lots = _lots(
        tmp_path,
        [
            ("washington", "1N1190002300", box(0, 0, 100, 100)),
            ("multnomah", "1S1E01AA  100", box(1000, 0, 1100, 100)),
            # One TLID in two counties, only one of them a park: the bridge
            # (which keys on TLID alone) must still scan the other.
            ("clackamas", "SHARED", box(2000, 0, 2100, 100)),
            ("multnomah", "SHARED", box(5000, 0, 5100, 100)),
        ],
    )
    src = _snapshot(
        tmp_path,
        [osm(box(-10, -10, 110, 110), amenity="school", name="Westview")],
        [orca(box(990, -10, 1110, 110)), orca(box(1990, -10, 2110, 110))],
    )
    meta = step.run(lots, src, tmp_path / "out", log=lambda _m: None)

    assert meta["institutional"] == 3 and meta["by_category"] == {"park": 2, "school": 1}
    assert meta["tlids_not_whole"] == 1
    assert step.skip_tlids(tmp_path / "out") == {"1N1190002300", "1S1E01AA  100"}
    got = step.by_lot(tmp_path / "out")
    assert got[("washington", "1N1190002300")]["name"] == "Westview"
    assert got[("clackamas", "SHARED")]["whole_tlid"] is False


def test_the_step_refuses_a_snapshot_without_the_extract(tmp_path: Path) -> None:
    lots = _lots(tmp_path, [("washington", "A", LOT)])
    src = tmp_path / "sources"
    src.mkdir()
    with pytest.raises(SystemExit, match="osm_land_use"):
        step.run(lots, src, tmp_path / "out", log=lambda _m: None)


# --- assign: RED whatever it would have read --------------------------------


def _bridge(tmp_path: Path, rows: list[dict[str, Any]], meta: dict[str, Any]) -> Path:
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    pd.DataFrame([{**{c: None for c in az.ROW_COLUMNS}, **r} for r in rows]).to_parquet(bridge / "lots.parquet", index=False)
    (bridge / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return bridge


def _normalized(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    normalized = tmp_path / "normalized"
    normalized.mkdir()
    base = {"jurisdiction": "or/a", "zone": "R5", "zone_raw": "R5", "area_sqft": 5000.0, "gate": None}
    pd.DataFrame([{**base, **r} for r in rows]).to_parquet(normalized / "lots.parquet", index=False)
    return normalized


def _reading(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    out = tmp_path / "institutional"
    out.mkdir()
    base = {"share": 0.97, "source": "osm:way/1", "name": None, "whole_tlid": True}
    pd.DataFrame([{**base, **r} for r in rows], columns=list(step.COLUMNS)).to_parquet(out / step.INSTITUTIONAL, index=False)
    return out


def test_assign_answers_institutional_land_red_measured_gated_or_not(tmp_path: Path) -> None:
    reading = _reading(
        tmp_path,
        [
            {"county": "washington", "TLID": "CAMPUS", "category": "school", "name": "Westview High School"},
            {"county": "washington", "TLID": "GATED", "category": "park", "source": "orca:Park"},
            {"county": "washington", "TLID": "HALF", "category": "park", "whole_tlid": False},
        ],
    )
    bridge = _bridge(
        tmp_path,
        [
            {"TLID": "CAMPUS", "design": "d1", "triage": "green", "if_signed": "green", "colour": "green"},
            {"TLID": "HOUSE", "design": "d1", "triage": "green", "if_signed": "green", "colour": "green"},
        ],
        {"institutional": str(reading)},
    )
    normalized = _normalized(
        tmp_path,
        [
            {"county": "washington", "tlid": "CAMPUS"},
            {"county": "washington", "tlid": "HOUSE"},
            {"county": "washington", "tlid": "GATED", "gate": "OUTSIDE_UGB"},
            {"county": "washington", "tlid": "HALF"},
        ],
    )
    meta = az.assign(normalized, bridge, tmp_path / "out")

    frame = pd.read_parquet(tmp_path / "out" / "lots.parquet")
    assert frame["TLID"].tolist().count("CAMPUS") == 1, "the scan's row for the campus must go"
    by = frame.set_index("TLID")
    campus = by.loc["CAMPUS"]
    assert (campus["triage"], campus["if_signed"], campus["colour"], campus["reasons"]) == ("red", "red", "red", "INSTITUTIONAL_USE")
    bind = json.loads(campus["binds"])[0]
    assert bind["check"] == "institutional_share" and bind["observed"] == 97.0 and bind["threshold"] == 50.0
    assert bind["source"] == "a school, college or university campus (Westview High School), 97% of the lot, per OpenStreetMap way/1"
    assert by.loc["GATED"]["colour"] == "red" and "Metro ORCA (Park)" in json.loads(by.loc["GATED"]["binds"])[0]["source"]
    assert by.loc["HOUSE"]["colour"] == "green"
    # A TLID the reading holds for one county only is answered as before.
    assert by.loc["HALF"]["reasons"] == "NOT_MEASURED,quadfit:unknown"
    assert meta["assign"]["institutional_by_category"] == {"park": 1, "school": 1}
    assert meta["assign"]["institutional_were_scanned"] == 1
    assert meta["institutional"] == str(reading)
    assert "INSTITUTIONAL_USE, by category (red, out of the scan): park 1, school 1" in (tmp_path / "out" / "summary.md").read_text(encoding="utf-8")


def test_without_a_reading_assign_is_unchanged(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, [{"TLID": "CAMPUS", "design": "d1", "triage": "green", "if_signed": "green"}], {})
    normalized = _normalized(tmp_path, [{"county": "washington", "tlid": "CAMPUS"}])
    meta = az.assign(normalized, bridge, tmp_path / "out")
    assert pd.read_parquet(tmp_path / "out" / "lots.parquet")["if_signed"].tolist() == ["green"]
    assert meta["assign"]["institutional_by_category"] == {}


def test_the_bridge_leaves_institutional_lots_out_of_the_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flats.ingest import quadfit as qf

    reading = _reading(tmp_path, [{"county": "washington", "TLID": "CAMPUS", "category": "school"}])
    seen: list[str] = []
    rows = [{"TLID": "CAMPUS", "edges_json": "[]"}, {"TLID": "HOUSE", "edges_json": "[]"}]
    monkeypatch.setattr(qf, "iter_rows", lambda *a, **k: iter([dict(r) for r in rows]))
    monkeypatch.setattr(qf, "_init_worker", lambda *a, **k: None)
    monkeypatch.setattr(qf, "_work_chunk", lambda chunk: [{"TLID": r["TLID"], "design": "d1"} for r in chunk if not seen.append(r["TLID"])])
    monkeypatch.setattr("flats.geom.curbs.missing", lambda _c: [])
    roads = tmp_path / "s1_streets.parquet"
    roads.write_bytes(b"")
    dem = tmp_path / "raw"
    (dem / "dem").mkdir(parents=True)
    (dem / "dem" / "t.tif").write_bytes(b"")

    qf.run(tmp_path / "run", s4=tmp_path / "s4.parquet", s5o=tmp_path / "s5o.parquet", results=None,
           roads=roads, dem=dem, institutional=reading, log=lambda _m: None)

    assert seen == ["HOUSE"]
    meta = json.loads((tmp_path / "run" / "meta.json").read_text(encoding="utf-8"))
    assert meta["institutional"] == str(reading) and meta["institutional_skipped"] == 1
