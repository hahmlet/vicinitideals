"""The USDA soil survey under each lot (FOLLOWUPS 196): the overlay, the
dominant and worst pick, the no-coverage case, the wet season, and the words.
A note, never a colour."""

from __future__ import annotations

import pytest
from shapely.geometry import box

from flats.ingest import soil
from flats.ingest.soil import (
    WATER_NO_DATA,
    WATER_NONE_RECORDED,
    WATER_RECORDED,
    describe,
    dominant_condition,
    fold_interpretations,
    fold_months,
    lep_class,
    measure_lots,
    pick,
    lot_units,
    rated_component,
    unit_wet_season,
    wet_season,
)


def _lot(tlid: str, geom) -> dict:
    return {"county": "multnomah", "tlid": tlid, "geom": geom}


def _rows(lot_rows: list[dict], tlid: str) -> list[dict]:
    return [r for r in lot_rows if r["tlid"] == tlid]


# --- overlay ------------------------------------------------------------------------


def test_a_lot_inside_one_map_unit_gets_one_row_for_its_whole_area():
    rows = list(measure_lots([_lot("A", box(10, 10, 60, 110))], [("100", box(0, 0, 1000, 1000))]))
    assert rows == [{"county": "multnomah", "tlid": "A", "lot_area_sqft": 5000.0, "mukey": "100",
                     "area_sqft": 5000.0, "share": 1.0}]


def test_a_lot_across_two_map_units_and_a_gap_sums_to_its_area():
    # 100 x 100 lot: 60 ft in unit 1, 30 ft in unit 2, 10 ft under nothing.
    lot = box(0, 0, 100, 100)
    soils = [("1", box(-50, -50, 60, 150)), ("2", box(60, -50, 90, 150))]
    rows = list(measure_lots([_lot("A", lot)], soils))
    by = {r["mukey"]: r for r in rows}
    assert by["1"]["area_sqft"] == 6000.0 and by["1"]["share"] == 0.6
    assert by["2"]["area_sqft"] == 3000.0
    assert by[None]["area_sqft"] == 1000.0 and by[None]["share"] == 0.1
    assert sum(r["area_sqft"] for r in rows) == pytest.approx(lot.area)
    # Largest first, the uncovered part last.
    assert [r["mukey"] for r in rows] == ["1", "2", None]


def test_two_parts_of_one_map_unit_add_up_to_one_row():
    rows = list(measure_lots([_lot("A", box(0, 0, 100, 100))],
                             [("1", box(0, 0, 50, 100)), ("1", box(50, 0, 100, 100))]))
    assert [(r["mukey"], r["area_sqft"]) for r in rows] == [("1", 10000.0)]


def test_overlapping_survey_areas_never_count_ground_twice():
    rows = list(measure_lots([_lot("A", box(0, 0, 100, 100))],
                             [("1", box(0, 0, 70, 100)), ("2", box(50, 0, 100, 100))]))
    assert sum(r["area_sqft"] for r in rows) == pytest.approx(10000.0, rel=soil.SUM_TOLERANCE)
    assert all(r["mukey"] for r in rows)


def test_a_lot_the_survey_does_not_reach_says_so():
    rows = list(measure_lots([_lot("W", box(5000, 5000, 5100, 5050))], [("1", box(0, 0, 100, 100))]))
    assert rows == [{"county": "multnomah", "tlid": "W", "lot_area_sqft": 5000.0, "mukey": None,
                     "area_sqft": 5000.0, "share": 1.0}]
    note = describe(rows, {}, {})
    assert note["covered"] is False
    assert note["no_coverage_words"] == "The USDA soil survey has no map unit under this lot."
    assert note["never_a_colour"] is True


def test_a_sliver_is_not_a_map_unit_on_the_lot():
    rows = list(measure_lots([_lot("A", box(0, 0, 100, 100))],
                             [("1", box(0, 0, 100, 100)), ("2", box(99.995, 0, 101, 100))]))
    assert {r["mukey"] for r in rows} == {"1"}


def test_an_empty_lot_geometry_is_skipped():
    from shapely.geometry import Polygon

    assert list(measure_lots([_lot("E", Polygon())], [("1", box(0, 0, 1, 1))])) == []


# --- ratings, components, wet season -------------------------------------------------------


