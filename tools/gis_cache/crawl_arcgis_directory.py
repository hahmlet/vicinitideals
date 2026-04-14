from __future__ import annotations

import argparse
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SERVICES_ROOT = "https://navigator.state.or.us/arcgis/rest/services"
DEFAULT_SDK_ROOT = "https://navigator.state.or.us/arcgis/sdk/rest/"
AUTHORITATIVE_DOCS = [
    "https://navigator.state.or.us/arcgis/sdk/rest/#/Resources_and_operations/02ss00000053000000/",
    "https://navigator.state.or.us/arcgis/sdk/rest/#/Using_the_Services_Directory/02ss00000066000000/",
    "https://navigator.state.or.us/arcgis/sdk/rest/#/Resource_hierarchy/02ss00000067000000/",
    "https://navigator.state.or.us/arcgis/sdk/rest/#/Get_started/02ss00000048000000/",
    "https://navigator.state.or.us/arcgis/sdk/rest/#/Configuring_the_REST_API/02ss0000001q000000/",
    "https://navigator.state.or.us/arcgis/sdk/rest/#/Catalog/02ss00000029000000/",
]

GLOBAL_SDK_TOPICS = {
    "resources and operations",
    "using the services directory",
    "resource hierarchy",
    "get started",
    "configuring the rest api",
    "catalog",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl an ArcGIS REST Services Directory and build a local catalog JSON/Markdown."
    )
    parser.add_argument(
        "--services-root",
        default=DEFAULT_SERVICES_ROOT,
        help="ArcGIS REST services root, for example https://host/arcgis/rest/services",
    )
    parser.add_argument(
        "--sdk-root",
        default=DEFAULT_SDK_ROOT,
        help="ArcGIS SDK docs root, for example https://host/arcgis/sdk/rest/",
    )
    parser.add_argument(
        "--include-sdk",
        action="store_true",
        help="Crawl SDK pages and enrich the catalog with sdk_pages/sdK_links.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Optional ArcGIS token for secured services.",
    )
    parser.add_argument(
        "--out-json",
        default="data/gis_cache/_raw/oregon/navigator_services_catalog.json",
        help="Output path for the full catalog JSON (relative to re-modeling root).",
    )
    parser.add_argument(
        "--out-md",
        default="data/gis_cache/_raw/oregon/navigator_services_catalog.md",
        help="Output path for a compact markdown summary (relative to re-modeling root).",
    )
    parser.add_argument(
        "--max-services",
        type=int,
        default=0,
        help="Optional cap on number of services to crawl (0 = no cap).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds.",
    )
    parser.add_argument(
        "--pause-ms",
        type=int,
        default=0,
        help="Optional pause in milliseconds between metadata requests.",
    )
    parser.add_argument(
        "--out-jsonl",
        default="data/gis_cache/_raw/oregon/navigator_layers.jsonl",
        help="Output path for a flat JSONL search index (one record per layer).",
    )
    return parser.parse_args()


