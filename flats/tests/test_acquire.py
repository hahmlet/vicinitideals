"""The acquire stage: a dated, checksummed copy of what the registry names.

Every server here is a fake behind ``httpx.MockTransport``: an ArcGIS layer
that answers metadata, an id query and batched feature queries; and a ZIP on a
host that honours Range requests, built in memory from a shapefile pyshp
wrote. What is driven is the stage's contract, not the county's data -- a
declared field the source lacks is a refusal with no file behind it, a hole in
a polygon survives both readers, the filter keeps the counties it names, the
where clause travels verbatim, and a second run touches nothing already there.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
import shapefile

from flats.ingest import acquire as stage
from flats.ingest.acquire import (
    Refused,
    acquire,
    describe,
    esri_polygon,
    latest_snapshot,
    parse_filter,
    read_manifest,
    snapshot_dir,
)
from flats.ingest.sources import load_pipeline

pytestmark = pytest.mark.unit

ARCGIS = "https://example.gov/arcgis/rest/services/Zoning/MapServer/0"
FEMA_WHERE = "\"DFIRM_ID\" = '41051C'"
RLIS = "https://example.gov/sharing/rest/content/items/abc/data"


def registry(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "pipeline.yaml"
    p.write_text("working_srid: 2913\ndisplay_srid: 4326\n" + body, encoding="utf-8")
    return p


ARCGIS_ONLY = f"""
jurisdictions:
  or/multnomah/portland: true
datasets:
  zoning_portland:
    kind: arcgis
    label: Portland zoning
    provides: zoning
    url: {ARCGIS}
    zone_field: ZONE
    fields: [ZONE, OVRLY]
    serves: [or/multnomah/portland]
"""


# --- fakes -----------------------------------------------------------------


# Esri rings: shells clockwise, holes anticlockwise.
SQUARE_CW = [[0, 0], [0, 100], [100, 100], [100, 0], [0, 0]]
HOLE_CCW = [[40, 40], [60, 40], [60, 60], [40, 60], [40, 40]]


class ArcGIS:
    """A layer with ``n`` features; records every request it is asked."""

    def __init__(self, n: int = 5, fields: tuple[str, ...] = ("OBJECTID", "ZONE", "OVRLY")) -> None:
        self.n = n
        self.fields = fields
        self.requests: list[httpx.Request] = []
        self.fail_ids: set[int] = set()
        self.metadata_error: str | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url).split("?", 1)[0]
        if url == ARCGIS:
            if self.metadata_error:
                return httpx.Response(200, json={"error": {"message": self.metadata_error}})
            return httpx.Response(
                200,
                json={"fields": [{"name": f} for f in self.fields], "maxRecordCount": 1000},
            )
        assert url == f"{ARCGIS}/query", url
        params = dict(request.url.params) if request.method == "GET" else _form(request)
        if params.get("returnIdsOnly") == "true":
            return httpx.Response(
                200, json={"objectIdFieldName": "OBJECTID", "objectIds": list(range(1, self.n + 1))}
            )
        ids = [int(i) for i in params["objectIds"].split(",")]
        if any(i in self.fail_ids for i in ids):
            return httpx.Response(200, json={"error": {"message": "Unable to complete operation."}})
        feats = []
        for i in ids:
            rings = [SQUARE_CW, HOLE_CCW] if i == 1 else [[[c + i for c in pt] for pt in SQUARE_CW]]
            feats.append({"attributes": {"OBJECTID": i, "ZONE": f"R{i}", "OVRLY": None}, "geometry": {"rings": rings}})
        return httpx.Response(200, json={"features": feats})


def _form(request: httpx.Request) -> dict[str, str]:
    return dict(httpx.QueryParams(request.content.decode()))


def shapefile_zip(records: list[tuple[str, str, list[list[tuple[float, float]]]]]) -> bytes:
    """A ZIP holding TAXLOTS/taxlots_public.{shp,shx,dbf} written by pyshp."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    w.field("TLID", "C", size=12)
    w.field("COUNTY", "C", size=1)
    w.field("LANDVAL", "N", size=12, decimal=0)
    for tlid, county, rings in records:
        w.poly(rings)
        w.record(tlid, county, 1000)
    w.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # A member bigger than the tail the stage reads first, so that only a
        # reader that asks for members by offset can finish under the archive's
        # size (the real one is 1.4 GB; this one is 400 KB).
        z.writestr("README.txt", b"Metro RLIS quarterly " * 20_000, compress_type=zipfile.ZIP_STORED)
        z.writestr("TAXLOTS/taxlots_public.shp", shp.getvalue())
        z.writestr("TAXLOTS/taxlots_public.shx", shx.getvalue())
        z.writestr("TAXLOTS/taxlots_public.dbf", dbf.getvalue())
        z.writestr("STREETS/streets.shp", b"not a shapefile")
        z.writestr("2026_08_RLIS_QuarterlyUpdates_ReleaseNotes.pdf", b"%PDF-1.4 release notes")
    return buf.getvalue()


