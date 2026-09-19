"""``flats.ingest.assign`` -- every lot answered, the screen's rows untouched.

The join has one job: a lot the bridge screened keeps its rows byte for byte;
a lot it did not screen gets ``unknown`` per design with the reason -- the
normalize gate when there is one, else ``NOT_MEASURED`` with quadfit's own
step for dropping it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flats.ingest.assign import NOT_MEASURED, ROW_COLUMNS, assign, read_dropped, synthetic_row

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

DESIGNS = ("pod56x36@2", "pod80x25@2")
MEASURED = "1S2E05DA -01900"
GATED = "1S2E05DA -02000"
DROPPED = "1S2E05DA -02100"
UNCLAIMED = "1S2E05DA -02200"
GHOST = "1N1E29DD -09999"  # measured by the bridge, absent from the lot table


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
    ]
    pd.DataFrame(rows).to_parquet(bridge / "lots.parquet", index=False)
    (bridge / "meta.json").write_text(
        json.dumps({"lots": 2, "rows": 4, "step_deg": 1.0, "processes": 2, "seconds": 9.0, "s4": "/x/s4.parquet"}),
        encoding="utf-8",
    )

    normalized = tmp_path / "normalized"
    normalized.mkdir()
    lots = [
        {"county": "multnomah", "tlid": MEASURED, "jurisdiction": "or/multnomah/portland", "zone": "R5", "zone_raw": "R5", "area_sqft": 5000.0, "gate": None},
        {"county": "multnomah", "tlid": GATED, "jurisdiction": "or/multnomah/portland", "zone": None, "zone_raw": "QQ9", "area_sqft": 4000.0, "gate": "ZONE_NOT_ENCODED"},
        {"county": "multnomah", "tlid": DROPPED, "jurisdiction": "or/multnomah/portland", "zone": "R5", "zone_raw": "R5", "area_sqft": 800.0, "gate": None},
        {"county": "multnomah", "tlid": UNCLAIMED, "jurisdiction": "or/multnomah/portland", "zone": "R5", "zone_raw": "R5", "area_sqft": 6000.0, "gate": None},
        # The same TLID in the other county: allowed as long as the bridge did not measure it.
        {"county": "clackamas", "tlid": UNCLAIMED, "jurisdiction": "or/clackamas", "zone": "R-10", "zone_raw": "R-10", "area_sqft": 9000.0, "gate": None},
    ]
    pd.DataFrame(lots).to_parquet(normalized / "lots.parquet", index=False)
    (normalized / "summary.json").write_text(
        json.dumps({"snapshot": "2026-09-18", "new_zones": {"or/multnomah/portland": {"QQ9": 1}}, "funnel": [{"step": "features", "count": 5}]}),
        encoding="utf-8",
    )

    quadfit = tmp_path / "quadfit"
    quadfit.mkdir()
    (quadfit / "s3_dropped.csv").write_text(f"TLID,step\n{DROPPED},sliver_area\n", encoding="utf-8")
    return {"bridge": bridge, "normalized": normalized, "quadfit": quadfit, "out": tmp_path / "assign"}


def test_measured_rows_pass_through_and_every_other_lot_gets_a_reason(world: dict[str, Path]) -> None:
    meta = assign(world["normalized"], world["bridge"], world["out"], quadfit_dir=world["quadfit"])

    frame = pd.read_parquet(world["out"] / "lots.parquet")
    assert list(frame.columns) == list(ROW_COLUMNS)
    before = pd.read_parquet(world["bridge"] / "lots.parquet")
    kept = frame[frame["TLID"].isin([MEASURED, GHOST])].reset_index(drop=True)
    pd.testing.assert_frame_equal(kept, before[list(ROW_COLUMNS)], check_dtype=False)

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
    assert {r["reasons"] for r in dropped} == {f"{NOT_MEASURED},quadfit:sliver_area"}
    unclaimed = rows_for(UNCLAIMED)
    assert len(unclaimed) == 4, "two counties' lots share the TLID; each gets its rows"
    assert {r["reasons"] for r in unclaimed} == {f"{NOT_MEASURED},quadfit:unknown"}

    assert meta["caller"] == "flats.ingest.assign"
    assert meta["snapshot_date"] == "2026-09-18"
    assert meta["normalized"] == str(world["normalized"].resolve())
    assert meta["quadfit_dir"] == str(world["quadfit"].resolve())
    assert meta["new_zones"] == {"or/multnomah/portland": {"QQ9": 1}}
    assert meta["s4"] == "/x/s4.parquet", "the bridge's meta rides along"
    assert (meta["lots"], meta["rows"]) == (5, 4 + 2 * 4)
    a = meta["assign"]
    assert a["measured"] == 2 and a["unmeasured"] == 4
    assert a["by_reason"] == {NOT_MEASURED: 3, "ZONE_NOT_ENCODED": 1}
    assert a["not_measured_by_step"] == {"sliver_area": 1, "unknown": 2}
    assert a["measured_not_in_lots"] == 1 and a["measured_not_in_lots_examples"] == [GHOST]
    assert a["tlids_shared_across_counties"] == 1
    written = json.loads((world["out"] / "meta.json").read_text(encoding="utf-8"))
    assert written["assign"]["by_reason"] == a["by_reason"]
    summary = (world["out"] / "summary.md").read_text(encoding="utf-8")
    assert "ZONE_NOT_ENCODED: 1" in summary and "QQ9 (1)" in summary and "sliver_area 1" in summary


def test_without_quadfit_dir_every_unmeasured_lot_is_unclaimed(world: dict[str, Path]) -> None:
    meta = assign(world["normalized"], world["bridge"], world["out"])
    assert meta["quadfit_dir"] is None
    assert meta["assign"]["not_measured_by_step"] == {"unknown": 3}


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
