"""Carrying a bridge run into ``flats.*`` without changing what it said.

The load crosses two boundaries at once -- from the analysis box's parquet
files to the production database, and from the screen's flat record to the
schema's three tables -- and a mistake at either is silent: a row that lands
under the wrong lot, a colour that lands in the verdict's place, a polygon in
the wrong feet. So these tests hold the contract end to end on a bundle
small enough to read: two lots, two designs, one real polygon at Oregon
North coordinates.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.flats_load_bridge import (
    LOT_COLUMNS,
    LOTS_FILE,
    RESULT_COLUMNS,
    RESULTS_FILE,
    RUN_FILE,
    export,
    load,
    load_changes,
    result_binding,
    result_checks,
    rules_version,
    screen_version,
)

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")
shapely = pytest.importorskip("shapely")

# Two Portland lots in EPSG:2913 feet, one per design winner.
LOT_A = "1S2E05DA -01900"
LOT_B = "1N1E29DD -05600"
POLY_A = shapely.box(7_640_000.0, 680_000.0, 7_640_050.0, 680_100.0)
POLY_B = shapely.box(7_650_000.0, 690_000.0, 7_650_060.0, 690_120.0)
DESIGNS = ("pod56x36@2", "pod80x25@2")


def _bridge_row(tlid: str, design: str, **over) -> dict:
    row = {
        "TLID": tlid,
        "jurisdiction": "portland",
        "zone": "R5",
        "layer_id": "or/multnomah/portland",
        "tier": "A",
        "design": design,
        "rule_verdict": "draft",
        "triage": "unknown",
        "if_signed": "green",
        "reasons": "RULE_UNVERIFIED",
        "if_signed_reasons": "",
        "head": None,
        "dominant": "fit_ft",
        "failing": "",
        "unchecked": "",
        "ask": "none",
        "fits": True,
        "fit_slack_ft": 12.5,
        "stalls_charged": 4,
        "stalls_seated": 5,
        "parking_band": "minimum",
        "fit_best_depth_ft": 48.5,
        "fit_required_ft": 36.0,
        "fit_angle_deg": 91.0,
        "fit_across_ft": 48.0,
        "fit_orientation": "end_on",
        "lot_sqft": 5000.0,
        "frontage_ft": 50.0,
        "lot_width_ft": 50.0,
        "lot_depth_ft": 100.0,
        "observed": json.dumps({"abuts_alley": False, "corner_lot": False}),
        "assumed_leaning": "steep_slope",
        "unknown_leaning": "",
        "angles": 180,
        "step_deg": 1.0,
    }
    row.update(over)
    return row


def _make_run(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """A bridge run directory plus the s4 / s5o / results files it was made from."""
    run_dir = tmp_path / "bridge"
    run_dir.mkdir()
    rows = [
        _bridge_row(LOT_A, DESIGNS[0]),
        _bridge_row(LOT_A, DESIGNS[1], if_signed="yellow", if_signed_reasons="RELIEF_UNCONFIRMED", head="fit_ft", failing="fit_ft,lot_width_ft", fits=False, fit_slack_ft=-3.0, stalls_seated=0, parking_band=None, ask="adjustment"),
        _bridge_row(LOT_B, DESIGNS[0], if_signed="unknown", if_signed_reasons="FACT_UNOBSERVED", stalls_seated=8, parking_band="preferred"),
        _bridge_row(LOT_B, DESIGNS[1], if_signed="red", if_signed_reasons="", head="parking_cap", failing="parking_cap", stalls_seated=2, parking_band=None, ask="none"),
    ]
    pd.DataFrame(rows).to_parquet(run_dir / "lots.parquet", index=False)
    (run_dir / "meta.json").write_text(
        json.dumps({"lots": 2, "rows": 4, "step_deg": 1.0, "processes": 2, "seconds": 120.0, "sample": None, "limit": None, "jurisdictions": []}),
        encoding="utf-8",
    )
    s4 = tmp_path / "s4_lots.parquet"
    pd.DataFrame(
        [
            {
                "TLID": LOT_A, "COUNTY": "M", "SITEADDR": "1234 SE MAIN ST", "jurisdiction": "portland",
                "zone_raw": "R5", "zone": "R5", "area_sqft": 5000.0, "tier": "A", "frontage_ft": 50.0,
                "lot_width_ft": 50.0, "lot_depth_ft": 100.0, "front_bearings_json": "[90.0]",
                "alley_width_ft": None, "fronts_cul_de_sac": False, "split_zone": False, "inside_ugb": True,
                "has_z_overlay": False, "zone_frac": 1.0, "stack_count": 1, "wkb": shapely.to_wkb(POLY_A),
            },
            {
                # Portland's jurisdiction, Clackamas County's roll: the county is the roll's.
                "TLID": LOT_B, "COUNTY": "C", "SITEADDR": "1829 NW 25TH AVE", "jurisdiction": "portland",
                "zone_raw": "R2.5", "zone": "R2.5", "area_sqft": 7200.0, "tier": "B", "frontage_ft": 60.0,
                "lot_width_ft": 60.0, "lot_depth_ft": 120.0, "front_bearings_json": "[0.0, 90.0]",
                "alley_width_ft": 20.0, "fronts_cul_de_sac": False, "split_zone": False, "inside_ugb": True,
                "has_z_overlay": True, "zone_frac": 1.0, "stack_count": 1, "wkb": shapely.to_wkb(POLY_B),
            },
            # A lot outside the run: must not be exported.
            {
                "TLID": "1S1E01AA -00100", "COUNTY": "C", "SITEADDR": None, "jurisdiction": "milwaukie",
                "zone_raw": "R-7", "zone": "R-7", "area_sqft": 7000.0, "tier": "A", "frontage_ft": 70.0,
                "lot_width_ft": 70.0, "lot_depth_ft": 100.0, "front_bearings_json": "[0.0]",
                "alley_width_ft": None, "fronts_cul_de_sac": False, "split_zone": False, "inside_ugb": True,
                "has_z_overlay": False, "zone_frac": 1.0, "stack_count": 1, "wkb": shapely.to_wkb(POLY_A),
            },
        ]
    ).to_parquet(s4, index=False)
    s5o = tmp_path / "s5o_lots.parquet"
    # No slope columns on purpose: a stage file from before they existed.
    pd.DataFrame(
        [
            {"TLID": LOT_A, "envelope_sqft": 2100.0, "sewer_main_dist_ft": 12.0, "in_sewer_district": None, "ovl_fema_sfha": False, "ovl_fema_floodway": False},
            {"TLID": LOT_B, "envelope_sqft": 3300.0, "sewer_main_dist_ft": 400.0, "in_sewer_district": None, "ovl_fema_sfha": True, "ovl_fema_floodway": False},
        ]
    ).to_parquet(s5o, index=False)
    results = tmp_path / "lots_results.csv"
    pd.DataFrame(
        [
            {"TLID": LOT_A, "triage": "green", "binding_constraint": "", "policy_exclusion": "", "parking_tier": "minimum", "stalls_provided": "4", "layout_method": "rear_court"},
            {"TLID": LOT_B, "triage": "red", "binding_constraint": "z_overlay", "policy_exclusion": "z_overlay_constrained_site", "parking_tier": "", "stalls_provided": "0", "layout_method": ""},
        ]
    ).to_csv(results, index=False)
    return run_dir, s4, s5o, results


def _read(path: Path) -> list[dict]:
    import csv
    import gzip

    with gzip.open(path, "rt", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --- the export --------------------------------------------------------


def test_the_bundle_carries_the_run_the_lots_and_the_verdicts(tmp_path: Path) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    out = tmp_path / "bundle"

    run = export(run_dir, out, s4=s4, s5o=s5o, quadfit_results=results, code_version="abc1234")

    assert {p.name for p in out.iterdir()} == {LOTS_FILE, RESULTS_FILE, RUN_FILE}
    assert run["design_keys"] == list(DESIGNS)
    assert run["counties"] == ["clackamas", "multnomah"]
    assert run["code_version"] == "abc1234"
    assert run["rules_version"] == rules_version()
    assert run["screen_version"] == screen_version()
    # a re-export that only refreshes quadfit's columns from an earlier
    # screen names the screen's versions, not this checkout's
    again = export(run_dir, tmp_path / "bundle2", s4=s4, s5o=s5o, quadfit_results=results,
                   code_version="abc1234", rules_ver="13aec434" + "0" * 56)
    assert again["rules_version"] == "13aec434" + "0" * 56
    assert run["counts"] == {
        "lots": 2,
        "results": 4,
        "tiers": {"unknown": 4},
        "if_signed": {"green": 1, "red": 1, "unknown": 1, "yellow": 1},
        "by_county": {"clackamas": 1, "multnomah": 1},
        "by_source": {"quadfit": 2},
        "unmeasured": {},
    }
    assert run["params"]["source_id"] == run["source_id"]
    assert run["status"] == "complete", "a run read from quadfit's own tree is the copy in use"
    assert run["snapshot_date"] is None and run["new_zones"] == {}

    lots = _read(out / LOTS_FILE)
    assert [tuple(r) for r in lots][0] == LOT_COLUMNS
    assert [r["tlid"] for r in lots] == sorted([LOT_A, LOT_B])
    a = next(r for r in lots if r["tlid"] == LOT_A)
    assert (a["county"], a["jurisdiction"], a["zone_raw"], a["zone"]) == ("multnomah", "or/multnomah/portland", "R5", "R5")
    assert a["site_address"] == "1234 SE MAIN ST"
    assert a["condo_verdict"] == "land", "without a normalized table every lot is land, as the bridge always said"
    assert float(a["area_sqft"]) == 5000.0
    assert shapely.from_wkb(bytes.fromhex(a["wkb_hex"])).equals(POLY_A)
    facts = json.loads(a["facts"])
    assert facts["quadfit_jurisdiction"] == "portland"
    assert facts["geometry_tier"] == "A"
    assert facts["front_bearings_deg"] == [90.0]
    assert facts["observed"] == {"abuts_alley": False, "corner_lot": False}
    assert facts["envelope"] == {"sqft": 2100.0, "setback_sqft": None, "carved_sqft": None}
    assert facts["slope"] == {"mean_pct": None, "p85_pct": None, "max_pct": None, "source": None}
    assert facts["sewer"] == {"main_dist_ft": 12.0, "in_district": None}
    assert facts["quadfit"] == {
        "triage": "green",
        "binding_constraint": None,
        "policy_exclusion": None,
        "parking_tier": "minimum",
        "stalls_provided": 4,
        "layout_method": "rear_court",
    }
    b = next(r for r in lots if r["tlid"] == LOT_B)
    assert (b["county"], b["jurisdiction"]) == ("clackamas", "or/multnomah/portland")
    assert json.loads(b["facts"])["quadfit"]["policy_exclusion"] == "z_overlay_constrained_site"
    assert json.loads(b["facts"])["alley_width_ft"] == 20.0

    rows = _read(out / RESULTS_FILE)
    assert [tuple(r) for r in rows][0] == RESULT_COLUMNS
    assert len(rows) == 4
    assert {r["tier"] for r in rows} == {"unknown"}
    yellow = next(r for r in rows if r["tlid"] == LOT_A and r["design_key"] == DESIGNS[1])
    assert json.loads(yellow["binding"]) == ["fit_ft", "lot_width_ft"]
    assert float(yellow["slack_ft"]) == -3.0
    checks = json.loads(yellow["checks"])
    assert checks["verdict"] == "unknown"
    assert checks["if_signed"] == "yellow"
    assert checks["if_signed_reasons"] == ["RELIEF_UNCONFIRMED"]
    assert checks["reasons"] == ["RULE_UNVERIFIED"]
    assert checks["stalls"] == {"charged": 4, "seated": 0, "band": None}
    assert checks["fit"]["orientation"] == "end_on"
    assert checks["leaning"] == {"assumed": ["steep_slope"], "unknown": []}
    green = next(r for r in rows if r["tlid"] == LOT_A and r["design_key"] == DESIGNS[0])
    assert json.loads(green["binding"]) == []
    assert json.loads(green["checks"])["stalls"] == {"charged": 4, "seated": 5, "band": "minimum"}


def test_the_binding_list_is_the_head_first_and_each_check_once() -> None:
    assert result_binding({"head": "fit_ft", "failing": "lot_width_ft,fit_ft"}) == ["fit_ft", "lot_width_ft"]
    assert result_binding({"head": None, "failing": ""}) == []
    assert result_binding({"head": "parking_cap", "failing": None}) == ["parking_cap"]


def test_the_checks_record_keeps_the_signed_colour_beside_the_verdict_never_in_its_place() -> None:
    checks = result_checks(_bridge_row(LOT_A, DESIGNS[0], triage="unknown", if_signed="green"))
    assert checks["verdict"] == "unknown"
    assert checks["if_signed"] == "green"
    assert checks["fits"] is True


def test_a_lot_the_stage_file_lacks_refuses_the_export(tmp_path: Path) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    short = tmp_path / "s4_short.parquet"
    pd.read_parquet(s4).query("TLID != @LOT_B").to_parquet(short, index=False)

    with pytest.raises(SystemExit, match="1 lots in the run are not in"):
        export(run_dir, tmp_path / "bundle", s4=short, s5o=s5o, quadfit_results=results)


LOT_C = "1S1E01AA -00100"  # in s4 but never measured by the bridge; the snapshot answers for it
LOT_D = "1S1E01AA -00200"  # in the snapshot only: dropped by quadfit's filter
LOT_E = "24E01  03900"  # Canby: on the Clackamas roll, in no layer the rules hold


def _make_snapshot_run(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    """The bridge run plus three ``unknown`` lots the assign stage added, and the normalized table they came from."""
    run_dir, s4, s5o, results = _make_run(tmp_path)
    frame = pd.read_parquet(run_dir / "lots.parquet")
    extra = []
    for design in DESIGNS:
        extra.append(_bridge_row(LOT_C, design, jurisdiction="or/clackamas/milwaukie", zone=None, layer_id="or/clackamas/milwaukie", tier=None, rule_verdict=None, triage="unknown", if_signed="unknown", reasons="ZONE_NOT_ENCODED", if_signed_reasons="ZONE_NOT_ENCODED", head="", dominant=None, ask=None, fits=False, fit_slack_ft=None, stalls_charged=None, stalls_seated=None, parking_band=None, fit_best_depth_ft=None, fit_required_ft=None, fit_angle_deg=None, fit_across_ft=None, fit_orientation=None, lot_sqft=7000.0, frontage_ft=None, lot_width_ft=None, lot_depth_ft=None, observed="{}", assumed_leaning="", unknown_leaning="", angles=None, step_deg=None))
        extra.append(_bridge_row(LOT_D, design, jurisdiction="or/multnomah/portland", zone="R5", layer_id="or/multnomah/portland", tier=None, rule_verdict=None, triage="unknown", if_signed="unknown", reasons="NOT_MEASURED,quadfit:sliver_area", if_signed_reasons="NOT_MEASURED,quadfit:sliver_area", head="", dominant=None, ask=None, fits=False, fit_slack_ft=None, stalls_charged=None, stalls_seated=None, parking_band=None, fit_best_depth_ft=None, fit_required_ft=None, fit_angle_deg=None, fit_across_ft=None, fit_orientation=None, lot_sqft=800.0, frontage_ft=None, lot_width_ft=None, lot_depth_ft=None, observed="{}", assumed_leaning="", unknown_leaning="", angles=None, step_deg=None))
        extra.append(_bridge_row(LOT_E, design, jurisdiction=None, zone=None, layer_id=None, tier=None, rule_verdict=None, triage="unknown", if_signed="unknown", reasons="JURISDICTION_NOT_ENCODED", if_signed_reasons="JURISDICTION_NOT_ENCODED", head="", dominant=None, ask=None, fits=False, fit_slack_ft=None, stalls_charged=None, stalls_seated=None, parking_band=None, fit_best_depth_ft=None, fit_required_ft=None, fit_angle_deg=None, fit_across_ft=None, fit_orientation=None, lot_sqft=138687.7, frontage_ft=None, lot_width_ft=None, lot_depth_ft=None, observed="{}", assumed_leaning="", unknown_leaning="", angles=None, step_deg=None))
    pd.concat([frame, pd.DataFrame(extra)], ignore_index=True).to_parquet(run_dir / "lots.parquet", index=False)

    normalized = tmp_path / "normalized"
    normalized.mkdir()
    roll = {"LANDVAL": 250000, "BLDGVAL": 180000, "TOTALVAL": 430000, "ASSESSVAL": 310500, "YEARBUILT": 1948, "BLDGSQFT": 1250, "SALEDATE": "20210615", "SALEPRICE": 415000, "PROP_CODE": "101", "STATECLASS": "101", "LANDUSE": "SFR"}
    pd.DataFrame(
        [
            {"county": "multnomah", "tlid": LOT_A, "juris_city": "PO", "jurisdiction": "or/multnomah/portland", "site_address": "1234 SE MAIN ST", "area_sqft": 5000.0, "part_count": 1, "stack_count": 1, "condo_verdict": "land", "condo_reason": None, "zone_raw": "R5", "zone": "R5", "zone_frac": 1.0, "split_zone": False, "inside_ugb": True, "gate": None, **roll, "wkb": shapely.to_wkb(POLY_A)},
            {"county": "clackamas", "tlid": LOT_B, "juris_city": "PO", "jurisdiction": "or/multnomah/portland", "site_address": "1829 NW 25TH AVE", "area_sqft": 7200.0, "part_count": 1, "stack_count": 1, "condo_verdict": "suspect", "condo_reason": "stacked", "zone_raw": "R2.5", "zone": "R2.5", "zone_frac": 1.0, "split_zone": False, "inside_ugb": True, "gate": None, **{k: None for k in roll}, "wkb": shapely.to_wkb(POLY_B)},
            {"county": "clackamas", "tlid": LOT_C, "juris_city": "MI", "jurisdiction": "or/clackamas/milwaukie", "site_address": "9 SE HARRISON ST", "area_sqft": 7000.0, "part_count": 1, "stack_count": 1, "condo_verdict": "land", "condo_reason": None, "zone_raw": "QQ9", "zone": None, "zone_frac": 1.0, "split_zone": False, "inside_ugb": True, "gate": "ZONE_NOT_ENCODED", **roll, "wkb": shapely.to_wkb(POLY_A)},
            {"county": "multnomah", "tlid": LOT_D, "juris_city": "PO", "jurisdiction": "or/multnomah/portland", "site_address": None, "area_sqft": 800.0, "part_count": 1, "stack_count": 1, "condo_verdict": "land", "condo_reason": None, "zone_raw": "R5", "zone": "R5", "zone_frac": 0.97, "split_zone": False, "inside_ugb": True, "gate": None, **{k: None for k in roll}, "wkb": shapely.to_wkb(shapely.box(7_640_100.0, 680_000.0, 7_640_120.0, 680_040.0))},
            # Outside Metro's boundary, in a city no layer holds: the map still names the city.
            {"county": "clackamas", "tlid": LOT_E, "juris_city": "CANBY", "jurisdiction": None, "site_address": "14450 BAUMBACK RD", "area_sqft": 138687.7, "part_count": 1, "stack_count": 1, "condo_verdict": "land", "condo_reason": None, "zone_raw": None, "zone": None, "zone_frac": None, "split_zone": False, "inside_ugb": False, "gate": "JURISDICTION_NOT_ENCODED", **{k: None for k in roll}, "wkb": shapely.to_wkb(shapely.box(7_660_000.0, 600_000.0, 7_660_300.0, 600_462.3))},
        ]
    ).to_parquet(normalized / "lots.parquet", index=False)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    meta.update(
        caller="flats.ingest.assign",
        snapshot_date="2026-09-18",
        normalized=str(normalized),
        new_zones={"or/clackamas/milwaukie": {"QQ9": 1}},
        lots=5,
        rows=10,
        assign={"measured": 2, "unmeasured": 3, "by_reason": {"JURISDICTION_NOT_ENCODED": 1, "NOT_MEASURED": 1, "ZONE_NOT_ENCODED": 1}},
    )
    (run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return run_dir, s4, s5o, results, normalized


def test_a_snapshot_fed_run_exports_every_lot_as_a_candidate(tmp_path: Path) -> None:
    run_dir, s4, s5o, results, normalized = _make_snapshot_run(tmp_path)
    out = tmp_path / "bundle"

    run = export(run_dir, out, s4=s4, s5o=s5o, quadfit_results=results)

    assert run["status"] == "candidate"
    assert run["snapshot_date"] == "2026-09-18"
    assert run["new_zones"] == {"or/clackamas/milwaukie": {"QQ9": 1}}
    assert run["params"]["caller"] == "flats.ingest.assign"
    assert run["counts"]["lots"] == 5 and run["counts"]["results"] == 10
    assert run["counts"]["by_source"] == {"quadfit": 3, "snapshot": 2}, "LOT_C is in s4 (measured by quadfit, screened by nobody); LOT_D and LOT_E are the snapshot's"
    assert run["counts"]["unmeasured"] == {"JURISDICTION_NOT_ENCODED": 1, "NOT_MEASURED": 1, "ZONE_NOT_ENCODED": 1}
    assert run["counts"]["if_signed"] == {"green": 1, "red": 1, "unknown": 7, "yellow": 1}

    lots = {r["tlid"]: r for r in _read(out / LOTS_FILE)}
    assert set(lots) == {LOT_A, LOT_B, LOT_C, LOT_D, LOT_E}
    # A measured lot keeps s4's record and gains the roll and the condo verdict.
    a = lots[LOT_A]
    assert (a["jurisdiction"], a["zone"], a["condo_verdict"]) == ("or/multnomah/portland", "R5", "land")
    facts = json.loads(a["facts"])
    assert facts["quadfit_jurisdiction"] == "portland" and facts["geometry_tier"] == "A"
    assert facts["assessor"] == {"land_value": 250000.0, "building_value": 180000.0, "total_value": 430000.0, "assessed_value": 310500.0, "year_built": 1948, "building_sqft": 1250.0, "sale_date": "20210615", "sale_price": 415000.0, "prop_code": "101", "state_class": "101", "land_use": "SFR"}
    assert facts["condo"] == {"verdict": "land", "reason": None}
    assert facts["snapshot_zone"] == {"raw": "R5", "zone": "R5", "gate": None}
    b = lots[LOT_B]
    assert b["condo_verdict"] == "suspect" and json.loads(b["facts"])["condo"] == {"verdict": "suspect", "reason": "stacked"}
    assert json.loads(b["facts"])["assessor"]["total_value"] is None
    # A lot quadfit never measured takes the snapshot's record and says why it is unanswered.
    d = lots[LOT_D]
    assert (d["county"], d["jurisdiction"], d["zone"], d["site_address"], d["condo_verdict"]) == ("multnomah", "or/multnomah/portland", "R5", "", "land")
    assert float(d["area_sqft"]) == 800.0 and shapely.from_wkb(bytes.fromhex(d["wkb_hex"])).area == 800.0
    df = json.loads(d["facts"])
    assert df["source"] == "snapshot"
    assert df["unmeasured"] == {"reason": "NOT_MEASURED", "quadfit_step": "sliver_area"}
    assert df["zone_frac"] == 0.97 and df["juris_city"] == "PO" and df["observed"] == {}
    assert "geometry_tier" not in df
    c = json.loads(lots[LOT_C]["facts"])
    assert c["snapshot_zone"] == {"raw": "QQ9", "zone": None, "gate": "ZONE_NOT_ENCODED"}
    # A lot in a city no layer holds is never blank: the map's city name rides the column.
    e = lots[LOT_E]
    assert (e["county"], e["jurisdiction"], e["zone"], e["site_address"]) == ("clackamas", "juris_city:canby", "", "14450 BAUMBACK RD")
    ef = json.loads(e["facts"])
    assert ef["unmeasured"] == {"reason": "JURISDICTION_NOT_ENCODED", "quadfit_step": None} and ef["juris_city"] == "CANBY"
    assert ef["snapshot_zone"] == {"raw": None, "zone": None, "gate": "JURISDICTION_NOT_ENCODED"}

    rows = _read(out / RESULTS_FILE)
    unknowns = [r for r in rows if r["tlid"] == LOT_D]
    assert len(unknowns) == 2 and {r["tier"] for r in unknowns} == {"unknown"}
    assert json.loads(unknowns[0]["checks"])["reasons"] == ["NOT_MEASURED", "quadfit:sliver_area"]
    assert json.loads(unknowns[0]["binding"]) == []
    assert {r["county"] for r in rows if r["tlid"] == LOT_C} == {"clackamas"}


def test_a_lot_in_neither_the_stage_file_nor_the_snapshot_refuses_the_export(tmp_path: Path) -> None:
    run_dir, s4, s5o, results, normalized = _make_snapshot_run(tmp_path)
    short = normalized / "lots.parquet"
    pd.read_parquet(short).query("tlid != @LOT_D").to_parquet(short, index=False)

    with pytest.raises(SystemExit, match=r"1 lots in the run are not in .* or "):
        export(run_dir, tmp_path / "bundle", s4=s4, s5o=s5o, quadfit_results=results)


# --- the load ----------------------------------------------------------


async def _count(session: AsyncSession, sql: str, **params) -> int:
    return (await session.execute(text(sql), params)).scalar_one()


async def _snapshot(session: AsyncSession, taken: str = "2026-09-18", status: str = "current") -> int:
    """A registered county copy for the bundle's lots to belong to; committed,
    because the loader opens its own connection."""
    row = (
        await session.execute(
            text(
                "INSERT INTO flats.snapshots (snapshot_date, host, status, manifest, counts) "
                "VALUES (:d, '137', :s, '{}'::jsonb, '{}'::jsonb) RETURNING id"
            ),
            {"d": date.fromisoformat(taken), "s": status},
        )
    ).scalar_one()
    await session.commit()
    return row


@pytest.mark.asyncio
async def test_the_load_lands_every_row_where_the_schema_keys_it(tmp_path: Path, session: AsyncSession, _test_db_url: str) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)
    copy = await _snapshot(session)

    report = await load(bundle, _test_db_url, snapshot_id=copy)

    assert report["verified"] is True
    assert report["run_created"] is True
    assert (report["snapshot_id"], report["snapshot_date"]) == (copy, "2026-09-18")
    assert (report["lots_inserted"], report["lots_updated"]) == (2, 0)
    assert (report["results_inserted"], report["results_updated"]) == (4, 0)
    assert report["tiers"] == {"unknown": 4}
    assert report["if_signed"] == {"green": 1, "red": 1, "unknown": 1, "yellow": 1}

    assert await _count(session, "SELECT count(*) FROM flats.designs WHERE key = ANY(:k)", k=list(DESIGNS)) == 2
    run = (await session.execute(text("SELECT status, design_keys, counties, code_version, rules_version, params->>'source_id', snapshot_id, screen_version FROM flats.runs"))).one()
    assert run[0] == "complete"
    assert list(run[1]) == list(DESIGNS)
    assert list(run[2]) == ["clackamas", "multnomah"]
    assert run[4] == rules_version()
    assert run[5] == json.loads((bundle / RUN_FILE).read_text())["source_id"]
    assert run[6] == copy
    assert run[7] == screen_version()

    lot = (
        await session.execute(
            text(
                "SELECT county, jurisdiction, zone_raw, zone, site_address, area_sqft, condo_verdict, "
                "ST_SRID(geom), ST_GeometryType(geom), round(ST_Area(geom)), ST_SRID(centroid), "
                "ST_X(centroid), ST_Y(centroid), facts->'quadfit'->>'triage', first_seen_run_id, updated_run_id, "
                "snapshot_id "
                "FROM flats.lots WHERE tlid = :t"
            ),
            {"t": LOT_A},
        )
    ).one()
    assert lot[16] == copy
    assert tuple(lot)[:7] == ("multnomah", "or/multnomah/portland", "R5", "R5", "1234 SE MAIN ST", 5000, "land")
    assert (lot[7], lot[8], lot[9]) == (2913, "ST_MultiPolygon", 5000)
    assert lot[10] == 4326
    assert -124 < lot[11] < -121 and 45 < lot[12] < 46  # Portland, in degrees
    assert lot[13] == "green"
    assert lot[14] == lot[15] == report["run_id"]

    rows = (
        await session.execute(
            text(
                "SELECT l.tlid, r.design_key, r.tier, r.slack_ft, r.binding, r.checks->>'if_signed' "
                "FROM flats.lot_results r JOIN flats.lots l ON l.id = r.lot_id ORDER BY 1, 2"
            )
        )
    ).all()
    assert [(r[0], r[1], r[2], r[5]) for r in rows] == [
        (LOT_B, DESIGNS[0], "unknown", "unknown"),
        (LOT_B, DESIGNS[1], "unknown", "red"),
        (LOT_A, DESIGNS[0], "unknown", "green"),
        (LOT_A, DESIGNS[1], "unknown", "yellow"),
    ]
    yellow = rows[3]
    assert float(yellow[3]) == -3.0
    assert list(yellow[4]) == ["fit_ft", "lot_width_ft"]


@pytest.mark.asyncio
async def test_loading_the_same_bundle_twice_changes_nothing(tmp_path: Path, session: AsyncSession, _test_db_url: str) -> None:
    """A bundle lands on its run row in place -- while the run is a candidate.
    The run the Lots pages show is never overwritten in place: that would
    change what the site says with no gate and no way back, so a re-screen
    of the copy in use is a new run (a new source id) promoted with
    ``flats_promote.py promote --run``."""
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)
    copy = await _snapshot(session)
    first = await load(bundle, _test_db_url, snapshot_id=copy)
    assert (await session.execute(text("SELECT status FROM flats.runs WHERE id = :r"), {"r": first["run_id"]})).scalar_one() == "complete"

    with pytest.raises(SystemExit, match="is complete; a re-screen of the copy in use is loaded as a NEW run"):
        await load(bundle, _test_db_url, snapshot_id=copy)
    assert await _count(session, "SELECT count(*) FROM flats.lot_results") == 4

    await session.execute(text("UPDATE flats.runs SET status = 'candidate' WHERE id = :r"), {"r": first["run_id"]})
    await session.commit()
    second = await load(bundle, _test_db_url, snapshot_id=copy)

    assert second["verified"] is True
    assert second["run_created"] is False
    assert second["run_id"] == first["run_id"]
    assert (second["lots_inserted"], second["lots_updated"]) == (0, 2)
    assert (second["results_inserted"], second["results_updated"]) == (0, 4)
    assert await _count(session, "SELECT count(*) FROM flats.runs") == 1
    assert await _count(session, "SELECT count(*) FROM flats.lots") == 2
    assert await _count(session, "SELECT count(*) FROM flats.lot_results") == 4
    notes = (await session.execute(text("SELECT notes FROM flats.runs WHERE id = :r"), {"r": first["run_id"]})).scalar_one()
    assert "re-loaded from" in notes and f"screen {screen_version()}" in notes


def test_the_screen_version_reads_the_screens_files_and_nothing_else(tmp_path: Path) -> None:
    """One hash over the screen's own files, so a checkout that differs only
    outside the screen (a doc, the app, a test, a rule, the corpus) carries
    the same version and the drift report never puts a move to "code" that
    no screen change explains."""
    root = tmp_path / "repo"
    for rel in (
        "flats/score/screen.py",
        "flats/geom/alley.py",
        "flats/config/relief.yaml",
        "flats/provenance/store.py",
        "Lot Analysis/quadfit/s6s_siteplan.py",
        "Lot Analysis/quadfit/config/rules.yaml",
    ):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("v1\n", encoding="utf-8")
    for rel in (
        "flats/tests/test_screen.py",
        "flats/config/jurisdictions/or/multnomah/portland.yaml",
        "flats/provenance/docs/or/portland/33.110.json",
        "Lot Analysis/quadfit/provenance/portland-33.418.txt",
        "Lot Analysis/quadfit/README.md",
        "app/services/flats_refresh.py",
        "docs/FOLLOWUPS.md",
    ):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("v1\n", encoding="utf-8")
    first = screen_version(root)
    assert first == screen_version(root) and len(first) == 64

    # Nothing outside the screen moves it.
    for rel in (
        "flats/tests/test_screen.py",
        "flats/config/jurisdictions/or/multnomah/portland.yaml",
        "flats/provenance/docs/or/portland/33.110.json",
        "Lot Analysis/quadfit/provenance/portland-33.418.txt",
        "Lot Analysis/quadfit/README.md",
        "app/services/flats_refresh.py",
        "docs/FOLLOWUPS.md",
    ):
        (root / rel).write_text("v2\n", encoding="utf-8")
    assert screen_version(root) == first
    # Line endings do not either: one version across a Windows and a Linux checkout.
    (root / "flats/score/screen.py").write_bytes(b"v1\r\n")
    assert screen_version(root) == first

    # Every screen file does.
    for rel in (
        "flats/score/screen.py",
        "flats/geom/alley.py",
        "flats/config/relief.yaml",
        "flats/provenance/store.py",
        "Lot Analysis/quadfit/s6s_siteplan.py",
        "Lot Analysis/quadfit/config/rules.yaml",
    ):
        before = screen_version(root)
        (root / rel).write_text("v3\n", encoding="utf-8")
        assert screen_version(root) != before, rel


@pytest.mark.asyncio
async def test_a_dry_run_verifies_and_leaves_nothing_behind(tmp_path: Path, session: AsyncSession, _test_db_url: str) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)
    copy = await _snapshot(session)

    report = await load(bundle, _test_db_url, snapshot_id=copy, dry_run=True)

    assert report["verified"] is True
    assert report["rolled_back"] is True
    assert report["tiers"] == {"unknown": 4}
    assert await _count(session, "SELECT count(*) FROM flats.runs") == 0
    assert await _count(session, "SELECT count(*) FROM flats.lots") == 0
    assert await _count(session, "SELECT count(*) FROM flats.lot_results") == 0
    assert await _count(session, "SELECT count(*) FROM flats.designs") == 0


@pytest.mark.asyncio
async def test_a_lot_with_a_very_long_outline_loads(tmp_path: Path, session: AsyncSession, _test_db_url: str) -> None:
    """The county's largest tracts have outlines whose WKB, written as one
    CSV field, runs past the reader's 128 KB default. The first September
    load stopped on one; every lot rides the bundle now, so the loader must
    read a field of any length."""
    run_dir, s4, s5o, results = _make_run(tmp_path)
    frame = pd.read_parquet(s4)
    long_outline = shapely.segmentize(POLY_A, 0.05)  # ~6,000 vertices on the same 50 x 100 box
    frame.loc[frame["TLID"] == LOT_A, "wkb"] = shapely.to_wkb(long_outline)
    frame.to_parquet(s4, index=False)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)
    hex_len = max(len(r["wkb_hex"]) for r in _read(bundle / LOTS_FILE))
    assert hex_len > 131_072, hex_len
    copy = await _snapshot(session)

    report = await load(bundle, _test_db_url, snapshot_id=copy, dry_run=True)

    assert report["verified"] is True
    assert report["rolled_back"] is True


@pytest.mark.asyncio
async def test_a_bundle_whose_counts_do_not_match_its_files_is_refused(tmp_path: Path, session: AsyncSession, _test_db_url: str) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)
    run = json.loads((bundle / RUN_FILE).read_text(encoding="utf-8"))
    run["counts"]["if_signed"]["green"] = 2  # a claim the files do not support
    (bundle / RUN_FILE).write_text(json.dumps(run), encoding="utf-8")
    copy = await _snapshot(session)

    with pytest.raises(SystemExit, match="VERIFY FAILED"):
        await load(bundle, _test_db_url, snapshot_id=copy)

    assert await _count(session, "SELECT count(*) FROM flats.lot_results") == 0


@pytest.mark.asyncio
async def test_a_bundle_needs_a_registered_copy_to_belong_to(tmp_path: Path, session: AsyncSession, _test_db_url: str) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)

    with pytest.raises(SystemExit, match="register the snapshot first"):
        await load(bundle, _test_db_url, snapshot_id=999)
    retired = await _snapshot(session, status="retired")
    with pytest.raises(SystemExit, match="retired"):
        await load(bundle, _test_db_url, snapshot_id=retired)

    assert await _count(session, "SELECT count(*) FROM flats.lots") == 0


@pytest.mark.asyncio
async def test_a_second_copy_lands_beside_the_first_and_a_run_reads_one_copy(
    tmp_path: Path, session: AsyncSession, _test_db_url: str
) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)
    july = await _snapshot(session, taken="2026-07-28")
    september = await _snapshot(session, taken="2026-09-18", status="candidate")
    await load(bundle, _test_db_url, snapshot_id=july)

    # The same run does not straddle two copies.
    with pytest.raises(SystemExit, match="a run reads one copy"):
        await load(bundle, _test_db_url, snapshot_id=september)

    # A second run over the refreshed copy keeps the same lot numbers beside
    # the first copy's rows, not on top of them.
    later = tmp_path / "later"
    later.mkdir()
    for name in ("lots.parquet", "meta.json"):
        (later / name).write_bytes((run_dir / name).read_bytes())
    bundle2 = tmp_path / "bundle2"
    export(later, bundle2, s4=s4, s5o=s5o, quadfit_results=results)
    report = await load(bundle2, _test_db_url, snapshot_id=september)

    assert report["run_created"] is True
    assert (report["lots_inserted"], report["lots_updated"]) == (2, 0)
    assert await _count(session, "SELECT count(*) FROM flats.lots") == 4
    assert await _count(session, "SELECT count(DISTINCT (county, tlid)) FROM flats.lots") == 2
    assert await _count(session, "SELECT count(*) FROM flats.lots WHERE snapshot_id = :s", s=september) == 2
    # Each run's results point at the lot rows of its own copy.
    assert await _count(
        session,
        "SELECT count(*) FROM flats.lot_results r JOIN flats.lots l ON l.id = r.lot_id "
        "JOIN flats.runs u ON u.id = r.run_id WHERE l.snapshot_id <> u.snapshot_id",
    ) == 0


@pytest.mark.asyncio
async def test_a_candidate_load_writes_the_promotion_gate_on_its_snapshot(
    tmp_path: Path, session: AsyncSession, _test_db_url: str
) -> None:
    """The gate is read against the copy the default run shows, and written in the load's own transaction."""
    run_dir, s4, s5o, results = _make_run(tmp_path)
    july_bundle = tmp_path / "july"
    export(run_dir, july_bundle, s4=s4, s5o=s5o, quadfit_results=results)
    july = await _snapshot(session, taken="2026-07-28")
    await session.execute(
        text("UPDATE flats.snapshots SET counts = CAST(:c AS jsonb) WHERE id = :s"),
        {"c": json.dumps({"lots": 2, "datasets": {"rlis_taxlots": {"status": "acquired", "features": 1000, "unfetched": 0}}}), "s": july},
    )
    await session.commit()
    await load(july_bundle, _test_db_url, snapshot_id=july)

    (tmp_path / "sep").mkdir()
    sep_dir, s4b, s5ob, results_b, normalized = _make_snapshot_run(tmp_path / "sep")
    sep_bundle = tmp_path / "sep_bundle"
    export(sep_dir, sep_bundle, s4=s4b, s5o=s5ob, quadfit_results=results_b)
    september = await _snapshot(session, taken="2026-09-18", status="candidate")
    await session.execute(
        text("UPDATE flats.snapshots SET counts = CAST(:c AS jsonb), report = CAST(:r AS jsonb) WHERE id = :s"),
        {
            "c": json.dumps({"features": 1040, "datasets": {"rlis_taxlots": {"status": "acquired", "features": 1040, "unfetched": 0}, "zoning_portland": {"status": "acquired", "features": 5, "unfetched": 2}}}),
            "r": json.dumps({"delta": {"crosscheck": {"min_recall": 0.9, "agrees": True, "counties": {"multnomah": {"added": {"recall": 0.9}, "deleted": {"recall": 0.95}}}}}}),
            "s": september,
        },
    )
    await session.commit()

    dry = await load(sep_bundle, _test_db_url, snapshot_id=september, dry_run=True)
    assert dry["rolled_back"] is True and "checks" in dry
    stored = (await session.execute(text("SELECT checks, counts FROM flats.snapshots WHERE id = :s"), {"s": september})).one()
    assert stored[0] == {} and "lots" not in stored[1], "a dry run leaves the gate unwritten"

    report = await load(sep_bundle, _test_db_url, snapshot_id=september)

    assert report["verified"] is True
    assert set(report["checks"]) == {"layers_incomplete", "count_drift", "new_zones", "lots_drift", "zone_changes", "rlis_agreement"}
    assert report["blocks"] == ["layers_incomplete", "count_drift", "new_zones", "lots_drift"]
    checks = report["checks"]
    assert checks["layers_incomplete"]["detail"] == "zoning_portland: 2 features never fetched"
    assert checks["count_drift"]["detail"] == "rlis_taxlots: 1,000 -> 1,040 (+4.0%)"
    assert checks["new_zones"]["detail"] == "or/clackamas/milwaukie: QQ9 (1)"
    assert checks["lots_drift"]["detail"] == "2 -> 3 measured lots (+50.0%)"
    assert checks["zone_changes"]["detail"] == "1 jurisdictions share fewer than 20 lots with the earlier copy"
    assert checks["rlis_agreement"]["tripped"] is False

    row = (await session.execute(text("SELECT checks, counts, status FROM flats.snapshots WHERE id = :s"), {"s": september})).one()
    assert row[0] == checks
    assert row[1]["lots"] == 5 and row[1]["measured"] == 3 and row[1]["results"] == 10
    assert row[1]["by_reason"] == {"JURISDICTION_NOT_ENCODED": 1, "NOT_MEASURED": 1, "ZONE_NOT_ENCODED": 1}
    assert row[1]["new_zones"] == {"or/clackamas/milwaukie": {"QQ9": 1}}, "the next refresh reads these as already known"
    assert row[1]["baseline_snapshot_id"] == july
    assert row[1]["features"] == 1040, "the counts the register step wrote stay"
    assert row[2] == "candidate", "a load never promotes"
    run = (await session.execute(text("SELECT status FROM flats.runs WHERE snapshot_id = :s"), {"s": september})).scalar_one()
    assert run == "candidate"
    verdicts = (
        await session.execute(
            text("SELECT l.condo_verdict, r.tier, r.checks->>'if_signed' FROM flats.lot_results r JOIN flats.lots l ON l.id = r.lot_id WHERE l.snapshot_id = :s AND l.tlid = :t"),
            {"s": september, "t": LOT_B},
        )
    ).all()
    assert {v[0] for v in verdicts} == {"suspect"}, "the condo verdict is the snapshot's, not a constant"
    unmeasured = (
        await session.execute(
            text("SELECT l.facts->'unmeasured'->>'reason', r.tier, r.checks->'reasons' FROM flats.lot_results r JOIN flats.lots l ON l.id = r.lot_id WHERE l.snapshot_id = :s AND l.tlid = :t"),
            {"s": september, "t": LOT_D},
        )
    ).all()
    assert unmeasured and all(u[0] == "NOT_MEASURED" and u[1] == "unknown" and u[2] == ["NOT_MEASURED", "quadfit:sliver_area"] for u in unmeasured)
    canby = (
        await session.execute(
            text("SELECT jurisdiction, zone, facts->>'juris_city', facts->'unmeasured'->>'reason' FROM flats.lots WHERE snapshot_id = :s AND tlid = :t"),
            {"s": september, "t": LOT_E},
        )
    ).one()
    assert tuple(canby) == ("juris_city:canby", None, "CANBY", "JURISDICTION_NOT_ENCODED"), "a city no layer holds lands with its name, never a blank"