class RangeHost:
    """Serves one file, honouring Range; counts bytes actually sent."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.sent = 0
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not request.url.path.endswith("/data"):
            # The portal item itself (the URL without its /data): what the
            # archive is called and when it last changed.
            return httpx.Response(
                200,
                json={"title": "RLIS Open Data Updates from Last Quarter", "name": "rlis_free_quarter.zip",
                      "modified": 1787768567000, "size": len(self.body)},
            )
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": str(len(self.body))})
        rng = request.headers.get("range")
        assert rng, "the acquire stage must never ask for the whole archive"
        m = re.fullmatch(r"bytes=(\d+)-(\d+)", rng)
        assert m
        start, end = int(m.group(1)), min(int(m.group(2)), len(self.body) - 1)
        chunk = self.body[start : end + 1]
        self.sent += len(chunk)
        return httpx.Response(
            206,
            content=chunk,
            headers={"content-range": f"bytes {start}-{end}/{len(self.body)}"},
        )


def client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def quiet(_: str) -> None:
    pass


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stage, "_sleep", lambda _s: None)


def features_of(path: Path) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["type"] == "FeatureCollection"
    return doc["features"]


# --- ArcGIS ----------------------------------------------------------------


def test_an_arcgis_layer_lands_in_the_working_crs_with_its_fields(tmp_path: Path) -> None:
    server = ArcGIS(n=5)
    pipeline = load_pipeline(registry(tmp_path, ARCGIS_ONLY))
    out = tmp_path / "2026-09-18"

    doc = acquire(pipeline, out, client=client(server), log=quiet)

    entry = doc["datasets"]["zoning_portland"]
    assert entry["status"] == "acquired"
    assert entry["features"] == 5
    assert entry["srid"] == 2913
    assert entry["fields"] == {"declared": ["ZONE", "OVRLY"], "present": ["OBJECTID", "ZONE", "OVRLY"], "checked": True}
    feats = features_of(out / "zoning_portland.geojson")
    assert [f["properties"]["ZONE"] for f in feats] == ["R1", "R2", "R3", "R4", "R5"]
    # The server reprojects: every feature query asked for the working CRS
    # and only the declared fields.
    queries = [_form(r) for r in server.requests if r.method == "POST"]
    assert queries and all(q["outSR"] == "2913" and q["outFields"] == "ZONE,OVRLY" for q in queries)
    assert json.loads((out / "zoning_portland.geojson").read_text())["srid"] == 2913


def test_a_polygon_with_a_courtyard_stays_one_polygon_with_a_hole(tmp_path: Path) -> None:
    pipeline = load_pipeline(registry(tmp_path, ARCGIS_ONLY))
    out = tmp_path / "2026-09-18"

    acquire(pipeline, out, client=client(ArcGIS(n=1)), log=quiet)

    geom = features_of(out / "zoning_portland.geojson")[0]["geometry"]
    assert geom["type"] == "MultiPolygon"
    assert len(geom["coordinates"]) == 1, "the hole was split off as a second lot"
    assert len(geom["coordinates"][0]) == 2


def test_a_hole_no_shell_contains_is_kept_rather_than_dropped() -> None:
    # Esri publishes the odd anticlockwise ring that is not inside anything.
    # Dropping it loses a lot; keeping it as a shell reads the lot large,
    # which is the failure that can be seen.
    geom = esri_polygon({"rings": [SQUARE_CW, [[p[0] + 500, p[1] + 500] for p in HOLE_CCW]]})

    assert geom and len(geom["coordinates"]) == 2


def test_a_declared_field_the_layer_lacks_is_refused_with_no_file(tmp_path: Path) -> None:
    server = ArcGIS(n=5, fields=("OBJECTID", "ZONE"))  # no OVRLY
    pipeline = load_pipeline(registry(tmp_path, ARCGIS_ONLY))
    out = tmp_path / "2026-09-18"

    doc = acquire(pipeline, out, client=client(server), log=quiet)

    entry = doc["datasets"]["zoning_portland"]
    assert entry["status"] == "refused"
    assert "OVRLY" in entry["error"]
    assert not (out / "zoning_portland.geojson").exists()
    assert not list(out.glob("*.part"))
    # Refusal is decided from the metadata alone; no feature was asked for.
    assert all(r.method == "GET" for r in server.requests)


def test_the_where_clause_travels_verbatim(tmp_path: Path) -> None:
    # FEMA's NFHL rejects a reworded where clause intermittently; the registry
    # keeps the exact quoting and the fetch must not touch it.
    server = ArcGIS(n=2, fields=("OBJECTID", "FLD_ZONE"))
    body = f"""
