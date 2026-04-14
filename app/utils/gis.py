"""Shared GIS utilities — geometry helpers, overlay registry, cached + live ArcGIS fetch.

Adding a new overlay source requires only one new entry in OVERLAY_REGISTRY.
  fetch_type="geojson_file" → reads from data/gis_cache/<group>/<slug>.geojson (instant, no network)
  fetch_type="arcgis_rest"  → live ArcGIS envelope query (for layers not yet cached)

No other code needs to change when adding layers.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx

try:
    from shapely.geometry import shape
    from shapely.ops import unary_union
    _SHAPELY = True
except ImportError:
    _SHAPELY = False


# ---------------------------------------------------------------------------
# Cache root
# ---------------------------------------------------------------------------

# Resolves to re-modeling/data/gis_cache/
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
GIS_CACHE_ROOT = _PACKAGE_ROOT / "data" / "gis_cache"


# ---------------------------------------------------------------------------
# Overlay registry
# ---------------------------------------------------------------------------

# Bounding box used for reference layers (UGB, city limits, OZs, etc.)
# Covers all of Multnomah + Clackamas + generous buffer — avoids sending all-Oregon data
# while ensuring Metro context layers are always returned regardless of parcel position.
# (xmin, ymin, xmax, ymax) in WGS84
METRO_REFERENCE_BBOX: tuple[float, float, float, float] = (-123.3, 45.1, -122.1, 45.8)

GRESHAM_PLANNING = "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer"
GRESHAM_ENV      = "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer"


@dataclass
class OverlayLayerDef:
    key: str
    label: str
    color: str
    # "geojson_file": read from GIS_CACHE_ROOT/<cache_group>/<key>.geojson
    # "arcgis_rest":  live ArcGIS envelope query against fetch_url
    fetch_type: Literal["geojson_file", "arcgis_rest"]
    fetch_url: str = ""          # path suffix for geojson_file OR full URL for arcgis_rest
    fetch_params: dict = field(default_factory=dict)
    # None = all jurisdictions; ["gresham"] = only when gresham detected; ["oregon"] = any OR parcel
    jurisdictions: list[str] | None = None
    default_on: bool = True
    group: str = "overlays"
    cache_group: str = ""        # subdirectory under GIS_CACHE_ROOT (auto-set from jurisdictions if empty)
    reference: bool = False      # if True, load full layer regardless of parcel envelope (UGB, OZs, city limits)


def _cache_path(layer_def: OverlayLayerDef) -> Path:
    """Resolve the local GeoJSON file path for a geojson_file layer."""
    group = layer_def.cache_group or (
        (layer_def.jurisdictions or ["external"])[0]
        if layer_def.jurisdictions else "external"
    )
    filename = layer_def.fetch_url or f"{layer_def.key}.geojson"
    return GIS_CACHE_ROOT / group / filename


OVERLAY_REGISTRY: dict[str, OverlayLayerDef] = {

    # ════════════════════════════════════════════════════════════════════
    # GRESHAM LOCAL — Environmental (cached)
    # ════════════════════════════════════════════════════════════════════
    "gresham_open_space": OverlayLayerDef(
        key="gresham_open_space",
        label="Open Space Overlay",
        color="#16a34a",
        fetch_type="geojson_file",
        fetch_url="open_space_planning_overlay.geojson",
        jurisdictions=["gresham"],
        default_on=True,
        group="environment",
        cache_group="gresham",
    ),
    "gresham_historic": OverlayLayerDef(
        key="gresham_historic",
        label="Historic & Cultural Overlay",
        color="#ea580c",
        fetch_type="geojson_file",
        fetch_url="historic_cultural_overlay.geojson",
        jurisdictions=["gresham"],
        default_on=True,
        group="design",
        cache_group="gresham",
    ),
    "gresham_natural_resource": OverlayLayerDef(
        key="gresham_natural_resource",
        label="Natural Resource Overlay",
        color="#0f766e",
        fetch_type="geojson_file",
        fetch_url="natural_resource_overlay.geojson",
        jurisdictions=["gresham"],
        default_on=True,
        group="environment",
        cache_group="gresham",
    ),
    "gresham_title3_wetlands": OverlayLayerDef(
        key="gresham_title3_wetlands",
        label="Title 3 Wetlands",
        color="#0369a1",
        fetch_type="geojson_file",
        fetch_url="title3_wetlands.geojson",
        jurisdictions=["gresham"],
        default_on=True,
        group="environment",
        cache_group="gresham",
    ),
    "gresham_streams": OverlayLayerDef(
        key="gresham_streams",
        label="Streams",
        color="#38bdf8",
        fetch_type="geojson_file",
        fetch_url="streams.geojson",
        jurisdictions=["gresham"],
        default_on=True,
        group="environment",
        cache_group="gresham",
    ),
    "gresham_hillside": OverlayLayerDef(
        key="gresham_hillside",
        label="Gresham Butte Overlay",
        color="#dc2626",
        fetch_type="geojson_file",
        fetch_url="gresham_butte_overlay.geojson",
        jurisdictions=["gresham"],
        default_on=False,
        group="safety",
        cache_group="gresham",
    ),
    "gresham_high_value_resource": OverlayLayerDef(
        key="gresham_high_value_resource",
        label="High Value Resource Area",
        color="#065f46",
        fetch_type="geojson_file",
        fetch_url="high_value_resource_area_overlay.geojson",
        jurisdictions=["gresham"],
        default_on=False,
        group="environment",
        cache_group="gresham",
    ),
    "gresham_downstream_conditions": OverlayLayerDef(
        key="gresham_downstream_conditions",
        label="Downstream Conditions",
        color="#0284c7",
        fetch_type="geojson_file",
        fetch_url="downstream_conditions.geojson",
        jurisdictions=["gresham"],
        default_on=False,
        group="environment",
        cache_group="gresham",
    ),

    # ════════════════════════════════════════════════════════════════════
    # GRESHAM LOCAL — Planning (cached)
    # ════════════════════════════════════════════════════════════════════
    "gresham_design_districts": OverlayLayerDef(
        key="gresham_design_districts",
        label="Design Districts",
        color="#9333ea",
        fetch_type="geojson_file",
        fetch_url="design_districts.geojson",
        jurisdictions=["gresham"],
        default_on=True,
        group="design",
        cache_group="gresham",
    ),
    "gresham_rockwood": OverlayLayerDef(
        key="gresham_rockwood",
        label="Rockwood Plan District",
        color="#a855f7",
        fetch_type="geojson_file",
        fetch_url="rockwood_plan_district.geojson",
        jurisdictions=["gresham"],
        default_on=False,
        group="zoning",
        cache_group="gresham",
    ),

    # ════════════════════════════════════════════════════════════════════
    # GRESHAM LOCAL — Incentive Zones (cached)
    # ════════════════════════════════════════════════════════════════════
    "gresham_enterprise_zone": OverlayLayerDef(
        key="gresham_enterprise_zone",
        label="Enterprise Zone",
        color="#b45309",
        fetch_type="geojson_file",
        fetch_url="enterprise_zone.geojson",
        jurisdictions=["gresham"],
        default_on=True,
        group="incentives",
        cache_group="gresham",
    ),
    "gresham_urban_renewal": OverlayLayerDef(
        key="gresham_urban_renewal",
        label="Rockwood Urban Renewal Area",
        color="#c2410c",
        fetch_type="geojson_file",
        fetch_url="rockwood_urban_renewal_area.geojson",
        jurisdictions=["gresham"],
        default_on=True,
        group="incentives",
        cache_group="gresham",
    ),
    "gresham_vertical_housing": OverlayLayerDef(
        key="gresham_vertical_housing",
        label="Vertical Housing Dev Zone",
        color="#d97706",
        fetch_type="geojson_file",
        fetch_url="vertical_housing_development_zone.geojson",
        jurisdictions=["gresham"],
        default_on=False,
        group="incentives",
        cache_group="gresham",
    ),
    "gresham_strategic_investment": OverlayLayerDef(
        key="gresham_strategic_investment",
        label="Strategic Investment Zone",
        color="#92400e",
        fetch_type="geojson_file",
        fetch_url="strategic_investment_zone.geojson",
        jurisdictions=["gresham"],
        default_on=False,
        group="incentives",
        cache_group="gresham",
    ),

    # ════════════════════════════════════════════════════════════════════
    # GRESHAM LOCAL — Live ArcGIS (not yet cached)
    # ════════════════════════════════════════════════════════════════════
    "gresham_zoning": OverlayLayerDef(
        key="gresham_zoning",
        label="City Zoning",
        color="#7c3aed",
        fetch_type="arcgis_rest",
        fetch_url=f"{GRESHAM_PLANNING}/4/query",
        jurisdictions=["gresham"],
        default_on=True,
        group="zoning",
    ),
    "gresham_flood_plain": OverlayLayerDef(
        key="gresham_flood_plain",
        label="Flood Plain",
        color="#1d4ed8",
        fetch_type="arcgis_rest",
        fetch_url=f"{GRESHAM_ENV}/2/query",
        jurisdictions=["gresham"],
        default_on=True,
        group="safety",
    ),

    # ════════════════════════════════════════════════════════════════════
    # OREGON STATEWIDE — cached
    # ════════════════════════════════════════════════════════════════════
    "or_urban_growth_boundary": OverlayLayerDef(
        key="or_urban_growth_boundary",
        label="Urban Growth Boundary (OR)",
        color="#f59e0b",
        fetch_type="geojson_file",
        fetch_url="urban_growth_boundaries_or.geojson",
        jurisdictions=["oregon"],
        default_on=True,
        group="planning",
        cache_group="oregon",
        reference=True,
    ),
    "or_city_limits": OverlayLayerDef(
        key="or_city_limits",
        label="City Limits (OR)",
        color="#6b7280",
        fetch_type="geojson_file",
        fetch_url="city_limits_or.geojson",
        jurisdictions=["oregon"],
        default_on=False,
        group="planning",
        cache_group="oregon",
        reference=True,
    ),
    "or_enterprise_zones": OverlayLayerDef(
        key="or_enterprise_zones",
        label="Enterprise Zones (OR)",
        color="#b45309",
        fetch_type="geojson_file",
        fetch_url="enterprise_zones_or.geojson",
        jurisdictions=["oregon"],
        default_on=True,
        group="incentives",
        cache_group="oregon",
        reference=True,
    ),

    # ════════════════════════════════════════════════════════════════════
    # EXTERNAL / NATIONAL — cached
    # ════════════════════════════════════════════════════════════════════
    "opportunity_zones": OverlayLayerDef(
        key="opportunity_zones",
        label="Opportunity Zones",
        color="#7c3aed",
        fetch_type="geojson_file",
        fetch_url="opportunity_zones_or.geojson",
        jurisdictions=["oregon"],
        default_on=True,
        group="incentives",
        cache_group="external",
        reference=True,
    ),
    "nmtc_qualified_tracts": OverlayLayerDef(
        key="nmtc_qualified_tracts",
        label="NMTC Qualified Tracts",
        color="#db2777",
        fetch_type="geojson_file",
        fetch_url="nmtc_qualified_tracts_or.geojson",
        jurisdictions=["oregon"],
        default_on=True,
        group="incentives",
        cache_group="external",
        reference=True,
    ),
}


# ---------------------------------------------------------------------------
# Jurisdiction detection
# ---------------------------------------------------------------------------

def detect_jurisdiction(address: str | None, owner_city: str | None = None) -> str | None:
    """
    Return jurisdiction slug from address/city text.
    "oregon" is returned for any recognized Oregon address so statewide layers always load.
    Local slug (gresham, portland, etc.) returned when city is specifically recognized.
    """
    for text in (address or "", owner_city or ""):
        upper = text.upper()
        if "GRESHAM" in upper:
            return "gresham"
        if "PORTLAND" in upper:
            return "portland"
        if "OREGON CITY" in upper:
            return "oregoncity"
        if "CLACKAMAS" in upper:
            return "clackamas"
        if "LAKE OSWEGO" in upper:
            return "lakeoswego"
        if "BEAVERTON" in upper:
            return "beaverton"
        # Catch-all: any OR address gets statewide layers
        if " OR " in upper or upper.endswith(" OR") or " OR," in upper or "OREGON" in upper:
            return "oregon"
    return None


def layers_for_jurisdiction(jurisdiction: str | None) -> list[OverlayLayerDef]:
    """
    Return all overlay defs applicable for the given jurisdiction.
    Local jurisdictions also receive "oregon" layers (statewide always applies to local).
    """
    LOCAL_TO_OREGON = {"gresham", "portland", "oregoncity", "clackamas", "lakeoswego", "beaverton"}
    # Default to oregon when jurisdiction is unknown — all parcels in this app are in Oregon Metro
    effective = {jurisdiction} if jurisdiction else {"oregon"}
    if jurisdiction in LOCAL_TO_OREGON:
        effective.add("oregon")

    result = []
    for layer_def in OVERLAY_REGISTRY.values():
        if layer_def.jurisdictions is None:
            result.append(layer_def)
        elif effective and any(j in effective for j in layer_def.jurisdictions):
            result.append(layer_def)
    return result


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def esri_to_geojson(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert ESRI rings/paths/point geometry to GeoJSON geometry object.

    Also passes through native GeoJSON (already has 'type' + 'coordinates').
    """
    if not isinstance(geometry, dict):
        return None
    # Already GeoJSON — pass through
    if geometry.get("type") and "coordinates" in geometry:
        return geometry
    # ESRI rings → Polygon
    if geometry.get("rings"):
        return {"type": "Polygon", "coordinates": geometry["rings"]}
    if geometry.get("paths"):
        return {"type": "MultiLineString", "coordinates": geometry["paths"]}
    if {"x", "y"}.issubset(geometry.keys()):
        return {"type": "Point", "coordinates": [geometry["x"], geometry["y"]]}
    return None


