"""Public sewer service (Steph 2026-11-10, rulings.yaml 2026-11-10-no-public-sewer-red).

A lot shown outside public sewer is RED; a place with no sewer data leaves the
lot's colour alone and flags it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapely

from flats.geom import sewer

ROOT = Path(__file__).resolve().parents[2]

#: A small spec of the real file's shape: Portland measured by its own
#: mains, Clackamas by its districts, Canby nowhere.
DOC = {
    "reach_ft_per_dwelling": 200,
    "dwellings": 4,
    "reach_quote": "or/oar.340-071-0160.txt#L56",
    "front_ft": 50,
    "mains": {
        "mains_pdx": {"serves": ["or/multnomah/portland"], "exclude": {"SERVSTAT": ["ABAN"]}},
        "mains_lo": {"serves": ["or/clackamas/lake-oswego"]},
    },
    "areas": {"districts": {}},
    "measured": {"or/multnomah/portland": "mains", "or/clackamas/_unincorporated": "districts"},
}
SPEC = sewer.parse(DOC)


def _fc(features: list[tuple[object, dict]]) -> str:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": shapely.geometry.mapping(g), "properties": p} for g, p in features
            ],
        }
    )


@pytest.fixture
def snap(tmp_path: Path) -> Path:
    """Portland main along y=0 from x=0 to 1000 (and an abandoned one by
    x=5000), a Lake Oswego main along y=0 from x=10000 to 11000, and one
    district: the square 20000..21000."""
    s = tmp_path / "2026-11-10"
    s.mkdir()
    (s / "mains_pdx.geojson").write_text(
        _fc(
            [
                (shapely.LineString([(0, 0), (1000, 0)]), {"SERVSTAT": "IN"}),
                (shapely.LineString([(5000, 0), (5100, 0)]), {"SERVSTAT": "ABAN"}),
            ]
        ),
        encoding="utf-8",
    )
    (s / "mains_lo.geojson").write_text(_fc([(shapely.LineString([(10000, 0), (11000, 0)]), {})]), encoding="utf-8")
    (s / "districts.geojson").write_text(_fc([(shapely.box(20000, 0, 21000, 1000), {})]), encoding="utf-8")
    return s


def _read(snap: Path, lot, layer_id: str) -> sewer.Reading:
    (got,) = sewer.read_lots([lot], [layer_id], sewer.load_maps(snap, SPEC), SPEC)
    return got


# --- the file and its law ------------------------------------------------------


def test_the_reach_is_the_states_200_ft_per_dwelling_for_four_homes() -> None:
    spec = sewer.load_spec()
    assert spec.reach_ft == 800.0
    path, line = spec.reach_quote.split("#L")
    text = (ROOT / "flats" / "provenance" / "docs" / path).read_text(encoding="utf-8").splitlines()
    assert "200 feet multiplied by the number of dwellings" in text[int(line) - 1]


def test_every_layer_named_is_registered_and_every_main_serves_a_place() -> None:
    from flats.ingest.sources import load_pipeline

    spec = sewer.load_spec()
    registered = set(load_pipeline().datasets)
    assert set(spec.keys) <= registered
    assert all(spec.serves[k] for k in spec.mains)


def test_the_bridge_refuses_a_snapshot_without_the_layers(tmp_path: Path) -> None:
    assert sewer.missing(None, SPEC) == SPEC.keys
    (tmp_path / "mains_pdx.geojson").write_text(_fc([]), encoding="utf-8")
    assert sewer.missing(tmp_path, SPEC) == ("mains_lo", "districts")


def test_the_bridge_run_names_the_missing_sewer_layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flats.ingest import quadfit as qf

    monkeypatch.setattr("flats.geom.curbs.missing", lambda _c: [])
    monkeypatch.setattr("flats.geom.pdx_overlays.missing", lambda _s: [])
    monkeypatch.setattr("flats.geom.driveway_spacing.missing", lambda _s: [])
    roads = tmp_path / "s1_streets.parquet"
    roads.write_bytes(b"")
    (tmp_path / "raw" / "dem").mkdir(parents=True)
    (tmp_path / "raw" / "dem" / "t.tif").write_bytes(b"")
    snap = tmp_path / "snap"
    snap.mkdir()
    with pytest.raises(FileNotFoundError, match="util_sewer_cws_boundary"):
        qf.run(tmp_path / "out", s4=tmp_path / "s4.parquet", roads=roads, dem=tmp_path / "raw", sources=snap)


# --- the three states ----------------------------------------------------------


def test_a_lot_by_its_own_providers_main_is_served(snap: Path) -> None:
    got = _read(snap, shapely.box(100, 700, 200, 790), "or/multnomah/portland")
    assert got.state == sewer.SERVED and got.main_ft == pytest.approx(700)


def test_a_lot_inside_a_district_is_served_with_no_main(snap: Path) -> None:
    got = _read(snap, shapely.box(20100, 100, 20200, 200), "or/clackamas/_unincorporated")
    assert got.state == sewer.SERVED


def test_a_measured_lot_past_the_reach_is_outside(snap: Path) -> None:
    got = _read(snap, shapely.box(100, 900, 200, 1000), "or/multnomah/portland")
    assert got.state == sewer.OUTSIDE and got.main_ft == pytest.approx(900)
    assert "800 ft" in got.why


def test_an_abandoned_main_serves_nobody(snap: Path) -> None:
    got = _read(snap, shapely.box(5000, 10, 5100, 110), "or/multnomah/portland")
    assert got.state == sewer.OUTSIDE


def test_another_citys_main_off_the_street_does_not_serve(snap: Path) -> None:
    """The Lake Oswego edge: an unincorporated lot outside every district,
    300 ft from the city's main, is outside -- the city need not serve it."""
    got = _read(snap, shapely.box(10100, 300, 10200, 400), "or/clackamas/_unincorporated")
    assert got.state == sewer.OUTSIDE and got.main_ft is None