jurisdictions:
  or/multnomah/portland: true
datasets:
  overlay_fema_flood:
    kind: arcgis
    label: FEMA
    provides: overlay
    url: {ARCGIS}
    fields: [FLD_ZONE]
    where: '"DFIRM_ID" = ''41051C'''
    serves: [or/multnomah]
"""
    pipeline = load_pipeline(registry(tmp_path, body))

    acquire(pipeline, tmp_path / "2026-09-18", client=client(server), log=quiet)

    ids = [r for r in server.requests if r.url.params.get("returnIdsOnly") == "true"]
    assert ids and ids[0].url.params["where"] == FEMA_WHERE


def test_a_feature_the_server_cannot_serve_is_named_not_dropped(tmp_path: Path) -> None:
    server = ArcGIS(n=5)
    server.fail_ids = {3}
    pipeline = load_pipeline(registry(tmp_path, ARCGIS_ONLY))
    out = tmp_path / "2026-09-18"

    doc = acquire(pipeline, out, client=client(server), log=quiet)

    entry = doc["datasets"]["zoning_portland"]
    assert entry["status"] == "acquired"
    assert entry["features"] == 4
    assert entry["unfetched_ids"] == [3]
    assert [f["properties"]["OBJECTID"] for f in features_of(out / "zoning_portland.geojson")] == [1, 2, 4, 5]


def test_a_server_error_is_a_failure_with_no_file(tmp_path: Path) -> None:
    server = ArcGIS(n=5)
    server.metadata_error = "Service unavailable"
    pipeline = load_pipeline(registry(tmp_path, ARCGIS_ONLY))
    out = tmp_path / "2026-09-18"

    doc = acquire(pipeline, out, client=client(server), log=quiet)

    entry = doc["datasets"]["zoning_portland"]
    assert entry["status"] == "failed"
    assert "Service unavailable" in entry["error"]
    assert not (out / "zoning_portland.geojson").exists()


def test_one_dataset_failing_does_not_stop_the_next(tmp_path: Path) -> None:
    body = ARCGIS_ONLY + f"""
  zoning_gresham:
    kind: arcgis
    label: Gresham zoning
    provides: zoning
    url: {ARCGIS}
    zone_field: ZONE
    fields: [ZONE, DISTRICT]
    serves: [or/multnomah/portland]
