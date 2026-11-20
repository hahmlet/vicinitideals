"""Run a lot file through the foundation model, in place (FD6 build step 7).

    uv run python -m flats.foundation <path to fd2_lots.csv>
    uv run python -m flats.foundation --test-lots      # the section 8 test lots only

Reads the lot file where it lies and prints counts and shares only: no lot row
is written anywhere, into the repo or out of it. Every lot with all six
readings is run from its six readings with the lump allowance.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from flats.foundation import ground as grounds
from flats.foundation import lot as lots_mod
from flats.foundation import support
from flats.foundation.cost import dollars
from flats.foundation.lot import LotResult
from flats.foundation.model import MethodResult
from flats.foundation.settings import Settings, load

TEST_LOTS = (
    ("flat", 0, 0),
    ("1 ft along", 1, 0),
    ("2 ft along", 2, 0),
    ("2 ft across", 0, 2),
    ("3 ft along, 1 ft across", 3, 1),
    ("4 ft along", 4, 0),
    ("6 ft along", 6, 0),
)


def ft_in(inches: float) -> str:
    """The section 8 tables' feet-and-inches (nearest inch)."""
    r = round(inches)
    return f"{r // 12} ft {r % 12} in"


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "-"


def quantile(values: list[float], q: float) -> float:
    """The reference model's quantile: the value at index int(q * n) of the sorted list."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def table(title: str, header: list[str], rows: list[list[object]]) -> None:
    print()
    print(f"### {title}")
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for r in rows:
        print("| " + " | ".join(str(c) for c in r) + " |")


def row_of(name: str, r: MethodResult) -> list[object]:
    return [
        name,
        ft_in(r.tallest_wall_in),
        ft_in(r.showing_max_in),
        f"{r.concrete_yd3:.1f}",
        f"{r.bars_lb:,.0f}",
        f"{r.form_sf:,.0f}",
        f"{r.fill_ton:.0f}",
        ft_in(r.highest_door_in),
        f"{r.risers_least}-{r.risers_most}",
        r.risers_total,
        f"{r.longest_stair_in / 12:.1f}",
        r.guards,
        f"{dollars(r.cost.low):,}-{dollars(r.cost.high):,}",
        "; ".join(r.flag_words) or "-",
    ]


def test_lots(s: Settings) -> None:
    header = [
        "lot",
        "tallest wall",
        "concrete showing",
        "concrete cu yd",
        "bars lb",
        "form face sq ft",
        "rock fill tons",
        "highest door",
        "risers least-most",
        "risers, 8 doors",
        "longest stair ft",
        "guards",
        "cost $",
        "flags",
    ]
    for title, method in (("B raised floor on a wall", "B"), ("A slab on fill (dry)", "A dry")):
        rows = []
        for name, along, across in TEST_LOTS:
            res = lots_mod.run_lot(grounds.plane(s, along, across), s)
            rows.append(row_of(name, res[method]))
        table(f"Test lots: {title}", header, rows)


def _dist(title: str, edges: list[float], unit: str, values: list[float]) -> None:
    labels = [f"up to {e:g}" for e in edges] + [f"over {edges[-1]:g}"]
    cnt: Counter[str] = Counter()
    for v in values:
        cnt[next((f"up to {e:g}" for e in edges if v <= e), f"over {edges[-1]:g}")] += 1
    n = len(values)
    table(title, [unit, "lots", "share"], [[k, cnt[k], pct(cnt[k], n)] for k in labels])


def lot_file(path: Path, s: Settings) -> list[LotResult]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    results = [r for r in (lots_mod.from_row(row, s) for row in rows) if r is not None]
    n = len(results)
    print(f"\nlots modelled: {n} of {len(rows)} (the rest lack one of the six readings)")
    groups = Counter(r.group for r in results)
    table("Ground-support groups (lots modelled)", ["group", "lots"], [[g, groups[g]] for g in support.GROUPS])
    lot_flags = Counter(f for r in results for f in r.flags)
    print(
        f"\ncoarse ground model (cell over {s.coarse_cell_over_m:g} m): {lot_flags[lots_mod.COARSE]} lots; "
        f"front face a guess: {lot_flags[lots_mod.FRONT_GUESS]} lots"
    )

    b = [r["B"] for r in results]
    a = [r["A dry"] for r in results]
    _dist("B: tallest wall on the lot, footing top to wall top", [3, 4, 5, 6, 8], "ft", [m.tallest_wall_in / 12 for m in b])
    _dist("B: most concrete showing above ground", [2, 3, 4, 5, 6], "ft", [m.showing_max_in / 12 for m in b])
    _dist("B: average wall height round the building", [2.5, 3, 3.5, 4, 5], "ft", [m.average_wall_in / 12 for m in b])
    _dist("B: risers at all eight doors together", [40, 48, 56, 64, 80], "risers", [m.risers_total for m in b])
    _dist("B: longest stair, out from the wall", [6, 8, 10, 12], "ft", [m.longest_stair_in / 12 for m in b])
    _dist("A: deepest rock fill under the slab", [1, 2, 3, 4], "ft", [m.fill_max_in / 12 for m in a])
    _dist("A: risers at all eight doors together", [8, 16, 24, 32, 40], "risers", [m.risers_total for m in a])

    def share(values: list[MethodResult], test: Callable[[MethodResult], bool]) -> str:
        return pct(sum(1 for m in values if test(m)), len(values))

    print("\nThe FD6 section 8 shares, this build:")
    print(f"- B: concrete showing 3 ft or less {share(b, lambda m: m.showing_max_in / 12 <= 3)}, "
          f"over 4 ft {share(b, lambda m: m.showing_max_in / 12 > 4)}, over 6 ft {share(b, lambda m: m.showing_max_in / 12 > 6)}")
    print(f"- B: risers at all eight doors 48 or fewer {share(b, lambda m: m.risers_total <= 48)}; "
          f"longest stair 8 ft or less {share(b, lambda m: m.longest_stair_in / 12 <= 8)}, "
          f"over 10 ft {share(b, lambda m: m.longest_stair_in / 12 > 10)}")
    print(f"- A: risers at all eight doors 24 or fewer {share(a, lambda m: m.risers_total <= 24)}")
    print(f"- A: deepest fill over 2 ft {share(a, lambda m: m.fill_max_in / 12 > 2)}")

    flag_rows = []
    for method in ("B", "A dry"):
        cnt = Counter(f for r in results for f in r[method].flags)
        for code, k in cnt.most_common():
            flag_rows.append([method, code, k, pct(k, n)])
    table("Flags by method (all lots modelled)", ["method", "flag", "lots", "share"], flag_rows)

    foot = [r for r in results if r.group == support.ORDINARY]
    out = []
    for i, price in enumerate(("low", "high")):
        series = {
            "A dry": [float(r["A dry"].cost.low if i == 0 else r["A dry"].cost.high) for r in foot],
            "A wet": [float(r["A wet"].cost.low if i == 0 else r["A wet"].cost.high) for r in foot],
            "B": [float(r["B"].cost.low if i == 0 else r["B"].cost.high) for r in foot],
        }
        for name, vals in series.items():
            out.append(
                [
                    price,
                    name,
                    f"{sum(vals) / len(vals):,.0f}",
                    f"{quantile(vals, 0.1):,.0f}",
                    f"{quantile(vals, 0.5):,.0f}",
                    f"{quantile(vals, 0.9):,.0f}",
                    f"{max(vals):,.0f}",
                    f"{quantile(vals, 0.9) - quantile(vals, 0.1):,.0f}",
                ]
            )
        wins = sum(1 for r in foot if any(c.prices == price and c.against == "A dry" and c.cheaper == "B" for c in r.cheaper))
        out.append([price, "B cheaper than A dry", pct(wins, len(foot)), "", "", "", "", ""])
    table(
        f"Cost on each lot's own ground, ordinary-footing lots ({len(foot)})",
        ["prices", "method", "mean $", "10th $", "median $", "90th $", "max $", "10th-90th $"],
        out,
    )
    styles = Counter(r.style.words.split(";")[-1].strip() if r.group == support.ORDINARY else r.style.words for r in results)
    table("Foundation style (all lots modelled)", ["style", "lots", "share"], [[k, v, pct(v, n)] for k, v in styles.most_common()])
    hard = Counter(f"{i.code}{' (' + i.method + ')' if i.method else ''}" for r in results for i in r.challenges)
    table("Challenges (lots; a method is named where it is about one)", ["challenge", "lots", "share"], [[k, v, pct(v, n)] for k, v in hard.most_common()])
    easy = Counter(f"{i.code}{' (' + i.method + ')' if i.method else ''}" for r in results for i in r.easy)
    table("Easy parts", ["easy part", "lots", "share"], [[k, v, pct(v, n)] for k, v in easy.most_common()])
    piles = [r for r in results if r.group == support.PILES]
    if piles:
        lo = [float(r["B+P"].cost.low) for r in piles]
        hi = [float(r["B+P"].cost.high) for r in piles]
        print(
            f"\nB+P on the {len(piles)} piles-under-the-wall lots: mean ${sum(lo) / len(lo):,.0f} (low) "
            f"to ${sum(hi) / len(hi):,.0f} (high); highest ${max(lo):,.0f}-{max(hi):,.0f}"
        )
    return results


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m flats.foundation", description=__doc__.split("\n\n")[0])
    ap.add_argument("lots", nargs="?", type=Path, help="lot file (fd2_lots.csv), read in place")
    ap.add_argument("--test-lots", action="store_true", help="print the section 8 test-lot tables")
    args = ap.parse_args(argv)
    s = load()
    if args.test_lots or args.lots is None:
        test_lots(s)
    if args.lots is not None:
        lot_file(args.lots, s)


if __name__ == "__main__":
    main()
