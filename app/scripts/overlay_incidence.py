"""Overlay incidence matrix for target ("green"/prime) opportunities.

For every non-archived Multnomah County opportunity in the selected priority
bucket(s), intersects its lat/lng against the jurisdiction's zoning + overlay
GIS layers (ArcGIS REST, server-side point-in-polygon) and reports the
distinct `jurisdiction x base_zone x overlay-set` combinations, ranked by
parcel count and asking-price exposure.

The combo list is the codification worklist: each row is one "adjudication
unit" whose development standards need to be formalized exactly once.

Endpoints come from docs/ops/data-sources-inventory.md. Layers on the Gresham
and Troutdale MapServers are auto-discovered by name pattern; Fairview and
Wood Village layers are pinned statically. Fairview has no GIS zoning (PDF
only) so its base zone falls back to the opportunity's scraped `zoning` text.

Run (needs LAN access to the DB and open egress to the GIS hosts — i.e. from
VM 114 or a dev machine on the LAN, NOT from a restricted cloud sandbox):

    uv run python -m app.scripts.overlay_incidence --buckets prime
    uv run python -m app.scripts.overlay_incidence --buckets prime,target --limit 25

Outputs (to --out-dir, default ./data/overlay_incidence/):
    parcels.csv  — one row per opportunity with base zone + overlay hits
    combos.csv   — aggregated combos, ranked
and prints the ranked combo table to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import httpx

# ---------------------------------------------------------------------------
# Layer registry (sources: docs/ops/data-sources-inventory.md)
# ---------------------------------------------------------------------------

GRESHAM_PLANNING = "https://gis.greshamoregon.gov/arcgis/rest/services/Planning/MapServer"
GRESHAM_BASE_DATA = "https://gis.greshamoregon.gov/arcgis/rest/services/Base_Data/MapServer"
TROUTDALE_CITY_GIS = "https://maps.troutdaleoregon.gov/server/rest/services/Public_Web/City_GIS/MapServer"
FAIRVIEW_ORG = "https://services5.arcgis.com/3DoY8p7EnUTzaIE7/arcgis/rest/services"
WOOD_VILLAGE_ORG = "https://services7.arcgis.com/5Loh3xXKWLd2M7xA/arcgis/rest/services"
PORTLAND_BDS = "https://www.portlandmaps.com/arcgis/rest/services/Public/BDS_Property/FeatureServer/0"


@dataclass(frozen=True)
class LayerRef:
    """One queryable ArcGIS layer and how to read a value out of it."""

    name: str                      # short label used in combo keys, e.g. "fv:overlay"
    url: str                       # full layer URL (ends in /<layer_id>)
    role: str                      # "base_zone" | "overlay"
    value_fields: tuple[str, ...] = ()  # preferred attribute names, first non-empty wins


# Field-name candidates for zoning-ish attributes, used when the exact field
# name isn't documented. Checked case-insensitively, in order.
ZONE_FIELD_CANDIDATES = (
    "ZONE", "ZONING", "ZONE_CODE", "ZONECODE", "ZONECLASS", "ZONE_DESC",
    "Labeling", "LABEL", "DISTRICT", "TYPE", "NAME", "OVERLAY",
)

# MapServer layers whose name matches this are treated as overlay layers
# during discovery. Deliberately broad — false positives just add columns
# that turn out empty for every parcel and are easy to prune via
# --layers-config on later runs.
OVERLAY_NAME_RE = re.compile(
    r"overlay|plan\s?district|design|historic|corridor|flood|slope|greenway"
    r"|buffer|riparian|wetland|natural\s?resource|transit|center|downtown"
    r"|frontage|airport",
    re.IGNORECASE,
)

# Layer names that are clearly not regulatory overlays even if the regex hits.
OVERLAY_NAME_EXCLUDE_RE = re.compile(
    r"annotation|label|grid|index|basemap|aerial|contour|address",
    re.IGNORECASE,
)

STATIC_LAYERS: dict[str, list[LayerRef]] = {
    "gresham": [
        LayerRef("gresham:zoning", f"{GRESHAM_PLANNING}/4", "base_zone"),
        # overlays discovered from GRESHAM_PLANNING at runtime
    ],
    "troutdale": [
        LayerRef("troutdale:zoning", f"{TROUTDALE_CITY_GIS}/69", "base_zone", ("ZONE",)),
        # overlays discovered from TROUTDALE_CITY_GIS at runtime
    ],
    "fairview": [
        # No GIS zoning (PDF only) — base zone comes from opportunity.zoning.
        LayerRef("fv:overlay", f"{FAIRVIEW_ORG}/Overlay_Districts20230406/FeatureServer/0", "overlay"),
        LayerRef("fv:nat_resource", f"{FAIRVIEW_ORG}/Natural_Resource_Layer/FeatureServer/0", "overlay", ("TYPE",)),
        LayerRef("fv:lake_35ft", f"{FAIRVIEW_ORG}/Fairview_Lake_35ft/FeatureServer/0", "overlay"),
        LayerRef("fv:lake_50ft", f"{FAIRVIEW_ORG}/Fairview_Lake_50ft/FeatureServer/0", "overlay"),
        LayerRef("fv:enterprise_zone", f"{FAIRVIEW_ORG}/Enterprise_Zones_201806_FVR/FeatureServer/6", "overlay"),
    ],
    "wood village": [
        LayerRef("wv:zoning", f"{WOOD_VILLAGE_ORG}/Zoning/FeatureServer/9", "base_zone", ("Labeling",)),
        # No overlay layers documented for Wood Village yet.
    ],
    "portland": [
        LayerRef("pdx:zoning", PORTLAND_BDS, "base_zone", ("ZONE",)),
    ],
    # Unincorporated Multnomah / east county fallback zoning
    "multnomah county": [
        LayerRef("eastco:zoning", f"{GRESHAM_BASE_DATA}/9", "base_zone", ("ZONE",)),
    ],
}

# Services to scan for overlay layers, per jurisdiction.
DISCOVERY_SERVICES: dict[str, list[tuple[str, str]]] = {
    # (label prefix, service root)
    "gresham": [("gresham", GRESHAM_PLANNING)],
    "troutdale": [("troutdale", TROUTDALE_CITY_GIS)],
}

MULTNOMAH_JURISDICTIONS = {
    "gresham", "troutdale", "fairview", "wood village", "maywood park",
    "portland", "multnomah county",
}


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested, no I/O)
# ---------------------------------------------------------------------------


def is_overlay_candidate(layer_name: str) -> bool:
    """Should a discovered MapServer layer be queried as an overlay?"""
    if OVERLAY_NAME_EXCLUDE_RE.search(layer_name):
        return False
    return bool(OVERLAY_NAME_RE.search(layer_name))


def pick_value(attrs: dict[str, Any], preferred: Iterable[str] = ()) -> str | None:
    """First non-empty attribute value, trying preferred names then the
    generic zoning-ish candidates (case-insensitive)."""
    lowered = {k.lower(): v for k, v in attrs.items()}
    for name in (*preferred, *ZONE_FIELD_CANDIDATES):
        val = lowered.get(name.lower())
        if val not in (None, "", " "):
            return str(val).strip()
    return None


def normalize_jurisdiction(value: str | None) -> str:
    s = (value or "").strip().lower()
    if s in ("city of portland",):
        return "portland"
    if s in ("unincorporated", "unincorporated multnomah", "multnomah", "multnomah county"):
        return "multnomah county"
    return s


@dataclass
class ParcelResult:
    opportunity_id: str
    name: str
    jurisdiction: str
    base_zone: str | None
    base_zone_source: str            # layer name or "opportunity.zoning" or "missing"
    overlays: dict[str, str]         # layer name -> intersecting value
    asking_price: Decimal | None
    lot_sqft: Decimal | None
    errors: list[str] = field(default_factory=list)

    @property
    def combo_key(self) -> tuple[str, str, tuple[str, ...]]:
        overlay_ids = tuple(sorted(f"{k}={v}" for k, v in self.overlays.items()))
        return (self.jurisdiction, self.base_zone or "?", overlay_ids)


def summarize(results: list[ParcelResult]) -> list[dict[str, Any]]:
    """Aggregate parcel results into ranked combo rows."""
    groups: dict[tuple, list[ParcelResult]] = defaultdict(list)
    for r in results:
        groups[r.combo_key].append(r)

    rows = []
    for (jurisdiction, base_zone, overlays), members in groups.items():
        prices = [m.asking_price for m in members if m.asking_price]
        rows.append({
            "jurisdiction": jurisdiction,
            "base_zone": base_zone,
            "overlays": "; ".join(overlays) if overlays else "(none)",
            "parcel_count": len(members),
            "total_asking_price": str(sum(prices)) if prices else "",
            "example_parcels": ", ".join(m.name for m in members[:3]),
        })
    rows.sort(key=lambda r: (-r["parcel_count"], r["jurisdiction"], r["base_zone"]))
    return rows


# ---------------------------------------------------------------------------
# ArcGIS REST I/O
# ---------------------------------------------------------------------------


async def discover_overlay_layers(
    client: httpx.AsyncClient, prefix: str, service_root: str
) -> list[LayerRef]:
    """List a MapServer's layers and keep the overlay-looking ones."""
    resp = await client.get(service_root, params={"f": "json"})
    resp.raise_for_status()
    doc = resp.json()
    refs = []
    for layer in doc.get("layers", []):
        lname = layer.get("name", "")
        lid = layer.get("id")
        if lid is None or not is_overlay_candidate(lname):
            continue
        slug = re.sub(r"[^a-z0-9]+", "_", lname.lower()).strip("_")
        refs.append(LayerRef(f"{prefix}:{slug}", f"{service_root}/{lid}", "overlay"))
    return refs


