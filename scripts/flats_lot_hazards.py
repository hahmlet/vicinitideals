"""Mapped ground hazards under each lot: extract the maps, cut them against the lots, load them.

FOLLOWUPS 198 (:mod:`flats.ingest.hazards`). A NOTE, never a colour: nothing
that screens reads these tables. Four steps:

* ``inspect`` (pyogrio + rasterio) lists what a geodatabase holds -- every
  vector layer with its fields and every raster -- so a renamed layer is a
  one-line registry edit, not a guess.
* ``extract`` (pyogrio + rasterio + pyproj; LXC 137) reads every layer the
  registry (``flats/config/pipeline.yaml`` ``hazard_notes``) names: the DOGAMI
  layers out of the two geodatabases (``--gdb slido_4_5=<path>`` and
  ``--gdb o_19_09=<path>``; a directory is searched for its one ``.gdb``), the
  flood layers out of an acquire snapshot (``--held data/flats/sources/<date>``).
  Each vector layer is classed, carried into EPSG:2913, cut into tiles where a
  shape is huge (so a lot never intersects a statewide polygon), and written as
  ``layers/<key>.parquet``; a raster is opened and checked, and its path kept.
  ``meta.json`` records every file, layer name, field list, class count, and
  any printed label that disagrees with its class. A layer the registry names
  that is not there, or that lacks its class field, stops the extract: a layer
  read without its class would print as nothing.
* ``build`` (shapely + pyarrow + rasterio; LXC 137) cuts every layer against
  every lot of normalize's ``lots.parquet`` and writes ``lot_hazards.csv.gz``
  (:data:`flats.ingest.hazards.LOT_COLUMNS`) and ``summary.json``.
* ``load`` (asyncpg; the api container) replaces one snapshot's
  ``flats.lot_hazards`` rows for the layers in the build -- every lot, or with
  ``--colour green`` only the lots the run shown (or ``--run``) has GREEN, so
  the green lots go first -- and records each layer's source in
  ``flats.hazard_layers``. Layers not in the build are left as they were, so a
  layer can be loaded on its own. No lot, result or run is touched.

Usage::

    python scripts/flats_lot_hazards.py inspect --gdb data/flats/hazards/slido_4_5
    python scripts/flats_lot_hazards.py extract --gdb slido_4_5=data/flats/hazards/slido_4_5 \\
        --gdb o_19_09=data/flats/hazards/o_19_09 --held data/flats/sources/<date> --out data/flats/hazards/extract_<date>
    python scripts/flats_lot_hazards.py build --extract data/flats/hazards/extract_<date> \\
        --lots data/flats/normalized/<snapshot>/lots.parquet --out data/flats/hazards/build_<snapshot> --processes 12
    # copy the build directory to VM 114's /root/stacks/vicinitideals/data/flats/hazards/<name>, then
    docker compose run --rm api python scripts/flats_lot_hazards.py load \\
        --build /app/data/flats/hazards/<name> --snapshot <flats.snapshots id> [--colour green] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flats.ingest.hazards import (  # noqa: E402
    CLASS,
    CONFIG_PATH,
    LEVELS,
    LOT_COLUMNS,
    NEAREST,
    NOT_MAPPED,
    OUTSIDE,
    SUM_TOLERANCE,
    Feature,
    LayerSpec,
    RasterLayer,
    Registry,
    VectorLayer,
    classify,
    feature_detail,
    level_of,
    load_registry,
    measure_lots,
    printed_code,
)

META_FILE = "meta.json"
LOT_FILE = "lot_hazards.csv.gz"
SUMMARY_FILE = "summary.json"
LAYER_DIR = "layers"
OUT_SRID = 2913
COUNTY_LETTERS = {"M": "multnomah", "C": "clackamas", "W": "washington"}
#: A polygon with more vertices than this is cut into tiles of TILE_FT.
TILE_VERTICES = 2000
TILE_FT = 2000.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- reading the geodatabases ------------------------------------------------------


def find_gdb(path: Path) -> Path:
    """The ``.gdb`` at ``path``, or the one ``.gdb`` under it."""
    if path.suffix.lower() == ".gdb":
        return path
    found = sorted(p for p in path.rglob("*.gdb") if p.is_dir())
    if len(found) != 1:
        raise SystemExit(f"{path}: expected one .gdb under it, found {[str(p) for p in found]}")
    return found[0]


def _names(values: Any) -> list[str]:
    """pyogrio's field names (a numpy array, never tested for truth)."""
    return [] if values is None else [str(v) for v in values]


