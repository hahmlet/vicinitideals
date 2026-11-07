"""Match the historic lists to a lot table (FOLLOWUPS 87).

    uv run python scripts/flats_match_historic.py data/quadfit/s1_lots.parquet
    uv run python scripts/flats_match_historic.py <s1_lots.parquet> --lists gresham troutdale --write
    uv run python scripts/flats_match_historic.py <s1_lots.parquet> --lists shpo-2026-11-06 nps-2026-11-06 --write

Reads ``TLID``, ``SITEADDR``, ``SITECITY``, ``JURIS_CITY`` and prints every city
row's match and what is left unmatched. ``--write`` rewrites the CSVs. A list whose
city the table does not hold is left as it is. Without --write it changes nothing.

A state list (``flats/config/historic/state/<source>/``) also needs ``COUNTY`` and
``wkb``: its points are placed on the lots, and its rows of a county the table does
not hold stay as they are. It prints by place, class and method rather than row by
row, then what the screen would do with it, then the ``UNMATCHED`` ledger ready to
paste into ``flats/tests/test_historic_lists.py``.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from flats.geom import historic_lists as hl


def _state_lists(paths: list[Path], lots: Path, *, write: bool) -> dict[str, int]:
    """Match each state file, print its counts, and return its unmatched rows."""
    frame = pd.read_parquet(lots, columns=["TLID", "SITEADDR", "SITECITY", "JURIS_CITY", "COUNTY", "wkb"])
    rows_by_path = {path: hl.read_rows(path) for path in paths}
    keys = {
        (str(row["county"]).strip()[:1].upper(), row["city"].strip().upper())
        for rows in rows_by_path.values()
        for row in rows
    }
    table = hl.LotTable(frame, keys)
    print(f"lot table: {len(table.tlids):,} lots, counties {sorted(table.counties)}")
    unmatched: dict[str, int] = {}
    for path, rows in rows_by_path.items():
        name = path.parent.name
        new = hl.match_state_rows(rows, table)
        print(f"\n{name}: {len(new):,} rows, by method {dict(Counter(r['match_method'] for r in new).most_common())}")
        by_place: dict[str, Counter[str]] = defaultdict(Counter)
        for row in new:
            by_place[row["place"]][row["class"]] += 1
        for place, kinds in sorted(by_place.items(), key=lambda kv: -sum(kv[1].values())):
            print(f"  {place:<28} {sum(kinds.values()):>6} {dict(kinds.most_common())}")
        unmatched[name] = sum(not r["tlid"] for r in new)
        if write:
            hl.write_state_rows(path, new)
    return unmatched


def _state_outcome(names: set[str]) -> None:
    """What the screen would do with the state files as they now stand."""
    hl.load_lists.cache_clear()
    placed = [x for x in hl.load_lists() if x.list_name in names and x.tlids]
    lots: dict[str, set[str]] = defaultdict(set)
    grid: Counter[tuple[str, str, str]] = Counter()
    for x in placed:
        lots[x.standing].update(hl.compact(t) for t in x.tlids)
        grid[(x.place, x.listing_class, x.standing)] += 1
    print("\nthe screen, as files stand:")
    print(f"  distinct lots: protected {len(lots[hl.PROTECTED]):,}, doubtful {len(lots[hl.DOUBTFUL]):,}")
    for (place, kind, standing), count in sorted(grid.items()):
        print(f"  {place:<28} {kind:<30} {standing:<10} {count:>6}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lots", type=Path, help="a lot table parquet (s1_lots.parquet)")
    parser.add_argument("--lists", nargs="*", default=None, help="list names; default all")
    parser.add_argument("--write", action="store_true", help="rewrite the CSVs")
    args = parser.parse_args(argv)

    frame = pd.read_parquet(args.lots, columns=["TLID", "SITEADDR", "SITECITY", "JURIS_CITY"])
    policy = hl.load_policy()
    left = 0
    unmatched: dict[str, int] = {}
    for name, read in policy.items():
        if args.lists is not None and name not in args.lists:
            continue
        path = hl.LISTS_DIR / f"{name}.csv"
        rows = hl.read_rows(path)
        cities = read.get("cities") or []
        lots = hl.lots_by_street(frame, cities)
        if not lots:
            print(f"{name}: no lots of {cities or 'a named city'} in this table; left as it is")
            unmatched[name] = sum(not r["tlid"] for r in rows)
            left += unmatched[name]
            continue
        new = hl.match_rows(rows, lots)
        print(f"{name}: {dict(Counter(r['match_method'] for r in new))}")
        for row in new:
            mark = "  " if row["tlid"] else "??"
            print(f" {mark} {row['listing_id_or_row']:<10} {row['address_listed'][:40]:<40} "
                  f"{row['match_method']:<18} {row['tlid']} | {row['match_note'][:70]}")
        unmatched[name] = sum(not r["tlid"] for r in new)
        left += unmatched[name]
        if args.write:
            hl.write_rows(path, new)
    print(f"unmatched rows left: {left}")

    state = [p for p in hl.state_files() if args.lists is None or p.parent.name in args.lists]
    if state:
        unmatched.update(_state_lists(state, args.lots, write=args.write))
        if args.write:
            _state_outcome({p.parent.name for p in state})
    if args.write:
        # The ledger counts what the screen reports: a state row that adds nothing
        # in a city whose own list answers is not an unmatched listing.
        hl.load_lists.cache_clear()
        names = [*policy, *(p.parent.name for p in hl.state_files())]
        counts = dict.fromkeys(names, 0) | dict(Counter(x.list_name for x in hl.unmatched()))
        print(f"\nUNMATCHED = {counts!r}")
    else:
        print(f"\nrows naming no lot, before the screen reads them: {unmatched!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
