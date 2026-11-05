"""Build the sizing-study scope from current assignments.

Every study size has the same 500 sq ft floor plate, so floor area, density,
height, roof, lot area/width/frontage, use, and overlay checks cannot change
between sizes. Only the shape-driven checks in ``GEOMETRY_CHECKS`` can change.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

CURRENT_DESIGNS = ("pod56x36@2", "pod80x25@2")
GEOMETRY_CHECKS = {
    "fit_ft",
    "steep_ground",
    "open_space_shape",
    "fire_access_ft",
    "front_yard_vehicle_share",
    "parking_frontage_share",
    "driveway_frontage_share",
    "parking_frontage_width",
    "impervious_pct",
    "building_frontage_share",
    "building_frontage_other_share",
    "parking_cap",
    "open_space_sqft",
    "landscaped_pct",
}


def normalized_tlid(tlid: Any) -> str:
    return re.sub(r"[\s-]", "", str(tlid))


def lot_key(county: Any, tlid: Any) -> tuple[str, str]:
    return str(county).strip().casefold(), normalized_tlid(tlid)


def _county(row: dict[str, Any]) -> str:
    if "county" in row:
        return str(row["county"])
    parts = str(row["jurisdiction"]).split("/")
    if len(parts) < 3 or not parts[1]:
        raise ValueError(f"cannot derive county from jurisdiction {row['jurisdiction']!r}")
    return parts[1]


def _failing_checks(value: Any) -> set[str]:
    if value is None or pd.isna(value):
        return set()
    return {check.strip() for check in str(value).split(",") if check.strip()}


def _is_geometry_frontier(row: dict[str, Any], fit_margin_ft: float) -> bool:
    failing = _failing_checks(row["failing"])
    return (
        bool(failing)
        and failing <= GEOMETRY_CHECKS
        and ("fit_ft" not in failing or _slack(row["fit_slack_ft"]) >= -fit_margin_ft)
    )


def _slack(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("-inf")
    return number if pd.notna(number) else float("-inf")


def build_scope(
    assign_dir: Path,
    fit_csv: Path | None = None,
    fit_margin_ft: float = 15.0,
) -> list[dict[str, str]]:
    if not math.isfinite(fit_margin_ft) or fit_margin_ft < 0:
        raise ValueError("fit_margin_ft must be a finite non-negative number")

    frame = pd.read_parquet(assign_dir / "lots.parquet")
    required = {"jurisdiction", "TLID", "design", "colour", "failing", "fit_slack_ft"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{assign_dir / 'lots.parquet'} is missing columns: {missing}")

    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in frame.to_dict("records"):
        key = lot_key(_county(row), row["TLID"])
        design = str(row["design"])
        if design in CURRENT_DESIGNS:
            if design in grouped[key]:
                raise ValueError(f"duplicate current-design row for lot {key}, {design}")
            grouped[key][design] = row

    from_fit: set[tuple[str, str]] = set()
    if fit_csv is not None:
        with fit_csv.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not {"county", "tlid"} <= set(reader.fieldnames or ()):
                raise ValueError(f"{fit_csv} must contain county and tlid columns")
            for row in reader:
                from_fit.add(lot_key(row["county"], row["tlid"]))

    selected: dict[tuple[str, str], dict[str, str]] = {}
    for key, designs in grouped.items():
        if set(designs) != set(CURRENT_DESIGNS):
            raise ValueError(f"lot {key} does not have exactly both current-design rows")
        not_red = any(str(row["colour"]).strip().casefold() != "red" for row in designs.values())
        geometry_frontier = not not_red and any(
            _is_geometry_frontier(row, fit_margin_ft) for row in designs.values()
        )
        if not not_red and not geometry_frontier and key not in from_fit:
            continue
        representative = designs[CURRENT_DESIGNS[0]]
        selected[key] = {
            "county": _county(representative),
            "tlid": str(representative["TLID"]),
            "jurisdiction": str(representative["jurisdiction"]),
            "reason": (
                "not-red-under-both-current-designs"
                if not_red
                else "red-both-geometry-frontier"
            ),
        }

    return sorted(selected.values(), key=lambda row: (row["county"], normalized_tlid(row["tlid"])))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assign", type=Path, default=Path("/root/assign_pd2ab"))
    parser.add_argument("--fit-csv", type=Path, help="optional extra TLID include list")
    parser.add_argument("--fit-margin-ft", type=float, default=15.0)
    parser.add_argument("--out", type=Path, default=Path("flats_size_scope.csv"))
    parser.add_argument("--tlid-out", type=Path, help="one stored TLID per line (default: sibling .tlids file)")
    args = parser.parse_args(argv)
    rows = build_scope(args.assign, args.fit_csv, args.fit_margin_ft)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("county", "tlid", "jurisdiction", "reason"))
        writer.writeheader()
        writer.writerows(rows)
    tlid_out = args.tlid_out or args.out.with_suffix(".tlids")
    tlid_out.parent.mkdir(parents=True, exist_ok=True)
    with tlid_out.open("w", encoding="utf-8", newline="") as stream:
        stream.writelines(f"{row['tlid']}\n" for row in rows)
    print(f"Wrote {len(rows):,} lots to {args.out}")
    print(f"Wrote {len(rows):,} TLIDs to {tlid_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