def test_another_citys_main_in_the_street_is_the_street_main_state(snap: Path) -> None:
    """Steph 2026-11-11 (2026-11-11-sewer-pipe-in-street-yellow): outside
    every district with a city main in the street -- not outside, not
    unmeasured."""
    got = _read(snap, shapely.box(10100, 30, 10200, 130), "or/clackamas/_unincorporated")
    assert got.state == sewer.STREET_MAIN and "another provider" in got.why and "annexation" in got.why


def test_a_street_main_in_an_unmapped_place_stays_unmeasured(snap: Path) -> None:
    got = _read(snap, shapely.box(10100, 30, 10200, 130), "or/clackamas/canby")
    assert got.state == sewer.UNMEASURED and "not mapped" in got.why


def test_a_place_with_no_data_is_unmeasured_never_outside(snap: Path) -> None:
    got = _read(snap, shapely.box(50000, 50000, 50100, 50100), "or/clackamas/canby")
    assert got.state == sewer.UNMEASURED and "no sewer service data" in got.why


def test_the_real_file_leaves_canby_estacada_and_multnomah_pockets_unmeasured() -> None:
    spec = sewer.load_spec()
    for place in ("or/clackamas/canby", "or/clackamas/estacada", "or/multnomah/_unincorporated"):
        assert not spec.measures(place), place
    for place in ("or/washington/hillsboro", "or/clackamas/_unincorporated", "or/multnomah/portland"):
        assert spec.measures(place), place


def test_with_sewer_writes_the_reading_onto_rows(snap: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sewer, "load_spec", lambda *a: SPEC)
    rows = [
        {"TLID": "A", "lot_wkb": shapely.to_wkb(shapely.box(100, 10, 200, 110)), "j": "or/multnomah/portland"},
        {"TLID": "B", "lot_wkb": shapely.to_wkb(shapely.box(100, 900, 200, 1000)), "j": "or/multnomah/portland"},
        {"TLID": "C"},
    ]
    counts = sewer.with_sewer(rows, snap, lambda r: r["j"])
    assert counts == {sewer.SERVED: 1, sewer.OUTSIDE: 1, sewer.STREET_MAIN: 0, sewer.UNMEASURED: 0}
    assert sewer.reading_of(rows[1]).state == sewer.OUTSIDE
    assert sewer.reading_of(rows[2]) is None


# --- on the screen -------------------------------------------------------------