def arcgis_get_json(
    client: httpx.Client,
    url: str,
    *,
    token: str | None,
    retries: int = 3,
) -> dict[str, Any]:
    params = {"f": "pjson"}
    if token:
        params["token"] = token

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                raise RuntimeError(f"ArcGIS error for {url}: {payload['error']}")
            if not isinstance(payload, dict):
                raise RuntimeError(f"Unexpected payload type from {url}")
            return payload
        except Exception as exc:  # pragma: no cover - operator visibility
            last_error = exc
            if attempt == retries:
                break
            time.sleep(0.5 * attempt)

    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def list_services(
    client: httpx.Client,
    services_root: str,
    token: str | None,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    root_payload = arcgis_get_json(client, services_root, token=token)
    folder_names = [folder for folder in (root_payload.get("folders") or []) if isinstance(folder, str)]
    services: list[dict[str, Any]] = []
    folder_index: list[dict[str, Any]] = []

    root_services = [item for item in (root_payload.get("services") or []) if isinstance(item, dict)]
    services.extend({**item, "folder": None} for item in root_services)

    for folder in folder_names:
        folder_url = f"{services_root}/{folder}"
        folder_payload = arcgis_get_json(client, folder_url, token=token)
        folder_services = [item for item in (folder_payload.get("services") or []) if isinstance(item, dict)]
        folder_index.append(
            {
                "folder": folder,
                "url": folder_url,
                "service_count": len(folder_services),
            }
        )
        services.extend({**item, "folder": folder} for item in folder_services)

    return folder_names, services, folder_index


def service_url(services_root: str, service_name: str, service_type: str) -> str:
    return f"{services_root}/{service_name}/{service_type}"


def crawl_services(
    client: httpx.Client,
    services_root: str,
    services: list[dict[str, Any]],
    *,
    token: str | None,
    max_services: int,
    pause_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    selected = services[:max_services] if max_services > 0 else services
    for idx, svc in enumerate(selected, start=1):
        name = str(svc.get("name") or "")
        service_type = str(svc.get("type") or "")
        if not name or not service_type:
            failures.append({"service": svc, "error": "missing name/type"})
            continue

        url = service_url(services_root, name, service_type)
        try:
            metadata = arcgis_get_json(client, url, token=token)
            layers = [item for item in (metadata.get("layers") or []) if isinstance(item, dict)]
            tables = [item for item in (metadata.get("tables") or []) if isinstance(item, dict)]

            layer_details: list[dict[str, Any]] = []
            for child in layers + tables:
                child_id = child.get("id")
                if not isinstance(child_id, int):
                    continue
                child_url = f"{url}/{child_id}"
                try:
                    child_meta = arcgis_get_json(client, child_url, token=token)
                    raw_fields = [f for f in (child_meta.get("fields") or []) if isinstance(f, dict) and f.get("name")]
                    layer_details.append(
                        {
                            "id": child_id,
                            "url": child_url,
                            "name": child_meta.get("name"),
                            "type": child_meta.get("type"),
                            "geometryType": child_meta.get("geometryType"),
                            "capabilities": child_meta.get("capabilities"),
                            "field_count": len(raw_fields),
                            "field_names": [f["name"] for f in raw_fields],
                            "fields": [
                                {"name": f["name"], "type": f.get("type"), "alias": f.get("alias")}
                                for f in raw_fields
                            ],
                            "source_last_edit_at": (child_meta.get("editingInfo") or {}).get("lastEditDate"),
                        }
                    )
                except Exception as exc:  # pragma: no cover - operator visibility
                    failures.append(
                        {
                            "service": name,
                            "url": child_url,
                            "error": str(exc),
                        }
                    )

            records.append(
                {
                    "folder": svc.get("folder"),
                    "name": name,
                    "type": service_type,
                    "url": url,
                    "description": metadata.get("serviceDescription"),
                    "capabilities": metadata.get("capabilities"),
                    "maxRecordCount": metadata.get("maxRecordCount"),
                    "layers": layer_details,
                    "layer_count": len(layer_details),
                    "supportsDynamicLayers": metadata.get("supportsDynamicLayers"),
                    "currentVersion": metadata.get("currentVersion"),
                }
            )
            print(f"[{idx}/{len(selected)}] crawled {name} ({service_type}) -> {len(layer_details)} children")
        except Exception as exc:  # pragma: no cover - operator visibility
            failures.append({"service": name, "url": url, "error": str(exc)})
            print(f"[{idx}/{len(selected)}] failed {name} ({service_type}): {exc}")

        if pause_ms > 0:
            time.sleep(pause_ms / 1000)

    return records, failures


def write_markdown_summary(path: Path, payload: dict[str, Any]) -> None:
    services = payload.get("services") or []
    failures = payload.get("failures") or []
    folders = payload.get("folders") or []
    sdk_pages = payload.get("sdk_pages") or []
    sdk_pages_all = payload.get("sdk_pages_all") or []
    platform_sdk_pages = payload.get("platform_capabilities_not_implemented") or []

    lines = [
        "# ArcGIS Services Catalog",
        "",
        f"- Generated at: {payload.get('generated_at')}",
        f"- Services root: {payload.get('services_root')}",
        f"- Folder count: {len(folders)}",
        f"- Services crawled: {len(services)}",
        f"- Failures: {len(failures)}",
        f"- SDK pages: {len(sdk_pages)}",
        f"- All discovered SDK pages: {len(sdk_pages_all)}",
        f"- Platform-only SDK pages: {len(platform_sdk_pages)}",
        "",
        "## Authoritative REST Docs",
        "",
    ]
    lines.extend([f"- {url}" for url in AUTHORITATIVE_DOCS])
    lines.append("")
    lines.append("## Services")
    lines.append("")

    for service in services:
        lines.append(
            f"- `{service.get('name')}` ({service.get('type')}) "
            f"folder=`{service.get('folder') or '/'} ` layers={service.get('layer_count')}"
        )

    if sdk_pages:
        lines.append("")
        lines.append("## Live Matched SDK References")
        lines.append("")
        for page in sdk_pages:
            matched = page.get("matched_count", 0)
            lines.append(f"- `{page.get('title')}` doc_id=`{page.get('doc_id')}` matches={matched}")

    if platform_sdk_pages:
        lines.append("")
        lines.append("## Platform Capabilities Not Exposed By Oregon")
        lines.append("")
        for page in platform_sdk_pages:
            lines.append(f"- `{page.get('title')}` ({page.get('url')})")

    if failures:
        lines.append("")
        lines.append("## Failures")
        lines.append("")
        for failure in failures:
            lines.append(f"- `{failure.get('service')}`: {failure.get('error')}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def slug_to_title(text: str) -> str:
    return " ".join(part for part in text.replace("_", " ").replace("-", " ").split()).strip().lower()


def sdk_url_variants(sdk_root: str) -> set[str]:
    root = sdk_root.rstrip("/") + "/"
    variants = {
        root,
        root.rstrip("/"),
    }
    for url in AUTHORITATIVE_DOCS:
        variants.add(url)
        if "#/" in url:
            variants.add(url.split("#/", 1)[0])
    return variants


def parse_sdk_fragment(fragment: str) -> tuple[str, str | None]:
    clean = fragment.strip("/")
    parts = [item for item in clean.split("/") if item]
    title_part = parts[0] if parts else "sdk"
    doc_id = parts[1] if len(parts) > 1 else None
    return slug_to_title(title_part), doc_id


def extract_js_string_array(script_text: str, key: str) -> list[str]:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*\[(.*?)\]\s*(?:,|}})', script_text, flags=re.DOTALL)
    if not match:
        return []
    try:
        return json.loads("[" + match.group(1) + "]")
    except Exception:
        return []


def crawl_sdk_search_index(client: httpx.Client, sdk_root: str) -> list[dict[str, Any]]:
    base = sdk_root.rstrip("/") + "/"
    index_url = base + "rsrc/searchindex.js"
    try:
        response = client.get(index_url)
        response.raise_for_status()
        script_text = response.text
    except Exception:
        return []

    links = extract_js_string_array(script_text, "links")
    titles = extract_js_string_array(script_text, "titles")
    if not links:
        return []

    pages: list[dict[str, Any]] = []
    for idx, link in enumerate(links):
        if not isinstance(link, str):
            continue
        clean_link = link.lstrip("/")
        doc_id_match = re.search(r"(02ss[0-9a-z]{12})", clean_link)
        doc_id = doc_id_match.group(1) if doc_id_match else None
        title_raw = titles[idx] if idx < len(titles) and isinstance(titles[idx], str) else (doc_id or clean_link)
        pages.append(
            {
                "doc_id": doc_id,
                "title": slug_to_title(title_raw),
                "fragment": None,
                "url": base + clean_link,
                "source": "search_index",
            }
        )

    return pages


def crawl_sdk_pages(client: httpx.Client, sdk_root: str) -> list[dict[str, Any]]:
    variants = sdk_url_variants(sdk_root)
    html: str | None = None
    for candidate in variants:
        try:
            response = client.get(candidate)
            response.raise_for_status()
            html = response.text
            if html:
                break
        except Exception:
            continue

    pages: list[dict[str, Any]] = []
    if html:
        fragments = set(re.findall(r'href=["\'](#/[^"\']+)["\']', html))
        fragments.update("#/" + item.split("#/", 1)[1] for item in AUTHORITATIVE_DOCS if "#/" in item)

        base = sdk_root.rstrip("/")
        for fragment in sorted(fragments):
            frag = fragment.lstrip("#")
            title, doc_id = parse_sdk_fragment(frag)
            pages.append(
                {
                    "doc_id": doc_id,
                    "title": title,
                    "fragment": frag,
                    "url": f"{base}#{frag}",
                    "source": "sdk_index",
                }
            )

    # The SDK root is a thin shell; most pages are indexed in searchindex.js.
    pages.extend(crawl_sdk_search_index(client, sdk_root))

    if not pages:
        for url in AUTHORITATIVE_DOCS:
            fragment = url.split("#/", 1)[1] if "#/" in url else ""
            title, doc_id = parse_sdk_fragment(fragment)
            pages.append(
                {
                    "doc_id": doc_id,
                    "title": title,
                    "fragment": fragment,
                    "url": url,
                    "source": "seed",
                }
            )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str]] = set()
    for page in pages:
        key = (page.get("doc_id"), str(page.get("url")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(page)

    return deduped


def build_service_layer_candidates(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for service in services:
        service_text = " ".join(
            str(part or "")
            for part in [service.get("name"), service.get("type"), service.get("description")]
        ).lower()
        candidates.append(
            {
                "kind": "service",
                "target": service.get("url"),
                "label": service.get("name"),
                "text": service_text,
                "service_type": str(service.get("type") or "").lower(),
            }
        )
        for layer in service.get("layers") or []:
            layer_text = " ".join(
                str(part or "")
                for part in [
                    layer.get("name"),
                    layer.get("type"),
                    layer.get("geometryType"),
                    layer.get("capabilities"),
                ]
            ).lower()
            candidates.append(
                {
                    "kind": "layer",
                    "target": layer.get("url"),
                    "label": f"{service.get('name')}::{layer.get('name')}",
                    "text": layer_text,
                    "service_type": str(service.get("type") or "").lower(),
                }
            )
    return candidates


def type_hint_tokens(page_title: str) -> set[str]:
    hints: set[str] = set()
    if "feature" in page_title:
        hints.update({"feature layer", "featureserver", "esrigeometry"})
    if "query" in page_title:
        hints.update({"query", "map,query,data", "capabilities"})
    if "geometry" in page_title:
        hints.update({"geometryserver", "geometry"})
    if "geocode" in page_title or "locator" in page_title:
        hints.update({"geocodeserver", "locator"})
    if "map service" in page_title or "mapserver" in page_title:
        hints.update({"mapserver", "feature layer"})
    if "image" in page_title:
        hints.update({"imageserver", "raster"})
    return hints


# Maps SDK page title keywords to the ArcGIS service types they apply to.
# None = applies to all types (generic/global).
_SDK_PAGE_SERVICE_TYPE_HINTS: list[tuple[list[str], set[str]]] = [
    (["feature service", "feature layer", "apply edits", "add features", "delete features", "update features", "query features"], {"featureserver"}),
    (["map service", "export map", "identify", "dynamic layer"], {"mapserver"}),
    (["image service", "raster", "mosaic"], {"imageserver"}),
    (["geometry service"], {"geometryserver"}),
    (["gp service", "geoprocessing", "submit job", "execute task"], {"gpserver"}),
    (["geocode service", "find address candidates", "reverse geocode", "suggest", "locator"], {"geocodeserver"}),
    (["network service", "route", "service area", "closest facility"], {"naserver"}),
]


def service_type_filter_for_page(page_title: str) -> set[str] | None:
    """Return the allowed service_type values for a SDK page, or None for 'any'."""
    title = page_title.lower()
    for keywords, allowed in _SDK_PAGE_SERVICE_TYPE_HINTS:
        if any(kw in title for kw in keywords):
            return allowed
    return None


def link_sdk_pages(
    sdk_pages: list[dict[str, Any]],
    services: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = build_service_layer_candidates(services)
    links: list[dict[str, Any]] = []
    implemented: list[dict[str, Any]] = []
    platform_only: list[dict[str, Any]] = []

    for page in sdk_pages:
        title = str(page.get("title") or "").lower()
        if title in GLOBAL_SDK_TOPICS:
            page["scope"] = "platform_reference"
            page["capability_status"] = "documented_by_arcgis_not_matched_to_oregon_service"
            page["matched_count"] = 0
            platform_only.append(page)
            continue

        tokens = set(title.split())
        tokens.update(type_hint_tokens(title))
        tokens = {token for token in tokens if token}

        svc_type_filter = service_type_filter_for_page(title)

        scored: list[tuple[int, dict[str, Any]]] = []
        for candidate in candidates:
            # Skip candidates whose service type doesn't match the page's domain.
            if svc_type_filter is not None and candidate["service_type"] not in svc_type_filter:
                continue
            text = candidate["text"]
            score = 0
            for token in tokens:
                if token in text:
                    score += 1
            if score >= 2:  # Require at least 2 matching tokens to suppress noise.
                scored.append((score, candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        top_matches = scored[:5]

        if not top_matches:
            page["scope"] = "platform_reference"
            page["capability_status"] = "documented_by_arcgis_not_matched_to_oregon_service"
            page["matched_count"] = 0
            platform_only.append(page)
            continue

        page["scope"] = "matched_to_live_oregon_service"
        page["capability_status"] = "matched_to_live_oregon_service"
        page["matched_count"] = len(top_matches)
        implemented.append(page)
        for score, candidate in top_matches:
            links.append(
                {
                    "doc_id": page.get("doc_id"),
                    "doc_title": page.get("title"),
                    "doc_url": page.get("url"),
                    "target_kind": candidate["kind"],
                    "target_ref": candidate["target"],
                    "target_label": candidate["label"],
                    "match_type": "token_overlap",
                    "score": score,
                }
            )

    return links, implemented, platform_only


def write_flat_jsonl(
    path: Path,
    services: list[dict[str, Any]],
    sdk_links: list[dict[str, Any]],
) -> int:
    """Emit one JSONL record per layer with all context collapsed for search ingestion."""
    # Index sdk_links by target_ref for fast lookup.
    links_by_layer: dict[str, list[dict[str, Any]]] = {}
    for link in sdk_links:
        ref = str(link.get("target_ref") or "")
        links_by_layer.setdefault(ref, []).append(link)

    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for svc in services:
            svc_name = svc.get("name") or ""
            svc_folder = svc.get("folder") or ""
            svc_type = svc.get("type") or ""
            svc_url = svc.get("url") or ""
            svc_desc = svc.get("description") or ""
            svc_caps = svc.get("capabilities") or ""

            for layer in svc.get("layers") or []:
                layer_url = str(layer.get("url") or "")
                linked = links_by_layer.get(layer_url, [])
                field_names = layer.get("field_names") or []
                fields = layer.get("fields") or []

                record: dict[str, Any] = {
                    "id": f"{svc_name}::{layer.get('id')}",
                    "service_name": svc_name,
                    "service_folder": svc_folder,
                    "service_type": svc_type,
                    "service_url": svc_url,
                    "service_description": svc_desc,
                    "service_capabilities": svc_caps,
                    "layer_id": layer.get("id"),
                    "layer_url": layer_url,
                    "layer_name": layer.get("name") or "",
                    "layer_type": layer.get("type") or "",
                    "geometry_type": layer.get("geometryType") or "",
                    "layer_capabilities": layer.get("capabilities") or "",
                    "field_count": layer.get("field_count") or 0,
                    "field_names": field_names,
                    "fields": fields,
                    "matched_sdk_docs": [
                        {
                            "title": lk.get("doc_title"),
                            "url": lk.get("doc_url"),
                            "score": lk.get("score"),
                            "capability_status": "matched_to_live_oregon_service",
                        }
                        for lk in sorted(linked, key=lambda x: x.get("score", 0), reverse=True)
                    ],
                    "sdk_docs_scope": "matched_to_live_oregon_service_only",
                    # Denormalized text blob for BM25/keyword search.
                    "search_text": " ".join(filter(None, [
                        svc_name, svc_folder, svc_type, svc_desc,
                        layer.get("name") or "",
                        layer.get("type") or "",
                        layer.get("geometryType") or "",
                        " ".join(field_names),
                        " ".join(f.get("alias") or "" for f in fields),
                    ])).lower(),
                }
                record["sdk_docs"] = record["matched_sdk_docs"]
                fh.write(json.dumps(record) + "\n")
                count += 1
    return count


def main() -> int:
    args = parse_args()
    services_root = args.services_root.rstrip("/")
    sdk_root = args.sdk_root.rstrip("/") + "/"

    workspace_root = Path(__file__).resolve().parents[2]
    out_json = (workspace_root / args.out_json).resolve()
    out_md = (workspace_root / args.out_md).resolve()
    out_jsonl = (workspace_root / args.out_jsonl).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        folders, services, folder_index = list_services(client, services_root, args.token)
        records, failures = crawl_services(
            client,
            services_root,
            services,
            token=args.token,
            max_services=max(args.max_services, 0),
            pause_ms=max(args.pause_ms, 0),
        )

        sdk_pages: list[dict[str, Any]] = []
        sdk_pages_all: list[dict[str, Any]] = []
        sdk_links: list[dict[str, Any]] = []
        platform_sdk_pages: list[dict[str, Any]] = []
        if args.include_sdk:
            sdk_pages_all = crawl_sdk_pages(client, sdk_root)
            sdk_links, sdk_pages, platform_sdk_pages = link_sdk_pages(sdk_pages_all, records)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "services_root": services_root,
        "authoritative_docs": AUTHORITATIVE_DOCS,
        "folders": folders,
        "folder_index": folder_index,
        "services": records,
        "sdk_pages": sdk_pages if args.include_sdk else [],
        "sdk_pages_all": sdk_pages_all if args.include_sdk else [],
        "implemented_sdk_pages": sdk_pages if args.include_sdk else [],
        "sdk_links": sdk_links if args.include_sdk else [],
        "platform_capabilities_not_implemented": platform_sdk_pages if args.include_sdk else [],
        "unmatched_sdk_pages": platform_sdk_pages if args.include_sdk else [],
        "failures": failures,
        "stats": {
            "folder_count": len(folders),
            "service_count": len(records),
            "failure_count": len(failures),
            "sdk_page_count": len(sdk_pages) if args.include_sdk else 0,
            "sdk_page_all_count": len(sdk_pages_all) if args.include_sdk else 0,
            "sdk_link_count": len(sdk_links) if args.include_sdk else 0,
            "sdk_platform_only_count": len(platform_sdk_pages) if args.include_sdk else 0,
            "sdk_unmatched_count": len(platform_sdk_pages) if args.include_sdk else 0,
        },
    }

    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_markdown_summary(out_md, payload)
    layer_count = write_flat_jsonl(out_jsonl, records, sdk_links)

    print(f"Wrote JSON catalog: {out_json}")
    print(f"Wrote markdown summary: {out_md}")
    print(f"Wrote JSONL index: {out_jsonl} ({layer_count} layer records)")
    print(
        f"Crawl complete: folders={len(folders)} services={len(records)} "
        f"sdk_pages={len(sdk_pages) if args.include_sdk else 0} "
        f"sdk_pages_all={len(sdk_pages_all) if args.include_sdk else 0} failures={len(failures)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
