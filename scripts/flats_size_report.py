"""Summarize seven-design assignment results and green changes by jurisdiction."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

STATUS_RANK = {"unknown": 0, "red": 1, "yellow": 2, "green": 3}
STATUS_NAMES = ("green", "yellow", "red")
CURRENT_DESIGNS = ("pod56x36@2", "pod80x25@2")
# Never-screened synthetic markers written by assign.py (flats/ingest/assign.py:10-12).
NEVER_SCREENED_REASONS = (
    "OUTSIDE_UGB",
    "JURISDICTION_OFF",
    "JURISDICTION_NOT_ENCODED",
    "NO_ZONE",
    "ZONE_UNENCODABLE",
)


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


def _value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().casefold()


def _place_path(value: Any) -> str | None:
    parts = _value(value).split("/")
    if len(parts) == 3 and parts[0] == "or" and parts[1] and parts[2]:
        return "/".join(parts)
    return None


@lru_cache(maxsize=1)
def _jurisdiction_slugs() -> dict[str, set[str]]:
    root = Path(__file__).resolve().parents[1] / "flats" / "config" / "jurisdictions" / "or"
    slugs: dict[str, set[str]] = defaultdict(set)
    for path in root.rglob("*.yaml"):
        relative = path.relative_to(root)
        if len(relative.parts) != 2:
            continue
        county = path.parent.name
        city = path.stem.replace("-", "_")
        place = f"or/{county}/{city}"
        slug = f"{county}_unincorporated" if city == "_unincorporated" else city
        slugs[slug].add(place)
    return slugs


def canonical_place(row: dict[str, Any]) -> str:
    for field in ("layer_id", "jurisdiction"):
        path = _place_path(row.get(field))
        if path:
            return path

    slug = _value(row.get("jurisdiction"))
    candidates = _jurisdiction_slugs().get(slug, set())
    if len(candidates) == 1:
        return next(iter(candidates))
    county = _value(row.get("county"))
    county_match = [place for place in candidates if place.split("/")[1] == county]
    return county_match[0] if len(county_match) == 1 else "unknown"


def _read_scope(path: Path) -> set[str]:
    if path.suffix.casefold() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = {field.casefold(): field for field in reader.fieldnames or ()}
            tlid_field = fields.get("tlid")
            if tlid_field is None:
                raise ValueError(f"{path} must have a tlid column")
            values = [row.get(tlid_field) for row in reader]
    else:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            values = (line.removesuffix("\n").removesuffix("\r") for line in stream)
            return {key for value in values if (key := normalized_tlid(value))}
    return {key for value in values if (key := normalized_tlid(value))}


def render_report(
    assign_dir: Path, scope: Path | None = None, measured_only: bool = True
) -> str:
    from flats.designs.model import load_catalog

    designs = [design.key for design in load_catalog().active()]
    if len(designs) != 7:
        raise ValueError(f"expected seven active study designs, found {len(designs)}: {designs}")
    frame = pd.read_parquet(assign_dir / "lots.parquet")
    required = {"jurisdiction", "TLID", "design", "colour", "fit_slack_ft", "reasons"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{assign_dir / 'lots.parquet'} is missing columns: {missing}")

    frame = frame[frame["design"].astype(str).isin(designs)]
    if scope is not None:
        allowed_tlids = _read_scope(scope)
        frame = frame[frame["TLID"].map(normalized_tlid).isin(allowed_tlids)]
    dropped_reasons: Counter[str] = Counter()
    if measured_only:
        dropped = frame["reasons"].isin(NEVER_SCREENED_REASONS)
        dropped_reasons.update(frame.loc[dropped, "reasons"].value_counts().to_dict())
        frame = frame.loc[~dropped]

    by_lot: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    places: dict[tuple[str, str], str] = {}
    for row in frame.to_dict("records"):
        design = str(row["design"])
        key = lot_key(row)
        status = str(row["colour"]).strip().casefold()
        if status not in STATUS_RANK:
            raise ValueError(f"unrecognized colour {row['colour']!r} for {key}, {design}")
        if design in by_lot[key]:
            raise ValueError(f"duplicate assignment row for lot {key}, {design}")
        by_lot[key][design] = {**row, "_status": status}
        place = canonical_place(row)
        prior = places.setdefault(key, place)
        if prior != place:
            raise ValueError(f"lot {key} has inconsistent places: {prior!r}, {place!r}")

    from io import StringIO

    out = StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(("Design counts and green change",))
    writer.writerow(
        (
            "design",
            *STATUS_NAMES,
            f"green_change_vs_{CURRENT_DESIGNS[0]}",
            f"green_change_vs_{CURRENT_DESIGNS[1]}",
        )
    )
    green_counts: Counter[str] = Counter()
    color_counts: dict[str, Counter[str]] = {}
    for design in designs:
        rows_with_design = [rows[design] for rows in by_lot.values() if design in rows]
        counts = Counter(row["_status"] for row in rows_with_design)
        color_counts[design] = counts
        green_counts[design] = counts["green"]
    for design in designs:
        writer.writerow(
            (
                design,
                *(color_counts[design][name] for name in STATUS_NAMES),
                *(green_counts[design] - green_counts[reference] for reference in CURRENT_DESIGNS),
            )
        )

    writer.writerow(())
    writer.writerow(("Rows dropped by measured-only filter", sum(dropped_reasons.values())))
    writer.writerow(("reason", "rows"))
    for reason in NEVER_SCREENED_REASONS:
        writer.writerow((reason, dropped_reasons[reason]))

    writer.writerow(())
    writer.writerow(("Green gains/losses by place",))
    writer.writerow(("design", "reference", "place", "gained", "lost"))
    green_places = {
        places[key]
        for key, rows in by_lot.items()
        if any(row["_status"] == "green" for row in rows.values())
    }
    place_names = sorted(green_places)
    for design in designs:
        for reference in CURRENT_DESIGNS:
            for jurisdiction in place_names:
                gained = lost = 0
                for key, rows in by_lot.items():
                    if (
                        places[key] != jurisdiction
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
    parser.add_argument("--scope", type=Path, help="CSV with a tlid column or one TLID per line")
    parser.add_argument(
        "--measured-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="exclude synthetic rows for lots that were never screened (default: on)",
    )
    args = parser.parse_args(argv)
    print(render_report(args.assign, scope=args.scope, measured_only=args.measured_only), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
