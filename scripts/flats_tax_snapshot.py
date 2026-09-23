"""Property-tax impact snapshot: what each green lot pays today, as one new
house, and as the pod split into four fee-simple lots.

A one-off, not a pipeline stage -- nothing recomputes it when lots are
re-screened. The arithmetic (Oregon Measures 5 and 50) is ``flats/tax/``; the
rates are ``flats/config/tax/or/<county>/<year>.yaml``; this script picks the
lots, joins each to its tax code area, prices the three scenarios and writes
``flats.tax_snapshots`` / ``flats.tax_impact_lots`` plus a CSV and a short
summary.

The green lots are those of the promoted run (the newest ``complete`` run,
as the Lots pages default to) in one jurisdiction that quadfit triaged green
or that FLATS answers green if signed, on any design; each row says which.

The tax code area is not on the lot rows -- acquire keeps only the roll's
declared fields -- so ``taxcodes`` reads RLIS TAXCODE for the county straight
out of the quarterly ZIP by range request (the same reader acquire uses; only
the ``.dbf`` is fetched) into a CSV, and ``run`` joins on TLID. The CSV also
carries ASSESSVAL, and ``run`` reports how many lots' AV matches the loaded
roll's, which is the check that the values and the rates are from one year.

Usage (inside the api container):

    python scripts/flats_tax_snapshot.py taxcodes --county M \\
        --out /app/data/flats/tax/rlis_taxcodes_multnomah.csv
    python scripts/flats_tax_snapshot.py run \\
        --taxcodes /app/data/flats/tax/rlis_taxcodes_multnomah.csv \\
        [--jurisdiction or/multnomah/gresham] [--county multnomah] [--tax-year 2025-26] \\
        [--run 12] [--out-dir /app/data/flats] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import io
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.models.flats import (  # noqa: E402
    FlatsLot,
    FlatsLotResult,
    FlatsRun,
    FlatsTaxImpactLot,
    FlatsTaxSnapshot,
)
from flats.tax import impact, rates  # noqa: E402
from flats.tax.snapshot import COLUMNS, green_source, house_value, price_lot, summarize  # noqa: E402

#: The pod's per-unit market value band. No base case: the resale terms that
#: would pick one are undecided.
BAND = (Decimal("275000"), Decimal("450000"))
UNITS = 4
#: New single-family houses the new-house value is read from: residential
#: property class, land use SFR, built in these years. The roll's year is
#: valued as of January 1 of its assessment year, so a house built in that
#: year (or later) was at most part-finished on the roll -- it is left out.
HOUSE_YEARS = (2020, 2024)
TAXCODE_FIELDS = ("TLID", "TAXCODE", "ASSESSVAL", "TOTALVAL", "JURIS_CITY")


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


# --- taxcodes ------------------------------------------------------------------


def _taxcodes(args: argparse.Namespace) -> int:
    import httpx
    import shapefile  # pyshp

    from flats.ingest.acquire import _archive_identity, _RemoteZip
    from flats.ingest.sources import load_pipeline

    ds = load_pipeline().datasets["rlis_taxlots"]
    assert ds.member
    dbf_name = ds.member.rsplit(".", 1)[0] + ".dbf"
    with httpx.Client(follow_redirects=True, timeout=600) as client:
        archive = _RemoteZip(client, ds.url)
        identity = _archive_identity(client, ds.url, archive)
        print(f"RLIS release {identity.get('release')} ({identity.get('modified')}); reading {dbf_name}")
        dbf = archive.member(dbf_name)
    reader = shapefile.Reader(dbf=io.BytesIO(dbf))
    names = [f[0] for f in reader.fields[1:]]
    missing = [f for f in (*TAXCODE_FIELDS, "COUNTY") if f not in names]
    if missing:
        print(f"refused: the dbf has no {', '.join(missing)}")
        return 2
    at = {n: names.index(n) for n in (*TAXCODE_FIELDS, "COUNTY")}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with args.out.open("w", newline="", encoding="utf-8") as f:
        f.write(f"# RLIS release {identity.get('release')}, {ds.url}\n")
        w = csv.writer(f)
        w.writerow(TAXCODE_FIELDS)
        for rec in reader.iterRecords():
            if str(rec[at["COUNTY"]]).strip().upper() != args.county.upper():
                continue
            w.writerow([str(rec[at[k]]).strip() for k in TAXCODE_FIELDS])
            n += 1
    print(f"{n:,} {args.county} rows -> {args.out}")
    return 0


def read_taxcodes(path: Path) -> tuple[dict[str, dict[str, str]], str]:
    with path.open(encoding="utf-8") as f:
        first = f.readline()
        header = first.strip() if first.startswith("#") else ""
        if not header:
            f.seek(0)
        rows = {r["TLID"].strip(): r for r in csv.DictReader(f)}
    return rows, header.lstrip("# ")


# --- run ------------------------------------------------------------------------


async def _pick_run(session: AsyncSession, run_id: int | None) -> FlatsRun | None:
    if run_id:
        return await session.get(FlatsRun, run_id)
    stmt = select(FlatsRun).where(FlatsRun.status == "complete").order_by(FlatsRun.id.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _green_lots(session: AsyncSession, run: FlatsRun, jurisdiction: str) -> list[dict[str, Any]]:
    flats_green = func.bool_or(FlatsLotResult.checks["if_signed"].astext == "green")
    stmt = (
        select(
            FlatsLot.id,
            FlatsLot.tlid,
            FlatsLot.facts["assessor"],
            FlatsLot.facts["quadfit"]["triage"].astext,
            flats_green,
        )
        .join(FlatsLotResult, and_(FlatsLotResult.lot_id == FlatsLot.id, FlatsLotResult.run_id == run.id))
        .where(FlatsLot.jurisdiction == jurisdiction)
        .group_by(FlatsLot.id)
    )
    out = []
    for lot_id, tlid, assessor, triage, fgreen in (await session.execute(stmt)).all():
        source = green_source(triage == "green", bool(fgreen))
        if source:
            out.append({"lot_id": lot_id, "tlid": tlid, "assessor": assessor or {}, "green_source": source})
    return out


async def _house_records(session: AsyncSession, run: FlatsRun, jurisdiction: str) -> list[tuple[Decimal, Decimal]]:
    a = FlatsLot.facts["assessor"]
    stmt = select(a["building_value"].astext, a["building_sqft"].astext).where(
        FlatsLot.snapshot_id == run.snapshot_id,
        FlatsLot.jurisdiction == jurisdiction,
        a["prop_code"].astext.like("1%"),
        a["land_use"].astext == "SFR",
        a["year_built"].astext.cast(Integer).between(*HOUSE_YEARS),
    )
    out = []
    for bv, sf in (await session.execute(stmt)).all():
        bv, sf = _dec(bv), _dec(sf)
        if bv is not None and sf is not None:
            out.append((bv, sf))
    return out


def _roll(assessor: dict[str, Any]) -> impact.Roll | None:
    vals = [_dec(assessor.get(k)) for k in ("land_value", "building_value", "total_value", "assessed_value")]
    if any(v is None for v in vals):
        return None
    return impact.Roll(*vals)  # type: ignore[arg-type]


async def _run(session: AsyncSession, args: argparse.Namespace) -> int:
    rate_file = rates.for_county(args.county, args.tax_year)
    run = await _pick_run(session, args.run)
    if run is None:
        print("refused: no complete run to read green lots from")
        return 2
    lots = await _green_lots(session, run, args.jurisdiction)
    house = house_value(await _house_records(session, run, args.jurisdiction))
    codes, taxcode_source = read_taxcodes(args.taxcodes)
    today = dt.date.today().isoformat()

    rows: list[dict[str, Any]] = []
    av_checked = av_same = 0
    for lot in lots:
        code_row = codes.get(lot["tlid"].strip())
        taxcode = (code_row or {}).get("TAXCODE") or None
        roll = _roll(lot["assessor"])
        if code_row and roll is not None:
            av_checked += 1
            av_same += _dec(code_row.get("ASSESSVAL")) == roll.assessed_value
        figures, notes = price_lot(
            roll,
            rate_file.levies(taxcode),
            city=rate_file.city,
            cpr=rate_file.cpr_residential,
            house_rmv=house.rmv,
            band=BAND,
            units=UNITS,
        )
        if code_row is None:
            notes["taxcode"] = "tlid_not_in_taxcode_file"
        rows.append(
            {
                "lot_id": lot["lot_id"],
                "tlid": lot["tlid"],
                "green_source": lot["green_source"],
                "taxcode": taxcode.zfill(3) if taxcode else None,
                **figures,
                "notes": notes,
            }
        )

    params = {
        "created": today,
        "jurisdiction": args.jurisdiction,
        "tax_year": rate_file.tax_year,
        "run_id": run.id,
        "snapshot_id": run.snapshot_id,
        "units": UNITS,
        "cpr": str(rate_file.cpr_residential),
        "band": {"low": int(BAND[0]), "high": int(BAND[1])},
        "house": {
            "rmv": int(house.rmv),
            "per_sqft": str(house.per_sqft.quantize(Decimal("0.01"))),
            "sqft": str(house.sqft),
            "sample": house.sample,
            "derivation": (
                f"median building value per sq ft ${house.per_sqft:,.2f} x median building "
                f"{house.sqft:,.0f} sq ft, {house.sample:,} {args.jurisdiction} single-family "
                f"houses built {HOUSE_YEARS[0]}-{HOUSE_YEARS[1]} on the roll"
            ),
        },
        "rates_file": str(rate_file.path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "rates_sources": rate_file.sources,
        "taxcodes": {"file": str(args.taxcodes), "source": taxcode_source},
        "vintage_check": {"lots_compared": av_checked, "av_matches_roll": av_same},
        "counts": {
            src: sum(1 for r in rows if r["green_source"] == src) for src in ("both", "quadfit_only", "flats_only")
        },
    }
    print(
        f"run {run.id}: {len(rows):,} green lots in {args.jurisdiction} {params['counts']}; "
        f"house RMV ${house.rmv:,} ({house.sample} builds); "
        f"AV matches the taxcode file on {av_same:,} of {av_checked:,}"
    )

    snap = FlatsTaxSnapshot(jurisdiction=args.jurisdiction, tax_year=rate_file.tax_year, run_id=run.id, params=params)
    session.add(snap)
    await session.flush()
    session.add_all(FlatsTaxImpactLot(tax_snapshot_id=snap.id, **r) for r in rows)
    await session.flush()
    params["tax_snapshot_id"] = snap.id

    slug = args.jurisdiction.rsplit("/", 1)[-1]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_dir / f"tax_impact_{slug}_{today}.csv"
    md_path = args.out_dir / f"tax_impact_{slug}_{today}.md"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tlid", "lot_id", "green_source", "taxcode", *COLUMNS, "notes"])
        for r in rows:
            w.writerow([r["tlid"], r["lot_id"], r["green_source"], r["taxcode"] or "",
                        *("" if r[c] is None else r[c] for c in COLUMNS), _flat(r["notes"])])
    md_path.write_text(summarize(rows, params), encoding="utf-8")
    print(f"wrote {csv_path} and {md_path}")

    if args.dry_run:
        await session.rollback()
        print(f"dry run, rolled back (snapshot {snap.id} not kept)")
    else:
        await session.commit()
        print(f"tax snapshot {snap.id} committed")
    return 0


def _flat(notes: dict[str, Any]) -> str:
    return "; ".join(f"{k}={v}" for k, v in notes.items())


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", default=settings.database_url)
    sub = parser.add_subparsers(dest="command", required=True)

    tc = sub.add_parser("taxcodes", help="read RLIS TAXCODE for one county out of the quarterly ZIP")
    tc.add_argument("--county", default="M", help="RLIS COUNTY letter (M, C, W)")
    tc.add_argument("--out", type=Path, required=True)

    rn = sub.add_parser("run", help="price the green lots and write the snapshot")
    rn.add_argument("--taxcodes", type=Path, required=True, help="the CSV `taxcodes` wrote")
    rn.add_argument("--jurisdiction", default="or/multnomah/gresham")
    rn.add_argument("--county", default="multnomah", help="rate file directory under flats/config/tax/or/")
    rn.add_argument("--tax-year", default="2025-26")
    rn.add_argument("--run", type=int, default=None, help="flats.runs id (default: newest complete)")
    rn.add_argument("--out-dir", type=Path, default=REPO_ROOT / "data" / "flats")
    rn.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "taxcodes":
        return _taxcodes(args)
    engine = create_async_engine(args.db_url, echo=False, future=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            return await _run(session, args)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
