from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from flats.designs.model import load_catalog
from scripts.flats_size_curve import frontier_status
from scripts.flats_size_report import NEVER_SCREENED_REASONS, canonical_place, render_report
from scripts.flats_size_scope import build_scope, main as scope_main

STUDY_FOOTPRINTS = {
    "pod60x33": (60, 33),
    "pod64x31": (64, 31),
    "pod68x29": (68, 29),
    "pod72x28": (72, 28),
    "pod76x26": (76, 26),
}


def test_new_study_designs_are_four_two_storey_homes_near_500_sqft_per_floor() -> None:
    catalog = load_catalog()
    baseline = catalog.latest("pod56x36")

    for design_id, (width, depth) in STUDY_FOOTPRINTS.items():
        design = catalog.latest(design_id)
        assert design.version == 1
        assert (design.footprint.width_ft, design.footprint.depth_ft) == (width, depth)
        assert design.units == 4 and design.stories == 2
        assert abs(width * depth / design.units - 500) <= 15
        assert design.model_dump(exclude={"id", "version", "label", "footprint"}) == baseline.model_dump(
            exclude={"id", "version", "label", "footprint"}
        )
        header = (Path(__file__).parents[1] / "config" / "pods" / f"{design_id}.yaml").read_text(
            encoding="utf-8"
        )
        assert "STUDY DESIGN" in header and "FOLLOWUPS 149" in header and "NOT FOR THE LIVE MAP" in header


def _assignment_rows() -> list[dict[str, object]]:
    keys = [design.key for design in load_catalog().active()]
    statuses = {
        "1N1E22CD  -00300": {
            "pod56x36@2": ("red", -14.0, "fit_ft"),
            "pod80x25@2": ("red", -20.0, "fit_ft"),
            "pod60x33@1": ("green", 1.0, ""),
            "pod64x31@1": ("green", 5.0, ""),
        },
        "1N1E22CD  -00400": {
            "pod56x36@2": ("red", -1.0, "steep_ground"),
            "pod80x25@2": ("green", 2.0, ""),
            "pod60x33@1": ("yellow", 0.2, ""),
        },
    }
    rows = []
    for tlid, known in statuses.items():
        for key in keys:
            colour, slack, failing = known.get(key, ("red", -3.0, "min_lot_area_sqft"))
            rows.append(
                {
                    "jurisdiction": "or/multnomah/portland",
                    "TLID": tlid,
                    "zone": "R2.5",
                    "design": key,
                    "colour": colour,
                    "failing": failing,
                    "fit_slack_ft": slack,
                    "fit_across_ft": 36.0,
                    "fit_best_depth_ft": 36.0,
                    "fit_required_ft": 36.0,
                    "reasons": "",
                    "binds": "",
                    "flags": "",
                    "forms": "",
                }
            )
    return rows


def test_size_scope_uses_geometry_frontier_and_non_red_current_designs(tmp_path: Path) -> None:
    assign = tmp_path / "assign"
    assign.mkdir()
    pd.DataFrame(_assignment_rows()).to_parquet(assign / "lots.parquet", index=False)

    rows = build_scope(assign)

    assert [row["tlid"] for row in rows] == ["1N1E22CD  -00300", "1N1E22CD  -00400"]
    assert rows[0]["county"] == rows[1]["county"] == "multnomah"
    assert rows[0]["reason"] == "red-both-geometry-frontier"
    assert rows[1]["reason"] == "not-red-under-both-current-designs"


def test_size_scope_geometry_frontier_rejects_fit_margin_and_size_blind_failures(
    tmp_path: Path,
) -> None:
    assign = tmp_path / "assign"
    assign.mkdir()
    candidates = {
        "1N1E22CD  -01000": ("fit_ft", (-15.0, -16.0)),
        "1N1E22CD  -02000": ("fit_ft", (-20.0, -20.0)),
        "1N1E22CD  -03000": ("min_lot_area_sqft", (-1.0, -1.0)),
        "1N1E22CD  -04000": ("steep_ground", (-1.0, -1.0)),
    }
    rows = []
    for tlid, (check, slacks) in candidates.items():
        for design, slack in zip(("pod56x36@2", "pod80x25@2"), slacks, strict=True):
            rows.append(
                {
                    "jurisdiction": "or/multnomah/portland",
                    "TLID": tlid,
                    "design": design,
                    "colour": "red",
                    "failing": check,
                    "fit_slack_ft": slack,
                }
            )
    pd.DataFrame(rows).to_parquet(assign / "lots.parquet", index=False)

    scope = build_scope(assign)

    assert [row["tlid"] for row in scope] == [
        "1N1E22CD  -01000",
        "1N1E22CD  -04000",
    ]