def inspect(gdb: Path) -> dict[str, Any]:
    import pyogrio

    gdb = find_gdb(gdb)
    out: dict[str, Any] = {"gdb": str(gdb), "vector": {}, "raster": []}
    for name, geom_type in pyogrio.list_layers(gdb):
        info = pyogrio.read_info(gdb, layer=name)
        out["vector"][str(name)] = {"geometry": geom_type, "features": int(info.get("features") or 0),
                                    "fields": _names(info.get("fields")), "crs": info.get("crs")}
    try:
        import rasterio

        with rasterio.open(f"OpenFileGDB:{gdb}") as ds:
            out["raster"] = list(ds.subdatasets) or [ds.name]
    except Exception as exc:  # no raster in the gdb, or the driver cannot list them
        out["raster_error"] = f"{type(exc).__name__}: {exc}"
    return out


def _pick_layer(available: list[str], spec_layer: str | None, candidates: tuple[str, ...], key: str) -> str:
    lower = {a.lower(): a for a in available}
    wanted = [spec_layer] if spec_layer else list(candidates)
    hits = sorted({lower[w.lower()] for w in wanted if w and w.lower() in lower})
    if len(hits) != 1:
        raise SystemExit(f"{key}: wanted one of {wanted} in the geodatabase, found {hits}; it holds {sorted(available)}")
    return hits[0]


def _field_map(fields: list[str]) -> dict[str, str]:
    return {f.lower(): f for f in fields}


def _transformer(crs: Any) -> Any:
    from pyproj import CRS, Transformer

    return Transformer.from_crs(CRS.from_user_input(crs), OUT_SRID, always_xy=True)


def _to_working(geoms: Any, crs: Any) -> Any:
    import numpy as np
    import shapely

    tr = _transformer(crs)

    def fn(coords: Any) -> Any:
        x, y = tr.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(geoms, fn)


def tiles(geom: Any, size: float = TILE_FT) -> list[Any]:
    """A huge polygon cut into square tiles (a lot then meets small pieces)."""
    import numpy as np
    import shapely

    minx, miny, maxx, maxy = geom.bounds
    xs = np.arange(minx, maxx + size, size)
    ys = np.arange(miny, maxy + size, size)
    boxes = shapely.box(*np.meshgrid(xs[:-1], ys[:-1]), *np.meshgrid(xs[1:], ys[1:])) if len(xs) > 1 and len(ys) > 1 else None
    if boxes is None:
        return [geom]
    boxes = boxes.ravel()
    shapely.prepare(geom)
    boxes = boxes[shapely.intersects(geom, boxes)]
    pieces = shapely.intersection(geom, boxes)
    return [p for p in pieces if not shapely.is_empty(p) and shapely.area(p) > 0]


def _explode(geom: Any, kind: str) -> list[Any]:
    import shapely

    if geom is None or shapely.is_empty(geom):
        return []
    if kind in ("polygon", "coverage"):
        geom = shapely.make_valid(geom)
        polys = [p for p in shapely.get_parts(geom) if shapely.get_type_id(p) in (3, 6)]
        out = []
        for p in polys:
            out.extend(tiles(p) if shapely.get_num_coordinates(p) > TILE_VERTICES else [p])
        return out
    return list(shapely.get_parts(geom))


def read_vector(spec: LayerSpec, gdb: Path, layer: str, *, part: Any = None) -> tuple[list[Feature], dict[str, Any]]:
    """One geodatabase layer, classed and in EPSG:2913."""
    import pyogrio
    import shapely

    info = pyogrio.read_info(gdb, layer=layer)
    fields = _names(info.get("fields"))
    fmap = _field_map(fields)
    needed = [f for f in (spec.class_field, spec.label_field) if f and part is None]
    missing = [f for f in needed if f.lower() not in fmap]
    if missing:
        raise SystemExit(f"{spec.key}: layer {layer} has no {missing}; its fields are {fields}")
    wanted = [fmap[f.lower()] for f in (*needed, *spec.detail_fields) if f.lower() in fmap]
    _meta, _fids, wkb, field_data = pyogrio.raw.read(gdb, layer=layer, columns=list(dict.fromkeys(wanted)))
    geoms = _to_working(shapely.from_wkb(wkb), info["crs"])
    columns = {name: list(values) for name, values in zip(_meta["fields"], field_data)}
    feats: list[Feature] = []
    codes: Counter = Counter()
    disagree: Counter = Counter()
    for i, geom in enumerate(geoms):
        props = {name: _plain(columns[fmap[name.lower()]][i]) for name in (*needed, *spec.detail_fields)
                 if name.lower() in fmap and fmap[name.lower()] in columns}
        classed = classify(spec, props, part)
        if classed is None:
            continue
        state, code, label = classed
        codes[f"{state}:{code}"] += 1
        found = spec.class_def(code)
        if spec.label_field and found is not None and label is not None and label.lower() != found.label.lower():
            disagree[f"{code}={label}"] += 1
        attrs = feature_detail(spec, props)
        for piece in _explode(geom, spec.kind):
            feats.append(Feature(state, code, label, attrs, piece))
    meta = {
        "layer": layer,
        "fields": fields,
        "missing_detail_fields": [f for f in spec.detail_fields if f.lower() not in fmap],
        "crs": str(info.get("crs")),
        "features_read": len(geoms),
        "pieces": len(feats),
        "classes": dict(sorted(codes.items())),
        "label_disagreements": dict(sorted(disagree.items())),
    }
    return feats, meta


