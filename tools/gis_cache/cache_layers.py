from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from oregon_statewide_sources import ACTIVE_LAYERS, ALL_LAYER_SPECS, LayerSpec

ROOT = Path(__file__).resolve().parents[2] / "data" / "gis_cache"
RAW_DIR = ROOT / "_raw"
MANIFEST_PATH = ROOT / "manifest.json"

BATCH_SIZE = 250           # Smaller batches = less data per request, fewer timeouts
TIMEOUT = 180.0            # Per-request timeout — large geometry responses can be slow
BATCH_RETRIES = 3          # Retry a failed batch before giving up
# Number of parallel batch workers per layer (one proxy per worker)
PARALLEL_WORKERS = 5


def _load_proxy_pool() -> list[str]:
    """Read PROXYON_DATACENTER_PROXIES from env (comma-separated URLs)."""
    raw = os.environ.get("PROXYON_DATACENTER_PROXIES", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


class _RoundRobin:
    """Thread-safe round-robin over a list of proxy URLs."""

    def __init__(self, urls: list[str]) -> None:
        self._cycle = itertools.cycle(urls) if urls else None
        self._lock = threading.Lock()

    def next_proxy(self) -> str | None:
        if self._cycle is None:
            return None
        with self._lock:
            return next(self._cycle)
REFRESH_POLICY_DAYS: dict[str, int | None] = {
    "monthly": 31,
    "quarterly": 92,
    "semiannual": 183,
    "annual": 366,
    "manual": None,
}


def group_dir(group: str) -> Path:
    return ROOT / group


def ensure_dirs(layers: list[LayerSpec]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for spec in layers:
        group_dir(spec.group).mkdir(parents=True, exist_ok=True)
        (RAW_DIR / spec.group).mkdir(parents=True, exist_ok=True)


def chunked(values: list[int], size: int) -> list[list[int]]:
    return [values[idx : idx + size] for idx in range(0, len(values), size)]


def normalize_arcgis_timestamp(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
    return None


def parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def next_refresh_due_at(cached_at: datetime, refresh_policy: str) -> str | None:
    days = REFRESH_POLICY_DAYS.get(refresh_policy)
    if days is None:
        return None
    return (cached_at + timedelta(days=days)).isoformat()


def load_manifest_index() -> dict[str, dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    layers = payload.get("layers") if isinstance(payload, dict) else None
    if not isinstance(layers, list):
        return {}
    return {
        entry.get("slug"): entry
        for entry in layers
        if isinstance(entry, dict) and isinstance(entry.get("slug"), str)
    }


def refresh_state_for(spec: LayerSpec, manifest_entry: dict[str, Any] | None) -> tuple[str, str | None]:
    if not spec.enabled:
        return ("planned", None)
    if manifest_entry is None:
        if cache_path_for(spec).exists():
            return ("untracked", None)
        return ("missing", None)
    cached_at = parse_iso_datetime(manifest_entry.get("cached_at"))
    if cached_at is None:
        return ("unknown", None)
    due_at = next_refresh_due_at(cached_at, spec.refresh_policy)
    if due_at is None:
        return ("manual", None)
    due_dt = parse_iso_datetime(due_at)
    if due_dt and due_dt <= datetime.now(UTC):
        return ("due", due_at)
    return ("fresh", due_at)


def print_status_report() -> None:
    manifest_index = load_manifest_index()
    for spec in ALL_LAYER_SPECS:
        state, due_at = refresh_state_for(spec, manifest_index.get(spec.slug))
        cached_at = (manifest_index.get(spec.slug) or {}).get("cached_at")
        print(
            f"{spec.slug:32} group={spec.group:8} state={state:8} "
            f"refresh={spec.refresh_policy:10} cached_at={cached_at or '-'} due_at={due_at or '-'}"
        )


def sha256_for(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def arcgis_get_json(
    client: httpx.Client,
    url: str,
    params: dict[str, Any] | None = None,
    *,
    use_post: bool = False,
) -> dict[str, Any]:
    if use_post:
        response = client.post(url, data=params)
    else:
        response = client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"ArcGIS error for {url}: {payload['error']}")
    return payload


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


def feature_to_geojson(feature: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": feature.get("attributes") or {},
        "geometry": esri_geometry_to_geojson(feature.get("geometry")),
    }


def _fetch_batch(
    url: str,
    batch: list[int],
    proxy: str | None,
    fetch_geometry: bool = True,
) -> list[dict[str, Any]]:
    """Fetch one batch of object IDs with retries. Used by parallel workers."""
    params: dict[str, Any] = {
        "objectIds": ",".join(str(i) for i in batch),
        "outFields": "*",
        "returnGeometry": "true" if fetch_geometry else "false",
        "f": "pjson",
    }
    if fetch_geometry:
        params["outSR"] = 4326

    last_exc: Exception | None = None
    for attempt in range(1, BATCH_RETRIES + 1):
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True, proxy=proxy) as client:
                payload = arcgis_get_json(client, f"{url}/query", params, use_post=True)
            return [f for f in payload.get("features", []) if isinstance(f, dict)]
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f"  [batch {batch[0]}-{batch[-1]}] attempt {attempt}/{BATCH_RETRIES} failed: {exc}")
    raise RuntimeError(f"Batch {batch[0]}-{batch[-1]} failed after {BATCH_RETRIES} attempts") from last_exc


def fetch_layer(
    client: httpx.Client,
    spec: LayerSpec,
    proxy_pool: _RoundRobin | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = arcgis_get_json(client, spec.layer_url, {"f": "pjson"})
    ids_payload = arcgis_get_json(
        client,
        f"{spec.layer_url}/query",
        {"where": spec.where, "returnIdsOnly": "true", "f": "pjson"},
        use_post=True,
    )
    object_ids = sorted(int(item) for item in (ids_payload.get("objectIds") or []))
    features: list[dict[str, Any]] = []

    if object_ids:
        batches = chunked(object_ids, BATCH_SIZE)
        workers = min(PARALLEL_WORKERS, len(batches))

        if proxy_pool and proxy_pool._cycle is not None and workers > 1:
            # Parallel fetch — each worker picks up the next proxy in rotation
            results: dict[int, list[dict[str, Any]]] = {}
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_fetch_batch, spec.layer_url, batch, proxy_pool.next_proxy(), spec.fetch_geometry): idx
                    for idx, batch in enumerate(batches)
                }
                completed = 0
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        results[idx] = future.result()
                    except Exception as exc:  # noqa: BLE001
                        print(f"  [batch idx={idx}] permanently failed: {exc}")
                        results[idx] = []
                    completed += 1
                    if completed % 50 == 0:
                        print(f"  {completed}/{len(batches)} batches done ({sum(len(v) for v in results.values())} features so far)")
            # Reassemble in order
            for idx in range(len(batches)):
                features.extend(results.get(idx, []))
        else:
            # Sequential fallback (no proxies configured)
            for batch in batches:
                seq_params: dict[str, Any] = {
                    "objectIds": ",".join(str(i) for i in batch),
                    "outFields": "*",
                    "returnGeometry": "true" if spec.fetch_geometry else "false",
                    "f": "pjson",
                }
                if spec.fetch_geometry:
                    seq_params["outSR"] = 4326
                payload = arcgis_get_json(client, f"{spec.layer_url}/query", seq_params, use_post=True)
                features.extend(f for f in payload.get("features", []) if isinstance(f, dict))
    else:
        payload = arcgis_get_json(
            client,
            f"{spec.layer_url}/query",
            {
                "where": spec.where,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "f": "pjson",
            },
            use_post=True,
        )
        features.extend(f for f in payload.get("features", []) if isinstance(f, dict))

    return metadata, features


def cache_path_for(spec: LayerSpec) -> Path:
    return group_dir(spec.group) / f"{spec.slug}.geojson"


def metadata_path_for(spec: LayerSpec) -> Path:
    return RAW_DIR / spec.group / f"{spec.slug}.metadata.json"


def write_geojson(path: Path, label: str, features: list[dict[str, Any]]) -> int:
    geojson = {
        "type": "FeatureCollection",
        "name": label,
        "features": [feature_to_geojson(feature) for feature in features],
    }
    path.write_text(json.dumps(geojson, separators=(",", ":")), encoding="utf-8")
    return path.stat().st_size


def write_metadata(path: Path, spec: LayerSpec, metadata: dict[str, Any]) -> None:
    payload = {
        "captured_at": datetime.now(UTC).isoformat(),
        "layer": asdict(spec),
        "metadata": metadata,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_manifest(entries: list[dict[str, Any]]) -> None:
    merged_entries = load_manifest_index()
    for entry in entries:
        slug = entry.get("slug") if isinstance(entry, dict) else None
        if isinstance(slug, str):
            merged_entries[slug] = entry

    manifest = {
        "cached_at": datetime.now(UTC).isoformat(),
        "layers": [merged_entries[key] for key in sorted(merged_entries)],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache local GIS layers as GeoJSON with provenance metadata.")
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Optional slugs to cache (default: all active ArcGIS layers).",
    )
    parser.add_argument(
        "--group",
        nargs="*",
        default=None,
        help="Optional groups to cache (for example: gresham oregon external).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all configured sources, including planned/manual layers, and exit.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show manifest-aware refresh status for all configured layers and exit.",
    )
    return parser.parse_args()


def list_layers() -> None:
    for spec in ALL_LAYER_SPECS:
        status = "active" if spec.enabled and spec.source_type == "arcgis" else "planned"
        print(
            f"{spec.slug:32} group={spec.group:8} status={status:7} "
            f"refresh={spec.refresh_policy:10} authority={spec.authority}"
        )


def main() -> int:
    args = parse_args()
    if args.list:
        list_layers()
        return 0
    if args.status:
        print_status_report()
        return 0

    selected = list(ACTIVE_LAYERS)
    if args.group:
        groups = {item.strip() for item in args.group if item.strip()}
        selected = [spec for spec in selected if spec.group in groups]
    if args.only:
        wanted = {item.strip() for item in args.only if item.strip()}
        selected = [spec for spec in selected if spec.slug in wanted]

    if not selected:
        print("No layers selected.")
        return 1

    ensure_dirs(selected)

    proxy_urls = _load_proxy_pool()
    proxy_pool = _RoundRobin(proxy_urls) if proxy_urls else None
    if proxy_pool:
        print(f"Proxy pool: {len(proxy_urls)} datacenter proxies, {PARALLEL_WORKERS} parallel workers")
    else:
        print("No proxy pool configured — sequential fetch (set PROXYON_DATACENTER_PROXIES to enable)")

    manifest_entries: list[dict[str, Any]] = []
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for spec in selected:
            print(f"Caching {spec.label} ({spec.slug})...")
            try:
                metadata, features = fetch_layer(client, spec, proxy_pool)
                output_path = cache_path_for(spec)
                metadata_path = metadata_path_for(spec)
                size_bytes = write_geojson(output_path, spec.label, features)
                write_metadata(metadata_path, spec, metadata)
                cached_at = datetime.now(UTC)
                entry = {
                    **asdict(spec),
                    "feature_count": len(features),
                    "geometry_type": metadata.get("geometryType"),
                    "size_bytes": size_bytes,
                    "size_mb": round(size_bytes / (1024 * 1024), 3),
                    "sha256": sha256_for(output_path),
                    "output_path": str(output_path.relative_to(ROOT.parent)),
                    "metadata_path": str(metadata_path.relative_to(ROOT.parent)),
                    "cached_at": cached_at.isoformat(),
                    "next_refresh_due_at": next_refresh_due_at(cached_at, spec.refresh_policy),
                    "source_max_record_count": metadata.get("maxRecordCount"),
                    "source_last_edit_at": normalize_arcgis_timestamp((metadata.get("editingInfo") or {}).get("lastEditDate")),
                    "service_item_id": metadata.get("serviceItemId"),
                }
                manifest_entries.append(entry)
                print(f"  -> {len(features)} features, {entry['size_mb']} MB")
            except Exception as exc:  # pragma: no cover - operator visibility
                manifest_entries.append({
                    **asdict(spec),
                    "error": str(exc),
                    "cached_at": datetime.now(UTC).isoformat(),
                })
                print(f"  !! failed: {exc}")

    build_manifest(manifest_entries)
    print(f"Wrote manifest to {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
