"""Acquire: a dated, checksummed copy of every source the registry names.

The first stage of the offline source Steph asked for on 2026-09-17 ("bridge
from the county map for now, but we will need an authoritative offline
source"). :mod:`flats.ingest.quadfit` reads the county map as quadfit left it;
this module reads the county itself. Each run writes one snapshot directory,
``data/flats/sources/<YYYY-MM-DD>/``, holding one GeoJSON file per dataset in
``flats/config/pipeline.yaml`` and a ``manifest.json`` that says, per dataset,
where it came from, when, what it hashed to, how many features it holds, and
which declared fields the service actually had. A verdict can then be traced
to the map it was read from, which is the property the bridge lacks: quadfit's
raw directory is undated and overwritten in place.

Where the normalized copy of a snapshot lands (``flats.lots`` in Postgres, or
files beside the snapshot) is HUMAN_TODO 20 and is not decided here. Both
answers need this stage; neither changes it.

**What it fetches.** ArcGIS layers by objectId, in batches, with the server
reprojecting to the working CRS (``outSR``) and the dataset's ``where`` sent
verbatim -- the FEMA layer rejects any rewording of its own. Metro RLIS
members straight out of the quarterly ZIP by HTTP range request: the central
directory first, then only the ``.shp`` and ``.dbf`` of the member asked for,
never the 1.4 GB archive. Shapefile rings are read through pyshp's
``__geo_interface__`` so a lot with a courtyard stays one polygon with a
hole; Esri rings are sorted by orientation for the same reason. Every file is
written in the working CRS and says so.

**What it refuses.** A dataset whose declared fields are not on the service is
recorded as ``refused`` and no file is written: a zoning layer without its
zone field is geometry nobody can zone, and a file that exists would be read
as one. A dataset the server would not give up (an error on every retry) is
``failed``, with the error in the manifest. Terrain (``tnm_dem``) is
``deferred`` -- tiles are not a vector layer and the slope stage that needs
them is not built.

**What it does not do.** Nothing is normalized, joined or assigned; the files
are the sources as published, with the columns the registry asked for. A
second run against the same snapshot directory touches nothing that is
already there unless ``--force`` is given or the dataset's registry entry has
changed since it was fetched.

Run::

    uv run python -m flats.ingest.acquire                       # today's snapshot
    uv run python -m flats.ingest.acquire --snapshot 2026-09-18 --keys rlis_taxlots zoning_portland
    uv run python -m flats.ingest.acquire --show 2026-09-18     # read a manifest back
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import re
import struct
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx
import shapefile  # pyshp

from flats.ingest.sources import Dataset, Geometry, Kind, Pipeline, load_pipeline

SNAPSHOTS = Path(__file__).resolve().parents[2] / "data" / "flats" / "sources"
MANIFEST = "manifest.json"

#: Features asked for per ArcGIS query. AGOL hosts cap at 1,000–2,000 and the
#: objectId list travels in a POST body, so this is a courtesy, not a limit.
BATCH = 400
#: Bytes of the ZIP's tail fetched first — comfortably holds the end-of-central-
#: directory record and, for the RLIS archive, the whole central directory.
_ZIP_TAIL = 262_144
_USER_AGENT = "flats-acquire/1.0"

#: Injectable so tests do not wait out a retry.
_sleep: Callable[[float], None] = time.sleep


class AcquireError(Exception):
    """A dataset could not be taken; the server or the archive would not give it up."""


class Refused(AcquireError):
    """A dataset could not be taken *as declared*: the registry asks for a field
    or a filter the source does not have. A file written anyway would be read as
    the dataset, so none is."""


# --- the manifest --------------------------------------------------------


def snapshot_dir(snapshot: str, root: Path = SNAPSHOTS) -> Path:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", snapshot):
        raise ValueError(f"a snapshot is named by its date, YYYY-MM-DD, not {snapshot!r}")
    return root / snapshot


def latest_snapshot(root: Path = SNAPSHOTS) -> Path | None:
    """The newest snapshot directory that has a manifest, or None."""
    if not root.is_dir():
        return None
    dated = sorted(p for p in root.iterdir() if p.is_dir() and (p / MANIFEST).is_file())
    return dated[-1] if dated else None


def read_manifest(directory: Path) -> dict[str, Any]:
    path = directory / MANIFEST
    if not path.is_file():
        return {"snapshot": directory.name, "datasets": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(directory: Path, doc: dict[str, Any]) -> None:
    # Rewritten after every dataset so an interrupted run leaves a manifest
    # that describes exactly what is on disk.
    tmp = directory / f"{MANIFEST}.part"
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(directory / MANIFEST)


def _spec_sha(ds: Dataset) -> str:
    """Fingerprint of the registry entry, so an edited field list re-fetches."""
    spec = ds.model_dump(mode="json", exclude={"label", "notes"})
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --- writing features ----------------------------------------------------


class _Sink:
    """Streams a FeatureCollection to disk, hashing as it goes.

    Written to a ``.part`` file and renamed on close, so a run that dies
    mid-write never leaves a file that looks finished.
    """

    def __init__(self, path: Path, srid: int) -> None:
        self.path = path
        self.part = path.with_name(path.name + ".part")
        self._fh = self.part.open("wb")
        self._hash = hashlib.sha256()
        self.features = 0
        self.bytes = 0
        self._write(b'{"type": "FeatureCollection", "srid": %d, "features": [' % srid)

    def _write(self, chunk: bytes) -> None:
        self._fh.write(chunk)
        self._hash.update(chunk)
        self.bytes += len(chunk)

    def add(self, feature: dict[str, Any]) -> None:
        sep = b"\n" if self.features == 0 else b",\n"
        self._write(sep + json.dumps(feature, separators=(",", ":"), default=str).encode())
        self.features += 1

    def close(self) -> str:
        self._write(b"\n]}\n")
        self._fh.close()
        self.part.replace(self.path)
        return self._hash.hexdigest()

    def abandon(self) -> None:
        self._fh.close()
        self.part.unlink(missing_ok=True)


# --- ArcGIS ----------------------------------------------------------------


def _shoelace(ring: list[list[float]]) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _point_in_ring(pt: list[float], ring: list[list[float]]) -> bool:
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def esri_polygon(geom: dict[str, Any] | None) -> dict[str, Any] | None:
    """Esri rings (shells clockwise, holes anticlockwise) to a MultiPolygon.

    A hole is attached to the shell that contains its first vertex. A hole
    that no shell contains is kept as a shell: a lot dropped is worse than a
    lot read slightly large, and the manifest cannot say which it was.
    """
    if not geom or "rings" not in geom:
        return None
    shells: list[list[list[float]]] = []
    holes: list[list[list[float]]] = []
    for ring in geom["rings"]:
        if len(ring) < 4:
            continue
        (shells if _shoelace(ring) < 0 else holes).append(ring)
    if not shells:  # a server that publishes anticlockwise shells
        shells, holes = holes, []
    polys: list[list[list[list[float]]]] = [[s] for s in shells]
    for hole in holes:
        for poly in polys:
            if _point_in_ring(hole[0], poly[0]):
                poly.append(hole)
                break
        else:
            polys.append([hole])
    return {"type": "MultiPolygon", "coordinates": polys}


def esri_polyline(geom: dict[str, Any] | None) -> dict[str, Any] | None:
    if not geom or "paths" not in geom:
        return None
    paths = [p for p in geom["paths"] if len(p) >= 2]
    return {"type": "MultiLineString", "coordinates": paths} if paths else None


def _json(resp: httpx.Response) -> dict[str, Any]:
    resp.raise_for_status()
    doc = resp.json()
    if not isinstance(doc, dict):
        raise AcquireError(f"{resp.url}: not a JSON object")
    return doc


def _arcgis_fields(client: httpx.Client, ds: Dataset) -> list[str]:
    """The layer's own field names, from its metadata document."""
    meta = _json(client.get(ds.url, params={"f": "json"}))
    if "error" in meta:
        raise AcquireError(f"layer metadata: {meta['error'].get('message', meta['error'])}")
    return [f["name"] for f in meta.get("fields", []) if isinstance(f, dict) and "name" in f]