"""
    pipeline = load_pipeline(registry(tmp_path, body))
    out = tmp_path / "2026-09-18"

    doc = acquire(pipeline, out, client=client(ArcGIS(n=2)), log=quiet)

    assert doc["datasets"]["zoning_gresham"]["status"] == "refused"  # no DISTRICT on the fake
    assert doc["datasets"]["zoning_portland"]["status"] == "acquired"
    on_disk = read_manifest(out)
    assert on_disk["datasets"].keys() == {"zoning_portland", "zoning_gresham"}


# --- Metro RLIS ---------------------------------------------------------------


RLIS_ONLY = f"""
jurisdictions:
  or/multnomah/portland: true
datasets:
  rlis_taxlots:
    kind: rlis_zip
    label: Metro RLIS taxlots
    provides: lots
    url: {RLIS}
    member: TAXLOTS/taxlots_public.shp
    filter: COUNTY in (M, C)
    fields: [TLID, COUNTY]
    serves: [or/multnomah, or/clackamas]
"""

# Shapefile rings: outer clockwise, hole anticlockwise.
OUTER = [(0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0), (0.0, 0.0)]
INNER = [(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0), (40.0, 40.0)]
LOTS = [
    ("R100", "M", [OUTER, INNER]),
    ("R200", "C", [[(p[0] + 200, p[1]) for p in OUTER]]),
    ("R300", "W", [[(p[0] + 400, p[1]) for p in OUTER]]),
]


def test_an_rlis_member_is_pulled_by_range_and_filtered_to_our_counties(tmp_path: Path) -> None:
    host = RangeHost(shapefile_zip(LOTS))
    pipeline = load_pipeline(registry(tmp_path, RLIS_ONLY))
    out = tmp_path / "2026-09-18"

    doc = acquire(pipeline, out, client=client(host), log=quiet)

    entry = doc["datasets"]["rlis_taxlots"]
    assert entry["status"] == "acquired", entry
    feats = features_of(out / "rlis_taxlots.geojson")
    assert [f["properties"] for f in feats] == [
        {"TLID": "R100", "COUNTY": "M"},
        {"TLID": "R200", "COUNTY": "C"},
    ], "Washington County was kept, or LANDVAL leaked past the declared fields"
    assert entry["fields"]["present"] == ["TLID", "COUNTY", "LANDVAL"]
    # Only the two members' bytes plus the archive's tail crossed the wire —
    # never the archive (which here also carries a streets member and a README
    # bigger than the tail).
    assert host.sent < len(host.body)
    assert all(
        r.method == "HEAD" or r.headers.get("range") or not r.url.path.endswith("/data")
        for r in host.requests
    ), "something asked the archive for more than a range"


def test_the_manifest_says_which_release_the_archive_was(tmp_path: Path) -> None:
    # The portal's title is the same every quarter; the release-notes member
    # is not. A later check reads this record to tell a new release from the
    # one the copy was taken from.
    host = RangeHost(shapefile_zip(LOTS))
    pipeline = load_pipeline(registry(tmp_path, RLIS_ONLY))
    out = tmp_path / "2026-09-18"

    doc = acquire(pipeline, out, client=client(host), log=quiet)

    archive = doc["archives"][RLIS]
    assert archive["release"] == "2026_08"
    assert archive["modified"] == "2026-08-26"
    assert archive["size"] == len(host.body)
    assert archive["name"] == "rlis_free_quarter.zip"
    assert any(line.startswith(f"archive {RLIS}: release 2026_08") for line in describe(doc))


def test_a_portal_that_will_not_say_does_not_cost_the_members(tmp_path: Path) -> None:
    body = shapefile_zip(LOTS)
    host = RangeHost(body)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/data"):
            return httpx.Response(500, text="portal down")
        return host(request)

    pipeline = load_pipeline(registry(tmp_path, RLIS_ONLY))
    out = tmp_path / "2026-09-18"

    doc = acquire(pipeline, out, client=client(handler), log=quiet)

    assert doc["datasets"]["rlis_taxlots"]["status"] == "acquired"
    archive = doc["archives"][RLIS]
    assert archive["release"] == "2026_08" and archive["size"] == len(body)
    assert "500" in archive["error"]


def test_a_shapefile_hole_is_read_as_a_hole(tmp_path: Path) -> None:
    # The registry note on rlis_taxlots: the delta helper's converter split
    # interior rings into separate polygons, inflating lot areas.
    host = RangeHost(shapefile_zip(LOTS))
    pipeline = load_pipeline(registry(tmp_path, RLIS_ONLY))
    out = tmp_path / "2026-09-18"

    acquire(pipeline, out, client=client(host), log=quiet)

    geom = features_of(out / "rlis_taxlots.geojson")[0]["geometry"]
    assert geom["type"] == "Polygon"
    assert len(geom["coordinates"]) == 2


def test_a_member_missing_a_declared_field_is_refused(tmp_path: Path) -> None:
    host = RangeHost(shapefile_zip(LOTS))
    body = RLIS_ONLY.replace("fields: [TLID, COUNTY]", "fields: [TLID, COUNTY, SITEADDR]")
    pipeline = load_pipeline(registry(tmp_path, body))
    out = tmp_path / "2026-09-18"

    doc = acquire(pipeline, out, client=client(host), log=quiet)

    entry = doc["datasets"]["rlis_taxlots"]
    assert entry["status"] == "refused"
    assert "SITEADDR" in entry["error"]
    assert not (out / "rlis_taxlots.geojson").exists()


def test_a_member_not_in_the_archive_is_a_failure(tmp_path: Path) -> None:
    host = RangeHost(shapefile_zip(LOTS))
    body = RLIS_ONLY.replace("TAXLOTS/taxlots_public.shp", "LAND/zoning.shp")
    pipeline = load_pipeline(registry(tmp_path, body))

    doc = acquire(pipeline, tmp_path / "2026-09-18", client=client(host), log=quiet)

    entry = doc["datasets"]["rlis_taxlots"]
    assert entry["status"] == "failed"
    assert "LAND/zoning.shp" in entry["error"]


def test_the_filter_grammar_is_one_shape() -> None:
    assert parse_filter("COUNTY in (M, C)") == ("COUNTY", frozenset({"M", "C"}))
    assert parse_filter("county IN ('m','c')") == ("county", frozenset({"M", "C"}))
    assert parse_filter(None) is None
    with pytest.raises(Refused):
        parse_filter("COUNTY = 'M'")


# --- the snapshot ----------------------------------------------------------------


def test_a_second_run_touches_nothing_already_there(tmp_path: Path) -> None:
    pipeline = load_pipeline(registry(tmp_path, ARCGIS_ONLY))
    out = tmp_path / "2026-09-18"
    first = ArcGIS(n=3)
    acquire(pipeline, out, client=client(first), log=quiet)
    sha = read_manifest(out)["datasets"]["zoning_portland"]["sha256"]

    second = ArcGIS(n=3)
    doc = acquire(pipeline, out, client=client(second), log=quiet)

    assert second.requests == [], "the snapshot was re-fetched"
    assert doc["datasets"]["zoning_portland"]["status"] == "present"
    assert doc["datasets"]["zoning_portland"]["sha256"] == sha


def test_force_re_fetches(tmp_path: Path) -> None:
    pipeline = load_pipeline(registry(tmp_path, ARCGIS_ONLY))
    out = tmp_path / "2026-09-18"
    acquire(pipeline, out, client=client(ArcGIS(n=3)), log=quiet)

    second = ArcGIS(n=4)
    doc = acquire(pipeline, out, client=client(second), force=True, log=quiet)

    assert second.requests
    assert doc["datasets"]["zoning_portland"]["features"] == 4


def test_an_edited_registry_entry_re_fetches_without_force(tmp_path: Path) -> None:
    # The file on disk was taken with yesterday's field list; a snapshot that
    # kept it would carry columns the registry no longer describes.
    out = tmp_path / "2026-09-18"
    acquire(load_pipeline(registry(tmp_path, ARCGIS_ONLY)), out, client=client(ArcGIS(n=3)), log=quiet)

    edited = load_pipeline(registry(tmp_path, ARCGIS_ONLY.replace("[ZONE, OVRLY]", "[ZONE]")))
    second = ArcGIS(n=3)
    doc = acquire(edited, out, client=client(second), log=quiet)

    assert second.requests
    assert doc["datasets"]["zoning_portland"]["fields"]["declared"] == ["ZONE"]


def test_terrain_is_deferred_not_fetched(tmp_path: Path) -> None:
    body = ARCGIS_ONLY + """
  dem_3dep:
    kind: tnm_dem
    label: USGS 3DEP
    provides: terrain
    url: https://tnmaccess.nationalmap.gov/api/v1/products
    native_srid: 4326
    serves: [or/multnomah]