def test_size_scope_extra_include_and_tlid_file_preserve_spaces(tmp_path: Path) -> None:
    assign = tmp_path / "assign"
    assign.mkdir()
    rows = _assignment_rows()
    extra = dict(rows[0], TLID="1N1E22CD  -00500", failing="min_lot_area_sqft")
    extra_other_design = dict(extra, design="pod80x25@2")
    rows.extend((extra, extra_other_design))
    pd.DataFrame(rows).to_parquet(assign / "lots.parquet", index=False)
    curve = tmp_path / "extra.csv"
    with curve.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("county", "tlid"))
        writer.writeheader()
        writer.writerow({"county": "MULTNOMAH", "tlid": "1N1E22CD - 00500"})
    output = tmp_path / "scope.csv"
    tlid_output = tmp_path / "quadfit.tlids"

    assert scope_main(
        [
            "--assign",
            str(assign),
            "--fit-csv",
            str(curve),
            "--out",
            str(output),
            "--tlid-out",
            str(tlid_output),
        ]
    ) == 0

    assert [line for line in tlid_output.read_text(encoding="utf-8").splitlines()] == [
        "1N1E22CD  -00300",
        "1N1E22CD  -00400",
        "1N1E22CD  -00500",
    ]


def test_size_report_counts_colors_gains_losses_and_best_design(tmp_path: Path) -> None:
    assign = tmp_path / "assign"
    assign.mkdir()
    pd.DataFrame(_assignment_rows()).to_parquet(assign / "lots.parquet", index=False)

    report = render_report(assign)

    assert (
        "design,green,yellow,red,green_change_vs_pod56x36@2,"
        "green_change_vs_pod80x25@2"
    ) in report
    assert "pod60x33@1,1,1,0,1,0" in report
    assert "pod60x33@1,pod56x36@2,or/multnomah/portland,1,0" in report
    assert "pod56x36@2,pod80x25@2,or/multnomah/portland,0,1" in report
    assert "pod64x31@1,1" in report
    assert "pod80x25@2,1" in report


def test_size_report_counts_partial_design_rows_and_missing_lots(tmp_path: Path) -> None:
    assign = tmp_path / "assign"
    assign.mkdir()
    rows = [
        row
        for row in _assignment_rows()
        if not (row["TLID"] == "1N1E22CD  -00300" and row["design"] == "pod60x33@1")
    ]
    pd.DataFrame(rows).to_parquet(assign / "lots.parquet", index=False)

    report = render_report(assign)

    assert "pod60x33@1,0,1,0,0,-1" in report
    assert "pod64x31@1,1,0,1,1,0" in report


def test_size_report_scope_preserves_spaced_tlids_and_drops_synthetic_reasons(
    tmp_path: Path,
) -> None:
    assign = tmp_path / "assign"
    assign.mkdir()
    rows = _assignment_rows()
    marker_rows = (rows[0], rows[1], rows[4], rows[5], rows[6])
    for row, reason in zip(marker_rows, NEVER_SCREENED_REASONS, strict=True):
        row["reasons"] = reason
    pd.DataFrame(rows).to_parquet(assign / "lots.parquet", index=False)
    scope = tmp_path / "scope.csv"
    scope.write_text("tlid\n1N1E22CD - 00300\n", encoding="utf-8")
    tlid_file = tmp_path / "scope.tlids"
    tlid_file.write_text("1N1E22CD - 00300\n", encoding="utf-8")

    report = render_report(assign, scope=scope)
    line_report = render_report(assign, scope=tlid_file)

    assert "Rows dropped by measured-only filter,5" in report
    assert line_report == report
    for reason in NEVER_SCREENED_REASONS:
        assert f"{reason},1" in report
    assert "pod56x36@2,0,0,0,0,0" in report
    assert "1N1E22CD00300" not in report
    assert "or/multnomah/portland" in report
    assert "Rows dropped by measured-only filter,0" in render_report(
        assign, scope=scope, measured_only=False
    )