def _arcgis_ids(client: httpx.Client, ds: Dataset) -> tuple[str, list[int]]:
    where = ds.where or "1=1"
    last: dict[str, Any] = {}
    for attempt in range(3):
        if attempt:
            _sleep(5.0 * attempt)  # FEMA 400s the identical query intermittently
        last = _json(
            client.get(
                f"{ds.url}/query",
                params={"where": where, "returnIdsOnly": "true", "f": "json"},
            )
        )
        if "error" not in last:
            break
    if "error" in last:
        raise AcquireError(f"id query: {last['error'].get('message', last['error'])}")
    return str(last.get("objectIdFieldName") or "OBJECTID"), sorted(last.get("objectIds") or [])


def _fetch_arcgis(
    client: httpx.Client, ds: Dataset, srid: int, sink: _Sink, log: Callable[[str], None]
) -> list[int]:
    """Every feature of the layer into the sink; returns the ids it could not get."""
    _oid, oids = _arcgis_ids(client, ds)
    if not oids:
        raise AcquireError("the id query returned no features; check the where clause")
    log(f"  {len(oids):,} features to fetch")
    convert = esri_polygon if ds.geometry is Geometry.polygon else esri_polyline
    unfetched: list[int] = []

    def batch(ids: list[int], offset_ft: float = 0.0, retried: bool = False) -> None:
        params: dict[str, Any] = {
            "objectIds": ",".join(map(str, ids)),
            "outFields": ",".join(ds.fields),
            "returnGeometry": "true",
            "outSR": srid,
            "f": "json",
        }
        if offset_ft:
            params["maxAllowableOffset"] = offset_ft
        doc = _json(client.post(f"{ds.url}/query", data=params))
        if "error" in doc:
            # A transient hiccup and a feature the server cannot serialise
            # look the same. Retry once, then bisect, then simplify, then
            # record the id rather than drop it in silence.
            if not retried:
                _sleep(2.0)
                batch(ids, offset_ft, retried=True)
            elif len(ids) > 1:
                mid = len(ids) // 2
                batch(ids[:mid], offset_ft, retried=True)
                batch(ids[mid:], offset_ft, retried=True)
            elif not offset_ft:
                batch(ids, offset_ft=1.0, retried=True)
            else:
                unfetched.extend(ids)
            return
        for feat in doc.get("features", []):
            sink.add(
                {
                    "type": "Feature",
                    "properties": feat.get("attributes", {}),
                    "geometry": convert(feat.get("geometry")),
                }
            )

    for i in range(0, len(oids), BATCH):
        batch(oids[i : i + BATCH])
        if (i // BATCH) % 25 == 0 and i:
            log(f"  {sink.features:,}/{len(oids):,}")
    return unfetched


# --- Metro RLIS (a ZIP read by range request) ------------------------------


class _RemoteZip:
    """The members of a ZIP on a server that honours Range, without the ZIP."""

    def __init__(self, client: httpx.Client, url: str) -> None:
        self.client = client
        self.url = url
        self.total = 0
        try:
            head = client.head(url)
            head.raise_for_status()
            self.url = str(head.url)
            self.total = int(head.headers.get("content-length") or 0)
        except httpx.HTTPStatusError:
            pass  # a host that answers HEAD with 405 still answers a one-byte range
        if not self.total:
            probe = self._range(0, 0)
            self.url = str(probe.url)
            self.total = int(probe.headers["content-range"].rsplit("/", 1)[1])
        self.entries = self._central_directory()

    def _range(self, start: int, end: int) -> httpx.Response:
        resp = self.client.get(self.url, headers={"Range": f"bytes={start}-{end}"})
        resp.raise_for_status()
        if resp.status_code != 206:
            raise AcquireError("the server ignored the range request; refusing to pull the whole archive")
        return resp

    def _bytes(self, start: int, end: int) -> bytes:
        return self._range(start, end).content

    def _central_directory(self) -> dict[str, dict[str, int]]:
        tail_start = max(0, self.total - _ZIP_TAIL)
        tail = self._bytes(tail_start, self.total - 1)
        at = tail.rfind(b"PK\x05\x06")
        if at < 0:
            raise AcquireError("no end-of-central-directory record in the archive's tail")
        _, _, _, _, cd_size, cd_offset, _ = struct.unpack_from("<HHHHIIH", tail, at + 4)
        if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
            raise AcquireError("ZIP64 archive; the range reader holds only classic offsets")
        if cd_offset >= tail_start:
            cd = tail[cd_offset - tail_start : cd_offset - tail_start + cd_size]
        else:
            cd = self._bytes(cd_offset, cd_offset + cd_size - 1)
        entries: dict[str, dict[str, int]] = {}
        pos = 0
        while pos + 46 <= len(cd) and cd[pos : pos + 4] == b"PK\x01\x02":
            (_, _, _, method, _, _, _, comp, uncomp, fl, el, cl, _, _, _, local) = struct.unpack_from(
                "<HHHHHHIIIHHHHHII", cd, pos + 4
            )
            name = cd[pos + 46 : pos + 46 + fl].decode("utf-8", errors="replace")
            entries[name] = {"local": local, "comp": comp, "uncomp": uncomp, "method": method}
            pos += 46 + fl + el + cl
        if not entries:
            raise AcquireError("the central directory parsed to no entries")
        return entries

    def member(self, name: str) -> bytes:
        entry = self.entries.get(name)
        if entry is None:
            raise AcquireError(f"{name} is not in the archive")
        head = self._bytes(entry["local"], entry["local"] + 29)
        if head[:4] != b"PK\x03\x04":
            raise AcquireError(f"{name}: bad local header at {entry['local']}")
        fl, el = struct.unpack_from("<HH", head, 26)
        start = entry["local"] + 30 + fl + el
        raw = self._bytes(start, start + entry["comp"] - 1)
        if entry["method"] == 8:
            return zlib.decompress(raw, -15)
        if entry["method"] == 0:
            return raw
        raise AcquireError(f"{name}: compression method {entry['method']} not supported")


_FILTER = re.compile(r"^\s*(\w+)\s+in\s*\(([^)]*)\)\s*$", re.IGNORECASE)


def parse_filter(text: str | None) -> tuple[str, frozenset[str]] | None:
    """``COUNTY in (M, C)`` -> ("COUNTY", {"M", "C"}). Anything else is refused."""
    if not text:
        return None
    m = _FILTER.match(text)
    if not m:
        raise Refused(f"filter {text!r} is not of the form FIELD in (a, b)")
    values = frozenset(v.strip().strip("'\"").upper() for v in m.group(2).split(",") if v.strip())
    if not values:
        raise Refused(f"filter {text!r} keeps nothing")
    return m.group(1), values


def _fetch_rlis(
    archive: _RemoteZip, ds: Dataset, sink: _Sink, log: Callable[[str], None]
) -> list[str]:
    """Every record of the member that passes the filter; returns the dbf's fields."""
    assert ds.member
    stem = ds.member.rsplit(".", 1)[0]
    shp = archive.member(ds.member)
    dbf = archive.member(f"{stem}.dbf")
    log(f"  {len(shp) / 1e6:.0f} MB shp, {len(dbf) / 1e6:.0f} MB dbf")
    reader = shapefile.Reader(shp=io.BytesIO(shp), dbf=io.BytesIO(dbf))
    names = [f[0] for f in reader.fields[1:]]
    _check_fields(ds, names)
    keep = [i for i, n in enumerate(names) if not ds.fields or n in ds.fields]
    rule = parse_filter(ds.filter)
    where = None
    if rule:
        if rule[0] not in names:
            raise Refused(f"filter field {rule[0]} is not in the dbf")
        where = (names.index(rule[0]), rule[1])
    for sr in reader.iterShapeRecords():
        rec = sr.record
        if where and str(rec[where[0]]).strip().upper() not in where[1]:
            continue
        props = {names[i]: (rec[i].isoformat() if hasattr(rec[i], "year") else rec[i]) for i in keep}
        try:
            geom = sr.shape.__geo_interface__ if sr.shape.shapeType else None
        except Exception:  # the county data has degenerate shapes
            geom = None
        sink.add({"type": "Feature", "properties": props, "geometry": geom})
    return names


# --- the stage -------------------------------------------------------------


def _check_fields(ds: Dataset, present: Iterable[str]) -> None:
    have = {n.lower() for n in present}
    missing = [f for f in ds.fields if f.lower() not in have]
    if ds.zone_field and ds.zone_field.lower() not in have and ds.zone_field not in missing:
        missing.append(ds.zone_field)
    if missing:
        raise Refused(f"declared fields not on the source: {missing}")


def _entry(ds: Dataset, srid: int) -> dict[str, Any]:
    return {
        "kind": ds.kind.value,
        "label": ds.label,
        "provides": ds.provides.value,
        "url": ds.url,
        "member": ds.member,
        "where": ds.where,
        "filter": ds.filter,
        "geometry": ds.geometry.value,
        "srid": srid,
        "spec_sha256": _spec_sha(ds),
        "fields": {"declared": list(ds.fields), "present": [], "checked": False},
    }


def _present(entry: dict[str, Any] | None, directory: Path, ds: Dataset) -> bool:
    """Is the dataset already on disk as this registry entry describes it?"""
    if not entry or entry.get("status") not in ("acquired", "present"):
        return False
    if entry.get("spec_sha256") != _spec_sha(ds):
        return False
    path = directory / str(entry.get("file") or "")
    return path.is_file() and path.stat().st_size == entry.get("bytes")


def acquire(
    pipeline: Pipeline,
    directory: Path,
    *,
    keys: Iterable[str] | None = None,
    force: bool = False,
    client: httpx.Client | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Fetch every (or the named) dataset into ``directory``; return the manifest.

    One dataset failing does not stop the next: a snapshot with a hole in it
    and a manifest that says where is worth more than no snapshot.
    """
    directory.mkdir(parents=True, exist_ok=True)
    doc = read_manifest(directory)
    doc.setdefault("snapshot", directory.name)
    doc["working_srid"] = pipeline.working_srid
    doc.setdefault("datasets", {})
    wanted = list(keys) if keys is not None else list(pipeline.datasets)
    unknown = [k for k in wanted if k not in pipeline.datasets]
    if unknown:
        raise AcquireError(f"not in the registry: {unknown}")

    own = client is None
    client = client or httpx.Client(
        timeout=httpx.Timeout(600.0, connect=60.0),
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    )
    archives: dict[str, _RemoteZip] = {}
    try:
        for key in wanted:
            ds = pipeline.datasets[key]
            previous = doc["datasets"].get(key)
            if not force and _present(previous, directory, ds):
                previous["status"] = "present"
                log(f"{key}: present ({previous['features']:,} features)")
                _write_manifest(directory, doc)
                continue
            entry = _entry(ds, pipeline.working_srid)
            started = time.monotonic()
            log(f"{key}: {ds.label}")
            path = directory / f"{key}.geojson"
            sink: _Sink | None = None
            try:
                if ds.kind is Kind.tnm_dem:
                    entry["status"] = "deferred"
                    entry["error"] = "terrain tiles are not a vector layer; the slope stage fetches them"
                elif ds.kind is Kind.arcgis:
                    names = _arcgis_fields(client, ds)
                    if names:
                        _check_fields(ds, names)
                    # A server that publishes no field list cannot be checked;
                    # the manifest says so rather than claiming nothing is missing.
                    entry["fields"] = {"declared": list(ds.fields), "present": names, "checked": bool(names)}
                    sink = _Sink(path, pipeline.working_srid)
                    unfetched = _fetch_arcgis(client, ds, pipeline.working_srid, sink, log)
                    entry["unfetched_ids"] = unfetched
                    entry["status"] = "acquired"
                elif ds.kind is Kind.rlis_zip:
                    archive = archives.get(ds.url)
                    if archive is None:
                        archive = archives[ds.url] = _RemoteZip(client, ds.url)
                        log(f"  archive is {archive.total / 1e9:.2f} GB, {len(archive.entries)} members")
                    sink = _Sink(path, pipeline.working_srid)
                    names = _fetch_rlis(archive, ds, sink, log)
                    entry["fields"] = {"declared": list(ds.fields), "present": names, "checked": True}
                    entry["status"] = "acquired"
                if sink is not None:
                    entry["file"] = path.name
                    entry["sha256"] = sink.close()
                    entry["bytes"] = sink.bytes
                    entry["features"] = sink.features
                    sink = None
            except Refused as exc:
                entry["status"] = "refused"
                entry["error"] = str(exc)
            except AcquireError as exc:
                entry["status"] = "failed"
                entry["error"] = str(exc)
            except Exception as exc:  # transport, JSON, ZIP, shapefile — the next dataset still runs
                entry["status"] = "failed"
                entry["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                if sink is not None:
                    sink.abandon()
            entry["retrieved_at"] = _now()
            entry["seconds"] = round(time.monotonic() - started, 1)
            doc["datasets"][key] = entry
            _write_manifest(directory, doc)
            if entry["status"] == "acquired":
                log(f"  {entry['status']}: {entry['features']:,} features, {entry['bytes'] / 1e6:.1f} MB")
            else:
                log(f"  {entry['status']}: {entry.get('error', '')}")
    finally:
        if own:
            client.close()
    return doc


def describe(doc: dict[str, Any]) -> list[str]:
    """One line per dataset, the way the CLI prints a manifest back."""
    out = [f"snapshot {doc.get('snapshot')} in EPSG:{doc.get('working_srid')}"]
    for key, e in sorted(doc.get("datasets", {}).items()):
        status = e.get("status", "?")
        if status in ("acquired", "present"):
            detail = f"{e.get('features', 0):,} features, {e.get('bytes', 0) / 1e6:.1f} MB, sha256 {str(e.get('sha256', ''))[:12]}"
            if e.get("unfetched_ids"):
                detail += f", {len(e['unfetched_ids'])} ids unfetched"
        else:
            detail = e.get("error", "")
        out.append(f"{key}: {status} -- {detail}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    ap.add_argument("--keys", nargs="*", help="dataset keys to acquire (default: every dataset)")
    ap.add_argument("--force", action="store_true", help="re-fetch datasets already in the snapshot")
    ap.add_argument("--config", type=Path, help="registry to read (default: flats/config/pipeline.yaml)")
    ap.add_argument("--root", type=Path, default=SNAPSHOTS, help="where snapshots live")
    ap.add_argument("--show", metavar="SNAPSHOT", help="print a snapshot's manifest and exit")
    args = ap.parse_args(argv)

    if args.show:
        for line in describe(read_manifest(snapshot_dir(args.show, args.root))):
            print(line)
        return 0

    pipeline = load_pipeline(args.config)
    doc = acquire(pipeline, snapshot_dir(args.snapshot, args.root), keys=args.keys, force=args.force)
    print()
    for line in describe(doc):
        print(line)
    bad = [k for k, e in doc["datasets"].items() if e.get("status") in ("refused", "failed")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