async def query_point(
    client: httpx.AsyncClient,
    layer: LayerRef,
    lat: float,
    lng: float,
    cache: dict,
    sem: asyncio.Semaphore,
) -> str | None:
    """Server-side point-in-polygon intersect. Returns the layer's value at
    the point, or None if no feature intersects. Raises on transport errors."""
    key = (layer.url, round(lat, 6), round(lng, 6))
    if key in cache:
        return cache[key]
    params = {
        "f": "json",
        "geometry": json.dumps({"x": lng, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": "5",
    }
    async with sem:
        resp = await client.get(f"{layer.url}/query", params=params)
    resp.raise_for_status()
    doc = resp.json()
    if "error" in doc:
        raise RuntimeError(f"{layer.name}: {doc['error'].get('message', 'query error')}")
    features = doc.get("features", [])
    value = None
    if features:
        value = pick_value(features[0].get("attributes", {}), layer.value_fields) or "yes"
    cache[key] = value
    return value


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> int:
    # Imported here so the pure helpers stay importable without app config.
    from sqlalchemy import select

    from app.db import AsyncSessionLocal
    from app.models.opportunity import Opportunity

    buckets = [b.strip() for b in args.buckets.split(",") if b.strip()]

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Opportunity)
            .where(
                Opportunity.archived.is_(False),
                Opportunity.priority_bucket.in_(buckets),
            )
        )
        opps = list((await session.execute(stmt)).scalars())

    # County filter in Python — county strings vary ("Multnomah", "Multnomah County").
    def in_multnomah(o) -> bool:
        county = (o.county or "").strip().lower().removesuffix(" county")
        if county:
            return county == "multnomah"
        return normalize_jurisdiction(o.jurisdiction or o.city) in MULTNOMAH_JURISDICTIONS

    opps = [o for o in opps if in_multnomah(o)]
    if args.limit:
        opps = opps[: args.limit]

    located = [o for o in opps if o.lat is not None and o.lng is not None]
    unlocated = [o for o in opps if o.lat is None or o.lng is None]

    print(f"Opportunities in bucket(s) {buckets}, Multnomah: {len(opps)} "
          f"({len(located)} with lat/lng, {len(unlocated)} unlocated)")

    # Build per-jurisdiction layer sets
    layers_by_juris: dict[str, list[LayerRef]] = {
        j: list(refs) for j, refs in STATIC_LAYERS.items()
    }
    failed_layers: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for juris, services in DISCOVERY_SERVICES.items():
            for prefix, root in services:
                try:
                    discovered = await discover_overlay_layers(client, prefix, root)
                    layers_by_juris.setdefault(juris, []).extend(discovered)
                    print(f"  discovered {len(discovered)} overlay layers on {root}")
                except Exception as exc:  # noqa: BLE001 — report and continue
                    failed_layers[root] = str(exc)

        cache: dict = {}
        sem = asyncio.Semaphore(args.concurrency)
        results: list[ParcelResult] = []

        for o in located:
            juris = normalize_jurisdiction(o.jurisdiction or o.city)
            refs = layers_by_juris.get(juris, [])
            lat, lng = float(o.lat), float(o.lng)
            base_zone, base_src = None, "missing"
            overlays: dict[str, str] = {}
            errors: list[str] = []

            for layer in refs:
                try:
                    value = await query_point(client, layer, lat, lng, cache, sem)
                except Exception as exc:  # noqa: BLE001 — one layer failing shouldn't kill the run
                    errors.append(f"{layer.name}: {exc}")
                    failed_layers[layer.url] = str(exc)
                    continue
                if layer.role == "base_zone" and value and base_zone is None:
                    base_zone, base_src = value, layer.name
                elif layer.role == "overlay" and value:
                    overlays[layer.name] = value

            if base_zone is None and o.zoning:
                base_zone, base_src = o.zoning.strip()[:40], "opportunity.zoning"

            results.append(ParcelResult(
                opportunity_id=str(o.id),
                name=o.name or o.listing_name or o.address_raw or str(o.id),
                jurisdiction=juris,
                base_zone=base_zone,
                base_zone_source=base_src,
                overlays=overlays,
                asking_price=o.asking_price,
                lot_sqft=o.lot_sqft,
                errors=errors,
            ))
            print(f"  [{len(results)}/{len(located)}] {results[-1].name[:50]!r} "
                  f"{juris} zone={base_zone} overlays={len(overlays)}")

    # ── Outputs ───────────────────────────────────────────────────────────
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with (out_dir / "parcels.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["opportunity_id", "name", "jurisdiction", "base_zone",
                    "base_zone_source", "overlays", "asking_price", "lot_sqft", "errors"])
        for r in results:
            w.writerow([r.opportunity_id, r.name, r.jurisdiction, r.base_zone or "",
                        r.base_zone_source,
                        "; ".join(f"{k}={v}" for k, v in sorted(r.overlays.items())),
                        r.asking_price or "", r.lot_sqft or "", "; ".join(r.errors)])

    combos = summarize(results)
    with (out_dir / "combos.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(combos[0].keys()) if combos else
                           ["jurisdiction", "base_zone", "overlays", "parcel_count",
                            "total_asking_price", "example_parcels"])
        w.writeheader()
        w.writerows(combos)

    print(f"\n=== Overlay incidence: {len(combos)} distinct combos "
          f"across {len(results)} parcels ===\n")
    for row in combos:
        print(f"  {row['parcel_count']:>3}x  {row['jurisdiction']:<18} "
              f"{row['base_zone']:<12} {row['overlays']}")

    if unlocated:
        print(f"\nWARNING: {len(unlocated)} opportunities skipped (no lat/lng): "
              + ", ".join((o.name or str(o.id))[:40] for o in unlocated[:10]))
    if failed_layers:
        print("\nWARNING: layer failures (blind spots in the matrix):")
        for url, err in failed_layers.items():
            print(f"  {url}\n    {err[:150]}")
    print(f"\nWrote {out_dir / 'parcels.csv'} and {out_dir / 'combos.csv'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--buckets", default="prime",
                        help="Comma-separated priority buckets (default: prime)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap the number of opportunities processed")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="Max concurrent GIS requests")
    parser.add_argument("--out-dir", default="data/overlay_incidence",
                        help="Output directory for CSVs")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
