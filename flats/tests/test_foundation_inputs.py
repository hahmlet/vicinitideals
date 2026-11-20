"""FD6 foundation model, slice 4: every drawn lot measured from the sources.

The per-lot inputs the lot file held for the research lots are worked out from
the sources by FD2 pass 1's rules (:mod:`flats.foundation.inputs`): a lot whose
ground cannot be read sorts "not sorted", never "ordinary". Each record is
stamped with the drawn ring it was measured on, and a record whose drawing has
moved since reads "measured on an earlier drawing" with no figure.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from flats.foundation import ground as grounds
from flats.foundation import inputs as fin
from flats.foundation import measure, record, report, settings, support

S = settings.load()
VERSION = record.settings_version()
WHEN = "2026-11-20T04:00:00+00:00"
RING = [[7_640_000.0, 690_000.0], [7_640_080.0, 690_000.0], [7_640_080.0, 690_025.0], [7_640_000.0, 690_025.0],
        [7_640_000.0, 690_000.0]]
REPO = Path(__file__).resolve().parents[2]


def _script():
    spec = importlib.util.spec_from_file_location("flats_foundation_script", REPO / "scripts" / "flats_foundation.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("flats_foundation_script", mod)
    spec.loader.exec_module(mod)
    return mod


def _doc(*, ring=RING, run="run 128", tlid: str = "1S2E08BA  -09500") -> dict:
    m = measure.measure(grounds.plane(S, 2.0, 1.0), S, tlid=tlid, county="multnomah",
                        inputs={"ground_class": "FIRM", "frost_register_in": 12.0})
    return json.loads(json.dumps(record.document(m, drawing="run 128 drawings", measured_at=WHEN, run=run, ring=ring)))


def _moved(ring, dx: float = 0.0, dy: float = 0.0) -> list[list[float]]:
    return [[x + dx, y + dy] for x, y in ring]


# ---------------------------------------------------------------- the framing footprint


def test_the_framing_sits_centred_in_the_drawn_finished_box() -> None:
    from flats.foundation.frame import frame

    fr = frame(RING, ((7_639_900.0, 689_990.0, 7_640_200.0, 689_990.0),))  # a street along the front
    x0, y0 = RING[0]
    got = fr.world([0.0, S.length_ft], [0.0, S.width_ft], S.length_ft, S.width_ft, S.box_ft)
    assert got[0] == pytest.approx([x0 + 1.625 / 12, y0 + 1.53125 / 12])  # 1-5/8 in in, 1-17/32 in in
    assert got[1] == pytest.approx([x0 + 80 - 1.625 / 12, y0 + 25 - 1.53125 / 12])
    back = fr.model(got, S.length_ft, S.width_ft, S.box_ft)
    assert back[1] == pytest.approx([S.length_ft, S.width_ft])
    # without a box the model spans the drawn rectangle, as before
    assert fr.world([80.0], [25.0], 80.0, 25.0)[0] == pytest.approx([x0 + 80, y0 + 25])


def test_a_record_names_the_footprint_it_was_measured_on() -> None:
    on = _doc()["measured_on"]
    assert on["footprint"] == "framing 956.75 x 296.9375 in, centred in the 80 x 25 ft finished faces"
    assert record.footprint_words({"length_ft": 80, "width_ft": 25}) == "80 x 25 ft (the finished faces)"


def test_a_record_on_another_footprint_reads_needs_remeasuring() -> None:
    from flats.tests.foundation_key import key_settings

    old = key_settings()
    m = measure.measure(grounds.plane(old, 2.0, 1.0), old, tlid="1S2E08BA  -09500", county="multnomah",
                        inputs={"ground_class": "FIRM", "frost_register_in": 12.0})
    doc = json.loads(json.dumps(record.document(m, drawing="d", measured_at=WHEN, run="run 128", ring=RING)))
    out = report.describe(doc, S, version=VERSION, drawing=RING)
    assert out["status"] == report.NEEDS_REMEASURING and out["remeasure_because"][0] == "footprint"
    assert "length_ft" in out["remeasure_because"]
    assert "Measured on a different building footprint" in out["status_words"]
    assert "framing 960 x 300 in" in out["status_words"] and "framing 956.75 x 296.9375 in" in out["status_words"]
    assert "methods" not in out and "$" not in out["status_words"]
    # a slice-3 record (finished size, no footprint stamp) says so too
    geo = json.loads(doc["lot"]["geometry"])
    for k in ("finished_length_ft", "finished_width_ft"):
        geo.pop(k)
    doc["lot"]["geometry"] = json.dumps(geo)
    doc["measured_on"].pop("footprint")
    out = report.describe(doc, S, version=VERSION)
    assert out["remeasure_because"][0] == "footprint" and "80 x 25 ft (the finished faces)" in out["status_words"]
    # measured on the shipped footprint: priced
    assert report.describe(_doc(), S, version=VERSION, drawing=RING)["status"] == report.PRICED


# ---------------------------------------------------------------- the drawing stamp


def test_a_record_carries_the_ring_it_was_measured_on() -> None:
    doc = _doc()
    on = doc["measured_on"]
    assert on["run"] == "run 128" and on["drawing"] == "run 128 drawings"
    assert on["drawing_hash"] == record.ring_hash(RING) and on["drawn_ring"] == RING
    # a slice-3 record (no ring given) is stamped with nothing new
    plain = record.document(measure.measure(grounds.plane(S, 2.0, 1.0), S), drawing="d", measured_at=WHEN)
    assert set(plain["measured_on"]) == {"drawing", "ground_source", "cell_m", "measured_at", "footprint"}


def test_the_ring_hash_holds_through_rounding_and_moves_with_the_drawing() -> None:
    assert record.ring_hash(RING) == record.ring_hash(_moved(RING, 0.01, -0.02))
    assert record.ring_hash(RING) != record.ring_hash(_moved(RING, 1.0))


@pytest.mark.parametrize(
    ("now", "changed"),
    [
        (RING, False),
        (_moved(RING, 0.1, 0.05), False),  # within 0.15 ft a vertex: the same drawing, rounded
        (_moved(RING, 0.5), True),  # drawn half a foot along
        (_moved(RING, 6.0), True),
        (RING[:-1], True),  # another vertex count
        (None, None),  # the page has no drawing: not checked
        ([], None),
    ],
)
def test_drawing_changed(now, changed) -> None:
    assert record.drawing_changed(_doc(), now) is changed


def test_a_slice_3_record_is_never_called_moved() -> None:
    doc = _doc(ring=None, run=None)
    assert record.drawing_changed(doc, RING) is None


def test_the_flat_tables_keep_the_drawing_stamp() -> None:
    docs = [_doc(), _doc(ring=None, run=None, tlid="1N1E29DD  -05600")]
    tables: dict[str, list[dict]] = {name: [] for name in record.TABLES}
    for d in docs:
        for name, recs in record.table_rows(d).items():
            tables[name].extend(recs)
    assert json.loads(tables["lots"][0]["drawn_ring"]) == RING and tables["lots"][0]["run"] == "run 128"
    assert "drawn_ring" not in tables["lots"][1]
    assert [json.loads(json.dumps(d)) for d in record.documents_from_tables(tables)] == docs


# ---------------------------------------------------------------- the report


def test_a_moved_drawing_shows_no_figure() -> None:
    block = report.describe(_doc(), S, version=VERSION, drawing=_moved(RING, 6.0))
    assert block["status"] == report.NEEDS_REMEASURING and block["remeasure_because"] == ["drawing"]
    assert block["status_words"] == report.EARLIER_DRAWING
    assert block["drawing_checked"] is True
    for key in ("methods", "cheaper", "old_buildings", "challenges", "style", "flags"):
        assert key not in block
    # the stored ring stays out of the block; its hash and run are shown
    assert "drawn_ring" not in block["measured_on"] and block["measured_on"]["run"] == "run 128"


def test_the_same_drawing_is_priced_and_says_it_was_checked() -> None:
    same = report.describe(_doc(), S, version=VERSION, drawing=RING)
    assert same["status"] == report.PRICED and same["drawing_checked"] is True
    unchecked = report.describe(_doc(), S, version=VERSION)
    assert unchecked["status"] == report.PRICED and unchecked["drawing_checked"] is False
    old = report.describe(_doc(ring=None, run=None), S, version=VERSION, drawing=_moved(RING, 6.0))
    assert old["status"] == report.PRICED and old["drawing_checked"] is False


def test_a_moved_drawing_wins_over_other_settings() -> None:
    block = report.describe(_doc(), S.replace(grow_ft=4.0), version=VERSION, drawing=_moved(RING, 6.0))
    assert block["remeasure_because"] == ["drawing"]


# ---------------------------------------------------------------- the ground class (FD2's rules)

FIRM_SOIL = {"soil_no_data": False, "restrictions_known": True, "bedrock_cm": None, "pan_cm": None,
             "frag_gt3in_pct": 2.0, "lep_1_5ft_pct": 1.5, "hydric": "No", "organic_1_5ft": False,
             "drainage": "Well drained", "water_cm": None, "water_months_held": True}
NO_HAZARD = {"slide_mapped": False, "slide_top": False, "liq_top2": False, "flood_100": False}


def _group(cls: str, alt: str | None = None) -> str:
    return support.group_of_class(support.effective_class_of(cls, alt), S)


@pytest.mark.parametrize(
    ("change", "cls"),
    [
        ({}, "FIRM"),
        ({"slide_mapped": True}, "HAZ-SLIDE"),
        ({"slide_top": True}, "HAZ-SLIDE"),
        ({"liq_top2": True}, "HAZ-LIQ"),
        ({"flood_100": True}, "FLOOD"),
        ({"soil_no_data": True}, "NO-DATA"),
        ({"soil_no_data": None}, "NO-DATA"),  # no survey polygon under the footprint
        ({"bedrock_cm": 100.0}, "ROCK"),
        ({"frag_gt3in_pct": 20.0}, "COBBLE"),
        ({"lep_1_5ft_pct": 7.0}, "SWELL"),
        ({"hydric": "Yes"}, "SOFT"),
        ({"water_cm": 30.0}, "WET-FINE"),
        ({"drainage": "Poorly drained"}, "WET-FINE"),
    ],
)
def test_ground_class_first_match_wins(change, cls) -> None:
    got, _unread, _pan = fin.ground_class({**FIRM_SOIL, **NO_HAZARD, **change})
    assert got == cls


def test_an_unread_check_is_named_never_matched() -> None:
    got, unread, _ = fin.ground_class({**FIRM_SOIL, **NO_HAZARD, "liq_top2": None, "flood_100": None})
    assert got == "FIRM" and unread == ["HAZ-LIQ", "FLOOD"]


def test_an_unread_hazard_check_sorts_not_sorted_never_ordinary() -> None:
    # FD2 calls this FIRM (an unread check never matches); the model may not
    unread_flood = {**NO_HAZARD, "flood_100": None}
    ins, facts = fin.model_inputs(FIRM_SOIL, unread_flood, frost_in=12, year=None, turn_deg=0.0)
    assert ins["ground_class"] == fin.UNREAD
    assert facts["fd2_ground_class"] == "FIRM" and facts["ground_class_unread"] == "FLOOD"
    assert _group(ins["ground_class"], ins["alt_ground_class"]) == support.NOT_SORTED
    # an Urban-land lot whose named series is firm, flood unread: still not sorted
    ins, _ = fin.model_inputs({**FIRM_SOIL, "soil_no_data": True, "_alt": FIRM_SOIL}, unread_flood,
                              frost_in=12, year=None, turn_deg=0.0)
    assert _group(ins["ground_class"], ins["alt_ground_class"]) == support.NOT_SORTED
    # a check below a class that matched is not needed: the hazard class stands
    ins, facts = fin.model_inputs(FIRM_SOIL, {**unread_flood, "slide_mapped": True}, frost_in=12, year=None,
                                  turn_deg=0.0)
    assert ins["ground_class"] == "HAZ-SLIDE" and facts["ground_class_unread"] is None
    # every check read: FD2's class is the model's
    ins, facts = fin.model_inputs(FIRM_SOIL, NO_HAZARD, frost_in=12, year=None, turn_deg=0.0)
    assert ins["ground_class"] == facts["fd2_ground_class"] == "FIRM"


def test_ground_that_cannot_be_read_is_not_sorted_never_ordinary() -> None:
    # no survey polygon under the footprint
    soil = fin.soil_facts({}, 2000.0, {})
    assert soil["soil_no_data"] is None and soil["soil_missing"]
    ins, facts = fin.model_inputs(soil, NO_HAZARD, frost_in=None, year=None, turn_deg=None)
    assert ins["ground_class"] == "NO-DATA" and ins["alt_ground_class"] is None
    assert _group(ins["ground_class"], ins["alt_ground_class"]) == support.NOT_SORTED
    assert facts["soil_missing"] == "no survey polygon under the footprint"
    # a map unit with no components
    soil = fin.soil_facts({"1": 2000.0}, 2000.0, {"1": {"musym": "X", "components": []}})
    assert soil["soil_no_data"] is True
    ins, _ = fin.model_inputs(soil, NO_HAZARD, frost_in=None, year=None, turn_deg=None)
    assert _group(ins["ground_class"], ins["alt_ground_class"]) == support.NOT_SORTED
    # nothing at all
    assert _group("", None) == support.NOT_SORTED and _group(None, None) == support.NOT_SORTED


def _horizons(unified: str = "ML", lep: float = 1.5) -> list[dict]:
    return [{"hzdept_r": 0, "hzdepb_r": 200, "unified": unified, "lep_r": lep, "frag3to10_r": 0, "fraggt10_r": 0}]


def test_urban_land_takes_the_named_series_as_its_alternative() -> None:
    units = {"77": {"musym": "50", "muname": "Urban land-Quatama complex", "components": [
        {"cokey": "a", "compname": "Urban land", "comppct_r": 60, "horizons": []},
        {"cokey": "b", "compname": "Quatama", "comppct_r": 30, "horizons": _horizons(), "drainagecl": "Moderately well drained",
         "hydricrating": "No", "months": [{"month": "Jan", "monthseq": 1, "wet_top_cm": 90}]},
    ]}}
    soil = fin.soil_facts({"77": 1500.0, "12": 500.0}, 2000.0, units)
    assert soil["soil_no_data"] is True and soil["alt_comp"] == "Quatama" and soil["mu_share"] == 0.75
    ins, _ = fin.model_inputs(soil, NO_HAZARD, frost_in=12, year="1948", turn_deg=3.2)
    assert ins["ground_class"] == "NO-DATA" and ins["alt_ground_class"] == "FIRM"
    assert _group(ins["ground_class"], ins["alt_ground_class"]) == support.ORDINARY
    assert ins["frost_register_in"] == 12.0 and ins["year_built"] == 1948.0 and ins["front_face_turn_deg"] == 3.2
    assert ins["relief_input_ft"] is None and ins["bldg_overlap_share"] is None
    # flooded ground under the named series sorts FLOOD
    flooded = fin.classes(soil, {**NO_HAZARD, "flood_100": True})
    assert flooded["ground_class"] == "FLOOD"


def _row(layer: str, state: str, code, label=None, share: float = 1.0, detail=None) -> dict:
    return {"layer": layer, "state": state, "class_code": code, "class_label": label, "share": share, "detail": detail}


def test_hazard_facts_read_slides_liquefaction_and_flood() -> None:
    have = set(fin.HAZARD_KEYS)
    rows = [
        _row("landslide_shallow", "class", "3", "High", 0.4),
        _row("landslide_shallow", "outside", None, share=0.0),
        _row("landslide_inventory", "nearest", "Deposit", detail={"distance_ft": 80.0}),
        _row("liquefaction", "class", "4", "High", 1.0),
        _row("flood_fema", "class", "X", None, 1.0, {"in_100_year": False}),
    ]
    out = fin.hazard_facts(rows, have, scarp_within_100ft=False)
    assert out["slide_top"] is True and out["slide_mapped"] is True  # a deposit 80 ft away
    assert out["liq_top2"] is True and out["flood_100"] is False and out["fema_zone"] == "X"
    quiet = fin.hazard_facts([_row("landslide_shallow", "class", "1", "Low")], have, scarp_within_100ft=False)
    assert quiet["slide_top"] is False and quiet["slide_mapped"] is False
    assert quiet["liq_top2"] is None  # no liquefaction polygon: unread
    assert quiet["fema_zone"] == "not mapped" and quiet["flood_100"] is None
    gone = fin.hazard_facts([], set(), scarp_within_100ft=None)
    assert gone["slide_top"] is None and gone["slide_mapped"] is None and gone["flood_100"] is None


def test_nfhl_answers_flood_only_where_the_held_layer_does_not() -> None:
    unmapped = {"fema_zone": "not mapped", "flood_100": None}
    assert fin.with_nfhl(unmapped, [])["flood_100"] is None
    hit = fin.with_nfhl(unmapped, [{"FLD_ZONE": "AE", "ZONE_SUBTY": "", "SFHA_TF": "T"}, {"FLD_ZONE": "X", "SFHA_TF": "F"}])
    assert hit["flood_100"] is True and hit["fema_zone"] == "AE, X" and hit["fema_source"].startswith("FEMA NFHL")
    held = {"fema_zone": "A", "flood_100": True, "fema_source": "held overlay_fema_flood"}
    assert fin.with_nfhl(held, [{"FLD_ZONE": "X", "SFHA_TF": "F"}]) == held


def test_reach_and_held_box() -> None:
    assert fin.hazard_reach_ft([None, 1000.0, 50.0]) == 1001.0
    assert fin.hazard_reach_ft([None]) == fin.SCARP_RING_FT + 1.0
    assert fin.held_box((10.0, 20.0, 30.0, 40.0)) == (-1490.0, -1480.0, 1530.0, 1540.0)


def test_front_face_turn_and_year() -> None:
    fl, fr, bl, br = (0.0, 0.0), (80.0, 0.0), (0.0, 25.0), (80.0, 25.0)
    street = [(-10.0, -20.0, 100.0, -20.0)]
    got = fin.front_face(fl, fr, bl, br, street)
    assert got["front_face_turn_deg"] == 0.0 and got["front_face_street_ft"] == 20.0
    end_on = fin.front_face(fl, fr, bl, br, [(-20.0, -10.0, -20.0, 40.0)])
    assert end_on["front_face_turn_deg"] == 90.0
    assert fin.front_face(fl, fr, bl, br, [])["front_face_turn_deg"] is None
    assert fin.year_built("1948") == 1948 and fin.year_built("0") is None and fin.year_built("") is None


# ---------------------------------------------------------------- the routine's plumbing


def test_county_of_and_geojson_reading() -> None:
    mod = _script()
    assert mod.county_of("or/multnomah/portland") == "multnomah" and mod.county_of(None) is None
    text = ('{"type":"FeatureCollection","fetched":"2026-11-18","features":[ {"type":"Feature","geometry":null,'
            '"properties":{"a":1}},\n {"type":"Feature","properties":{"a":2}} ],"envelope":"-122.79,45.4"}')
    assert [f["properties"]["a"] for f in mod.geojson_features(text)] == [1, 2]
    assert mod.geojson_head(text) == {"fetched": "2026-11-18", "envelope": "-122.79,45.4"}


def test_population_keeps_drawn_lots_of_the_colours_asked(tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    mod = _script()
    drawn = json.dumps({"building": RING})
    rows = [
        {"TLID": "2S1E  -00200", "colour": "green", "layer_id": "or/washington/tigard", "jurisdiction": "or/tigard", "drawing": drawn},
        {"TLID": "1S2E08BA  -09500", "colour": "yellow", "layer_id": "or/multnomah/portland", "jurisdiction": "or/portland", "drawing": drawn},
        {"TLID": "1S2E08BA  -09600", "colour": "yellow", "layer_id": "or/multnomah/portland", "jurisdiction": "or/portland", "drawing": None},
        {"TLID": "1S2E08BA  -09700", "colour": "red", "layer_id": "or/multnomah/portland", "jurisdiction": "or/portland", "drawing": drawn},
    ]
    src = tmp_path / "lots.parquet"
    pq.write_table(pa.Table.from_pylist(rows), src)
    got = mod.population(src, {"green", "yellow"}, tmp_path / "pop.parquet")
    assert got["lots"] == 2 and got["counts"]["yellow not drawn"] == 1
    pop = pq.read_table(tmp_path / "pop.parquet").to_pylist()
    assert [p["TLID"] for p in pop] == ["1S2E08BA  -09500", "2S1E  -00200"]  # county + TLID order, spaces kept
    assert pop[0]["drawing_hash"] == record.ring_hash(RING) and json.loads(pop[0]["ring"]) == RING
    pq.write_table(pa.Table.from_pylist(rows + rows[:1]), src)
    with pytest.raises(SystemExit):
        mod.population(src, {"green"}, tmp_path / "pop2.parquet")
