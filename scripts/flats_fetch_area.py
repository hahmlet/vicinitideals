"""Fetch one Portland Maps polygon or polyline layer as an area GeoJSON file."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flats.ingest.acquire import (  # noqa: E402
    AcquireError,
    _USER_AGENT,
    _arcgis_meta,
    _fetch_arcgis,
)
from flats.ingest.sources import Dataset, Geometry, Kind, Provides  # noqa: E402


class _FeatureCollector:
    def __init__(self, feature_source: str) -> None:
        self.features: list[dict[str, Any]] = []
        self.feature_source = feature_source

    def add(self, feature: dict[str, Any]) -> None:
        feature.setdefault("properties", {})["source"] = self.feature_source
        self.features.append(feature)


def fetch_area(
    service_url: str,
    layer_id: int,
    where: str,
    output_path: Path,
    note: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Fetch a layer using the shared ArcGIS acquire and geometry helpers."""
    url = f"{service_url.rstrip('/')}/{layer_id}"
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing area file: {output_path}")

    owned_client = client is None
    http = client or httpx.Client(
        headers={"User-Agent": _USER_AGENT},
        timeout=60.0,
    )
    try:
        metadata_ds = Dataset(
            key=output_path.stem,
            kind=Kind.arcgis,
            label=output_path.stem,
            provides=Provides.overlay,
            url=url,
            serves=("or/multnomah/portland",),
            fields=("placeholder",),
            where=where,
        )
        metadata = _arcgis_meta(http, metadata_ds)
        geometry_types = {
            "esriGeometryPolygon": Geometry.polygon,
            "esriGeometryPolyline": Geometry.polyline,
        }
        geometry = geometry_types.get(metadata.get("geometryType"))
        if geometry is None:
            raise AcquireError(
                f"unsupported ArcGIS geometry type: {metadata.get('geometryType')!r}"
            )
        fields = tuple(
            field["name"]
            for field in metadata.get("fields", [])
            if isinstance(field, dict)
            and isinstance(field.get("name"), str)
            and field["name"].upper() != "OBJECTID"
            and not field["name"].upper().startswith("SHAPE")
        )
        if not fields:
            raise AcquireError("the layer has no attribute fields after excluding OBJECTID and Shape*")

        dataset = metadata_ds.model_copy(update={"geometry": geometry, "fields": fields})
        fetched = date.today().isoformat()
        feature_source = f"Portland Maps {url}, fetched {fetched}; {note}"
        collector = _FeatureCollector(feature_source)
        missed = _fetch_arcgis(http, dataset, 2913, collector, lambda _: None)
        if missed:
            raise AcquireError(f"failed to fetch objectIds: {', '.join(map(str, missed))}")

        document = {
            "type": "FeatureCollection",
            "name": f"pdx_{output_path.stem.replace('-', '_')}",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::2913"},
            },
            "source": {
                "url": url,
                "where": where,
                "fields": ",".join(fields),
                "fetched": fetched,
                "note": note,
                "count": len(collector.features),
            },
            "features": collector.features,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        part = output_path.with_name(output_path.name + ".part")
        if part.exists():
            raise FileExistsError(f"refusing to overwrite existing temporary file: {part}")
        try:
            part.write_text(
                json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            part.replace(output_path)
        finally:
            part.unlink(missing_ok=True)
        return document
    finally:
        if owned_client:
            http.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-url", required=True, help="ArcGIS MapServer service URL")
    parser.add_argument("--layer-id", required=True, type=int)
    parser.add_argument("--where", default="1=1")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--note", required=True)
    args = parser.parse_args(argv)
    document = fetch_area(args.service_url, args.layer_id, args.where, args.out, args.note)
    print(f"{args.out}: {document['source']['count']} features")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
