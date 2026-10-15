"""Portland's Centers Main Street overlay and protected historic resources
(FOLLOWUPS 78, :mod:`flats.geom.pdx_overlays`), at the two lots the
2026-10-14 sample found, on the city's own polygons (EPSG:2913, clipped to a
box around each lot, from the 2026-10-15 acquire)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import shapely
from shapely.geometry import Polygon, box, mapping

from flats.geom import pdx_overlays as pdx

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

# 1S1E22BA  -02300, 6805 S Macadam (CM2), 8,907 sf: the county's taxlot.
MACADAM = Polygon(
    [
        (7644967.51, 666771.91),
        (7645051.95, 666768.65),
        (7645056.67, 666668.08),
        (7644963.64, 666671.68),
        (7644965.58, 666721.95),
    ]
)
# The city's CM2 "d,m" polygon around it, and the Inner pattern area.
MACADAM_M = Polygon(
    [
        (7644917.28, 666671.47), (7644919.61, 666734.19), (7644921.01, 666771.69),
        (7644922.51, 666801.69), (7644903.69, 666802.41), (7644903.69, 666831.86),
        (7645092.51, 666831.86), (7645093.0, 666821.57), (7645095.83, 666761.42),
        (7645102.89, 666611.05), (7645103.03, 666608.12), (7644903.69, 666608.12),
        (7644903.69, 666671.99), (7644917.26, 666671.47),
    ]
)
MACADAM_PATTERN = box(7644903.69, 666608.12, 7645116.6, 666831.86)

# 1N1E22CB  -01200, 4044 N Missouri Ave, 5,000 sf: the county's taxlot.
MISSOURI = Polygon(
    [
        (7644355.95, 695184.99),
        (7644455.80, 695181.75),
        (7644454.18, 695131.78),
        (7644354.33, 695135.01),
    ]
)
MISSOURI_PATTERN = box(7644294.36, 695071.81, 7644515.76, 695244.95)
#: The city's district status polygons: the lot's own house and its two
#: neighbours along N Missouri, as the city draws them.
MISSISSIPPI = "MISSISSIPPI CONSERVATION DISTRICT"
RESOURCES = [
    (
        {"Status": "Contributing", "DistStatus": "Contributing", "DistName": MISSISSIPPI,
         "Address": "4044 N MISSOURI AVE", "YearBuilt": 1910},
        Polygon([(7644357.92, 695132.85), (7644359.54, 695182.82), (7644459.38, 695179.59), (7644457.77, 695129.62)]),
    ),
    (
        {"Status": "Non-contributing", "DistStatus": "Non-contributing", "DistName": MISSISSIPPI,
         "Address": "4032 N MISSOURI AVE", "YearBuilt": 1994},
        Polygon([(7644356.3, 695082.88), (7644357.92, 695132.85), (7644457.77, 695129.62), (7644456.15, 695079.64)]),
    ),
    (
        {"Status": "Contributing", "DistStatus": "Contributing", "DistName": MISSISSIPPI,
         "Address": "4054 N MISSOURI AVE", "YearBuilt": 1910},
        Polygon([(7644359.54, 695182.82), (7644361.15, 695232.8), (7644461.0, 695229.56), (7644459.38, 695179.59)]),
    ),
]


def _fc(features) -> str:
    return json.dumps(
        {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": p, "geometry": mapping(g)} for p, g in features
        ]}
    )


def snapshot(tmp_path: Path, *, pattern: str = "Inner", landmarks=(), resources=RESOURCES) -> Path:
    snap = tmp_path / "snap"
    snap.mkdir(exist_ok=True)
    (snap / f"{pdx.MAIN_STREET_KEY}.geojson").write_text(
        _fc([({"ZONE": "CM2", "OVRLY": "d,m"}, MACADAM_M), ({"ZONE": "R5", "OVRLY": "d"}, MISSOURI)]),
        encoding="utf-8",
    )
    patterns = [({"MapLabel": pattern}, MACADAM_PATTERN), ({"MapLabel": "Inner"}, MISSOURI_PATTERN)]
    (snap / f"{pdx.PATTERN_KEY}.geojson").write_text(_fc(patterns), encoding="utf-8")
    (snap / f"{pdx.RESOURCE_KEY}.geojson").write_text(_fc(resources), encoding="utf-8")
    (snap / f"{pdx.LANDMARK_KEY}.geojson").write_text(_fc(landmarks), encoding="utf-8")
    return snap


@pytest.fixture
def maps(tmp_path):
    return pdx.load(snapshot(tmp_path))


# --- the code ----------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(pdx.CITES))
def test_every_cite_quotes_the_stored_chapter(name) -> None:
    _, where, quote = pdx.CITES[name]
    doc, lines = where.split("#")
    first, last = (int(n) for n in re.findall(r"\d+", lines))
    text = (DOCS / doc).read_text(encoding="utf-8").splitlines()[first - 1 : last]

    def flat(s: str) -> str:
        return " ".join(s.split())

    assert flat(quote) in flat(" ".join(text)), (name, flat(" ".join(text)))


def test_the_minimum_far_is_half_inner_a_quarter_east_and_west_and_none_elsewhere() -> None:
    assert pdx.Reading(True, ("Inner",)).min_far == 0.5
    assert pdx.Reading(True, ("Eastern",)).min_far == 0.25
    assert pdx.Reading(True, ("Western",)).min_far == 0.25
    # Across a line, the stricter; no pattern area at all, the worst case.
    assert pdx.Reading(True, ("Eastern", "Inner")).min_far == 0.5
    assert pdx.Reading(True, ()).min_far == 0.5
    # 33.415.310 states nothing for River or Central City: silence is none.
    assert pdx.Reading(True, ("River",)).min_far is None
    # Off the overlay, no minimum.
    assert pdx.Reading(False, ("Inner",)).min_far is None


def test_an_m_is_a_letter_of_the_overlay_list() -> None:
    assert pdx.has_m("d,m") and pdx.has_m("m") and pdx.has_m("h,m,x")
    assert not pdx.has_m("d") and not pdx.has_m("") and not pdx.has_m(None)


# --- 1S1E22BA  -02300 --------------------------------------------------------


def test_macadam_is_red_on_the_main_street_minimum_far(maps) -> None:
    got = pdx.read(MACADAM, maps)
    assert got.main_street and got.pattern_areas == ("Inner",) and not got.protected
    (bind,) = pdx.binds_for(got, 56 * 36 * 2, MACADAM.area)
    assert bind.check == pdx.MIN_FAR_CHECK
    # 4,032 sf on 8,907 sf: 0.45 against 0.5.
    assert bind.observed == pytest.approx(0.4527, abs=1e-3)
    assert bind.threshold == 0.5
    assert bind.source.startswith("PCC 33.415.310.A")
    # Under 8,064 sf the same pod clears it.
    assert pdx.binds_for(got, 4032, 8064) == ()


def test_the_same_lot_in_the_eastern_pattern_area_clears_a_quarter(tmp_path) -> None:
    got = pdx.read(MACADAM, pdx.load(snapshot(tmp_path, pattern="Eastern")))
    assert got.pattern_areas == ("Eastern",)
    assert pdx.binds_for(got, 4032, MACADAM.area) == ()
    # Past 16,128 sf it does not.
    (bind,) = pdx.binds_for(got, 4032, 16_200)
    assert bind.threshold == 0.25 and bind.source.startswith("PCC 33.415.310.B")


def test_a_lot_partly_in_the_overlay_is_measured_on_that_part(maps) -> None:
    # PCC 33.700.070.F: each zone's standards apply to the portion of the
    # site in that zone. A 150 x 120 ft lot reaching ~49 ft over the
    # overlay's west line on Macadam: 4,032 sf on the whole 18,000 sf is
    # 0.22, under 0.5, but the part in the overlay is ~5,900 sf, and 4,032 sf
    # on it clears the 0.5.
    lot = shapely.box(7644818, 666680, 7644968, 666800)
    got = pdx.read(lot, maps)
    assert got.main_street and 0.3 < got.main_street_share < 0.36
    assert got.main_street_part == got.main_street_share
    assert pdx.binds_for(got, 4032, lot.area) == ()
    # Reach ~99 ft over it and the part is ~11,900 sf: the same pod misses.
    wider = shapely.box(7644818, 666680, 7645018, 666800)
    got = pdx.read(wider, maps)
    (bind,) = pdx.binds_for(got, 4032, wider.area)
    assert bind.threshold == 0.5
    assert bind.observed == pytest.approx(4032 / (wider.area * got.main_street_share), abs=1e-3)
    assert "PCC 33.700.070.F" in bind.source and "in the overlay" in bind.source


def test_a_lot_nearly_all_in_the_overlay_is_the_whole_lot() -> None:
    # Past 90 % the rest is the zoning map and the taxlot disagreeing.
    near = pdx.Reading(True, ("Inner",), main_street_share=0.93)
    assert near.main_street_part == 1.0
    (bind,) = pdx.binds_for(near, 4032, 8907)
    assert bind.observed == pytest.approx(4032 / 8907, abs=1e-4)
    assert "33.700" not in bind.source
    # A row written before the share was read is the whole lot.
    assert pdx.decode('{"pdx_main_street_overlay": true}').main_street_share == 1.0
    assert pdx.decode(pdx.encode(pdx.Reading(True, ("Inner",), main_street_share=0.4))).main_street_share == 0.4


def test_a_lot_the_overlay_only_grazes_is_not_in_it(maps) -> None:
    # The Missouri lot sits under an R5 "d" polygon only; a strip of the
    # Macadam overlay drawn 5 ft into a lot is map noise.
    assert not pdx.read(MISSOURI, maps).main_street
    sliver = shapely.box(MACADAM_M.bounds[0] - 95, 666700, MACADAM_M.bounds[0] + 5, 666750)
    assert not pdx.read(sliver, maps).main_street


# --- 1N1E22CB  -01200 --------------------------------------------------------


def test_missouri_is_red_on_its_contributing_house(maps) -> None:
    got = pdx.read(MISSOURI, maps)
    assert not got.main_street
    # Its own house only: the contributing house next door, and the
    # non-contributing one on the other side, touch it along the lot lines.
    assert got.protected == (
        "contributing resource in Mississippi Conservation District (4044 N MISSOURI AVE, built 1910)",
    )
    (bind,) = pdx.binds_for(got, 4032, MISSOURI.area)
    assert bind.check == pdx.PROTECTED_RESOURCE_CHECK
    assert bind.source.startswith("PCC 33.445.210.E.1")


def test_a_noncontributing_house_in_the_district_stays_as_it_was(maps) -> None:
    # 4032 N Missouri, built 1994, on the city's own outline.
    got = pdx.read(RESOURCES[1][1], maps)
    assert got.protected == () and got.nr_district == ()
    assert pdx.binds_for(got, 4032, RESOURCES[1][1].area) == ()


def test_a_landmark_footprint_on_the_lot_is_protected(tmp_path) -> None:
    house = shapely.box(7644380, 695140, 7644420, 695175)
    landmarks = [({"designation_new": "Historic Landmark", "HISTNAME": "A House"}, house)]
    maps = pdx.load(snapshot(tmp_path, landmarks=landmarks, resources=[]))
    got = pdx.read(MISSOURI, maps)
    assert got.protected == ("historic landmark (A House)",)
    (bind,) = pdx.binds_for(got, 4032, MISSOURI.area)
    assert bind.source.startswith("PCC 33.445.100.E.1")


def test_a_national_register_district_contributor_is_red_on_its_demolition_review(tmp_path) -> None:
    # 33.445.220.E: demolition review, and a permit only "if the review body
    # approves" -- a discretionary review, not a delay, so protected
    # (coordinator 2026-10-15 under Steph's 2026-10-14 rule).
    assert pdx.NR_DISTRICT_RED
    props = {"Status": "Contributing", "DistStatus": "Contributing",
             "DistName": "EASTMORELAND NATIONAL REGISTER DISTRICT", "Address": "X", "YearBuilt": 1920}
    maps = pdx.load(snapshot(tmp_path, resources=[(props, RESOURCES[0][1])]))
    got = pdx.read(MISSOURI, maps)
    assert got.protected == () and len(got.nr_district) == 1
    assert got.red_resources == got.nr_district
    (bind,) = pdx.binds_for(got, 4032, MISSOURI.area)
    assert bind.check == pdx.PROTECTED_RESOURCE_CHECK
    assert bind.source.startswith("PCC 33.445.220.E.1")
    assert "Eastmoreland National Register District" in bind.source
    # A non-contributing house there is not.
    other = {**props, "Status": "Non-contributing", "DistStatus": "Non-contributing"}
    maps = pdx.load(snapshot(tmp_path, resources=[(other, RESOURCES[0][1])]))
    assert pdx.binds_for(pdx.read(MISSOURI, maps), 4032, MISSOURI.area) == ()


# --- on the bridge -----------------------------------------------------------


def test_the_reading_rides_the_row_and_the_lot(tmp_path) -> None:
    from flats.ingest.quadfit import lot_from_row
    from flats.tests.test_quadfit_bridge import row

    rows = [
        row(TLID="1S1E22BA  -02300", zone="CM2", lot_wkb=shapely.to_wkb(MACADAM)),
        row(TLID="1N1E22CB  -01200", lot_wkb=shapely.to_wkb(MISSOURI)),
        row(TLID="elsewhere", jurisdiction="gresham", lot_wkb=shapely.to_wkb(MISSOURI)),
    ]
    assert pdx.with_overlays(rows, snapshot(tmp_path)) == 2
    assert pdx.ROW_KEY not in rows[2]
    assert lot_from_row(rows[0]).pdx_overlays.main_street
    assert lot_from_row(rows[1]).pdx_overlays.protected
    assert lot_from_row(rows[2]).pdx_overlays is None
    # Without the layers nothing is read, and the run refuses.
    assert pdx.with_overlays(rows, None) == 0
    assert pdx.missing(tmp_path) == pdx.KEYS
    assert pdx.missing(tmp_path / "snap") == ()


def test_the_bridge_answers_red_with_a_bind_and_a_reason(tmp_path) -> None:
    from flats.encode.load import load_trusted
    from flats.ingest.quadfit import lot_from_row, row_for, screen_lot
    from flats.score import relief, slack
    from flats.score.flags import Colour
    from flats.score.screen import Triage
    from flats.tests.test_quadfit_bridge import pod

    corpus = load_trusted(strict=False).rules
    policy, relieve = slack.load_policy(), relief.load_policy()
    from flats.tests.test_quadfit_bridge import row

    r = row(TLID="1S1E22BA  -02300", zone="CM2", area_sqft=8907.0, lot_wkb=shapely.to_wkb(MACADAM))
    pdx.with_overlays([r], snapshot(tmp_path))
    (s,) = screen_lot(lot_from_row(r, corpus.layers), [pod()], rules=corpus, policy=policy, relief=relieve, step_deg=30.0)
    assert s.signed.colour is Colour.red and s.signed.triage is Triage.red
    assert pdx.MIN_FAR_REASON in s.signed.reasons
    assert [b.check for b in s.signed.binds].count(pdx.MIN_FAR_CHECK) == 1
    out = row_for(s)
    assert pdx.MIN_FAR_CHECK in out["binds"] and pdx.MIN_FAR_REASON in out["if_signed_reasons"]
    # Run over its own answer, nothing is added twice.
    again = pdx.checked(s, lot_from_row(r).pdx_overlays)
    assert again.signed.binds == s.signed.binds and again.signed.reasons == s.signed.reasons


def test_the_bridge_refuses_a_snapshot_without_the_layers(tmp_path) -> None:
    from flats.geom import curbs
    from flats.ingest import quadfit

    s1 = tmp_path / "s1_streets.parquet"
    s1.write_bytes(b"")
    snap = tmp_path / "snapshot"
    snap.mkdir()
    for key in (*curbs.CURB_KEYS, *curbs.WIDTH_KEYS):
        (snap / f"{key}.geojson").write_text("{}", encoding="utf-8")
    raw = tmp_path / "raw"
    (raw / "dem").mkdir(parents=True)
    (raw / "dem" / "tile.tif").write_bytes(b"")
    with pytest.raises(FileNotFoundError, match=pdx.MAIN_STREET_KEY):
        quadfit.run(tmp_path / "out", s4=tmp_path / "s4_lots.parquet", roads=s1, dem=raw, sources=snap)