def _screened(reading: sewer.Reading | None):
    import dataclasses

    from flats.score.screen import Triage
    from flats.tests.test_historic_lists import _screened as screened

    s = screened("1S3E10BC  -99999", zone="R-5", jurisdiction="gresham")
    clean = dataclasses.replace(s.signed, triage=Triage.green, binds=(), flags=(), reasons=())
    return sewer.checked(dataclasses.replace(s, signed=clean, screening=clean), reading)


def test_a_served_lot_is_unchanged() -> None:
    from flats.score.flags import Colour

    s = _screened(sewer.Reading(sewer.SERVED, 20.0, "a public main"))
    assert s.signed.colour is Colour.green and not s.signed.flags and not s.signed.binds


def test_a_lot_outside_public_sewer_is_red_and_says_why() -> None:
    from flats.score.flags import Colour
    from flats.score.screen import Triage

    s = _screened(sewer.Reading(sewer.OUTSIDE, 7546.0, "outside every sewer district"))
    assert s.signed.colour is Colour.red and s.signed.triage is Triage.red
    assert sewer.NO_PUBLIC_SEWER in s.signed.reasons
    bind = next(b for b in s.signed.binds if b.check == sewer.CHECK)
    assert bind.observed == 7546.0 and bind.threshold == 800.0 and "2026-11-10" in bind.source
    again = sewer.checked(s, sewer.Reading(sewer.OUTSIDE, 7546.0, "outside every sewer district"))
    assert again.signed.binds == s.signed.binds and again.signed.reasons == s.signed.reasons


def test_a_place_with_no_data_flags_the_lot_and_keeps_its_colour() -> None:
    from flats.score.flags import Colour

    s = _screened(sewer.Reading(sewer.UNMEASURED, None, "no sewer service data for this place"))
    assert s.signed.colour is Colour.green
    assert [f.code for f in s.signed.flags] == [sewer.UNMEASURED_FLAG]
    assert sewer.NO_PUBLIC_SEWER not in s.signed.reasons


def test_a_city_main_in_the_street_makes_a_green_lot_yellow_with_its_flag() -> None:
    """Steph 2026-11-11: YELLOW + SEWER-STREET-MAIN, never GREEN, never RED
    on this ground; the flag is at or over the yellow line."""
    import dataclasses

    from flats.score import flags as flag_plan
    from flats.score.flags import Colour
    from flats.score.screen import Triage

    why = "outside every sewer district, but another provider's main is 26 ft off, in its street"
    s = _screened(sewer.Reading(sewer.STREET_MAIN, None, why))
    assert s.signed.triage is Triage.yellow and s.signed.colour is Colour.yellow
    assert [f.code for f in s.signed.flags] == [sewer.STREET_MAIN_FLAG]
    assert sewer.STREET_MAIN_REASON in s.signed.reasons and sewer.NO_PUBLIC_SEWER not in s.signed.reasons
    assert not any(b.check == sewer.CHECK for b in s.signed.binds)
    assert "2026-11-11" in s.signed.flags[0].source
    line = flag_plan.colour_rules().yellow_at_severity
    assert flag_plan.severity_of(s.signed.flags[0], flag_plan.registry()) >= line
    again = sewer.checked(s, sewer.Reading(sewer.STREET_MAIN, None, why))
    assert again.signed.flags == s.signed.flags and again.signed.reasons == s.signed.reasons
    red = dataclasses.replace(s.signed, triage=Triage.red)
    kept = sewer.checked(dataclasses.replace(s, signed=red, screening=red), sewer.Reading(sewer.STREET_MAIN, None, why))
    assert kept.signed.triage is Triage.red


def test_the_bridge_lot_carries_the_reading() -> None:
    from flats.ingest.quadfit import lot_from_row
    from flats.tests.test_quadfit_bridge import row

    r = row(TLID="X", lot_wkb=shapely.to_wkb(shapely.box(0, 0, 100, 100)))
    r.update({sewer.ROW_STATE: sewer.OUTSIDE, sewer.ROW_MAIN_FT: 900.0, sewer.ROW_WHY: "far"})
    assert lot_from_row(r).sewer == sewer.Reading(sewer.OUTSIDE, 900.0, "far")
