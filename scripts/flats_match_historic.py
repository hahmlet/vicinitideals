"""Match the historic lists to a lot table (FOLLOWUPS 87).

    uv run python scripts/flats_match_historic.py data/quadfit/s1_lots.parquet
    uv run python scripts/flats_match_historic.py <s1_lots.parquet> --lists gresham troutdale --write

Reads ``TLID``, ``SITEADDR``, ``SITECITY``, ``JURIS_CITY`` and prints every row's
match and what is left unmatched. ``--write`` rewrites the list CSVs. A list whose
city the table does not hold is left as it is. Without --write it changes nothing.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from flats.geom import historic_lists as hl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lots", type=Path, help="a lot table parquet (s1_lots.parquet)")
    parser.add_argument("--lists", nargs="*", default=None, help="list names; default all")
    parser.add_argument("--write", action="store_true", help="rewrite the CSVs")
    args = parser.parse_args(argv)

    frame = pd.read_parquet(args.lots, columns=["TLID", "SITEADDR", "SITECITY", "JURIS_CITY"])
    policy = hl.load_policy()
    left = 0
    for name, read in policy.items():
        if args.lists is not None and name not in args.lists:
            continue
        path = hl.LISTS_DIR / f"{name}.csv"
        rows = hl.read_rows(path)
        cities = read.get("cities") or []
        lots = hl.lots_by_street(frame, cities)
        if not lots:
            print(f"{name}: no lots of {cities or 'a named city'} in this table; left as it is")
            left += sum(not r["tlid"] for r in rows)
            continue
        new = hl.match_rows(rows, lots)
        print(f"{name}: {dict(Counter(r['match_method'] for r in new))}")
        for row in new:
            mark = "  " if row["tlid"] else "??"
            print(f" {mark} {row['listing_id_or_row']:<10} {row['address_listed'][:40]:<40} "
                  f"{row['match_method']:<18} {row['tlid']} | {row['match_note'][:70]}")
        left += sum(not r["tlid"] for r in new)
        if args.write:
            hl.write_rows(path, new)
    print(f"unmatched rows left: {left}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