def _iter_coords(value: Any):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for item in value:
                yield from _iter_coords(item)


def is_wgs84(geometry: dict[str, Any]) -> bool:
    """Return True if geometry coordinates appear to be WGS84 (lon/lat in ±180/±90)."""
    # Native GeoJSON
    if geometry.get("type") and "coordinates" in geometry:
        coords = list(_iter_coords(geometry["coordinates"]))
    else:
        coords = list(_iter_coords(
            geometry.get("rings") or geometry.get("paths") or
            ([geometry["x"], geometry["y"]] if {"x", "y"}.issubset(geometry.keys()) else [])
        ))
    if not coords:
        return False
    return all(-180 <= x <= 180 and -90 <= y <= 90 for x, y in coords)


def geometry_envelope(geometry: dict[str, Any], pad_ratio: float = 0.35, min_pad: float = 0.0015) -> tuple[float, float, float, float]:
    """Return (xmin, ymin, xmax, ymax) padded bounding box for a single geometry."""
    coords = list(_iter_coords(
        geometry.get("coordinates") or
        geometry.get("rings") or geometry.get("paths") or []
    ))
    if not coords and {"x", "y"}.issubset(geometry.keys()):
        coords = [(float(geometry["x"]), float(geometry["y"]))]
    if not coords:
        return (0, 0, 0, 0)
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    dx = max(xmax - xmin, min_pad)
    dy = max(ymax - ymin, min_pad)
    padx = max(dx * pad_ratio, min_pad)
    pady = max(dy * pad_ratio, min_pad)
    return (xmin - padx, ymin - pady, xmax + padx, ymax + pady)