@pytest.fixture
def canonical_place_cases() -> list[tuple[dict[str, object], str]]:
    return [
        ({"jurisdiction": "beaverton"}, "or/washington/beaverton"),
        (
            {"jurisdiction": "beaverton", "layer_id": "or/washington/beaverton"},
            "or/washington/beaverton",
        ),
        (
            {"jurisdiction": "washington_unincorporated"},
            "or/washington/_unincorporated",
        ),
        (
            {
                "jurisdiction": "or/washington/beaverton",
                "layer_id": "or/washington/_unincorporated",
            },
            "or/washington/_unincorporated",
        ),
        ({"jurisdiction": "nan", "layer_id": "nan"}, "unknown"),
        ({"jurisdiction": float("nan"), "layer_id": None}, "unknown"),
    ]


def test_size_report_canonicalizes_place_keys(canonical_place_cases: list[tuple[dict, str]]) -> None:
    assert [canonical_place(row) for row, _ in canonical_place_cases] == [
        expected for _, expected in canonical_place_cases
    ]


def test_size_report_place_table_omits_places_without_green_rows(tmp_path: Path) -> None:
    assign = tmp_path / "assign"
    assign.mkdir()
    rows = _assignment_rows()
    for design in load_catalog().active():
        rows.append(
            {
                **rows[0],
                "TLID": "1N1E22CD  -00600",
                "jurisdiction": "nan",
                "layer_id": None,
                "design": design.key,
                "colour": "red",
                "reasons": "",
            }
        )
    pd.DataFrame(rows).to_parquet(assign / "lots.parquet", index=False)

    report = render_report(assign)

    place_table = report.split("Green gains/losses by place\n", maxsplit=1)[1]
    assert "or/multnomah/portland" in place_table
    assert "unknown" not in place_table


def test_size_curve_refuses_to_guess_without_a_stored_frontier(tmp_path: Path) -> None:
    assign = tmp_path / "assign"
    bridge = tmp_path / "bridge"
    assign.mkdir()
    bridge.mkdir()
    pd.DataFrame(
        [
            {
                "fit_best_depth_ft": 54.0,
                "fit_required_ft": 36.0,
                "fit_across_ft": 68.0,
                "fit_slack_ft": 18.0,
                "fits": True,
                "envelope_sqft": 8000.0,
                "envelope_source": "test",
                "drawing": "{}",
            }
        ]
    ).to_parquet(assign / "lots.parquet", index=False)
    pd.DataFrame({"fit_best_depth_ft": [54.0], "envelope_sqft": [8000.0]}).to_parquet(
        bridge / "lots.parquet", index=False
    )

    message = frontier_status(assign, bridge)

    assert "No design-independent fit frontier is stored" in message
    assert "fit_best_depth_ft" in message and "fit_required_ft" in message
    assert "does not carry the buildable-envelope geometry" in message


def test_county_falls_back_to_layer_id_when_jurisdiction_is_a_bare_slug() -> None:
    # 2026-11-05 trial on 137: some assign rows carry jurisdiction "portland"
    # while layer_id keeps "or/multnomah/portland" (FOLLOWUPS 149).
    from scripts.flats_size_report import lot_key
    from scripts.flats_size_scope import _county

    row = {"TLID": "1N1E22CD  -00300", "jurisdiction": "portland", "layer_id": "or/multnomah/portland"}
    assert lot_key(row) == ("multnomah", "1N1E22CD00300")
    assert _county(row) == "multnomah"
    # Never-routed lots (JURISDICTION_NOT_ENCODED) carry no path at all.
    assert lot_key({"TLID": "X", "jurisdiction": None, "layer_id": None}) == ("unknown", "X")
    assert _county({"TLID": "X", "jurisdiction": None, "layer_id": None}) == "unknown"