def test_interpretations_fold_to_rating_and_top_reasons():
    rows = [
        {"cokey": "9", "mrulename": soil.DWELLINGS, "ruledepth": 0, "interphrc": "Very limited"},
        {"cokey": "9", "mrulename": soil.DWELLINGS, "ruledepth": 1, "interphrc": "Shrink-swell", "interphr": 1.0},
        {"cokey": "9", "mrulename": soil.DWELLINGS, "ruledepth": 1, "interphrc": "Depth to saturated zone",
         "interphr": 0.39},
        {"cokey": "9", "mrulename": soil.DWELLINGS, "ruledepth": 1, "interphrc": "Slope", "interphr": 0},
        {"cokey": "9", "mrulename": soil.SMALL_COMMERCIAL, "ruledepth": 0, "interphrc": "Somewhat limited"},
        {"cokey": "9", "mrulename": "ENG - Septic Tank Absorption Fields", "ruledepth": 0, "interphrc": "Very limited"},
    ]
    folded = fold_interpretations(rows)["9"]
    assert folded["dwellings_rating"] == "Very limited"
    assert folded["dwellings_reasons"] == "Shrink-swell (1.00); Depth to saturated zone (0.39)"
    assert folded["small_commercial_rating"] == "Somewhat limited"
    # A source with no reasons leaves them unread, never "none".
    assert "small_commercial_reasons" not in folded


def test_dominant_condition_is_the_class_with_the_most_percent_and_ties_go_worse():
    comps = [{"comppct_r": 50, "r": "Not limited"}, {"comppct_r": 30, "r": "Very limited"},
             {"comppct_r": 20, "r": "Very limited"}, {"comppct_r": 5, "r": None}]
    assert dominant_condition(comps, "r") == "Very limited"
    assert dominant_condition(comps[:1] + [{"comppct_r": 50, "r": "Somewhat limited"}], "r") == "Somewhat limited"
    assert dominant_condition([{"comppct_r": 100}], "r") is None


def test_urban_land_is_not_the_rated_component():
    urban = {"cokey": "1", "compname": "Urban land", "comppct_r": 55, "majcompflag": "Yes"}
    latourell = {"cokey": "2", "compname": "Latourell", "comppct_r": 35, "majcompflag": "Yes",
                 "drainagecl": "Well drained", "dwellings_rating": "Not limited"}
    assert rated_component([urban, latourell]) is latourell
    assert rated_component([urban]) is None


def _months(depths: dict[int, float | None]) -> list[dict]:
    rows = []
    for seq in range(1, 13):
        depth = depths.get(seq)
        rows.append({"cokey": "5", "monthseq": seq, "month": soil.MONTH_NAMES[seq - 1], "flodfreqcl": "None",
                     "pondfreqcl": None, "soimoiststat": "Wet" if depth is not None else "Moist",
                     "soimoistdept_r": depth if depth is not None else 0})
    return rows


def test_the_wet_season_is_november_to_april_and_names_its_months():
    months = fold_months(_months({1: 30, 2: 30, 3: 46, 12: 61, 7: 10}))["5"]
    assert [m["wet_top_cm"] for m in months][:3] == [30, 30, 46]
    assert months[0]["flood"] == "None"  # printed class, kept as printed
    status, cm, when = wet_season(months)
    # July's 10 cm is outside the season.
    assert (status, cm, when) == (WATER_RECORDED, 30, ["January", "February"])


def test_no_wet_layer_and_no_data_never_merge():
    dry = fold_months(_months({}))["5"]
    assert wet_season(dry) == (WATER_NONE_RECORDED, None, [])
    assert wet_season([]) == (WATER_NO_DATA, None, [])
    assert wet_season(None) == (WATER_NO_DATA, None, [])


def test_a_map_unit_takes_the_shallowest_wet_season_of_its_components():
    comps = [
        {"cokey": "1", "comppct_r": 60, "wet_season_status": WATER_RECORDED, "wet_season_cm": 76,
         "wet_season_months": "January"},
        {"cokey": "2", "comppct_r": 25, "wet_season_status": WATER_RECORDED, "wet_season_cm": 15,
         "wet_season_months": "December,January"},
        {"cokey": "3", "comppct_r": 15, "wet_season_status": WATER_NONE_RECORDED},
    ]
    assert unit_wet_season(comps) == (WATER_RECORDED, 15, ["December", "January"], "2")
    assert unit_wet_season(comps[2:])[0] == WATER_NONE_RECORDED
    assert unit_wet_season([{"cokey": "9"}])[0] == WATER_NO_DATA


def test_shrink_swell_classes_follow_the_handbook():
    assert [lep_class(v) for v in (None, 1.5, 3.0, 5.9, 6.0, 8.99, 9.0, 14)] == [
        None, "low", "moderate", "moderate", "high", "high", "very high", "very high"]


# --- dominant / worst, words -------------------------------------------------------------