# --- load-changes ---------------------------------------------------------------


def _changes(tmp_path: Path) -> Path:
    from flats.ingest.delta import Change, write_changes

    path = tmp_path / "changes.csv.gz"
    write_changes(
        [
            Change("multnomah", "1N1E08BD  -02500", "split", role="parent", related_tlids=["1N1E08BD  -02501", "1N1E08BD  -02502"], area_before=12_000.0, note="kept its TLID", rlis_change="CHANGE", area_after=4_000.0, iou=0.33),
            Change("multnomah", "1N1E08BD  -02501", "split", role="child", related_tlids=["1N1E08BD  -02500"], area_after=4_000.0, rlis_change="ADDED"),
            Change("multnomah", "1N1E08BD  -02502", "split", role="child", related_tlids=["1N1E08BD  -02500"], area_after=4_000.0, rlis_change="ADDED"),
            Change("clackamas", "22E22B 01800", "attr_change", area_before=8_000.0, area_after=8_000.0, iou=1.0, attr_diff={"TOTALVAL": [410_000, 455_000]}),
            Change("clackamas", "22E22B 01900", "vacated", area_before=1_500.0, rlis_change="DELETED"),
        ],
        path,
    )
    return path


@pytest.mark.asyncio
async def test_a_delta_lands_between_two_registered_copies_and_reloads_replace(
    tmp_path: Path, session: AsyncSession, _test_db_url: str
) -> None:
    july = await _snapshot(session, taken="2026-07-28")
    september = await _snapshot(session, taken="2026-09-18", status="candidate")
    changes = _changes(tmp_path)

    report = await load_changes(changes, _test_db_url, snapshot_from=july, snapshot_to=september)

    assert report["written"] == 5 and report["replaced"] == 0 and report["verified"] is True
    assert report["by_kind"] == {"attr_change": 1, "split": 3, "vacated": 1}
    assert report["snapshot_from_date"] == "2026-07-28" and report["snapshot_to_date"] == "2026-09-18"
    rows = (
        await session.execute(
            text(
                "SELECT county, tlid, kind, role, related_tlids, area_before, area_after, iou, attr_diff, rlis_change, note "
                "FROM flats.lot_changes WHERE snapshot_from = :f AND snapshot_to = :t ORDER BY county, tlid"
            ),
            {"f": july, "t": september},
        )
    ).all()
    assert len(rows) == 5
    parent = rows[2]
    assert (parent.county, parent.tlid, parent.kind, parent.role) == ("multnomah", "1N1E08BD  -02500", "split", "parent")
    assert parent.related_tlids == ["1N1E08BD  -02501", "1N1E08BD  -02502"]
    assert float(parent.area_before) == 12_000.0 and float(parent.iou) == 0.33 and parent.note == "kept its TLID"
    assert rows[0].attr_diff == {"TOTALVAL": [410_000, 455_000]} and rows[0].role is None
    assert rows[1].kind == "vacated" and rows[1].area_after is None and rows[1].rlis_change == "DELETED"

    # The same pair again replaces, never doubles.
    again = await load_changes(changes, _test_db_url, snapshot_from=july, snapshot_to=september)
    assert again["replaced"] == 5 and again["written"] == 5
    assert await _count(session, "SELECT count(*) FROM flats.lot_changes") == 5


@pytest.mark.asyncio
async def test_a_delta_dry_run_leaves_nothing_and_a_bad_pair_is_refused(
    tmp_path: Path, session: AsyncSession, _test_db_url: str
) -> None:
    july = await _snapshot(session, taken="2026-07-28")
    september = await _snapshot(session, taken="2026-09-18", status="candidate")
    changes = _changes(tmp_path)

    report = await load_changes(changes, _test_db_url, snapshot_from=july, snapshot_to=september, dry_run=True)
    assert report["written"] == 5 and report["rolled_back"] is True
    assert await _count(session, "SELECT count(*) FROM flats.lot_changes") == 0

    with pytest.raises(SystemExit, match="same snapshot"):
        await load_changes(changes, _test_db_url, snapshot_from=july, snapshot_to=july)
    with pytest.raises(SystemExit, match="no flats.snapshots row 999 for --to"):
        await load_changes(changes, _test_db_url, snapshot_from=july, snapshot_to=999)
    assert await _count(session, "SELECT count(*) FROM flats.lot_changes") == 0

