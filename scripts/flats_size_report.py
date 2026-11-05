"""Summarize seven-design assignment results and green changes by jurisdiction."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

STATUS_RANK = {"unknown": 0, "red": 1, "yellow": 2, "green": 3}
STATUS_NAMES = ("green", "yellow", "red", "unknown")
CURRENT_DESIGNS = ("pod56x36@2", "pod80x25@2")


def normalized_tlid(tlid: Any) -> str:
    return re.sub(r"[\s-]", "", str(tlid))


def lot_key(row: dict[str, Any]) -> tuple[str, str]:
    county = row.get("county")
    if county is None and "county" not in row:
        # Some assign rows carry a bare city slug ("portland") as jurisdiction;
        # layer_id keeps the full "or/<county>/<city>" path, so fall back to it.
        for source in ("jurisdiction", "layer_id"):
            parts = str(row.get(source, "")).split("/")
            if len(parts) >= 3 and parts[1]:
                county = parts[1]
                break
        else:
            # Lots never routed to a jurisdiction (JURISDICTION_NOT_ENCODED,
            # county-roll reds) carry neither; TLIDs are unique across counties.
            county = "unknown"
    return str(county).strip().casefold(), normalized_tlid(row["TLID"])


def _slack(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("-inf")
    return number if pd.notna(number) else float("-inf")


def render_report(assign_dir: Path) -> str:
    from flats.designs.model import load_catalog

    designs = [design.key for design in load_catalog().active()]
    if len(designs) != 7:
        raise ValueError(f"expected seven active study designs, found {len(designs)}: {designs}")
    frame = pd.read_parquet(assign_dir / "lots.parquet")
    required = {"jurisdiction", "TLID", "design", "colour", "fit_slack_ft"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{assign_dir / 'lots.parquet'} is missing columns: {missing}")

    by_lot: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    jurisdictions: dict[tuple[str, str], str] = {}
    for row in frame.to_dict("records"):
        design = str(row["design"])
        if design not in designs:
            continue
        key = lot_key(row)
        status = str(row["colour"]).strip().casefold()
        if status not in STATUS_RANK:
            raise ValueError(f"unrecognized colour {row['colour']!r} for {key}, {design}")
        if design in by_lot[key]:
            raise ValueError(f"duplicate assignment row for lot {key}, {design}")
        by_lot[key][design] = {**row, "_status": status}
        jurisdiction = str(row["jurisdiction"])
        prior = jurisdictions.setdefault(key, jurisdiction)
        if prior != jurisdiction:
            raise ValueError(f"lot {key} has inconsistent jurisdictions: {prior!r}, {jurisdiction!r}")

    from io import StringIO

    out = StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(("Design counts",))
    writer.writerow(("design", "green", "yellow", "red", "unknown", "missing_lots"))
    for design in designs:
        rows_with_design = [rows[design] for rows in by_lot.values() if design in rows]
        counts = Counter(row["_status"] for row in rows_with_design)
        writer.writerow(
            (design, *(counts[name] for name in STATUS_NAMES), len(by_lot) - len(rows_with_design))
        )

    writer.writerow(())
    writer.writerow(("Green gains/losses by jurisdiction",))
    writer.writerow(("design", "reference", "jurisdiction", "gained", "lost"))
    place_names = sorted(set(jurisdictions.values()))
    for design in designs:
        for reference in CURRENT_DESIGNS:
            for jurisdiction in place_names:
                gained = lost = 0
                for key, rows in by_lot.items():
                    if (
                        jurisdictions[key] != jurisdiction
                        or design not in rows
                        or reference not in rows
                    ):
                        continue
                    target_green = rows[design]["_status"] == "green"
                    reference_green = rows[reference]["_status"] == "green"
                    gained += target_green and not reference_green
                    lost += reference_green and not target_green
                writer.writerow((design, reference, jurisdiction, gained, lost))

    writer.writerow(())
    writer.writerow(("Best design per lot",))
    writer.writerow(("highest color, then greatest fit slack, then design key"))
    writer.writerow(("design", "lots"))
    best_counts = Counter()
    for rows in by_lot.values():
        best_counts[
            max(
                rows,
                key=lambda design: (
                    STATUS_RANK[rows[design]["_status"]],
                    _slack(rows[design]["fit_slack_ft"]),
                    design,
                ),
            )
        ] += 1
    for design in designs:
        writer.writerow((design, best_counts[design]))
    return out.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assign", type=Path, required=True, help="assign directory with seven-design lots.parquet")
    args = parser.parse_args(argv)
    print(render_report(args.assign), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