"""
    pipeline = load_pipeline(registry(tmp_path, body))
    server = ArcGIS(n=1)

    doc = acquire(pipeline, tmp_path / "2026-09-18", client=client(server), log=quiet)

    assert doc["datasets"]["dem_3dep"]["status"] == "deferred"
    assert not (tmp_path / "2026-09-18" / "dem_3dep.geojson").exists()
    assert all(str(r.url).startswith(ARCGIS) for r in server.requests)


def test_the_manifest_names_the_snapshot_and_reads_back(tmp_path: Path) -> None:
    pipeline = load_pipeline(registry(tmp_path, ARCGIS_ONLY))
    out = snapshot_dir("2026-09-18", tmp_path)

    acquire(pipeline, out, client=client(ArcGIS(n=2)), log=quiet)

    doc = read_manifest(out)
    assert doc["snapshot"] == "2026-09-18"
    assert doc["working_srid"] == 2913
    entry = doc["datasets"]["zoning_portland"]
    assert entry["retrieved_at"].endswith("Z")
    assert entry["file"] == "zoning_portland.geojson"
    assert entry["bytes"] == (out / "zoning_portland.geojson").stat().st_size
    assert latest_snapshot(tmp_path) == out
    lines = describe(doc)
    assert lines[0] == "snapshot 2026-09-18 in EPSG:2913"
    assert lines[1].startswith("zoning_portland: acquired -- 2 features")


def test_a_dataset_the_registry_dropped_is_retired_not_deleted(tmp_path: Path) -> None:
    # The first real snapshot found the RLIS ZIP no longer carries ugb.shp and
    # the registry moved the boundary to Metro's service under a new key. The
    # old entry must stop reading as part of the snapshot without anything
    # here deleting a file.
    out = tmp_path / "2026-09-18"
    both = ARCGIS_ONLY + f"""
  zoning_gresham:
    kind: arcgis
    label: Gresham zoning
    provides: zoning
    url: {ARCGIS}
    zone_field: ZONE
    fields: [ZONE]
    serves: [or/multnomah/portland]
"""
    acquire(load_pipeline(registry(tmp_path, both)), out, client=client(ArcGIS(n=2)), log=quiet)

    doc = acquire(load_pipeline(registry(tmp_path, ARCGIS_ONLY)), out, client=client(ArcGIS(n=2)), log=quiet)

    assert doc["datasets"]["zoning_gresham"]["status"] == "retired"
    assert (out / "zoning_gresham.geojson").exists()
    assert doc["datasets"]["zoning_portland"]["status"] == "present"
    assert any(line.startswith("zoning_gresham: retired") for line in describe(doc))


def test_a_snapshot_is_named_by_its_date(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        snapshot_dir("latest", tmp_path)


def test_the_shipped_registry_is_wholly_dispatchable() -> None:
    # Every kind in the registry has a branch here; a new kind added to
    # sources.py without one would be silently skipped with no manifest entry.
    pipeline = load_pipeline()
    kinds = {ds.kind for ds in pipeline.datasets.values()}
    assert kinds == {stage.Kind.arcgis, stage.Kind.rlis_zip, stage.Kind.tnm_dem}
    for ds in pipeline.datasets.values():
        if ds.filter:
            parse_filter(ds.filter)