def combined_envelope(geometries: list[dict[str, Any]], pad_ratio: float = 0.35, min_pad: float = 0.0015) -> tuple[float, float, float, float]:
    """Compute padded bounding box enclosing all geometries."""
    all_coords: list[tuple[float, float]] = []
    for g in geometries:
        coords = list(_iter_coords(
            g.get("coordinates") or g.get("rings") or g.get("paths") or []
        ))
        if not coords and {"x", "y"}.issubset(g.keys()):
            coords = [(float(g["x"]), float(g["y"]))]
        all_coords.extend(coords)
    if not all_coords:
        return (0, 0, 0, 0)
    xs = [c[0] for c in all_coords]
    ys = [c[1] for c in all_coords]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    dx = max(xmax - xmin, min_pad)
    dy = max(ymax - ymin, min_pad)
    padx = max(dx * pad_ratio, min_pad)
    pady = max(dy * pad_ratio, min_pad)
    return (xmin - padx, ymin - pady, xmax + padx, ymax + pady)


def envelope_str(bbox: tuple[float, float, float, float]) -> str:
    """Format bbox tuple as ArcGIS geometry envelope string."""
    return f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"


def bbox_to_leaflet(bbox: tuple[float, float, float, float]) -> list[list[float]]:
    """Convert (xmin,ymin,xmax,ymax) to Leaflet [[lat,lng],[lat,lng]] format."""
    xmin, ymin, xmax, ymax = bbox
    return [[ymin, xmin], [ymax, xmax]]


