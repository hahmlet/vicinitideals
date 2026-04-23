"""End-to-end live test of the LoopNet scraper against the real RapidAPI endpoint.

Uses an in-memory SQLite DB for api_call_log so BudgetGuard's budget enforcement
works, but nothing touches your production Postgres.

Run:
    uv run python scripts/test_loopnet_live.py

Requires RAPIDAPI_KEY set in the environment (or .env). Hard-caps budget at
50 calls (override via --budget). Tests:

  Phase 1 — single polygon bbox search (east_metro)
  Phase 2 — polygon clip + bulk triage classification
  Phase 3 — SaleDetails on a few representative keepers
  Phase 4 — ExtendedDetails on a confirmed MF listing
  Phase 5 — lease side sanity check (bbox + one LeaseDetails)

Prints a structured report at each phase with call counts and wall times.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import Base  # noqa: E402
from app.scrapers.loopnet import (  # noqa: E402
    BudgetGuard,
    bbox_search,
    classify_categories,
    classify_from_bulk,
    clip_to_polygon,
    fetch_bulk_details,
    fetch_extended_details,
    fetch_lease_details,
    fetch_sale_details,
    lease_bbox_search,
    load_polygons,
    map_lease_to_scraped_listing,
    map_to_scraped_listing,
    parse_target_ed_categories,
    polygon_bbox,
    should_fetch_extended_details,
    should_fetch_sale_details_after_bulk,
)


def _hdr(label: str) -> None:
    print()
    print("=" * 70)
    print(f"  {label}")
    print("=" * 70)


async def main(budget: int, polygon_name: str | None, do_lease: bool) -> int:
    # Check API key
    from app.config import settings
    if not settings.rapidapi_key:
        print("ERROR: RAPIDAPI_KEY not set in env/.env")
        return 1

    # In-memory SQLite for api_call_log
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    polygons = load_polygons()
    if polygon_name:
        polygons = [p for p in polygons if p["name"] == polygon_name]
        if not polygons:
            print(f"ERROR: polygon {polygon_name!r} not found in market_polygons.json")
            return 1
    # For safety, always pick just the first polygon in the test
    polygon = polygons[0]
    bbox = polygon_bbox(polygon["points"])

    print(f"POLYGON: {polygon['name']} (purpose={polygon.get('purpose')})")
    print(f"BBOX:    {bbox}")
    print(f"BUDGET CAP: {budget} calls")

    target_ed_categories = parse_target_ed_categories(
        settings.loopnet_target_ed_categories
    )

    async with session_factory() as session:
        async with BudgetGuard(session, monthly_budget=budget, safety_margin=0) as guard:

            # PHASE 1 — bbox search
            _hdr("PHASE 1 — bbox search")
            t0 = time.monotonic()
            rows = await bbox_search(guard, bbox)
            elapsed = time.monotonic() - t0
            clipped = clip_to_polygon(rows, polygon["points"])
            print(f"  bbox raw rows: {len(rows)}")
            print(f"  after polygon clip: {len(clipped)}")
            print(f"  calls used so far: {guard.calls_used}  | wall time: {elapsed:.1f}s")
            if not clipped:
                print("  No listings after clip — abort.")
                return 0

            # PHASE 2 — bulk triage
            _hdr("PHASE 2 — bulkDetails triage")
            candidate_ids = [str(r["listingId"]) for r in clipped]
            t0 = time.monotonic()
            bulk_rows = await fetch_bulk_details(guard, candidate_ids)
            elapsed = time.monotonic() - t0
            print(f"  bulk returned {len(bulk_rows)} rows from {len(candidate_ids)} IDs")
            print(f"  calls used so far: {guard.calls_used}  | wall time for this phase: {elapsed:.1f}s")

            bulk_cats: dict[str, set[str]] = {}
            cat_counts: dict[str, int] = {}
            for brow in bulk_rows:
                lid = str(brow.get("listingId") or "")
                cats = classify_from_bulk(brow)
                bulk_cats[lid] = cats
                for c in cats:
                    cat_counts[c] = cat_counts.get(c, 0) + 1
            print("  category distribution from bulk:")
            for c, n in sorted(cat_counts.items(), key=lambda kv: -kv[1]):
                print(f"    {c}: {n}")

            # Triage decision counts
            polygon_purposes = {polygon.get("purpose", "target")}
            keepers_for_sd = []
            for lid, cats in bulk_cats.items():
                if should_fetch_sale_details_after_bulk(
                    cats, polygon_purposes, target_ed_categories
                ):
                    keepers_for_sd.append(lid)
            print(
                f"  triage keepers (would fetch SaleDetails): "
                f"{len(keepers_for_sd)} of {len(bulk_cats)} "
                f"(saved {len(bulk_cats) - len(keepers_for_sd)} SD calls)"
            )

            # Dump per-keeper summary (first 10)
            print("  sample keepers:")
            for lid in keepers_for_sd[:10]:
                brow = next((b for b in bulk_rows if str(b.get("listingId")) == lid), None)
                if not brow:
                    continue
                title = (brow.get("title") or ["?"])[0]
                city = (brow.get("location") or {}).get("cityState", "?")
                price = brow.get("price")
                cats = bulk_cats[lid]
                print(f"    [{lid}] {title[:35]:35} | {city:20} | {price:12} | {sorted(cats)}")

            # PHASE 3 — SaleDetails on up to 3 keepers (cost control)
            _hdr("PHASE 3 — SaleDetails on up to 3 keepers (budget control)")
            sample_size = min(3, len(keepers_for_sd), max(0, budget - guard.calls_used - 2))
            if sample_size <= 0:
                print("  Budget exhausted — skipping SD phase.")
            else:
                mf_keeper_id: str | None = None
                for lid in keepers_for_sd[:sample_size]:
                    t0 = time.monotonic()
                    sale = await fetch_sale_details(guard, lid)
                    elapsed = time.monotonic() - t0
                    if not sale:
                        print(f"  [{lid}] SaleDetails returned empty")
                        continue
                    pf = sale.get("propertyFacts") or {}
                    cats = classify_categories(sale)
                    decision = should_fetch_extended_details(
                        cats, polygon_purposes, target_ed_categories
                    )
                    # Try to map it (dry-run, just to check no exceptions)
                    try:
                        clipped_row = next(
                            (r for r in clipped if str(r["listingId"]) == lid), None
                        )
                        coords = (clipped_row or {}).get("coordinations") or [[None, None]]
                        lng, lat = coords[0][0], coords[0][1]
                        mapped = map_to_scraped_listing(
                            sale, None, listing_id=lid, lat=lat, lng=lng,
                        )
                        mapping_ok = True
                        mapping_err: str | None = None
                    except Exception as exc:  # noqa: BLE001
                        mapped = {}
                        mapping_ok = False
                        mapping_err = str(exc)
                    print(
                        f"  [{lid}] {pf.get('propertyType', '?'):12} | "
                        f"price={pf.get('price', '?'):12} | cap={pf.get('capRate', '?'):8} | "
                        f"SF={pf.get('buildingSize', '?'):10} | "
                        f"cats_from_SD={sorted(cats)} | ED?={'yes' if decision else 'no'} | "
                        f"map_ok={mapping_ok} | {elapsed:.1f}s"
                    )
                    if mapping_ok:
                        print(
                            f"       mapped apn={mapped.get('apn')}  "
                            f"asking_price={mapped.get('asking_price')}  "
                            f"cap_rate={mapped.get('cap_rate')}  "
                            f"gba_sqft={mapped.get('gba_sqft')}  "
                            f"year_built={mapped.get('year_built')}"
                        )
                    elif mapping_err:
                        print(f"       ERROR: {mapping_err}")
                    if "multifamily" in cats and mf_keeper_id is None:
                        mf_keeper_id = lid

                # PHASE 4 — ExtendedDetails on one MF (if found)
                _hdr("PHASE 4 — ExtendedDetails on one MF keeper")
                if mf_keeper_id is None:
                    print("  No MF found in the SD sample — skipping ED phase.")
                elif guard.remaining <= 1:
                    print("  Budget too low for ED — skipping.")
                else:
                    # Re-fetch SD for the MF keeper so we can verify combined SD+ED mapping
                    t0 = time.monotonic()
                    sale_mf = await fetch_sale_details(guard, mf_keeper_id)
                    ext = await fetch_extended_details(guard, mf_keeper_id)
                    elapsed = time.monotonic() - t0
                    if not ext:
                        print(f"  [{mf_keeper_id}] ED returned empty")
                    else:
                        sale_summary = ext.get("saleSummary") or {}
                        demographics_present = "demographics" in ext
                        print(f"  [{mf_keeper_id}] ED size={len(str(ext))} bytes | {elapsed:.1f}s")
                        print(f"       saleSummary.apn={sale_summary.get('apn')}")
                        print(f"       saleSummary.lotSize={sale_summary.get('lotSize')!r}")
                        print(f"       saleSummary.yearBuilt={sale_summary.get('yearBuilt')!r}")
                        print(f"       demographics present: {demographics_present}")
                        print(f"       carousel count: {len(ext.get('carousel') or [])}")

                        # Combined SD+ED mapping — this is what the real weekly sweep does
                        clipped_row = next(
                            (r for r in clipped if str(r["listingId"]) == mf_keeper_id), None
                        )
                        coords = (clipped_row or {}).get("coordinations") or [[None, None]]
                        lng, lat = coords[0][0], coords[0][1]
                        mapped_full = map_to_scraped_listing(
                            sale_mf, ext, listing_id=mf_keeper_id, lat=lat, lng=lng,
                        )
                        print(f"       >> combined-map year_built={mapped_full['year_built']}")
                        print(f"       >> combined-map year_renovated={mapped_full['year_renovated']}")
                        print(f"       >> combined-map lot_sqft={mapped_full['lot_sqft']}")
                        print(f"       >> combined-map apn={mapped_full['apn']}")

            # PHASE 5 — lease side
            if do_lease and guard.remaining >= 2:
                _hdr("PHASE 5 — lease bbox + one LeaseDetails")
                t0 = time.monotonic()
                lease_rows = await lease_bbox_search(guard, bbox)
                elapsed = time.monotonic() - t0
                lease_clipped = clip_to_polygon(lease_rows, polygon["points"])
                print(f"  lease bbox: {len(lease_rows)} rows, clipped: {len(lease_clipped)}, {elapsed:.1f}s")

                if lease_clipped and guard.remaining >= 1:
                    sample_lease_id = str(lease_clipped[0]["listingId"])
                    t0 = time.monotonic()
                    lease = await fetch_lease_details(guard, sample_lease_id)
                    elapsed = time.monotonic() - t0
                    if lease:
                        spaces = lease.get("spaces") or []
                        first_space = spaces[0] if spaces else {}
                        print(
                            f"  [{sample_lease_id}] category={lease.get('category')} | "
                            f"title={str(lease.get('title'))[:40]}"
                        )
                        print(f"       spaces={len(spaces)} | first sfPerYear={first_space.get('sfPerYear')}")
                        try:
                            coords = (lease_clipped[0] or {}).get("coordinations") or [[None, None]]
                            lng, lat = coords[0][0], coords[0][1]
                            mapped_lease = map_lease_to_scraped_listing(
                                lease, listing_id=sample_lease_id, lat=lat, lng=lng,
                            )
                            print(
                                f"       lease map: street={mapped_lease.get('street')} "
                                f"ppsf={mapped_lease.get('price_per_sqft')}"
                            )
                        except Exception as exc:  # noqa: BLE001
                            print(f"       lease map ERROR: {exc}")

            # Final summary
            _hdr("SUMMARY")
            print(f"  total API calls: {guard.calls_used}  (cap was {budget})")
            print(f"  remaining budget this guard: {guard.remaining}")

            # Verify api_call_log persisted
            from sqlalchemy import func, select
            from app.models.api_call_log import ApiCallLog
            result = await session.execute(
                select(ApiCallLog.endpoint, func.count(ApiCallLog.id))
                .group_by(ApiCallLog.endpoint)
            )
            print("  api_call_log breakdown:")
            for endpoint, count in result:
                print(f"    {endpoint}: {count}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, default=50, help="Max API calls")
    parser.add_argument("--polygon", type=str, default="east_metro", help="Polygon name")
    parser.add_argument("--no-lease", action="store_true", help="Skip lease phase")
    args = parser.parse_args()

    if not os.environ.get("RAPIDAPI_KEY"):
        # Fallback: let Settings load from .env
        pass
    code = asyncio.run(main(args.budget, args.polygon, not args.no_lease))
    sys.exit(code)
