"""CLI entrypoint for HelloData batch enrichment.

Usage (inside the api container):
  # Dry run — show what would be enriched, no API calls
  docker exec vicinitideals-api python -m app.scripts.enrich_hellodata --dry-run

  # Enrich specific listing IDs
  docker exec vicinitideals-api python -m app.scripts.enrich_hellodata \
      --listing-ids id1,id2,id3

  # Enrich all non-Portland, non-enriched listings (capped at $50 for this run)
  docker exec vicinitideals-api python -m app.scripts.enrich_hellodata --max-dollars 50

  # Also fetch comparables for each listing (adds one call per property)
  docker exec vicinitideals-api python -m app.scripts.enrich_hellodata \
      --max-dollars 20 --include-comparables
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.config import settings
from app.db import AsyncSessionLocal
from app.scrapers.hellodata import enrich_batch


async def _run(args: argparse.Namespace) -> int:
    listing_ids: list[str] | None = None
    if args.listing_ids:
        listing_ids = [s.strip() for s in args.listing_ids.split(",") if s.strip()]

    max_calls: int | None = None
    if args.max_dollars is not None:
        cost_per = settings.hellodata_cost_per_call_cents
        max_calls = (args.max_dollars * 100) // cost_per
        print(f"Budget cap: ${args.max_dollars} → {max_calls} calls at ${cost_per / 100:.2f}/call")

    async with AsyncSessionLocal() as session:
        result = await enrich_batch(
            session,
            listing_ids=listing_ids,
            fetch_comparables=args.include_comparables,
            dry_run=args.dry_run,
            max_calls=max_calls,
        )
        await session.commit()

    print(json.dumps({
        "total_listings": result.total_listings,
        "enriched": result.enriched,
        "skipped_portland": result.skipped_portland,
        "skipped_flagged": result.skipped_flagged,
        "already_enriched": result.already_enriched,
        "no_match": result.no_match,
        "errors": result.errors,
        "total_cost_cents": result.total_cost_cents,
        "total_cost_dollars": round(result.total_cost_cents / 100, 2),
        "budget_locked_at": result.budget_locked_at,
    }, indent=2))

    if args.verbose:
        print()
        print("Per-listing results:")
        for r in result.results:
            print(f"  {r.listing_id}  {r.reason:20s}  calls={r.calls_made}  cost={r.cost_cents}c")
            if r.error:
                print(f"    error: {r.error}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="HelloData batch enrichment")
    parser.add_argument("--listing-ids", type=str, default=None,
                        help="Comma-separated listing UUIDs to enrich (default: all eligible)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be enriched without calling the API")
    parser.add_argument("--include-comparables", action="store_true",
                        help="Also fetch /property/comparables (one extra call per listing)")
    parser.add_argument("--max-dollars", type=int, default=None,
                        help="Cap total spend for this run, in whole dollars")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print per-listing results")
    args = parser.parse_args()

    if not args.dry_run and not settings.hellodata_api_key:
        print("ERROR: hellodata_api_key is not set in environment", file=sys.stderr)
        return 1

    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