# ---------------------------------------------------------------------------
# Overlap assessment (optional Shapely)
# ---------------------------------------------------------------------------

def compute_overlap_assessment(
    parcel_geometry: dict[str, Any],
    overlay_features: list[dict[str, Any]],
    *,
    threshold_pct: float = 1.0,
    parcel_sqft: float | None = None,
) -> dict[str, Any] | None:
    """
    Compute overlap between parcel and overlay features.
    Returns {status, overlap_pct, overlap_sqft_est} or None if Shapely unavailable.

    status:
      "definitely_yes"  — overlap >= threshold_pct (default 1%)
      "maybe"           — overlap > 0% but < threshold_pct
      "definitely_no"   — no overlap
    """
    if not _SHAPELY:
        return None
    geojson = esri_to_geojson(parcel_geometry)
    if not geojson:
        return None
    try:
        parcel_shape = shape(geojson)
        parcel_area = float(parcel_shape.area or 0)
        if parcel_area <= 0:
            return None

        overlay_shapes = []
        for feat in overlay_features:
            geom = feat.get("geometry")
            if geom:
                try:
                    overlay_shapes.append(shape(geom))
                except Exception:
                    pass

        if not overlay_shapes:
            return {"status": "definitely_no", "overlap_pct": 0.0, "overlap_sqft_est": None}

        merged = unary_union(overlay_shapes)
        overlap_area = float(parcel_shape.intersection(merged).area or 0)
        overlap_pct = round((overlap_area / parcel_area) * 100, 4)
        overlap_sqft_est = round(float(parcel_sqft) * overlap_pct / 100, 2) if parcel_sqft else None

        if overlap_pct >= threshold_pct:
            status = "definitely_yes"
        elif overlap_pct > 0:
            status = "maybe"
        else:
            status = "definitely_no"

        return {"status": status, "overlap_pct": overlap_pct, "overlap_sqft_est": overlap_sqft_est}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cached GeoJSON fetch (bbox filter)
