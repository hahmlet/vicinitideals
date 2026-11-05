from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from flats.designs.model import load_catalog
from scripts.flats_size_curve import frontier_status
from scripts.flats_size_report import render_report
from scripts.flats_size_scope import build_scope

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
        "1S 2E05DA -01900": {
            "pod56x36@2": ("red", -4.0),
            "pod80x25@2": ("red", -2.0),
            "pod60x33@1": ("green", 1.0),
            "pod64x31@1": ("green", 5.0),
        },
        "1S 2E05DA -02000": {
            "pod56x36@2": ("red", -1.0),
            "pod80x25@2": ("green", 2.0),
            "pod60x33@1": ("yellow", 0.2),
        },
    }
    rows = []
    for tlid, known in statuses.items():
        for key in keys:
            colour, slack = known.get(key, ("red", -3.0))
            rows.append(
                {
                    "county": "multnomah",
                    "jurisdiction": "or/multnomah/portland",
                    "TLID": tlid,
                    "design": key,
                    "colour": colour,
                    "fit_slack_ft": slack,
                }
            )
    return rows


def test_size_scope_keeps_non_red_lots_and_normalized_curve_matches(tmp_path: Path) -> None:
    assign = tmp_path / "assign"
    assign.mkdir()
    pd.DataFrame(_assignment_rows()).to_parquet(assign / "lots.parquet", index=False)
    curve = tmp_path / "curve.csv"
    with curve.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("county", "tlid", "design"))
        writer.writeheader()
        writer.writerow(
            {
                "county": "MULTNOMAH",
                "tlid": "1S2E05DA - 01900",
                "design": "pod60x33@1",
            }
        )

    rows = build_scope(assign, curve)

    assert [row["tlid"] for row in rows] == ["1S 2E05DA -01900", "1S 2E05DA -02000"]
    assert rows[0]["reason"] == "fits-new-size-while-current-both-red"
    assert rows[1]["reason"] == "not-red-under-both-current-designs"


def test_size_report_counts_colors_gains_losses_and_best_design(tmp_path: Path) -> None:
    assign = tmp_path / "assign"
    assign.mkdir()
    pd.DataFrame(_assignment_rows()).to_parquet(assign / "lots.parquet", index=False)

    report = render_report(assign)

    assert "pod60x33@1,1,1,0,0" in report
    assert "pod80x25@2,pod56x36@2,or/multnomah/portland,1,0" in report
    assert "pod56x36@2,pod80x25@2,or/multnomah/portland,0,1" in report
    assert "pod64x31@1,1" in report
    assert "pod80x25@2,1" in report


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
