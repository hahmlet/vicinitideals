"""``flats.ingest.assign`` -- every lot answered, the screen's rows untouched.

The join has one job: a lot the bridge screened keeps its rows byte for byte;
a lot it did not screen gets ``unknown`` per design with the reason -- the
normalize gate when there is one, else ``NOT_MEASURED`` with quadfit's own
step for dropping it.
"""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import pytest

from flats.ingest.assign import NOT_MEASURED, POD_CANNOT_FIT, ROW_COLUMNS, assign, read_dropped, synthetic_row
from flats.ingest.normalize import EXCLUDED_COLUMNS

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

DESIGNS = ("pod56x36@2", "pod80x25@2")
MEASURED = "1S2E05DA -01900"
GATED = "1S2E05DA -02000"
DROPPED = "1S2E05DA -02100"
UNCLAIMED = "1S2E05DA -02200"
NARROW = "1S2E05DA -02300"  # 3,000 sqft, but no 20 ft circle fits in its outline
ZONED_OUT = "1S2E05DA -02400"  # big enough, dropped for a reason arithmetic does not settle
GHOST = "1N1E29DD -09999"  # measured by the bridge, absent from the lot table
CONDO = "1N1E29DD -90001"  # measured by the bridge; the lot table dropped it as a condominium unit


def _bridge_row(tlid: str, design: str, **over) -> dict:
    row = {c: None for c in ROW_COLUMNS}
    row.update(
        TLID=tlid,
        jurisdiction="portland",
        zone="R5",
        layer_id="or/multnomah/portland",
        tier="A",
        design=design,
        rule_verdict="draft",
        triage="unknown",
        if_signed="green",
        reasons="RULE_UNVERIFIED",
        if_signed_reasons="",
        head="",
        failing="",
        unchecked="",
        ask="none",
        fits=True,
        fit_slack_ft=12.5,
        stalls_charged=4,
        stalls_seated=5,
        lot_sqft=5000.0,
        observed=json.dumps({"abuts_alley": False}),
        assumed_leaning="",
        unknown_leaning="",
        angles=180,
        step_deg=1.0,
        colour="green",
        flags="",
        binds="",
    )
    row.update(over)
    return row


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Path]:
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    rows = [
        _bridge_row(MEASURED, DESIGNS[0]),
        _bridge_row(MEASURED, DESIGNS[1], if_signed="yellow", fits=False, fit_slack_ft=-3.0),
        _bridge_row(GHOST, DESIGNS[0], if_signed="red"),
        _bridge_row(GHOST, DESIGNS[1], if_signed="red"),
        _bridge_row(CONDO, DESIGNS[0], if_signed="red", lot_sqft=1200.0),
        _bridge_row(CONDO, DESIGNS[1], if_signed="red", lot_sqft=1200.0),
    ]
    pd.DataFrame(rows).to_parquet(bridge / "lots.parquet", index=False)
    (bridge / "meta.json").write_text(
        json.dumps({"lots": 3, "rows": 6, "step_deg": 1.0, "processes": 2, "seconds": 9.0, "s4": "/x/s4.parquet"}),
        encoding="utf-8",
    )

    normalized = tmp_path / "normalized"
    normalized.mkdir()
    lots = [
        {"county": "multnomah", "tlid": MEASURED, "jurisdiction": "or/multnomah/portland", "zone": "R5", "zone_raw": "R5", "area_sqft": 5000.0, "gate": None},
        {"county": "multnomah", "tlid": GATED, "jurisdiction": "or/multnomah/portland", "zone": None, "zone_raw": "QQ9", "area_sqft": 4000.0, "gate": "ZONE_NOT_ENCODED"},
        {"county": "multnomah", "tlid": DROPPED, "jurisdiction": "or/multnomah/portland", "zone": "R5", "zone_raw": "R5", "area_sqft": 800.0, "gate": None},
        {"county": "multnomah", "tlid": UNCLAIMED, "jurisdiction": "or/multnomah/portland", "zone": "R5", "zone_raw": "R5", "area_sqft": 6000.0, "gate": None},
        {"county": "multnomah", "tlid": NARROW, "jurisdiction": "or/multnomah/portland", "zone": "R5", "zone_raw": "R5", "area_sqft": 3000.0, "gate": None},
        {"county": "multnomah", "tlid": ZONED_OUT, "jurisdiction": "or/multnomah/portland", "zone": "R5", "zone_raw": "R5", "area_sqft": 5000.0, "gate": None},
        # The same TLID in the other county: allowed as long as the bridge did not measure it.
        {"county": "clackamas", "tlid": UNCLAIMED, "jurisdiction": "or/clackamas", "zone": "R-10", "zone_raw": "R-10", "area_sqft": 9000.0, "gate": None},
    ]
    pd.DataFrame(lots).to_parquet(normalized / "lots.parquet", index=False)
    with gzip.open(normalized / "excluded.csv.gz", "wt", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(EXCLUDED_COLUMNS))
        w.writeheader()
        w.writerow({"county": "multnomah", "tlid": CONDO, "step": "condo_excluded", "reason": "CONDO_AIR_PARCEL", "area_sqft": "1200.0", "prop_code": "102"})
        w.writerow({"county": "multnomah", "tlid": "1N1E29DD -STR", "step": "not_a_taxlot", "reason": "", "area_sqft": "", "prop_code": ""})
    (normalized / "summary.json").write_text(
        json.dumps({"snapshot": "2026-09-18", "new_zones": {"or/multnomah/portland": {"QQ9": 1}}, "funnel": [{"step": "features", "count": 5}]}),
        encoding="utf-8",
    )

    quadfit = tmp_path / "quadfit"
    quadfit.mkdir()
    (quadfit / "s3_dropped.csv").write_text(f"TLID,step\n{DROPPED},sliver_area\n{NARROW},too_narrow_20ft\n{ZONED_OUT},zone_not_in_rules\n", encoding="utf-8")
    return {"bridge": bridge, "normalized": normalized, "quadfit": quadfit, "out": tmp_path / "assign"}