# ---------------------------------------------------------------------------

def _bbox_intersects(feature: dict[str, Any], xmin: float, ymin: float, xmax: float, ymax: float) -> bool:
    """Quick bbox check — returns True if any coordinate of the feature falls within the envelope."""
    geom = feature.get("geometry") or {}
    coords = list(_iter_coords(
        geom.get("coordinates") or
        geom.get("rings") or
        geom.get("paths") or []
    ))
    if not coords:
        return False
    for x, y in coords:
        if xmin <= x <= xmax and ymin <= y <= ymax:
            return True
    return False


def _load_cached_layer(layer_def: OverlayLayerDef, envelope: str) -> list[dict[str, Any]]:
    """
    Load a geojson_file layer from disk, filtering to features that intersect the envelope.
    Reference layers use a 0.1° expanded envelope so nearby context (UGB boundary, OZ edges)
    is always visible even when the parcel is well inside or outside the boundary.
    Returns [] if file not found or on error.
    """
    path = _cache_path(layer_def)
    if not path.exists():
        return []
    try:
        if layer_def.reference:
            # Use fixed Metro bbox so large-polygon reference layers (UGB, OZs) are always
            # returned even when the parcel sits entirely inside them (no vertices in parcel bbox).
            xmin, ymin, xmax, ymax = METRO_REFERENCE_BBOX
        else:
            parts = envelope.split(",")
            xmin, ymin, xmax, ymax = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
        fc = json.loads(path.read_bytes())
        features = fc.get("features") or []
        return [f for f in features if _bbox_intersects(f, xmin, ymin, xmax, ymax)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# ArcGIS REST fetch (live, for layers not yet cached)
# ---------------------------------------------------------------------------

async def _arcgis_envelope_query(
    client: httpx.AsyncClient,
    url: str,
    envelope: str,
    extra_params: dict | None = None,
) -> list[dict[str, Any]]:
    """Spatial query for features intersecting an envelope. Returns GeoJSON Feature dicts."""
    if not url:
        return []
    params: dict[str, Any] = {
        "where": "1=1",
        "geometry": envelope,
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": 4326,
        "outSR": 4326,
        "outFields": "*",
        "returnGeometry": "true",
        "f": "pjson",
    }
    if extra_params:
        params.update(extra_params)
    try:
        resp = await client.get(url, params=params, timeout=6.0)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return []
        raw_features = data.get("features") or []
        geojson_features = []
        for feat in raw_features:
            geom = esri_to_geojson(feat.get("geometry"))
            if geom:
                geojson_features.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": feat.get("attributes") or {},
                })
        return geojson_features
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Main fetch entrypoint
# ---------------------------------------------------------------------------

