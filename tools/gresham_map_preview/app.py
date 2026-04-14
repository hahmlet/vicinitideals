from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

try:
    from shapely.geometry import shape
    from shapely.ops import unary_union
except ImportError:  # pragma: no cover - sandbox fallback
    shape = None
    unary_union = None

app = FastAPI(title="Gresham GIS Preview", version="0.1.0")

TAXLOT_QUERY_URL = "https://gis.greshamoregon.gov/ext/rest/services/Taxlots/MapServer/0/query"
PLANNING_BASE = "https://gis.greshamoregon.gov/ext/rest/services/GME/Planning/MapServer"
ENV_BASE = "https://gis.greshamoregon.gov/ext/rest/services/GME/Environmental/MapServer"

OVERLAY_LAYERS: dict[str, dict[str, Any]] = {
    "city_zoning": {
        "label": "City Zoning",
        "query_url": f"{PLANNING_BASE}/4/query",
        "color": "#7c3aed",
    },
    "flood_plain": {
        "label": "Flood Plain",
        "query_url": f"{ENV_BASE}/2/query",
        "color": "#2563eb",
    },
    "open_space": {
        "label": "Open Space Overlay",
        "query_url": f"{ENV_BASE}/4/query",
        "color": "#16a34a",
    },
    "historic_cultural": {
        "label": "Historic & Cultural Overlay",
        "query_url": f"{ENV_BASE}/5/query",
        "color": "#ea580c",
    },
    "hillside_risk": {
        "label": "Hillside / Geologic Risk",
        "query_url": f"{ENV_BASE}/9/query",
        "color": "#dc2626",
    },
    "natural_resource": {
        "label": "Resource Area Overlay",
        "query_url": f"{ENV_BASE}/12/query",
        "color": "#0f766e",
    },
}
DEFAULT_LAYERS = ["city_zoning", "flood_plain", "open_space", "historic_cultural"]
DEFAULT_QUERY = "21255 SE STARK ST"