UNITS = {
    "A": {"mukey": "A", "areasymbol": "OR051", "areaname": "Multnomah County Area, Oregon",
          "saverest": "09/08/2026 19:50:15", "musym": "7B", "muname": "Cascade silt loam, 3 to 8 percent slopes",
          "mukind": "Consociation", "drclassdcd": "Somewhat poorly drained", "hydgrpdcd": "C/D", "hydclprs": "0",
          "dwellings_dcd": "Somewhat limited", "small_commercial_dcd": "Somewhat limited",
          "wet_season_status": WATER_RECORDED, "wet_season_cm": "46", "wet_season_months": "January,February"},
    "B": {"mukey": "B", "areasymbol": "OR051", "musym": "50A", "muname": "Urban land, 0 to 3 percent slopes",
          "mukind": "Consociation", "dwellings_dcd": None, "engdwobdcd": "Not rated"},
    "C": {"mukey": "C", "areasymbol": "OR051", "musym": "14", "muname": "Wapato silty clay loam",
          "mukind": "Consociation", "drclassdcd": "Poorly drained", "dwellings_dcd": "Very limited",
          "small_commercial_dcd": "Very limited"},
}
COMPONENTS = {
    "A": [{"cokey": "a1", "mukey": "A", "compname": "Cascade", "comppct_r": "90", "majcompflag": "Yes",
           "taxclname": "Fine-silty, mixed, active, mesic Aquic Fragixerepts", "drainagecl": "Somewhat poorly drained",
           "lep_max": "4.5", "restriction_cm": "56", "restriction_kind": "Fragipan",
           "dwellings_rating": "Somewhat limited"}],
    "B": [{"cokey": "b1", "mukey": "B", "compname": "Urban land", "comppct_r": "100", "majcompflag": "Yes"}],
    "C": [{"cokey": "c1", "mukey": "C", "compname": "Wapato", "comppct_r": "85", "majcompflag": "Yes",
           "drainagecl": "Poorly drained", "dwellings_rating": "Very limited"}],
}


def test_the_dominant_is_the_most_ground_and_the_worst_the_worst_rating():
    rows = [{"mukey": "A", "area_sqft": 4000, "share": 0.6}, {"mukey": "C", "area_sqft": 2000, "share": 0.3},
            {"mukey": "B", "area_sqft": 600, "share": 0.09}, {"mukey": None, "area_sqft": 66, "share": 0.01}]
    found, uncovered = lot_units(rows, UNITS, COMPONENTS)
    dominant, worst = pick(found)
    assert (dominant.mukey, worst.mukey, uncovered) == ("A", "C", 66)
    note = describe(rows, UNITS, COMPONENTS, source="USDA NRCS SSURGO")
    assert [u["mukey"] for u in note["units"]] == ["A", "C", "B"]
    assert note["worst"]["mukey"] == "C" and note["spans_several"] is True
    assert note["uncovered_sqft"] == 66 and note["lot_area_sqft"] == 6666
    a = note["units"][0]
    assert a["technical"] == "OR051 (survey version 09/08/2026 19:50:15) · musym 7B · mukey A · Consociation"
    assert a["components"][0]["technical"].startswith("cokey a1 · Cascade 90% · major · Fine-silty")
    assert a["rated"]["lep_class"] == "moderate"
    assert a["rated"]["restriction_words"] == "Fragipan at 56 cm (1 ft 10 in)"
    assert a["wet_season_words"] == "46 cm (1 ft 6 in) below the surface at its highest, November to April (January, February)"
    assert "USDA Natural Resources Conservation Service" in a["source_words"]
    assert "OR051" in a["source_words"] and "09/08/2026" in a["source_words"]
    urban = note["units"][2]
    assert urban["has_data"] is False
    assert urban["no_data_words"] == "Mapped as Urban land, 0 to 3 percent slopes: the survey holds no soil data for it."


def test_a_dominant_unit_that_is_also_the_worst_has_no_separate_worst():
    rows = [{"mukey": "C", "area_sqft": 4000, "share": 0.8}, {"mukey": "A", "area_sqft": 1000, "share": 0.2}]
    note = describe(rows, UNITS, COMPONENTS)
    assert note["dominant"]["mukey"] == "C" and note["worst"] is None


def test_an_unmeasured_lot_has_no_note():
    assert describe([], UNITS, COMPONENTS) is None


def test_nothing_that_screens_imports_the_soil_module():
    """A note, never a colour: the screen, score and flags never read it."""
    import pathlib

    root = pathlib.Path(soil.__file__).resolve().parents[1]
    readers = [p for p in root.rglob("*.py")
               if "tests" not in p.parts and p.name != "soil.py" and "flats.ingest.soil" in p.read_text(encoding="utf-8")]
    assert readers == []
