"""The monthly source check: what it finds, and what it refuses to conclude.

Fake services answer the two requests the probe makes per ArcGIS layer and
the one it makes per RLIS archive. Nothing here downloads a feature.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx

from flats.ingest.acquire import _spec_sha
from flats.ingest.probe import Finding, probe, summarize
from flats.ingest.sources import load_pipeline

ZONING = "https://example.gov/arcgis/rest/services/Zoning/MapServer/0"
SEWER = "https://example.gov/arcgis/rest/services/Sewer/FeatureServer/0"
RLIS = "https://example.gov/sharing/rest/content/items/abc/data"

REGISTRY = f"""
working_srid: 2913
display_srid: 4326
jurisdictions:
  or/multnomah/portland: true
datasets:
  rlis_taxlots:
    kind: rlis_zip
    label: Metro RLIS taxlots
    provides: lots
    url: {RLIS}
    member: TAXLOTS/taxlots_public.shp
    fields: [TLID, COUNTY]
    serves: [or/multnomah, or/clackamas]
  zoning_portland:
    kind: arcgis
    label: Portland zoning
    provides: zoning
    url: {ZONING}
    fields: [ZONE, OVRLY]
    zone_field: ZONE
    where: "CITY = 'Portland'"
    serves: [or/multnomah/portland]
  util_sewer_portland:
    kind: arcgis
    label: Portland sewer mains
    provides: utility
    url: {SEWER}
    fields: [DIAMETER]
    geometry: polyline
    serves: [or/multnomah/portland]
"""


def pipeline(tmp_path: Path):
    p = tmp_path / "pipeline.yaml"
    p.write_text(REGISTRY, encoding="utf-8")
    return load_pipeline(p)


def manifest(pipe, *, zoning_features: int = 15_700, sewer_features: int = 50_219) -> dict[str, Any]:
    ds = pipe.datasets
    return {
        "snapshot": "2026-09-18",
        "working_srid": 2913,
        "archives": {RLIS: {"release": "2026_08", "modified": "2026-08-26", "size": 1_067_276_384, "members": 426}},
        "datasets": {
            "rlis_taxlots": {"status": "acquired", "features": 453_782, "spec_sha256": _spec_sha(ds["rlis_taxlots"])},
            "zoning_portland": {"status": "acquired", "features": zoning_features, "spec_sha256": _spec_sha(ds["zoning_portland"])},
            "util_sewer_portland": {
                "status": "present", "features": sewer_features, "unfetched_ids": [7],
                "spec_sha256": _spec_sha(ds["util_sewer_portland"]),
            },
        },
    }


class Services:
    """The county's side, as the probe sees it: metadata, counts, the portal item."""

    def __init__(self) -> None:
        self.fields = {ZONING: ["OBJECTID", "ZONE", "OVRLY", "CITY"], SEWER: ["OBJECTID", "DIAMETER"]}
        self.counts = {ZONING: 15_700, SEWER: 50_220}
        self.item = {"title": "RLIS", "name": "rlis_free_quarter.zip", "modified": 1787768567000, "size": 1_067_276_384}
        self.down: set[str] = set()
        self.gone: set[str] = set()
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url).split("?", 1)[0]
        base = url[: -len("/query")] if url.endswith("/query") else url
        if base in self.down:
            raise httpx.ConnectError("no route to host", request=request)
        if base in self.gone:
            return httpx.Response(200, json={"error": {"code": 400, "message": "Invalid URL"}})
        if url.endswith("/query"):
            assert request.url.params.get("returnCountOnly") == "true", "the probe must not ask for features"
            return httpx.Response(200, json={"count": self.counts[base]})
        if url.endswith("/items/abc"):
            return httpx.Response(200, json=self.item)
        if base in self.fields:
            return httpx.Response(200, json={"name": "layer", "fields": [{"name": n} for n in self.fields[base]]})
        return httpx.Response(404, text="no such thing")