HTML = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Gresham GIS Preview</title>
  <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\" crossorigin=\"\"/>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; }
    .wrap { display: grid; grid-template-columns: 340px 1fr; height: 100vh; }
    .sidebar { padding: 16px; overflow: auto; border-right: 1px solid #334155; background: #111827; }
    .sidebar h1 { margin-top: 0; font-size: 1.2rem; }
    .sidebar p { color: #cbd5e1; }
    input[type=text] { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: white; }
    button { margin-top: 12px; width: 100%; padding: 10px; border: 0; border-radius: 8px; background: #2563eb; color: white; font-weight: 600; cursor: pointer; }
    button:hover { background: #1d4ed8; }
    .layer-list { display: grid; gap: 8px; margin: 12px 0 16px; }
    .layer-item { background: #0f172a; padding: 8px 10px; border-radius: 8px; border: 1px solid #334155; }
    .meta { margin-top: 16px; font-size: 0.92rem; }
    .pill { display: inline-block; padding: 3px 8px; border-radius: 999px; background: #1e293b; margin-right: 6px; margin-bottom: 6px; }
    .pill-yes { background: #7f1d1d; }
    .pill-maybe { background: #78350f; }
    .pill-no { background: #14532d; }
    #map { height: 100vh; width: 100%; }
    pre { white-space: pre-wrap; word-break: break-word; background: #0b1120; padding: 10px; border-radius: 8px; border: 1px solid #334155; }
    .legend { margin-top: 12px; }
    .legend-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
    .swatch { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }
    a { color: #93c5fd; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <aside class=\"sidebar\">
      <h1>Gresham GIS Preview</h1>
      <p>Quick standalone map for testing parcel polygons against a few live Gresham overlay layers.</p>
      <label for=\"query\">Address or APN</label>
      <input id=\"query\" type=\"text\" value=\"21255 SE STARK ST\" />
      <div class=\"layer-list\" id=\"layer-list\"></div>
      <button id=\"load-btn\">Load map</button>
      <div class=\"meta\" id=\"meta\"></div>
      <div class=\"legend\" id=\"legend\"></div>
    </aside>
    <div id=\"map\"></div>
  </div>

  <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\" integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\" crossorigin=\"\"></script>
  <script>
    const overlayConfig = __OVERLAY_CONFIG__;
    const defaultLayers = __DEFAULT_LAYERS__;
    const map = L.map('map').setView([45.505, -122.431], 13);
    const layers = [];
    let userMovedMap = false;
    let autoFitting = false;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    function clearLayers() {
      while (layers.length) {
        const layer = layers.pop();
        map.removeLayer(layer);
      }
    }

    function renderLegend() {
      const legend = document.getElementById('legend');
      legend.innerHTML = '<h3>Layers</h3>' + Object.entries(overlayConfig).map(([key, value]) => `
        <div class=\"legend-row\"><span class=\"swatch\" style=\"background:${value.color}\"></span>${value.label}</div>
      `).join('') + '<div class=\"legend-row\"><span class=\"swatch\" style=\"background:#111827;border:2px solid #f8fafc\"></span>Parcel</div>';
    }

    function renderLayerSelector() {
      const container = document.getElementById('layer-list');
      container.innerHTML = Object.entries(overlayConfig).map(([key, value]) => {
        const checked = defaultLayers.includes(key) ? 'checked' : '';
        return `<label class=\"layer-item\"><input type=\"checkbox\" value=\"${key}\" ${checked}/> ${value.label}</label>`;
      }).join('');
    }

    function selectedLayers() {
      return [...document.querySelectorAll('#layer-list input:checked')].map((el) => el.value);
    }

    function colorStyle(color, fillOpacity = 0.15) {
      return { color, weight: 2, fillColor: color, fillOpacity };
    }

    function hashText(value) {
      return [...String(value || '')].reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
    }

    function zoneName(props) {
      return props.ZONE || props.ZONE_DESC || props.BASEZONE || props.NAME || props.DESCRIPTION || 'zoning';
    }

    function zoneColor(zone) {
      const palette = ['#7c3aed', '#2563eb', '#0891b2', '#16a34a', '#ca8a04', '#ea580c', '#dc2626', '#db2777'];
      return palette[hashText(zone) % palette.length];
    }

    function overlayStyle(entry, feature) {
      if (entry.layer_key === 'city_zoning') {
        const color = zoneColor(zoneName(feature.properties || {}));
        return colorStyle(color, 0.22);
      }
      return colorStyle(entry.color, 0.18);
    }

    function prettyStatus(status) {
      return String(status || '').replaceAll('_', ' ');
    }

    function pillClass(status) {
      if (status === 'definitely_yes') return 'pill pill-yes';
      if (status === 'maybe') return 'pill pill-maybe';
      if (status === 'definitely_no') return 'pill pill-no';
      return 'pill';
    }

    async function loadPreview() {
      const query = document.getElementById('query').value.trim();
      if (!query) return;

      const meta = document.getElementById('meta');
      meta.innerHTML = '<p>Loading…</p>';
      clearLayers();

      const params = new URLSearchParams({ query });
      for (const layer of selectedLayers()) params.append('layers', layer);

      const bounds = map.getBounds();
      if (bounds.isValid()) {
        params.set('bbox', `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`);
      }

      const response = await fetch(`/api/preview?${params.toString()}`);
      const payload = await response.json();
      if (!response.ok) {
        meta.innerHTML = `<p><strong>Error:</strong> ${payload.detail || 'Request failed'}</p>`;
        return;
      }

      const parcelLayer = L.geoJSON(payload.parcels, {
        style: colorStyle('#f8fafc', 0.08),
      }).addTo(map);
      layers.push(parcelLayer);

      payload.overlays.forEach((entry) => {
        if (!entry.geojson.features.length) return;
        const overlayLayer = L.geoJSON(entry.geojson, {
          style: (feature) => overlayStyle(entry, feature),
          onEachFeature: (feature, layer) => {
            const props = feature.properties || {};
            const title = entry.layer_key === 'city_zoning' ? `${entry.label}: ${zoneName(props)}` : entry.label;
            const preview = Object.entries(props).slice(0, 8).map(([k, v]) => `<div><strong>${k}</strong>: ${v}</div>`).join('');
            layer.bindPopup(`<strong>${title}</strong>${preview}`);
          }
        }).addTo(map);
        layers.push(overlayLayer);
      });

      const combined = L.featureGroup(layers);
      const combinedBounds = combined.getBounds();
      if (!userMovedMap && combinedBounds.isValid()) {
        autoFitting = true;
        map.fitBounds(combinedBounds.pad(0.1));
        setTimeout(() => { autoFitting = false; }, 0);
      }

      const floodAssessment = payload.flood_assessment;
      const pills = payload.overlays.map((entry) => {
        if (entry.layer_key === 'flood_plain' && floodAssessment) {
          const suffix = `${prettyStatus(floodAssessment.status)} (${Number(floodAssessment.overlap_pct).toFixed(2)}%)`;
          return `<span class=\"${pillClass(floodAssessment.status)}\">${entry.label}: ${suffix}</span>`;
        }
        const suffix = entry.error ? `error` : `${entry.feature_count}`;
        return `<span class=\"pill\">${entry.label}: ${suffix}</span>`;
      }).join('');
      const layerNotes = payload.overlays
        .filter((entry) => entry.error || entry.feature_count === 0)
        .map((entry) => `<div><strong>${entry.label}</strong>: ${entry.error ? entry.error : 'no nearby features in the preview window'}</div>`)
        .join('');
      const floodNote = floodAssessment
        ? `<p><strong>Flood screen:</strong> ${prettyStatus(floodAssessment.status)} — ${Number(floodAssessment.overlap_pct).toFixed(2)}% of parcel${floodAssessment.overlap_sqft_est !== null ? ` (~${Number(floodAssessment.overlap_sqft_est).toFixed(0)} sq ft est.)` : ''}</p>`
        : '';
      meta.innerHTML = `
        <p><strong>Status:</strong> ${payload.match_status}</p>
        <p><strong>Query:</strong> ${payload.query}</p>
        <p><strong>Parcel count:</strong> ${payload.parcel_count}</p>
        ${floodNote}
        <p>${pills || 'No overlay hits'}</p>
        ${layerNotes ? `<div>${layerNotes}</div>` : ''}
        <pre>${JSON.stringify(payload.parcel_summary, null, 2)}</pre>
      `;
    }

    map.on('moveend zoomend', () => {
      if (!autoFitting) userMovedMap = true;
    });

    document.getElementById('load-btn').addEventListener('click', loadPreview);
    renderLegend();
    renderLayerSelector();
    loadPreview();
  </script>
</body>
</html>
"""


def normalize_query(value: str) -> str:
    return " ".join((value or "").strip().upper().split())


def looks_like_apn(value: str) -> bool:
    compact = normalize_query(value).replace(" ", "")
    return compact.startswith("R") and compact[1:].isdigit()


async def arcgis_query(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    timeout = httpx.Timeout(20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    if payload.get("error"):
        raise HTTPException(status_code=502, detail=str(payload["error"]))
    return [feature for feature in payload.get("features", []) if isinstance(feature, dict)]


def esri_geometry_to_geojson(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(geometry, dict):
        return None
    if geometry.get("rings"):
        return {"type": "Polygon", "coordinates": geometry["rings"]}
    if geometry.get("paths"):
        return {"type": "MultiLineString", "coordinates": geometry["paths"]}
    if {"x", "y"}.issubset(geometry.keys()):
        return {"type": "Point", "coordinates": [geometry["x"], geometry["y"]]}
    return None


def feature_to_geojson(feature: dict[str, Any]) -> dict[str, Any] | None:
    geometry = esri_geometry_to_geojson(feature.get("geometry"))
    if geometry is None:
        return None
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": feature.get("attributes") or {},
    }


def _iter_coords(value: Any):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for item in value:
                yield from _iter_coords(item)


def parcel_envelope(geometry: dict[str, Any], pad_ratio: float = 0.35, min_pad: float = 0.0015) -> str:
    coords = list(_iter_coords((geometry or {}).get("rings") or (geometry or {}).get("paths") or []))
    if not coords and {"x", "y"}.issubset((geometry or {}).keys()):
        coords = [(float(geometry["x"]), float(geometry["y"]))]
    if not coords:
        raise HTTPException(status_code=400, detail="Parcel geometry is missing usable coordinates")

    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    dx = max(xmax - xmin, min_pad)
    dy = max(ymax - ymin, min_pad)
    padx = max(dx * pad_ratio, min_pad)
    pady = max(dy * pad_ratio, min_pad)
    return f"{xmin - padx},{ymin - pady},{xmax + padx},{ymax + pady}"


async def fetch_parcel_features(query: str) -> list[dict[str, Any]]:
    normalized = normalize_query(query)
    if not normalized:
        return []

    escaped = normalized.replace("'", "''")
    if looks_like_apn(normalized):
        where_clauses = [f"UPPER(RNO) = '{escaped}'"]
    else:
        where_clauses = [
            f"SITEADDR = '{escaped}'",
            f"UPPER(SITEADDR) LIKE '%{escaped}%'",
        ]

    for where in where_clauses:
        features = await arcgis_query(
            TAXLOT_QUERY_URL,
            {
                "where": where,
                "outFields": "RNO,STATEID,SITEADDR,ZONE,LANDUSE,GIS_ACRES,SQFT,OWNER1",
                "returnGeometry": "true",
                "outSR": 4326,
                "f": "pjson",
            },
        )
        if features:
            return features
    return []


def compute_overlap_assessment(
    parcel_geojson: dict[str, Any],
    overlay_geojson: dict[str, Any],
    *,
    threshold_pct: float = 1.0,
    parcel_sqft: float | None = None,
) -> dict[str, Any] | None:
    if shape is None or unary_union is None:
        return None

    parcel_features = parcel_geojson.get("features") or []
    overlay_features = overlay_geojson.get("features") or []
    if not parcel_features:
        return None

    parcel_shape = shape(parcel_features[0]["geometry"])
    parcel_area = float(parcel_shape.area or 0.0)
    if parcel_area <= 0:
        return None

    overlay_shapes = [shape(feature["geometry"]) for feature in overlay_features if feature.get("geometry")]
    if not overlay_shapes:
        return {
            "status": "definitely_no",
            "overlap_pct": 0.0,
            "overlap_sqft_est": 0.0 if parcel_sqft not in (None, "") else None,
            "threshold_pct": threshold_pct,
        }

    merged_overlay = unary_union(overlay_shapes)
    overlap_area = float(parcel_shape.intersection(merged_overlay).area or 0.0)
    overlap_pct = round((overlap_area / parcel_area) * 100, 4)
    overlap_sqft_est = None
    if parcel_sqft not in (None, ""):
        overlap_sqft_est = round(float(parcel_sqft) * overlap_pct / 100.0, 2)

    if overlap_pct >= threshold_pct:
        status = "definitely_yes"
    elif overlap_pct > 0:
        status = "maybe"
    else:
        status = "definitely_no"

    return {
        "status": status,
        "overlap_pct": overlap_pct,
        "overlap_sqft_est": overlap_sqft_est,
        "threshold_pct": threshold_pct,
    }


async def fetch_overlay_hits(
    parcel_geometry: dict[str, Any],
    layer_keys: list[str],
    *,
    bbox: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    envelope = bbox or parcel_envelope(parcel_geometry)
    for key in layer_keys:
        config = OVERLAY_LAYERS.get(key)
        if not config:
            continue
        try:
            features = await arcgis_query(
                config["query_url"],
                {
                    "where": "1=1",
                    "geometry": envelope,
                    "geometryType": "esriGeometryEnvelope",
                    "spatialRel": "esriSpatialRelIntersects",
                    "inSR": 4326,
                    "outSR": 4326,
                    "outFields": "*",
                    "returnGeometry": "true",
                    "f": "pjson",
                },
            )
            geojson_features = [item for item in (feature_to_geojson(feature) for feature in features) if item]
            results.append(
                {
                    "layer_key": key,
                    "label": config["label"],
                    "color": config["color"],
                    "feature_count": len(geojson_features),
                    "error": None,
                    "geojson": {"type": "FeatureCollection", "features": geojson_features},
                }
            )
        except HTTPException as exc:
            results.append(
                {
                    "layer_key": key,
                    "label": config["label"],
                    "color": config["color"],
                    "feature_count": 0,
                    "error": exc.detail,
                    "geojson": {"type": "FeatureCollection", "features": []},
                }
            )
    return results


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html = (
        HTML.replace("__OVERLAY_CONFIG__", json.dumps(OVERLAY_LAYERS))
        .replace("__DEFAULT_LAYERS__", json.dumps(DEFAULT_LAYERS))
        .replace("21255 SE STARK ST", DEFAULT_QUERY)
    )
    return HTMLResponse(html)


@app.get("/api/preview")
async def preview(
    query: str = Query(..., description="Address or APN"),
    layers: list[str] = Query(default=DEFAULT_LAYERS),
    bbox: str | None = Query(default=None, description="Optional viewport bbox xmin,ymin,xmax,ymax in EPSG:4326"),
) -> dict[str, Any]:
    parcel_features = await fetch_parcel_features(query)
    if not parcel_features:
        raise HTTPException(status_code=404, detail="No parcel found for that query")

    parcel_geojson = [item for item in (feature_to_geojson(feature) for feature in parcel_features) if item]
    match_status = "single_match" if len(parcel_geojson) == 1 else "multiple_matches"

    overlays: list[dict[str, Any]] = []
    if parcel_features and isinstance(parcel_features[0].get("geometry"), dict):
        overlays = await fetch_overlay_hits(parcel_features[0]["geometry"], layers, bbox=bbox)

    first_props = parcel_features[0].get("attributes") or {}
    parcel_feature_collection = {"type": "FeatureCollection", "features": parcel_geojson}
    flood_entry = next((entry for entry in overlays if entry["layer_key"] == "flood_plain"), None)
    flood_assessment = None
    if flood_entry is not None:
        flood_assessment = compute_overlap_assessment(
            parcel_feature_collection,
            flood_entry["geojson"],
            threshold_pct=1.0,
            parcel_sqft=first_props.get("SQFT"),
        )

    return {
        "query": normalize_query(query),
        "match_status": match_status,
        "parcel_count": len(parcel_geojson),
        "parcels": parcel_feature_collection,
        "parcel_summary": {
            "apn": first_props.get("RNO"),
            "site_address": (first_props.get("SITEADDR") or "").strip() or None,
            "zone": first_props.get("ZONE"),
            "land_use": first_props.get("LANDUSE"),
            "gis_acres": first_props.get("GIS_ACRES"),
            "sqft": first_props.get("SQFT"),
            "owner": first_props.get("OWNER1"),
        },
        "overlays": overlays,
        "flood_assessment": flood_assessment,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8010)
