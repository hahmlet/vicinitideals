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

**Which parquet matters more than it looks.** ``CORPUS`` defaults to the copy
under this repo, and on a development machine that copy is whatever was last
pulled — for five weeks it was a Multnomah-only file while the pipeline this
ledger serves screened two counties. The corpus the screen actually runs on
lives beside the pipeline on the analysis host (LXC 137,
``/root/code/vicinitideals/data/quadfit/s2_lots.parquet``), and the honest way
to regenerate is to run this module there and bring the CSV back. ``shrinkage``
below is the guard for the day somebody forgets.

Run::

    python -m flats.encode.backlog
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from flats.encode.port_quadfit import layer_id_for
from flats.encode.reading_rate import readings, render as render_rates
from flats.normalize.condo import classify_frame
from flats.rules.ledger import (
    COVERAGE,
    CoverageRow,
    ObservedZone,
    ZoneMiss,
    build_coverage,
    coverage_summary,
    read_coverage,
    unweighed,
    unweighed_zones,
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

#: What a parcel whose zoning join came back blank is called in the ledger.
#: Deliberately not a zone code: nothing may read it as one, and it has to
#: sort and print like the gap it is.
UNZONED = "(unzoned in parcel data)"


def _plural(n: int, word: str) -> str:
    """``1 zone`` / ``3 zones``. A report a person reads should read like one."""
    return f"{n:,} {word}" + ("" if n == 1 else "s")



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
        if not juris:
            continue
        if not isinstance(zone, str) or not zone:
            # A parcel the zoning join left blank used to be dropped here,
            # silently, which is the exact failure this module was written to
            # stop: 327 lots -- the whole of Maywood Park -- left the ledger
            # without leaving a row. Blank is not a zone, so it is named as
            # what it is rather than guessed at, and it lands as zone_missing
            # against whatever jurisdiction it sits in.
            zone = UNZONED
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


def shrinkage(
    rows: Sequence[CoverageRow], previous: Sequence[CoverageRow] | None
) -> list[str]:
    """Jurisdictions the committed ledger counts that this run does not.

    A regeneration is not automatically an improvement. The corpus path is an
    argument with a default, the default file is whatever happens to be on the
    machine, and the ledger is committed -- so a run against a smaller corpus
    silently replaces a wider count with a narrower one and every ranking that
    reads it gets quieter about land that has not gone anywhere.

    That is not a hypothetical either. This ledger spent five weeks holding
    Multnomah County alone while the pipeline it serves screened two, and the
    cost surfaced as a district audit that ranked fourteen cities at zero lots
    apiece and nearly closed its own queue on the number. The check is cheap,
    the failure is silent, and silence is the part worth spending code on.

    Returns the jurisdictions that would be lost, empty where nothing is.
    """
    if not previous:
        return []
    before = {row.jurisdiction for row in previous}
    after = {row.jurisdiction for row in rows}
    return sorted(before - after)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--top", type=int, default=25, help="Rows to print.")
    ap.add_argument("--keep-condos", action="store_true", help="Do not drop condo/air parcels.")
    ap.add_argument(
        "--shrink",
        action="store_true",
        help="Write even if this corpus counts fewer jurisdictions than the committed ledger.",
    )
    args = ap.parse_args()

    rules = RuleSet(load_rules())
    rows = build_coverage(observed(args.corpus, drop_condos=not args.keep_condos), rules)

    lost = shrinkage(rows, read_coverage(args.out))
    if lost and not args.shrink:
        print(f"REFUSING TO WRITE {args.out}\n")
        print(f"  {args.corpus} counts no lot in {len(lost)} jurisdiction(s) the")
        print("  committed ledger already holds:\n")
        for name in lost:
            print(f"    {name}")
        print(
            "\n  A narrower corpus overwriting a wider ledger reads as those cities"
            "\n  having no land, not as nobody having counted it. Point --corpus at"
            "\n  the parcel file the screening pipeline runs on, or pass --shrink if"
            "\n  losing them is what you meant."
        )
        return 1

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

    blind = unweighed(rows, rules)
    if blind:
        # Printed before the queue, not after it. The queue is a ranking, and a
        # ranking computed over a corpus that does not contain these
        # jurisdictions is not a ranking of the work -- it is a ranking of the
        # part of the work somebody has counted.
        zones = sum(u.zones for u in blind)
        print(
            f"\nNOT WEIGHED: {len(blind)} encoded jurisdictions, {zones} zones, "
            f"no lot in this corpus:\n"
        )
        for u in blind:
            off = "" if u.eligible else "  (eligible: false)"
            print(f"  {u.jurisdiction:32s} {u.zones:3d} zones{off}")
        print(
            "\n  Nothing above is ranked below, counted in the totals, or able "
            "to appear\n  as a gap. Absence of a row is not a zero."
        )

    # The same question one level down, and the level where the misses are.
    # `unweighed` above returns nothing and is right to: a city is "weighed"
    # the moment one of its zones is, so a layer can look covered while most
    # of its districts have never been counted.
    zone_blind = unweighed_zones(rows, rules)
    if zone_blind:
        joined = [z for z in zone_blind if z.cause is ZoneMiss.near_miss]
        gone = [z for z in zone_blind if z.cause is ZoneMiss.unmapped]
        nojoin = [z for z in zone_blind if z.cause is ZoneMiss.unzoned]
        print(
            f"\nNOT WEIGHED, BY ZONE: {len(zone_blind)} encoded zones no lot has "
            f"ever been counted against\n  (the jurisdiction check above reports "
            f"{len(blind)} — every one of these lives in a city that does appear)"
        )

        if joined:
            lots = sum(z.lots for z in joined)
            print(
                f"\n  THE MAP PRINTS IT UNDER ANOTHER LABEL — "
                f"{_plural(len(joined), 'zone')}, {lots:,} lots:\n"
            )
            for z in joined:
                print(f"    {z.jurisdiction}  {z.zone}  is encoded; the map prints")
                for label, n in z.candidates:
                    print(f"      {label!r:<12} {n:>6,} {'lot' if n == 1 else 'lots'}")
            print(
                "\n    Those labels are in the zone_missing queue above, ranked as "
                "work to do.\n    They are not: the rules exist. What is missing is "
                "the join. Confirm the\n    reading, then alias them — this is a "
                "map-to-text discrepancy for a human,\n    and nothing here writes "
                "a rule."
            )

        if gone:
            print(
                f"\n  ENCODED, AND NOT ON THE MAP AT ALL — "
                f"{_plural(len(gone), 'zone')}:\n"
            )
            for z in gone:
                print(f"    {z.jurisdiction:32s} {z.zone}")
            print(
                "\n    The city has mapped districts and none of them is this one, "
                "and no near\n    label explains it. Either the district was "
                "repealed and our text is a\n    superseded edition, or it exists on "
                "paper and was never mapped. Both need\n    a person; neither is "
                "answerable from inside this repo."
            )

        if nojoin:
            cities: dict[str, int] = {}
            for z in nojoin:
                cities[z.jurisdiction] = cities.get(z.jurisdiction, 0) + 1
            live = [z for z in nojoin if z.eligible]
            print(
                f"\n  NO ZONING JOIN FOR THE CITY — "
                f"{_plural(len(nojoin), 'zone')} over "
                f"{_plural(len(cities), 'jurisdiction')}:\n"
            )
            for name, n in sorted(cities.items()):
                off = "" if any(z.eligible for z in nojoin if z.jurisdiction == name) \
                    else "  (eligible: false — expected)"
                print(f"    {name:32s} {_plural(n, 'zone'):>8s}{off}")
            if not live:
                print(
                    "\n    Every one is a jurisdiction the pipeline is switched off "
                    "for, so its lots\n    arrive with no zone and every zone in it "
                    "is unweighed at once. Expected,\n    and the reason to print it "
                    "is that it stops looking like encoding debt."
                )
            else:
                print(
                    "\n    At least one of these is switched ON, which means a live "
                    "city's lots are\n    arriving with no zone. That is a join "
                    "failure, not a switch."
                )

    print(f"\nTop {args.top} by lots blocked — this is the encoding queue:\n")
    print(f"  {'jurisdiction':28s} {'zone':10s} {'lots':>8s}  status")
    for r in rows[: args.top]:
        if not r.blocking:
            break
        print(f"  {r.jurisdiction:28s} {r.zone:10s} {r.lots:>8,}  {r.status}")

    # The queue says what is left. This says how good what is finished is,
    # which is the half a backlog cannot show and the half a reader who did
    # not write it has no other way to check.
    for line in render_rates(readings()):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