def client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def by_key(findings: list[Finding]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in findings:
        out.setdefault(f.key, []).append(f.finding)
    return out


def test_an_unchanged_county_is_all_ok_and_costs_one_or_two_requests_a_layer(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    county = Services()

    found = probe(pipe, manifest(pipe), client(county))

    assert by_key(found) == {"zoning_portland": ["ok"], "util_sewer_portland": ["ok"], RLIS: ["ok"]}
    assert summarize(found) == "ok"
    # One item request, and metadata + count per layer. Nothing else.
    assert len(county.requests) == 1 + 2 * 2
    assert not any("returnGeometry" in str(r.url) or "outFields" in str(r.url) for r in county.requests)
    # The count is asked under the registry's own where clause.
    counted = [r for r in county.requests if str(r.url.path).endswith("/query") and "Zoning" in str(r.url)]
    assert counted and counted[0].url.params["where"] == "CITY = 'Portland'"


def test_a_service_that_moved_is_moved_not_unreachable(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    county = Services()
    county.gone.add(SEWER)

    found = by_key(probe(pipe, manifest(pipe), client(county)))

    assert found["util_sewer_portland"] == ["moved"]
    assert found["zoning_portland"] == ["ok"]


def test_a_service_that_did_not_answer_is_unreachable_not_moved(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    county = Services()
    county.down.add(ZONING)

    found = probe(pipe, manifest(pipe), client(county))

    assert by_key(found)["zoning_portland"] == ["unreachable"]
    assert not any(f.changed for f in found if f.key == "zoning_portland")
    assert summarize(found) == "warn"


def test_a_declared_field_no_longer_published_is_named(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    county = Services()
    county.fields[ZONING] = ["OBJECTID", "ZONE_CODE", "OVRLY", "CITY"]

    found = probe(pipe, manifest(pipe), client(county))

    zoning = [f for f in found if f.key == "zoning_portland"]
    assert [f.finding for f in zoning] == ["fields_missing"]
    assert "ZONE" in zoning[0].detail and "OVRLY" not in zoning[0].detail


def test_a_count_outside_tolerance_is_drift_and_a_rezoning_is_not(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    county = Services()
    county.counts[ZONING] = 18_258  # the regional fabric under the city's name

    found = probe(pipe, manifest(pipe), client(county))
    zoning = [f for f in found if f.key == "zoning_portland"]
    assert [f.finding for f in zoning] == ["count_drift"]
    assert "15,700" in zoning[0].detail and "18,258" in zoning[0].detail

    county.counts[ZONING] = 15_740  # forty polygons: a rezoning
    found = probe(pipe, manifest(pipe), client(county))
    assert by_key(found)["zoning_portland"] == ["ok"]


def test_unfetched_features_count_toward_what_the_copy_saw(tmp_path: Path) -> None:
    # The manifest holds 50,219 features plus one it could not fetch; the
    # service says 50,220. That is not drift.
    pipe = pipeline(tmp_path)
    found = probe(pipe, manifest(pipe), client(Services()))
    assert by_key(found)["util_sewer_portland"] == ["ok"]


def test_a_registry_entry_edited_since_the_copy_is_said(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    doc = manifest(pipe)
    doc["datasets"]["zoning_portland"]["spec_sha256"] = "0" * 64

    found = by_key(probe(pipe, doc, client(Services())))

    assert found["zoning_portland"] == ["registry_changed", "ok"]


def test_a_dataset_added_after_the_copy_is_said_without_a_request(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    doc = manifest(pipe)
    del doc["datasets"]["util_sewer_portland"]
    county = Services()

    found = by_key(probe(pipe, doc, client(county)))

    assert found["util_sewer_portland"] == ["registry_changed"]
    assert not any("Sewer" in str(r.url) for r in county.requests)


def test_a_new_rlis_release_on_the_portal_is_seen(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    county = Services()
    county.item = {**county.item, "modified": 1795000000000, "size": 1_100_000_000}

    found = probe(pipe, manifest(pipe), client(county))

    archive = [f for f in found if f.key == RLIS]
    assert [f.finding for f in archive] == ["new_release"]
    assert "2026-08-26 -> 2026-11-18" in archive[0].detail
    assert "release 2026_08" in archive[0].detail


def test_a_copy_that_recorded_no_archive_identity_is_not_accused(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    doc = manifest(pipe)
    doc.pop("archives")
    county = Services()

    found = [f for f in probe(pipe, doc, client(county)) if f.key == RLIS]

    assert [f.finding for f in found] == ["ok"]
    assert "recorded no archive identity" in found[0].detail
    assert not any("items/abc" in str(r.url) for r in county.requests)


def test_every_finding_is_plain_data_for_a_database_row(tmp_path: Path) -> None:
    pipe = pipeline(tmp_path)
    found = probe(pipe, manifest(pipe), client(Services()))
    rows = [f.as_dict() for f in found]
    assert json.loads(json.dumps(rows)) == rows
    assert all(set(r) == {"key", "finding", "detail"} for r in rows)