def test_measured_rows_pass_through_and_every_other_lot_gets_a_reason(world: dict[str, Path]) -> None:
    meta = assign(world["normalized"], world["bridge"], world["out"], quadfit_dir=world["quadfit"])

    frame = pd.read_parquet(world["out"] / "lots.parquet")
    assert list(frame.columns) == list(ROW_COLUMNS)
    before = pd.read_parquet(world["bridge"] / "lots.parquet")
    kept = frame[frame["TLID"].isin([MEASURED, GHOST])].reset_index(drop=True)
    pd.testing.assert_frame_equal(kept, before[before["TLID"] != CONDO][list(ROW_COLUMNS)].reset_index(drop=True), check_dtype=False)
    # The condominium unit quadfit measured is not land by the lot table's reading: gone, and counted.
    assert CONDO not in set(frame["TLID"])

    def rows_for(tlid: str) -> list[dict]:
        return frame[frame["TLID"] == tlid].sort_values("design").to_dict("records")

    gated = rows_for(GATED)
    assert [r["design"] for r in gated] == list(DESIGNS)
    assert {(r["triage"], r["if_signed"], r["reasons"], r["if_signed_reasons"]) for r in gated} == {
        ("unknown", "unknown", "ZONE_NOT_ENCODED", "ZONE_NOT_ENCODED")
    }
    assert pd.isna(gated[0]["zone"]) and gated[0]["jurisdiction"] == "or/multnomah/portland"
    assert gated[0]["fits"] is False and pd.isna(gated[0]["fit_slack_ft"]) and gated[0]["observed"] == "{}"

    dropped = rows_for(DROPPED)
    assert {r["reasons"] for r in dropped} == {f"{POD_CANNOT_FIT},quadfit:sliver_area"}
    assert {(r["triage"], r["if_signed"], r["colour"]) for r in dropped} == {("red", "red", "red")}
    assert {b["check"] for r in dropped for b in json.loads(r["binds"])} == {"pod_footprint_area"}
    narrow = rows_for(NARROW)
    assert {r["reasons"] for r in narrow} == {f"{POD_CANNOT_FIT},quadfit:too_narrow_20ft"}
    assert {b["check"] for r in narrow for b in json.loads(r["binds"])} == {"pod_width"}
    zoned_out = rows_for(ZONED_OUT)
    assert {r["reasons"] for r in zoned_out} == {f"{NOT_MEASURED},quadfit:zone_not_in_rules"}
    assert {(r["triage"], r["colour"]) for r in zoned_out} == {("unknown", "yellow")}
    unclaimed = rows_for(UNCLAIMED)
    assert len(unclaimed) == 4, "two counties' lots share the TLID; each gets its rows"
    assert {r["reasons"] for r in unclaimed} == {f"{NOT_MEASURED},quadfit:unknown"}

    assert meta["caller"] == "flats.ingest.assign"
    assert meta["snapshot_date"] == "2026-09-18"
    assert meta["normalized"] == str(world["normalized"].resolve())
    assert meta["quadfit_dir"] == str(world["quadfit"].resolve())
    assert meta["new_zones"] == {"or/multnomah/portland": {"QQ9": 1}}
    assert meta["s4"] == "/x/s4.parquet", "the bridge's meta rides along"
    assert (meta["lots"], meta["rows"]) == (7, 4 + 2 * 6)
    a = meta["assign"]
    assert a["measured"] == 2 and a["unmeasured"] == 6
    assert a["by_reason"] == {NOT_MEASURED: 3, "ZONE_NOT_ENCODED": 1, POD_CANNOT_FIT: 2}
    assert a["not_measured_by_step"] == {"zone_not_in_rules": 1, "unknown": 2}
    assert a["pod_cannot_fit_by_proof"] == {"pod_footprint_area": 1, "pod_width": 1}
    assert a["measured_not_in_lots"] == 1 and a["measured_not_in_lots_examples"] == [GHOST]
    assert a["measured_but_excluded"] == {"CONDO_AIR_PARCEL": 1}
    assert a["tlids_shared_across_counties"] == 1
    written = json.loads((world["out"] / "meta.json").read_text(encoding="utf-8"))
    assert written["assign"]["by_reason"] == a["by_reason"]
    summary = (world["out"] / "summary.md").read_text(encoding="utf-8")
    assert "ZONE_NOT_ENCODED: 1" in summary and "QQ9 (1)" in summary and "pod_footprint_area 1" in summary
    assert "not land by the snapshot's reading (dropped): 1 -- CONDO_AIR_PARCEL 1" in summary
    assert "kept from quadfit's record): 1" in summary