def _plain(value: Any) -> Any:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return value


def read_held(spec: LayerSpec, snapshot: Path) -> tuple[list[Feature], dict[str, Any]]:
    """A flood layer as the acquire stage holds it (GeoJSON, already EPSG:2913)."""
    import shapely

    path = snapshot / f"{spec.held}.geojson"
    if not path.is_file():
        raise SystemExit(f"{spec.key}: {path} is not held")
    doc = json.loads(path.read_text(encoding="utf-8"))
    srid = int(doc.get("srid") or OUT_SRID)
    if srid != OUT_SRID:
        raise SystemExit(f"{spec.key}: {path} is EPSG:{srid}, not {OUT_SRID}")
    manifest = {}
    if (snapshot / "manifest.json").is_file():
        manifest = (json.loads((snapshot / "manifest.json").read_text(encoding="utf-8")).get("datasets") or {}).get(spec.held) or {}
    feats: list[Feature] = []
    codes: Counter = Counter()
    present: set[str] = set()
    for f in doc.get("features") or []:
        props = f.get("properties") or {}
        present.update(props)
        if not f.get("geometry"):
            continue
        classed = classify(spec, props)
        if classed is None:
            continue
        state, code, label = classed
        codes[f"{state}:{code}|{label}"] += 1
        geom = shapely.geometry.shape(f["geometry"])
        for piece in _explode(geom, spec.kind):
            feats.append(Feature(state, code, label, feature_detail(spec, props), piece))
    meta = {
        "file": str(path),
        "snapshot": snapshot.name,
        "retrieved_at": manifest.get("retrieved_at"),
        "sha256": manifest.get("sha256"),
        "features_read": len(doc.get("features") or []),
        "pieces": len(feats),
        "fields_present": sorted(present),
        "missing_detail_fields": [f for f in spec.detail_fields if f not in present],
        "classes": dict(sorted(codes.items())),
    }
    return feats, meta


def _gdal_lib() -> Any:
    """The GDAL library bundled with pyogrio, through ctypes.

    rasterio's wheels leave out the OpenFileGDB raster driver; pyogrio's GDAL
    (3.7+) reads file-geodatabase rasters. Only GDALTranslate is used, to copy a
    raster out to a GeoTIFF that rasterio then reads."""
    import ctypes
    import glob
    import os

    import pyogrio

    base = os.path.dirname(pyogrio.__file__)
    found = sorted(glob.glob(os.path.join(base, "..", "pyogrio.libs", "*gdal*")) + glob.glob(os.path.join(base, "*gdal*.dll")))
    if not found:
        raise SystemExit("no GDAL library found beside pyogrio")
    lib = ctypes.CDLL(found[0])
    lib.GDALAllRegister()
    lib.GDALOpenEx.restype = ctypes.c_void_p
    lib.GDALOpenEx.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    lib.GDALTranslateOptionsNew.restype = ctypes.c_void_p
    lib.GDALTranslateOptionsNew.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_void_p]
    lib.GDALTranslate.restype = ctypes.c_void_p
    lib.GDALTranslate.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    lib.GDALTranslateOptionsFree.argtypes = [ctypes.c_void_p]
    lib.GDALClose.argtypes = [ctypes.c_void_p]
    return lib


def copy_gdb_raster(gdb: Path, layer: str, out: Path, *, bbox_2913: tuple[float, float, float, float] | None = None) -> Path:
    """Copy one geodatabase raster to a tiled, compressed GeoTIFF, cut to
    ``bbox_2913`` (xmin, ymin, xmax, ymax in EPSG:2913) when given. Values and
    cells are copied as stored (no resampling)."""
    import ctypes

    lib = _gdal_lib()
    src = lib.GDALOpenEx(f'OpenFileGDB:"{gdb}":{layer}'.encode(), 0x02 | 0x40, None, None, None)
    if not src:
        raise SystemExit(f"{gdb}: raster {layer} does not open")
    args = ["-of", "GTiff", "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES", "-co", "BIGTIFF=IF_SAFER"]
    if bbox_2913 is not None:
        xmin, ymin, xmax, ymax = bbox_2913
        args += ["-projwin_srs", "EPSG:2913", "-projwin", str(xmin), str(ymax), str(xmax), str(ymin)]
    argv = (ctypes.c_char_p * (len(args) + 1))(*[a.encode() for a in args], None)
    opts = lib.GDALTranslateOptionsNew(argv, None)
    err = ctypes.c_int(0)
    dst = lib.GDALTranslate(str(out).encode(), src, opts, ctypes.byref(err))
    lib.GDALTranslateOptionsFree(opts)
    if dst:
        lib.GDALClose(dst)
    lib.GDALClose(src)
    if not dst or err.value:
        raise SystemExit(f"{gdb}: copying raster {layer} failed")
    return out