async def fetch_overlay_features(
    envelope: str,
    jurisdiction: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Fetch all applicable overlay layers for a given envelope + jurisdiction.
    Cached layers (geojson_file) are read synchronously from disk — no network.
    Live layers (arcgis_rest) are queried concurrently.

    Returns {layer_key: {"features": [...], "label": ..., "color": ..., "default_on": ..., "group": ...}}
    """
    applicable = layers_for_jurisdiction(jurisdiction)
    if not applicable:
        return {}

    cached_layers = [d for d in applicable if d.fetch_type == "geojson_file"]
    live_layers   = [d for d in applicable if d.fetch_type == "arcgis_rest"]

    # Cached: read from disk in thread pool to avoid blocking event loop on large files
    loop = asyncio.get_event_loop()
    cached_results = await asyncio.gather(*[
        loop.run_in_executor(None, _load_cached_layer, layer_def, envelope)
        for layer_def in cached_layers
    ])

    # Live: concurrent ArcGIS queries with per-layer timeout
    if live_layers:
        async with httpx.AsyncClient(timeout=8.0) as client:
            live_results = await asyncio.gather(*[
                asyncio.wait_for(
                    _arcgis_envelope_query(client, layer_def.fetch_url, envelope),
                    timeout=7.0,
                )
                for layer_def in live_layers
            ], return_exceptions=True)
    else:
        live_results = []

    output: dict[str, dict[str, Any]] = {}
    for layer_def, features in zip(cached_layers, cached_results):
        output[layer_def.key] = {
            "label": layer_def.label,
            "color": layer_def.color,
            "default_on": layer_def.default_on,
            "group": layer_def.group,
            "reference": layer_def.reference,
            "features": features if isinstance(features, list) else [],
        }
    for layer_def, features in zip(live_layers, live_results):
        output[layer_def.key] = {
            "label": layer_def.label,
            "color": layer_def.color,
            "default_on": layer_def.default_on,
            "group": layer_def.group,
            "reference": layer_def.reference,
            "features": features if isinstance(features, list) else [],
        }
    return output
