"""FD5 pass 2 measures (flats/ingest/fd5.py) and the lot-file join
(scripts/flats_fd5_pass2.py): report only, nothing screens on them."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from shapely.geometry import box

from flats.ingest import fd5

ROOT = Path(__file__).resolve().parents[2]


def _script():
    spec = importlib.util.spec_from_file_location("fd5_script", ROOT / "scripts" / "flats_fd5_pass2.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(("share", "band"), [
    (None, "not held"), (0.0, "none"), (0.001, "under 25%"), (0.2499, "under 25%"),
    (0.25, "25% and over"), (1.0, "25% and over"),
])
def test_overlap_band(share, band):
    assert fd5.overlap_band(share) == band


@pytest.mark.parametrize(("year", "band"), [
    (None, "not held"), ("", "not held"), ("0", "not held"), (1939, "before 1940"),
    ("1940", "1940-1959"), (1959.0, "1940-1959"), (1960, "1960 on"), ("2021", "1960 on"),
])
def test_year_band(year, band):
    assert fd5.year_band(year) == band


LOT = box(0, 0, 100, 150)
FP = box(10, 40, 90, 65)  # 80 x 25 = 2,000 sq ft


def test_stand_on_overlap_counts_any_building_and_blanks_the_gap():
    house = box(20, 50, 60, 100)  # 40 x 15 of it under the pod: 600 sq ft
    shed = box(80, 60, 89, 69)  # 81 sq ft, under 200: not a building on the lot, still under the pod
    got = fd5.stand_on(FP, LOT, [house, shed], [house, shed])
    assert got["bldg_overlap_sqft"] == pytest.approx(600 + 9 * 5)
    assert got["bldg_overlap_share"] == pytest.approx(645 / 2000, abs=1e-4)
    assert got["bldg_overlap_band"] == "25% and over"
    assert got["bldg_on_lot_n"] == 1  # the shed is under the occupancy rule's 200 sq ft
    assert got["bldg_gap_ft"] is None and got["bldg_gap_any_ft"] == 0.0


def test_stand_on_clear_footprint_measures_the_gap_to_the_lot_building_only():
    house = box(30, 100, 70, 140)  # 35 ft behind the pod's back face
    neighbour = box(-60, 40, -5, 80)  # off the lot, 15 ft from the pod
    got = fd5.stand_on(FP, LOT, [house], [house, neighbour])
    assert got["bldg_overlap_band"] == "none" and got["bldg_overlap_sqft"] == 0.0
    assert got["bldg_gap_ft"] == pytest.approx(35.0)
    assert got["bldg_gap_any_ft"] == pytest.approx(15.0)


def test_stand_on_sliver_is_none_and_drift_over_the_line_does_not_count_on_the_lot():
    sliver = box(89.5, 40, 120, 100)  # 0.5 ft x 25 under the pod = 12.5: not a sliver
    tiny = box(89.99, 40, 120, 60)  # 0.01 x 20 = 0.2 sq ft: a sliver
    got = fd5.stand_on(FP, LOT, [tiny], [tiny])
    assert got["bldg_overlap_band"] == "none"
    # 10 x 20 = 200 on the lot of a 600 sq ft footprint: 33% >= 20% -> counts
    assert got["bldg_on_lot_n"] == 1
    got = fd5.stand_on(FP, LOT, [sliver], [sliver])
    assert got["bldg_overlap_band"] == "under 25%"
    neighbour = box(95, 0, 200, 100)  # 5 x 100 = 500 on the lot of 10,500: under 20%
    assert fd5.counted_on_lot(LOT, neighbour) is None


def test_fill_not_mapped_is_none_not_no_fill():
    got = fd5.fill_measure(FP, [], [])
    assert got["fill_touches"] is None and got["fill_share"] is None and got["fill_map_cover"] == 0.0


def test_fill_share_and_distance():
    unit = box(-500, -500, 500, 500)
    fill = box(50, 0, 200, 150)  # the east 40 ft of the pod: half
    got = fd5.fill_measure(FP, [fill], [unit])
    assert got["fill_touches"] is True and got["fill_share"] == pytest.approx(0.5)
    assert got["fill_map_cover"] == 1.0 and got["fill_dist_ft"] == 0.0
    far = box(150, 0, 200, 150)
    got = fd5.fill_measure(FP, [far], [unit])
    assert got["fill_touches"] is False and got["fill_share"] == 0.0
    assert got["fill_dist_ft"] == pytest.approx(60.0)


def test_fill_part_mapped_without_fill_is_unanswered():
    half = box(-500, -500, 50, 500)  # the map covers the west half of the pod only
    got = fd5.fill_measure(FP, [box(150, 0, 200, 150)], [half])
    assert got["fill_map_cover"] == pytest.approx(0.5) and got["fill_touches"] is None
    got = fd5.fill_measure(FP, [box(40, 0, 50, 150)], [half])  # fill on the mapped part still counts
    assert got["fill_touches"] is True


def test_front_face_parallel_and_end_on():
    street = [(0.0, 0.0, 100.0, 0.0)]
    got = fd5.front_face((10, 40), (90, 40), (10, 65), (90, 65), street)
    assert got == {"front_face_street_ft": 40.0, "back_face_street_ft": 65.0, "front_face_turn_deg": 0.0}
    got = fd5.front_face((10, 40), (10, 120), (35, 40), (35, 120), street)
    assert got["front_face_turn_deg"] == 90.0
    assert fd5.front_face((0, 0), (1, 0), (0, 1), (1, 1), [])["front_face_turn_deg"] is None


def test_join_keeps_every_column_and_order_and_replaces_fd5_columns():
    s = _script()
    base_keys = ["county", "TLID", "basement", "liq_majority", "bldg_overlap_band"]
    base = [{"county": "multnomah", "TLID": "1N1E 01", "basement": "", "liq_majority": "Low (2)",
             "bldg_overlap_band": "stale"}]
    cols = {"1N1E 01": {"bldg_overlap_band": "none", "fill_touches": "False"}}
    keys, out = s.join_rows(base, base_keys, cols)
    assert keys[:4] == ["county", "TLID", "basement", "liq_majority"]
    assert keys[4:] == list(s.FD5_COLS)
    assert out[0]["bldg_overlap_band"] == "none" and out[0]["basement"] == "not held"
    assert out[0]["liq_majority"] == "Low (2)" and out[0]["TLID"] == "1N1E 01"


def test_fd5_column_names_do_not_collide_with_pass_1():
    """FD4_lot_reading.py reads pass 1's names; fd5 only adds."""
    s = _script()
    pass1 = {"basement", "year_built", "occupied", "occupancy_label", "liq_majority", "liq_class",
             "fit_orientation", "front_known", "flat_status", "flat_ring", "flat_relief_ft"}
    assert not (pass1 & set(s.FD5_COLS))
    assert all(re.fullmatch(r"[a-z0-9_]+", c) for c in s.FD5_COLS)