def check_raster(spec: LayerSpec, gdb: Path | None = None, *, path: str | None = None) -> dict[str, Any]:
    """Open a raster (a GeoTIFF copy, or the geodatabase's own where this GDAL
    reads it), check its sampled values against the legend."""
    import numpy as np
    import rasterio

    path = path or f"OpenFileGDB:{gdb}:{spec.layer}"
    with rasterio.open(path) as ds:
        step = max(1, max(ds.width, ds.height) // 2000)
        sample = ds.read(1, out_shape=(max(1, ds.height // step), max(1, ds.width // step)))
        values = Counter(int(v) for v in np.unique(sample) if ds.nodata is None or v != ds.nodata)
        unknown = sorted(v for v in values if spec.class_def(str(v)) is None)
        return {"path": path, "crs": str(ds.crs), "res": list(ds.res), "nodata": ds.nodata,
                "size": [ds.width, ds.height], "sampled_values": sorted(values), "values_not_in_legend": unknown}


def write_layer(path: Path, feats: list[Feature]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapely

    table = pa.table({
        "state": [f.state for f in feats],
        "code": [f.code for f in feats],
        "label": [f.label for f in feats],
        "attrs": [json.dumps(f.attrs, sort_keys=True, default=str) for f in feats],
        "wkb": [shapely.to_wkb(f.geom) for f in feats],
    })
    pq.write_table(table, path)


def read_layer(path: Path) -> list[Feature]:
    import pyarrow.parquet as pq
    import shapely

    t = pq.read_table(path)
    geoms = shapely.from_wkb(t.column("wkb").to_numpy(zero_copy_only=False))
    return [
        Feature(s, c, lab, json.loads(a) if a else {}, g)
        for s, c, lab, a, g in zip(t.column("state").to_pylist(), t.column("code").to_pylist(),
                                   t.column("label").to_pylist(), t.column("attrs").to_pylist(), geoms)
    ]


def registry_sha(path: Path = CONFIG_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def extract(
    out: Path,
    *,
    gdbs: dict[str, Path],
    held: Path | None,
    keys: list[str] | None = None,
    registry: Registry | None = None,
    bbox_2913: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """Class every wanted layer into ``out``. Rasters are copied to GeoTIFFs,
    cut to ``bbox_2913`` (EPSG:2913) when given -- the lots' extent."""
    registry = registry or load_registry()
    out.mkdir(parents=True, exist_ok=True)
    (out / LAYER_DIR).mkdir(exist_ok=True)
    meta: dict[str, Any] = {"made_at": _now(), "registry_sha": registry_sha(), "layers": {}}
    wanted = [k for k in registry.layers if keys is None or k in keys]
    # A layer's coverage comes with it.
    for k in list(wanted):
        cov = registry.layers[k].coverage
        if cov and cov not in wanted:
            wanted.insert(0, cov)
    resolved = {pub: find_gdb(p) for pub, p in gdbs.items()}
    for key in wanted:
        spec = registry.layers[key]
        started = time.time()
        entry: dict[str, Any] = {"kind": spec.kind, "hazard": spec.hazard, "publication": spec.publication}
        if spec.held:
            if held is None:
                print(f"{key}: skipped (no --held snapshot)", file=sys.stderr)
                continue
            feats, info = read_held(spec, held)
            entry.update(info)
            write_layer(out / LAYER_DIR / f"{key}.parquet", feats)
        else:
            pub = spec.source_publication
            if pub not in resolved:
                print(f"{key}: skipped (no --gdb {pub}=...)", file=sys.stderr)
                continue
            gdb = resolved[pub]
            entry["gdb"] = str(gdb)
            if spec.kind == "raster":
                tif = copy_gdb_raster(gdb, spec.layer, out / LAYER_DIR / f"{key}.tif", bbox_2913=bbox_2913)
                entry["raster"] = check_raster(spec, path=str(tif.resolve()))
                entry["raster"]["copied_from"] = f"{gdb}:{spec.layer}"
                entry["raster"]["bbox_2913"] = list(bbox_2913) if bbox_2913 else None
            else:
                import pyogrio

                available = [str(n) for n, _t in pyogrio.list_layers(gdb)]
                feats = []
                parts_meta = {}
                if spec.parts:
                    for part in spec.parts:
                        name = _pick_layer(available, part.layer, (), key)
                        got, info = read_vector(spec, gdb, name, part=part)
                        feats.extend(got)
                        parts_meta[part.code] = info
                    entry["parts"] = parts_meta
                else:
                    name = _pick_layer(available, spec.layer, spec.layer_candidates, key)
                    feats, info = read_vector(spec, gdb, name)
                    entry.update(info)
                write_layer(out / LAYER_DIR / f"{key}.parquet", feats)
        entry["seconds"] = round(time.time() - started, 1)
        meta["layers"][key] = entry
        (out / META_FILE).write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        print(f"{key}: {entry.get('pieces', entry.get('raster', {}).get('size'))} in {entry['seconds']} s", file=sys.stderr)
    return meta


# --- build -----------------------------------------------------------------------


def lots_bbox(path: Path, margin_ft: float = 2_000.0) -> tuple[float, float, float, float]:
    """The EPSG:2913 extent of every lot of normalize's ``lots.parquet``, plus a margin."""
    import shapely

    xs0, ys0, xs1, ys1 = [], [], [], []
    for lot in read_lots(path):
        x0, y0, x1, y1 = shapely.bounds(lot["geom"])
        xs0.append(x0)
        ys0.append(y0)
        xs1.append(x1)
        ys1.append(y1)
    return (min(xs0) - margin_ft, min(ys0) - margin_ft, max(xs1) + margin_ft, max(ys1) + margin_ft)


def read_lots(path: Path) -> list[dict[str, Any]]:
    """``county``, ``tlid``, ``jurisdiction`` and ``geom`` of every lot of normalize's ``lots.parquet``."""
    import pyarrow.parquet as pq
    import shapely

    names = set(pq.ParquetFile(path).schema_arrow.names)
    county_col = "county" if "county" in names else "COUNTY"
    tlid_col = "tlid" if "tlid" in names else "TLID"
    cols = [county_col, tlid_col, "wkb"] + (["jurisdiction"] if "jurisdiction" in names else [])
    table = pq.read_table(path, columns=cols)
    geoms = shapely.from_wkb(table.column("wkb").to_numpy(zero_copy_only=False))
    juris = table.column("jurisdiction").to_pylist() if "jurisdiction" in names else [None] * len(geoms)
    lots = []
    for county, tlid, j, geom in zip(table.column(county_col).to_pylist(), table.column(tlid_col).to_pylist(), juris, geoms):
        county = str(county or "")
        lots.append({"county": COUNTY_LETTERS.get(county, county.lower()), "tlid": tlid, "jurisdiction": j, "geom": geom})
    return lots


_LAYERS: list[Any] = []
_COVERAGES: dict[str, VectorLayer] = {}


def _measure_chunk(lots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(measure_lots(lots, _LAYERS, _COVERAGES))


def open_layers(extract_dir: Path, registry: Registry, keys: list[str] | None = None) -> tuple[list[Any], dict[str, VectorLayer]]:
    meta = json.loads((extract_dir / META_FILE).read_text(encoding="utf-8"))
    layers: list[Any] = []
    coverages: dict[str, VectorLayer] = {}
    for key, entry in meta["layers"].items():
        spec = registry.layers[key]
        if spec.kind == "coverage":
            coverages[key] = VectorLayer(spec, read_layer(extract_dir / LAYER_DIR / f"{key}.parquet"))
    for key, entry in meta["layers"].items():
        spec = registry.layers[key]
        if spec.kind == "coverage" or (keys is not None and key not in keys):
            continue
        if spec.coverage and spec.coverage not in coverages:
            raise SystemExit(f"{key}: its coverage {spec.coverage} is not in the extract")
        if spec.kind == "raster":
            tif = extract_dir / LAYER_DIR / f"{key}.tif"  # the extract's own copy, wherever it now sits
            layers.append(RasterLayer(spec, str(tif) if tif.exists() else entry["raster"]["path"], working_srid=OUT_SRID))
        else:
            layers.append(VectorLayer(spec, read_layer(extract_dir / LAYER_DIR / f"{key}.parquet")))
    return layers, coverages


def summarise(rows: list[dict[str, Any]], registry: Registry) -> dict[str, Any]:
    per_lot_layer: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        per_lot_layer[(r["county"], r["tlid"], r["layer"])].append(r)
    layers: dict[str, Counter] = defaultdict(Counter)
    worst_gap = 0.0
    for (_c, _t, key), lot_rows in per_lot_layer.items():
        spec = registry.layers[key]
        c = layers[key]
        c["lots"] += 1
        for r in lot_rows:
            if r["state"] == NEAREST:
                d = (json.loads(r["detail"]) if r["detail"] else {}).get("distance_ft")
                band = "none_within_search" if d is None else ("on_lot" if d == 0 else ("within_100_ft" if d <= 100 else "over_100_ft"))
                c[f"nearest_{r['class_code']}_{band}"] += 1
        lot_rows = [r for r in lot_rows if r["state"] != NEAREST]
        states = {r["state"] for r in lot_rows}
        classes = [r for r in lot_rows if r["state"] == CLASS]
        if classes:
            detail = [json.loads(r["detail"]) if r["detail"] else None for r in classes]
            worst = max(LEVELS.index(level_of(spec, r["class_code"], r["class_label"], d)) for r, d in zip(classes, detail))
            c[f"worst_{LEVELS[worst]}"] += 1
        elif states == {NOT_MAPPED}:
            c["not_mapped_only"] += 1
        if OUTSIDE in states and not classes:
            c["outside_no_class"] += 1
        if spec.kind not in ("line", "point"):
            total = sum(float(r["area_sqft"]) for r in lot_rows)
            area = float(lot_rows[0]["lot_area_sqft"])
            if area:
                worst_gap = max(worst_gap, abs(total - area) / area)
    return {
        "layers": {k: dict(sorted(v.items())) for k, v in sorted(layers.items())},
        "largest_sum_gap_share": round(worst_gap, 6),
        "sum_tolerance": SUM_TOLERANCE,
    }


def build(extract_dir: Path, lots_path: Path, out: Path, *, processes: int = 1, chunk: int = 2000,
          keys: list[str] | None = None, registry: Registry | None = None) -> dict[str, Any]:
    import shutil

    global _LAYERS, _COVERAGES
    registry = registry or load_registry()
    started = time.time()
    lots = read_lots(lots_path)
    _LAYERS, _COVERAGES = open_layers(extract_dir, registry, keys)
    batches = [lots[i:i + chunk] for i in range(0, len(lots), chunk)]
    rows: list[dict[str, Any]] = []
    if processes > 1:
        import multiprocessing as mp

        with mp.get_context("fork").Pool(processes) as pool:
            for part in pool.imap(_measure_chunk, batches):
                rows.extend(part)
    else:
        for batch in batches:
            rows.extend(_measure_chunk(batch))
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / LOT_FILE, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(LOT_COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in LOT_COLUMNS})
    shutil.copyfile(extract_dir / META_FILE, out / META_FILE)
    summary = {
        "lots_file": str(lots_path),
        "lots_read": len(lots),
        "layers": [layer.spec.key for layer in _LAYERS],
        "rows": len(rows),
        **summarise(rows, registry),
        "processes": processes,
        "seconds": round(time.time() - started, 1),
    }
    (out / SUMMARY_FILE).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


# --- load -----------------------------------------------------------------------


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _lot_rows(path: Path) -> Iterator[tuple[Any, ...]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            yield (r["county"], r["tlid"], r["hazard"], r["layer"], r["state"], r["class_code"] or None,
                   r["class_label"] or None, float(r["area_sqft"]), float(r["share"]), r["detail"] or None)


_TMP_COLUMNS = ("county", "tlid", "hazard", "layer", "state", "class_code", "class_label", "area_sqft", "share", "detail")


def source_words(key: str, entry: dict[str, Any], registry: Registry) -> str:
    """Where one layer came from, in a line: the publication and the file read."""
    spec = registry.layers[key]
    pub = registry.publications[spec.publication]
    words = f"{pub.publisher}, {pub.title} ({pub.number}, {pub.date})"
    if spec.download_from:
        src = registry.publications[spec.download_from]
        words += f", read from {src.number}"
    if entry.get("retrieved_at"):
        words += f", as fetched {str(entry['retrieved_at'])[:10]} (acquire snapshot {entry.get('snapshot')})"
    layer = entry.get("layer") or (entry.get("raster") or {}).get("path", "").rsplit(":", 1)[-1]
    if layer:
        words += f"; layer {layer}"
    return words[:600]


async def load(
    build_dir: Path,
    db_url: str,
    *,
    snapshot_id: int,
    colour: str | None = None,
    run_id: int | None = None,
    dry_run: bool = False,
    batch_size: int = 20_000,
    registry: Registry | None = None,
) -> dict[str, Any]:
    """Replace one snapshot's ``flats.lot_hazards`` rows for the build's layers
    (every lot, or only the lots the run has in ``colour``)."""
    import asyncpg

    from app.models.flats import FLATS_COLOUR_ORDER

    registry = registry or load_registry()
    meta = json.loads((build_dir / META_FILE).read_text(encoding="utf-8"))
    report: dict[str, Any] = {"snapshot_id": snapshot_id, "dry_run": dry_run, "colour": colour}
    conn = await asyncpg.connect(_dsn(db_url))
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            if await conn.fetchrow("SELECT id FROM flats.snapshots WHERE id = $1", snapshot_id) is None:
                raise SystemExit(f"no flats.snapshots row {snapshot_id}")
            await conn.execute(
                "CREATE TEMP TABLE tmp_lot_hazards (county text, tlid text, hazard text, layer text, state text, "
                "class_code text, class_label text, area_sqft double precision, share double precision, detail text) "
                "ON COMMIT DROP"
            )
            rows = 0
            batch: list[tuple[Any, ...]] = []
            for row in _lot_rows(build_dir / LOT_FILE):
                batch.append(row)
                if len(batch) >= batch_size:
                    await conn.copy_records_to_table("tmp_lot_hazards", records=batch, columns=list(_TMP_COLUMNS))
                    rows += len(batch)
                    batch = []
            if batch:
                await conn.copy_records_to_table("tmp_lot_hazards", records=batch, columns=list(_TMP_COLUMNS))
                rows += len(batch)
            report["file_rows"] = rows
            layers = [r["layer"] for r in await conn.fetch("SELECT DISTINCT layer FROM tmp_lot_hazards ORDER BY layer")]
            unknown = [k for k in layers if k not in registry.layers]
            if unknown:
                raise SystemExit(f"layers not in the registry: {unknown}")
            report["layers"] = layers
            await conn.execute(
                "CREATE TEMP TABLE tmp_hazard_lots ON COMMIT DROP AS "
                "SELECT DISTINCT l.id AS lot_id FROM tmp_lot_hazards t "
                "JOIN flats.lots l ON l.snapshot_id = $1 AND l.county = t.county AND l.tlid = t.tlid",
                snapshot_id,
            )
            report["file_lots_without_a_lot"] = await conn.fetchval(
                "SELECT count(*) FROM (SELECT DISTINCT county, tlid FROM tmp_lot_hazards) t WHERE NOT EXISTS "
                "(SELECT 1 FROM flats.lots l WHERE l.snapshot_id = $1 AND l.county = t.county AND l.tlid = t.tlid)",
                snapshot_id,
            )
            if colour is not None:
                if colour not in FLATS_COLOUR_ORDER:
                    raise SystemExit(f"--colour {colour!r} is not one of {FLATS_COLOUR_ORDER}")
                if run_id is None:
                    run_id = await conn.fetchval(
                        "SELECT id FROM flats.runs WHERE status = 'complete' ORDER BY id DESC LIMIT 1"
                    )
                snap = await conn.fetchval("SELECT snapshot_id FROM flats.runs WHERE id = $1", run_id)
                if snap != snapshot_id:
                    raise SystemExit(f"run {run_id} screens snapshot {snap}, not {snapshot_id}")
                await conn.execute(
                    "DELETE FROM tmp_hazard_lots s WHERE NOT EXISTS (SELECT 1 FROM flats.lot_best b "
                    "WHERE b.run_id = $1 AND b.lot_id = s.lot_id AND b.best_colour = $2)",
                    run_id, FLATS_COLOUR_ORDER.index(colour),
                )
                report["run_id"] = run_id
                removed = await conn.execute(
                    "DELETE FROM flats.lot_hazards WHERE lot_id IN (SELECT lot_id FROM tmp_hazard_lots) "
                    "AND layer = ANY($1::text[])",
                    layers,
                )
            else:
                removed = await conn.execute(
                    "DELETE FROM flats.lot_hazards WHERE snapshot_id = $1 AND layer = ANY($2::text[])",
                    snapshot_id, layers,
                )
            report["removed"] = int(removed.split()[-1])
            status = await conn.execute(
                """
                INSERT INTO flats.lot_hazards
                    (lot_id, snapshot_id, hazard, layer, state, class_code, class_label, area_sqft, share, detail)
                SELECT l.id, l.snapshot_id, t.hazard, t.layer, t.state, t.class_code, t.class_label,
                       t.area_sqft, t.share, t.detail::jsonb
                FROM tmp_lot_hazards t
                JOIN flats.lots l ON l.snapshot_id = $1 AND l.county = t.county AND l.tlid = t.tlid
                JOIN tmp_hazard_lots s ON s.lot_id = l.id
                """,
                snapshot_id,
            )
            report["written"] = int(status.split()[-1])
            report["lots_written"] = await conn.fetchval("SELECT count(*) FROM tmp_hazard_lots")
            for key in layers:
                entry = (meta.get("layers") or {}).get(key) or {}
                await conn.execute(
                    "INSERT INTO flats.hazard_layers (snapshot_id, layer, source, detail, loaded_at) "
                    "VALUES ($1, $2, $3, $4::jsonb, now()) ON CONFLICT (snapshot_id, layer) DO UPDATE SET "
                    "source = EXCLUDED.source, detail = EXCLUDED.detail, loaded_at = EXCLUDED.loaded_at",
                    snapshot_id, key, source_words(key, entry, registry),
                    json.dumps({k: v for k, v in entry.items() if k not in ("fields", "fields_present")}, default=str),
                )
            report["lots_with_hazards_in_snapshot"] = await conn.fetchval(
                "SELECT count(DISTINCT lot_id) FROM flats.lot_hazards WHERE snapshot_id = $1", snapshot_id
            )
            report["lots_in_snapshot"] = await conn.fetchval(
                "SELECT count(*) FROM flats.lots WHERE snapshot_id = $1", snapshot_id
            )
        except BaseException:
            await tx.rollback()
            raise
        if dry_run:
            await tx.rollback()
        else:
            await tx.commit()
    finally:
        await conn.close()
    return report


# --- cli ----------------------------------------------------------------------


def _gdb_args(values: list[str]) -> dict[str, Path]:
    out = {}
    for v in values:
        key, sep, path = v.partition("=")
        if not sep:
            raise SystemExit(f"--gdb wants PUBLICATION=PATH, not {v!r}")
        out[key.strip()] = Path(path.strip())
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ins = sub.add_parser("inspect", help="list a geodatabase's layers, fields and rasters (needs pyogrio)")
    ins.add_argument("--gdb", type=Path, required=True)
    ex = sub.add_parser("extract", help="class every registered layer into EPSG:2913 files")
    ex.add_argument("--gdb", action="append", default=[], help="PUBLICATION=PATH, e.g. slido_4_5=data/flats/hazards/slido_4_5")
    ex.add_argument("--held", type=Path, default=None, help="an acquire snapshot directory (the flood layers)")
    ex.add_argument("--out", type=Path, required=True, help="a new, empty directory")
    ex.add_argument("--layers", default=None, help="comma-separated layer keys (default: all)")
    ex.add_argument("--bbox", default=None, help="xmin,ymin,xmax,ymax in EPSG:2913: cut the rasters to it (the lots' extent)")
    ex.add_argument("--bbox-from-lots", type=Path, default=None, help="normalize's lots.parquet: --bbox is its extent plus 2,000 ft")
    bu = sub.add_parser("build", help="cut the extract against every lot of a lot table")
    bu.add_argument("--extract", type=Path, required=True)
    bu.add_argument("--lots", type=Path, required=True, help="normalize's lots.parquet")
    bu.add_argument("--out", type=Path, required=True)
    bu.add_argument("--processes", type=int, default=1)
    bu.add_argument("--layers", default=None)
    ld = sub.add_parser("load", help="replace a snapshot's lot rows for the build's layers (needs asyncpg)")
    ld.add_argument("--build", type=Path, required=True)
    ld.add_argument("--snapshot", type=int, required=True)
    ld.add_argument("--colour", default=None, help="only the lots the run has in this colour (e.g. green)")
    ld.add_argument("--run", type=int, default=None, help="the run --colour reads (default: newest complete)")
    ld.add_argument("--db-url", default=None, help="default: app settings' database_url")
    ld.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    keys = None
    if getattr(args, "layers", None):
        keys = [k.strip() for k in args.layers.split(",") if k.strip()]
    if args.command == "inspect":
        print(json.dumps(inspect(args.gdb), indent=2, default=str))
        return 0
    if args.command == "extract":
        if args.out.exists() and any(args.out.iterdir()):
            raise SystemExit(f"{args.out} is not empty; an extract goes in a new directory")
        bbox = tuple(float(v) for v in args.bbox.split(",")) if args.bbox else None
        if args.bbox_from_lots is not None:
            bbox = lots_bbox(args.bbox_from_lots)
        meta = extract(args.out, gdbs=_gdb_args(args.gdb), held=args.held, keys=keys, bbox_2913=bbox)
        print(json.dumps({k: {x: v.get(x) for x in ("pieces", "classes", "label_disagreements", "raster")}
                          for k, v in meta["layers"].items()}, indent=2, default=str))
        return 0
    if args.command == "build":
        print(json.dumps(build(args.extract, args.lots, args.out, processes=args.processes, keys=keys), indent=2))
        return 0
    db_url = args.db_url
    if db_url is None:
        from app.config import settings

        db_url = settings.database_url
    report = asyncio.run(load(args.build, db_url, snapshot_id=args.snapshot, colour=args.colour,
                              run_id=args.run, dry_run=args.dry_run))
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("written") else 1


if __name__ == "__main__":
    sys.exit(main())
