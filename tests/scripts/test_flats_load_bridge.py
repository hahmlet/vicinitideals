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
    result_binding,
    result_checks,
    rules_version,
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
                "TLID": LOT_B, "COUNTY": "M", "SITEADDR": "1829 NW 25TH AVE", "jurisdiction": "portland",
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
    assert run["counties"] == ["multnomah"]
    assert run["code_version"] == "abc1234"
    assert run["rules_version"] == rules_version()
    assert run["counts"] == {
        "lots": 2,
        "results": 4,
        "tiers": {"unknown": 4},
        "if_signed": {"green": 1, "red": 1, "unknown": 1, "yellow": 1},
        "by_county": {"multnomah": 2},
    }
    assert run["params"]["source_id"] == run["source_id"]
    assert run["status"] == "complete"

    lots = _read(out / LOTS_FILE)
    assert [tuple(r) for r in lots][0] == LOT_COLUMNS
    assert [r["tlid"] for r in lots] == sorted([LOT_A, LOT_B])
    a = next(r for r in lots if r["tlid"] == LOT_A)
    assert (a["county"], a["jurisdiction"], a["zone_raw"], a["zone"]) == ("multnomah", "or/multnomah/portland", "R5", "R5")
    assert a["site_address"] == "1234 SE MAIN ST"
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


# --- the load ----------------------------------------------------------


async def _count(session: AsyncSession, sql: str, **params) -> int:
    return (await session.execute(text(sql), params)).scalar_one()


@pytest.mark.asyncio
async def test_the_load_lands_every_row_where_the_schema_keys_it(tmp_path: Path, session: AsyncSession, _test_db_url: str) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)

    report = await load(bundle, _test_db_url)

    assert report["verified"] is True
    assert report["run_created"] is True
    assert (report["lots_inserted"], report["lots_updated"]) == (2, 0)
    assert (report["results_inserted"], report["results_updated"]) == (4, 0)
    assert report["tiers"] == {"unknown": 4}
    assert report["if_signed"] == {"green": 1, "red": 1, "unknown": 1, "yellow": 1}

    assert await _count(session, "SELECT count(*) FROM flats.designs WHERE key = ANY(:k)", k=list(DESIGNS)) == 2
    run = (await session.execute(text("SELECT status, design_keys, counties, code_version, rules_version, params->>'source_id' FROM flats.runs"))).one()
    assert run[0] == "complete"
    assert list(run[1]) == list(DESIGNS)
    assert list(run[2]) == ["multnomah"]
    assert run[4] == rules_version()
    assert run[5] == json.loads((bundle / RUN_FILE).read_text())["source_id"]

    lot = (
        await session.execute(
            text(
                "SELECT county, jurisdiction, zone_raw, zone, site_address, area_sqft, condo_verdict, "
                "ST_SRID(geom), ST_GeometryType(geom), round(ST_Area(geom)), ST_SRID(centroid), "
                "ST_X(centroid), ST_Y(centroid), facts->'quadfit'->>'triage', first_seen_run_id, updated_run_id "
                "FROM flats.lots WHERE tlid = :t"
            ),
            {"t": LOT_A},
        )
    ).one()
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
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)
    first = await load(bundle, _test_db_url)

    second = await load(bundle, _test_db_url)

    assert second["verified"] is True
    assert second["run_created"] is False
    assert second["run_id"] == first["run_id"]
    assert (second["lots_inserted"], second["lots_updated"]) == (0, 2)
    assert (second["results_inserted"], second["results_updated"]) == (0, 4)
    assert await _count(session, "SELECT count(*) FROM flats.runs") == 1
    assert await _count(session, "SELECT count(*) FROM flats.lots") == 2
    assert await _count(session, "SELECT count(*) FROM flats.lot_results") == 4


@pytest.mark.asyncio
async def test_a_dry_run_verifies_and_leaves_nothing_behind(tmp_path: Path, session: AsyncSession, _test_db_url: str) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)

    report = await load(bundle, _test_db_url, dry_run=True)

    assert report["verified"] is True
    assert report["rolled_back"] is True
    assert report["tiers"] == {"unknown": 4}
    assert await _count(session, "SELECT count(*) FROM flats.runs") == 0
    assert await _count(session, "SELECT count(*) FROM flats.lots") == 0
    assert await _count(session, "SELECT count(*) FROM flats.lot_results") == 0
    assert await _count(session, "SELECT count(*) FROM flats.designs") == 0


@pytest.mark.asyncio
async def test_a_bundle_whose_counts_do_not_match_its_files_is_refused(tmp_path: Path, session: AsyncSession, _test_db_url: str) -> None:
    run_dir, s4, s5o, results = _make_run(tmp_path)
    bundle = tmp_path / "bundle"
    export(run_dir, bundle, s4=s4, s5o=s5o, quadfit_results=results)
    run = json.loads((bundle / RUN_FILE).read_text(encoding="utf-8"))
    run["counts"]["if_signed"]["green"] = 2  # a claim the files do not support
    (bundle / RUN_FILE).write_text(json.dumps(run), encoding="utf-8")

    with pytest.raises(SystemExit, match="VERIFY FAILED"):
        await load(bundle, _test_db_url)

    assert await _count(session, "SELECT count(*) FROM flats.lot_results") == 0
