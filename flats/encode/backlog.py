"""Generate the encoding backlog from the parcel corpus.

Enumerates every ``(jurisdiction, zone)`` pair **observed in the data**, joins it
against the encoded rules, and ranks the gaps by how many lots each blocks. The
result is the work queue: what to encode next, in the order that unlocks the
most inventory.

This is the control for the failure that cost the project 40,500 lots. Quadfit
dropped unencoded zones into a ``zone_not_in_rules`` bucket where they stopped
being anyone's problem; nobody had decided to exclude Portland's multi-dwelling
land, nobody had written the rows, and the pipeline had no way to say so. A
generated ledger makes the gap a top row instead of an absence.

Reads quadfit's stage-2 parquet until the FLATS ingest stage exists. Condo and
air parcels are removed first — they inflate dense-zone counts and would skew
the ranking toward zones that are mostly not land.

Run::

    python -m flats.encode.backlog
"""

from __future__ import annotations

import argparse
from pathlib import Path

from flats.encode.port_quadfit import layer_id_for
from flats.normalize.condo import classify_frame
from flats.rules.ledger import (
    COVERAGE,
    ObservedZone,
    build_coverage,
    coverage_summary,
    write_coverage,
)
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "data" / "quadfit" / "s2_lots.parquet"
OUT = COVERAGE

_COLUMNS = [
    "jurisdiction",
    "zone_raw",
    "area_sqft",
    "BLDGSQFT",
    "PROP_CODE",
    "COUNTY",
    "inside_ugb",
]


def observed(corpus: Path = CORPUS, *, drop_condos: bool = True) -> list[ObservedZone]:
    import pandas as pd

    df = pd.read_parquet(corpus, columns=_COLUMNS)
    df = df[df.inside_ugb == True]  # noqa: E712 — pandas mask, not a bool test

    if drop_condos:
        df = classify_frame(df)
        df = df[df.condo_verdict != "excluded"]

    rows: list[ObservedZone] = []
    grouped = df.groupby(["jurisdiction", "zone_raw"], dropna=False)
    for (juris, zone), grp in grouped:
        if not juris or not isinstance(zone, str) or not zone:
            continue
        try:
            layer = layer_id_for(str(juris))
        except KeyError:
            # An unmapped jurisdiction is itself a gap; name it so it appears in
            # the ledger rather than vanishing.
            layer = f"UNMAPPED/{juris}"
        rows.append(
            ObservedZone(
                jurisdiction=layer,
                zone=zone,
                lots=int(len(grp)),
                acres=float(grp.area_sqft.sum()) / 43_560.0,
            )
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--top", type=int, default=25, help="Rows to print.")
    ap.add_argument("--keep-condos", action="store_true", help="Do not drop condo/air parcels.")
    args = ap.parse_args()

    rules = RuleSet(load_rules())
    rows = build_coverage(observed(args.corpus, drop_condos=not args.keep_condos), rules)
    write_coverage(rows, args.out)
    summary = coverage_summary(rows)

    total, blocked = summary["lots_total"], summary["lots_blocked"]
    print(f"coverage ledger -> {args.out}")
    print(f"{len(rows)} observed (jurisdiction, zone) pairs · {total:,} lots")
    print(f"{blocked:,} lots ({blocked / max(total, 1) * 100:.1f}%) cannot reach GREEN as encoded\n")

    for status in ("verified", "partial", "stale", "zone_missing", "jurisdiction_missing"):
        zones, lots = summary.get(f"zones_{status}"), summary.get(f"lots_{status}")
        if zones:
            print(f"  {status:22s} {zones:4d} zones  {lots:>9,} lots")

    print(f"\nTop {args.top} by lots blocked — this is the encoding queue:\n")
    print(f"  {'jurisdiction':28s} {'zone':10s} {'lots':>8s}  status")
    for r in rows[: args.top]:
        if not r.blocking:
            break
        print(f"  {r.jurisdiction:28s} {r.zone:10s} {r.lots:>8,}  {r.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