def test_nothing_that_screens_reads_fd5():
    flats = ROOT / "flats"
    importing = re.compile(r"^\s*(from|import)\s.*\bfd5\b", re.MULTILINE)
    offenders = [
        str(p.relative_to(flats)) for pkg in ("score", "fit", "rules", "geom", "encode", "normalize", "designs")
        for p in (flats / pkg).rglob("*.py") if importing.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == []


def test_frost_row_marks_the_whole_code_search_places_only():
    s = _script()
    note = {"outcome": "silent", "inches": 12, "below_ft": 2500, "level": "county", "kind": "practice",
            "cite": "county page", "caveats": ["Recorded silent on Steph's search."]}
    row = {"county": "clackamas", "layer_id": "or/clackamas/oregon-city", "ground_mean_ft": "300",
           "frost_hub_in": "18.0"}
    got = s.frost_row(row, note)
    assert got["frost_register_in"] == "12" and got["frost_register_outcome"] == "silent"
    assert got["frost_register_note"].startswith(s.SILENT_WORDS + " (ruling 2026-11-18-frost-silent-oregon-city)")
    assert got["frost_above_stated_band"] == "False"
    other = s.frost_row({**row, "layer_id": "or/washington/hillsboro", "county": "washington"}, note)
    assert not other["frost_register_note"].startswith(s.SILENT_WORDS)
    unread = s.frost_row(row, {"outcome": "not_read", "reference": {"inches": 12}})
    assert unread["frost_register_in"] == "" and unread["frost_register_level"] == "not resolved"
    assert not unread["frost_register_note"].startswith(s.SILENT_WORDS)


def test_static_reasons_keeps_depth_one_rules_above_zero_highest_first():
    m = _script()
    d = m.DWELLINGS
    rows = [
        {"cokey": "1", "mrulename": d, "ruledepth": "0", "rulename": d, "interphr": "1", "interphrc": "Very limited"},
        {"cokey": "1", "mrulename": d, "ruledepth": "1", "rulename": "Shrink-swell", "interphr": "0.5"},
        {"cokey": "1", "mrulename": d, "ruledepth": "1", "rulename": "Flooding", "interphr": "1"},
        {"cokey": "1", "mrulename": d, "ruledepth": "1", "rulename": "Depth to bedrock", "interphr": "0"},
        {"cokey": "1", "mrulename": "ENG - Septic", "ruledepth": "1", "rulename": "Ponding", "interphr": "1"},
        {"cokey": "2", "mrulename": d, "ruledepth": "1", "rulename": "Slope", "interphr": "1"},
    ]
    words, overall = m.static_reasons(rows, {"1"})
    assert words == {"1": "Flooding (1.00); Shrink-swell (0.50)"}
    assert overall == {"1": ("Very limited", "1")}


@pytest.mark.parametrize("sep", [",", "|"])
def test_fill_reasons_static_fills_by_cokey_and_compares_the_rating(tmp_path, sep):
    m = _script()
    lots = tmp_path / "lots.csv"
    lots.write_text("tlid,cokey,dwellings_rating,dwellings_reasons\nA B,1,Very limited,\nC,2,Not limited,\nD,,,\n",
                    encoding="utf-8")
    d = m.DWELLINGS
    cells = [
        ["1", "340", d, "0", "340", d, "0", "1", "Very limited", "0", "0", "0", "9"],
        ["1", "340", d, "1", "77", "Flooding", "1", "1", "", "0", "0", "0", "10"],
        ["2", "340", d, "0", "340", d, "0", "", "Somewhat limited", "0", "0", "0", "11"],
    ]
    rows = tmp_path / "rows.txt"
    rows.write_text("\n".join(sep.join(f'"{c}"' for c in line) for line in cells) + "\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    got = m.fill_reasons_static(lots, rows, out)
    assert got["lots_filled"] == 1 and got["rating_vs_lot_file"] == {"same": 1, "differ": 1}
    text = out.read_text(encoding="utf-8").splitlines()
    assert text[0] == "tlid,cokey,dwellings_rating,dwellings_reasons"
    assert text[1] == "A B,1,Very limited,Flooding (1.00)" and text[3] == "D,,,"
