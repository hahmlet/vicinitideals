"""Build a one-lot-per-line study scope from the current assignments and fit CSV."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

CURRENT_DESIGNS = ("pod56x36@2", "pod80x25@2")


def normalized_tlid(tlid: Any) -> str:
    return re.sub(r"[\s-]", "", str(tlid))


def lot_key(county: Any, tlid: Any) -> tuple[str, str]:
    return str(county).strip().casefold(), normalized_tlid(tlid)


def build_scope(assign_dir: Path, fit_csv: Path) -> list[dict[str, str]]:
    frame = pd.read_parquet(assign_dir / "lots.parquet")
    required = {"county", "jurisdiction", "TLID", "design", "colour"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{assign_dir / 'lots.parquet'} is missing columns: {missing}")

    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in frame.to_dict("records"):
        key = lot_key(row["county"], row["TLID"])
        design = str(row["design"])
        if design in CURRENT_DESIGNS:
            if design in grouped[key]:
                raise ValueError(f"duplicate current-design row for lot {key}, {design}")
            grouped[key][design] = row

    from_fit: set[tuple[str, str]] = set()
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
        statuses = {str(row["colour"]).strip().casefold() for row in designs.values()}
        not_red = any(status != "red" for status in statuses)
        in_curve = key in from_fit
        if not not_red and not in_curve:
            continue
        representative = designs[CURRENT_DESIGNS[0]]
        reasons = []
        if not_red:
            reasons.append("not-red-under-both-current-designs")
        if in_curve:
            reasons.append("fits-new-size-while-current-both-red")
        selected[key] = {
            "county": str(representative["county"]),
            "tlid": str(representative["TLID"]),
            "jurisdiction": str(representative["jurisdiction"]),
            "reason": ";".join(reasons),
        }

    return sorted(selected.values(), key=lambda row: (row["county"], normalized_tlid(row["tlid"])))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assign", type=Path, default=Path("/root/assign_pd2ab"))
    parser.add_argument("--fit-csv", type=Path, default=Path("size_curve_new_fit_red.csv"))
    parser.add_argument("--out", type=Path, default=Path("flats_size_scope.csv"))
    args = parser.parse_args(argv)
    rows = build_scope(args.assign, args.fit_csv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("county", "tlid", "jurisdiction", "reason"))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows):,} lots to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