def test_without_the_ledger_a_measured_lot_the_table_lacks_is_kept(world: dict[str, Path]) -> None:
    (world["normalized"] / "excluded.csv.gz").unlink()
    meta = assign(world["normalized"], world["bridge"], world["out"], quadfit_dir=world["quadfit"])
    a = meta["assign"]
    assert a["measured"] == 3 and a["measured_but_excluded"] == {}
    assert a["measured_not_in_lots"] == 2 and a["measured_not_in_lots_examples"] == sorted([GHOST, CONDO])
    assert CONDO in set(pd.read_parquet(world["out"] / "lots.parquet")["TLID"])


def test_without_quadfit_dir_every_unmeasured_lot_is_unclaimed(world: dict[str, Path]) -> None:
    meta = assign(world["normalized"], world["bridge"], world["out"])
    assert meta["quadfit_dir"] is None
    assert meta["assign"]["not_measured_by_step"] == {"unknown": 4}
    # The small lot is proven by its area alone; the narrow one needs the ledger's step.
    assert meta["assign"]["by_reason"][POD_CANNOT_FIT] == 1


def test_a_measured_tlid_in_two_counties_refuses(world: dict[str, Path]) -> None:
    lots = pd.read_parquet(world["normalized"] / "lots.parquet")
    twin = lots[lots["tlid"] == MEASURED].assign(county="clackamas", jurisdiction="or/clackamas")
    pd.concat([lots, twin]).to_parquet(world["normalized"] / "lots.parquet", index=False)
    with pytest.raises(SystemExit, match="names lots in two counties"):
        assign(world["normalized"], world["bridge"], world["out"])


def test_synthetic_row_shape_and_dropped_reader(tmp_path: Path) -> None:
    row = synthetic_row({"tlid": "T", "jurisdiction": "or/x", "zone": None, "area_sqft": 1.0}, "d", "NO_ZONE")
    assert set(row) == set(ROW_COLUMNS)
    assert row["reasons"] == "NO_ZONE" and row["layer_id"] == "or/x" and row["stalls_seated"] is None
    assert read_dropped(None) == {} and read_dropped(tmp_path / "missing.csv") == {}
    csv = tmp_path / "s3_dropped.csv"
    csv.write_text("TLID,step\n1N1E01AA -00100 ,too_narrow_20ft\n", encoding="utf-8")
    assert read_dropped(csv) == {"1N1E01AA -00100": "too_narrow_20ft"}


def test_the_quadfit_narrow_test_is_the_constant_the_proof_uses() -> None:
    """The width proof is only as good as s3's test: a lot whose outline
    shrunk by 10 ft all round is empty holds no 20 ft circle."""
    import importlib.util

    from flats.ingest.assign import QUADFIT_NARROW_TEST_FT

    path = Path(__file__).resolve().parents[2] / "Lot Analysis" / "quadfit" / "s3_filter.py"
    text = path.read_text(encoding="utf-8")
    assert "NARROW_TEST_BUFFER_FT = -10.0" in text
    assert QUADFIT_NARROW_TEST_FT == 2 * 10.0
    assert importlib.util.find_spec("flats") is not None


def test_a_proof_never_overreaches() -> None:
    from flats.designs.model import load_catalog
    from flats.ingest.assign import pod_proof

    catalog = load_catalog()
    small = {"area_sqft": 1900.0}
    # Under the footprint of every design the catalog holds.
    for d in catalog:
        assert pod_proof({"area_sqft": 0.5 * d.footprint.area_sqft}, None, d.key, catalog).check == "pod_footprint_area"
        # The footprint itself, or a hair under it, is not proven: the outline may differ by rounding.
        assert pod_proof({"area_sqft": d.footprint.area_sqft}, "zone_not_in_rules", d.key, catalog) is None
        assert pod_proof({"area_sqft": 0.99 * d.footprint.area_sqft}, None, d.key, catalog) is None
        # Narrow needs the step; a big lot dropped for another step is unproven.
        assert pod_proof({"area_sqft": 9000.0}, "too_narrow_20ft", d.key, catalog).check == "pod_width"
        assert pod_proof({"area_sqft": 9000.0}, "sliver_area", d.key, catalog) is None
        assert pod_proof({"area_sqft": None}, "unknown", d.key, catalog) is None
    assert pod_proof(small, None, "no-such-design@1", catalog) is None
