"""Mapped ground hazards under each lot -- landslide, liquefaction, flood -- as NOTES.

FOLLOWUPS 198 (Steph 2026-11-18: "Yes", build the landslide, liquefaction and
flood notes). A foundation-design analysis reads these per lot. Nothing in the
screen, the fit, the score or the flags reads this module: it never adds a
reason code, never carries a flag severity and never moves a colour. The lot
page and the lot report say it, and that is all.

**Sources** are registered in ``flats/config/pipeline.yaml`` under
``hazard_notes`` (publisher, title, publication number, date, URL and DOGAMI's
use constraint), which :func:`flats.ingest.sources.load_pipeline` ignores, so
the acquire stage never fetches them and the screen never sees them:

* landslide susceptibility, detailed: DOGAMI SLIDO-4.5's lidar shallow raster
  and deep polygons, inside the study footprints
  (``Detailed_Susceptibility_Map_Index``) only;
* landslide susceptibility, fallback: DOGAMI O-16-02's statewide overview
  (1:500,000), measured only on the part of a lot the detailed map does not
  reach, and labelled on the note as the coarse statewide map;
* landslide inventory: SLIDO-4.5 deposits and scarp flanks (areas), scarps
  touching the lot (lines) and historic landslide points on it;
* liquefaction: DOGAMI O-19-09 from DOGAMI's own geodatabase, its ``Class``
  (Hazus 0-5) and ``LQ_Label`` as printed;
* flood: the FEMA flood layer, Metro Title 3 and West Linn's flood area already
  held by the acquire stage -- no new layer.

**Four states, never confused.** Each lot row is one of: a printed class
(``class``; a class FLATS ranks none or low is still a class, and the page
says "mapped as" it), the part a map leaves unmapped inside its coverage
(``not_mapped``), the part outside the map's coverage (``outside``), or, for
the coarse overview, the part the detailed map covers instead
(``superseded``). A layer with **no rows** on a lot was not loaded there, and
the page says "not loaded yet". Nothing here prints "no hazard": an unmapped
or unread part is named as such.

**Measuring.** Areas are square feet in EPSG:2913 (Oregon North, feet), the
CRS every FLATS lot area is measured in. An area layer's rows sum to the lot:
where two classes overlap, the worse one takes the ground (a deposit outranks
a scarp flank), so nothing is counted twice. Rasters are cut cell-exact: the
cells under the lot are turned into polygons in the raster's own CRS and
carried into EPSG:2913. Line and point layers count the features touching or
on the lot (with the scarp length inside it) instead of an area.

The measuring half needs shapely (and rasterio for rasters) and runs where the
lot polygons are (LXC 137, ``scripts/flats_lot_hazards.py``); the registry and
the words are plain Python and are what the page reads.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal, Mapping, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "pipeline.yaml"

#: The row states (module docstring). "Not loaded" is the absence of rows.
CLASS = "class"
NOT_MAPPED = "not_mapped"
OUTSIDE = "outside"
SUPERSEDED = "superseded"
#: Not ground: the distance from the shape to the nearest feature of one class
#: (``nearest_ft`` layers; area and share 0). Shares of the other states sum to
#: the shape.
NEAREST = "nearest"
STATES = (CLASS, NOT_MAPPED, OUTSIDE, SUPERSEDED, NEAREST)

#: FLATS's rank of a printed class, least to most. ``undetermined`` (a FEMA
#: zone D, a raster value the legend does not name) sits above moderate: an
#: unknown is never read as mild.
LEVELS = ("none", "very_low", "low", "moderate", "undetermined", "high", "very_high")
LEVEL_WORDS = {
    "none": "none",
    "very_low": "very low",
    "low": "low",
    "moderate": "moderate",
    "undetermined": "undetermined",
    "high": "high",
    "very_high": "very high",
}
#: Levels the page calls "mapped as none or low".
LOW_LEVELS = frozenset({"none", "very_low", "low"})

HAZARDS = ("landslide", "liquefaction", "flood")
HAZARD_TITLES = {"landslide": "Landslide", "liquefaction": "Earthquake liquefaction", "flood": "Flood"}

#: Pieces under one square foot are dropped (they fall to the remainder).
MIN_PIECE_SQFT = 1.0
#: How far a lot's rows may stray from its area, as a share.
SUM_TOLERANCE = 0.005
#: Features listed per row at most (the count is always whole).
MAX_FEATURES = 50

#: Columns of the build's lot file.
LOT_COLUMNS = (
    "county", "tlid", "hazard", "layer", "state", "class_code", "class_label",
    "area_sqft", "share", "detail", "lot_area_sqft",
)

Level = Literal["none", "very_low", "low", "moderate", "undetermined", "high", "very_high"]


# --- the registry ----------------------------------------------------------------


class Download(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    bytes: int | None = None
    last_modified: str | None = None


class Publication(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    publisher: str
    title: str
    number: str
    date: str
    page: str
    scale: str | None = None
    download: Download | None = None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "publisher": self.publisher, "title": self.title, "number": self.number,
            "date": self.date, "url": self.page, "scale": self.scale,
            "download": self.download.url if self.download else None,
        }


class ClassDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    label: str
    level: Level


class PartDef(BaseModel):
    """One feature class measured into a layer with others (the inventory)."""

    model_config = ConfigDict(frozen=True)

    layer: str
    code: str
    label: str
    level: Level


class LayerSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    hazard: Literal["landslide", "liquefaction", "flood"]
    kind: Literal["coverage", "raster", "polygon", "line", "point"]
    title: str
    publication: str
    #: The publication whose download holds the layer, when not its own.
    download_from: str | None = None
    #: A layer held by the acquire stage (a ``datasets`` key) instead of a download.
    held: str | None = None
    layer: str | None = None
    layer_candidates: tuple[str, ...] = ()
    parts: tuple[PartDef, ...] = ()
    coverage: str | None = None
    coverage_mode: Literal["inside", "outside"] | None = None
    class_field: str | None = None
    label_field: str | None = None
    classes: tuple[ClassDef, ...] = ()
    #: Fixed class of a one-class layer (presence is the class).
    code: str | None = None
    level: Level | None = None
    rule: Literal["fema", "title3"] | None = None
    detail_fields: tuple[str, ...] = ()
    #: Collect each feature's details under its class instead of splitting
    #: rows by them.
    list_features: bool = False
    #: Jurisdiction paths the layer applies to; empty is everywhere.
    serves: tuple[str, ...] = ()
    #: Also record, per class, the distance in feet from the shape to the
    #: nearest feature, searched this far (beyond it the distance is None:
    #: "none within"). Vector layers only.
    nearest_ft: float | None = None

    @model_validator(mode="after")
    def _complete(self) -> LayerSpec:
        if not (self.held or self.layer or self.layer_candidates or self.parts):
            raise ValueError(f"{self.key}: names no layer to read")
        if (self.coverage is None) != (self.coverage_mode is None):
            raise ValueError(f"{self.key}: coverage and coverage_mode go together")
        if self.kind in ("line", "point") and not self.code:
            raise ValueError(f"{self.key}: a line or point layer names its class (code)")
        if self.kind in ("raster", "polygon") and not (self.classes or self.parts or self.rule or self.code):
            raise ValueError(f"{self.key}: an area layer needs classes, parts, a rule or a fixed code")
        if self.kind == "raster" and not self.classes:
            raise ValueError(f"{self.key}: a raster names the class of every value")
        if self.nearest_ft is not None and self.kind not in ("polygon", "line", "point"):
            raise ValueError(f"{self.key}: nearest_ft is measured on vector layers only")
        return self

    def nearest_classes(self) -> list[tuple[str | None, str | None]]:
        """The ``(code, label)`` classes a ``nearest_ft`` layer measures distance to."""
        if self.parts:
            return [(p.code, p.label) for p in self.parts]
        if self.classes:
            return [(c.code, c.label) for c in self.classes]
        return [(self.code, self.code)]

    def class_def(self, code: str | None) -> ClassDef | PartDef | None:
        for c in (*self.classes, *self.parts):
            if c.code == code:
                return c
        return None

    def covers(self, jurisdiction: str | None) -> bool:
        """Does the layer apply here? A lot whose place is unknown is measured."""
        if not self.serves or not jurisdiction:
            return True
        return any(jurisdiction == s or jurisdiction.startswith(f"{s}/") for s in self.serves)

    @property
    def source_publication(self) -> str:
        return self.download_from or self.publication


class Registry(BaseModel):
    model_config = ConfigDict(frozen=True)

    caveat: str
    publications: dict[str, Publication]
    layers: dict[str, LayerSpec]

    @model_validator(mode="after")
    def _linked(self) -> Registry:
        for spec in self.layers.values():
            for pub in (spec.publication, spec.download_from):
                if pub and pub not in self.publications:
                    raise ValueError(f"{spec.key}: no publication {pub!r}")
            if spec.coverage and (spec.coverage not in self.layers or self.layers[spec.coverage].kind != "coverage"):
                raise ValueError(f"{spec.key}: coverage {spec.coverage!r} is not a coverage layer")
        return self

    def measured(self) -> list[LayerSpec]:
        """The layers a lot carries rows for, in page order."""
        return [s for s in self.layers.values() if s.kind != "coverage"]


def parse_registry(raw: Mapping[str, Any]) -> Registry:
    section = raw.get("hazard_notes") or {}
    pubs = {k: Publication(key=k, **v) for k, v in (section.get("publications") or {}).items()}
    layers = {k: LayerSpec(key=k, **v) for k, v in (section.get("layers") or {}).items()}
    return Registry(caveat=" ".join(str(section.get("caveat") or "").split()), publications=pubs, layers=layers)


@lru_cache(maxsize=4)
def load_registry(path: Path | None = None) -> Registry:
    raw = yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8")) or {}
    return parse_registry(raw)


# --- classes ---------------------------------------------------------------------


def printed_code(value: Any) -> str | None:
    """A class value as the source prints it; a whole float reads as its integer."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    return text or None


def fema_level(zone: str | None, subtype: str | None, sfha: str | None) -> str:
    """FLATS's rank of a FEMA zone (NFHL ``FLD_ZONE``, ``ZONE_SUBTY``, ``SFHA_TF``).

    A special flood hazard area (``SFHA_TF`` T, the A and V zones) is high, its
    floodway very high; the 0.2 percent annual chance area and areas behind a
    levee are moderate; the area of minimal flood hazard is low; zone D (possible
    but undetermined hazard) and anything not recognised are undetermined.
    """
    z = (zone or "").strip().upper()
    s = (subtype or "").strip().upper()
    t = (sfha or "").strip().upper()
    if z == "OPEN WATER":
        return "high"
    if t == "T" or z.startswith(("A", "V")):
        return "very_high" if "FLOODWAY" in s else "high"
    if z == "D":
        return "undetermined"
    if z in ("X", "B", "C", "X500", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"):
        if z == "B" or "0.2" in s or "LEVEE" in s or "FUTURE" in s:
            return "moderate"
        if z == "C" or "MINIMAL" in s:
            return "low"
    return "undetermined"


def fema_in_100_year(zone: str | None) -> bool | None:
    """Is a printed FEMA zone a 100-year (1% annual chance, special flood hazard)
    zone? From the zone letter only: every A and V zone is; every other printed
    zone (X, B, C, D, open water) is not. None when no zone is printed."""
    z = (zone or "").strip().upper()
    if not z:
        return None
    if z == "AREA NOT INCLUDED":
        return None
    return z.startswith(("A", "V"))


def level_of(spec: LayerSpec, code: str | None, label: str | None, detail: Mapping[str, Any] | None) -> str:
    """FLATS's rank of one printed class of one layer (never ``none`` for an unknown)."""
    if spec.rule == "fema":
        return fema_level(code, label, (detail or {}).get("SFHA_TF"))
    if spec.rule == "title3":
        return "high"
    found = spec.class_def(code)
    if found is not None:
        return found.level
    if spec.level and (spec.code is None or code == spec.code):
        return spec.level
    return "undetermined"


def classify(spec: LayerSpec, props: Mapping[str, Any], part: PartDef | None = None) -> tuple[str, str | None, str | None] | None:
    """One feature's ``(state, class_code, class_label)``, or None when it is not
    a feature of this layer (a Title 3 polygon with neither flood flag)."""
    if part is not None:
        return CLASS, part.code, part.label
    if spec.rule == "fema":
        zone = printed_code(props.get(spec.class_field or "FLD_ZONE"))
        subtype = printed_code(props.get(spec.label_field or "ZONE_SUBTY"))
        if zone and zone.upper() == "AREA NOT INCLUDED":
            return OUTSIDE, zone, subtype
        return CLASS, zone, subtype
    if spec.rule == "title3":
        flags = [name for name in ("FLOOD96", "FEMA") if printed_code(props.get(name)) == "1"]
        if not flags:
            return None
        code = " ".join(f"{name}={printed_code(props.get(name)) or '0'}" for name in ("FLOOD96", "FEMA"))
        words = {"FLOOD96": "1996 flood inundation area", "FEMA": "FEMA floodplain"}
        return CLASS, code, " and ".join(words[f] for f in flags)
    if spec.class_field:
        code = printed_code(props.get(spec.class_field))
        if code is None:
            return CLASS, None, None
        label = printed_code(props.get(spec.label_field)) if spec.label_field else None
        if label is None:
            found = spec.class_def(code)
            label = found.label if found else None
        return CLASS, code, label
    return CLASS, spec.code, spec.code


def feature_detail(spec: LayerSpec, props: Mapping[str, Any]) -> dict[str, Any]:
    out = {}
    for name in spec.detail_fields:
        value = props.get(name)
        if isinstance(value, float) and math.isnan(value):
            value = None
        out[name] = value
    return out


# --- measuring (shapely) ---------------------------------------------------------


@dataclass
class Feature:
    """One classed shape of one layer, in EPSG:2913."""

    state: str
    code: str | None
    label: str | None
    attrs: dict[str, Any]
    geom: Any


@dataclass
class Group:
    state: str
    code: str | None
    label: str | None
    attrs: dict[str, Any] | None
    rank: int
    feats: list[Feature] = field(default_factory=list)


def _group(spec: LayerSpec, feats: Iterable[Feature]) -> list[Group]:
    groups: dict[tuple, Group] = {}
    for f in feats:
        attrs_key = None if spec.list_features else json.dumps(f.attrs, sort_keys=True, default=str)
        key = (f.state, f.code, f.label, attrs_key)
        g = groups.get(key)
        if g is None:
            level = level_of(spec, f.code, f.label, f.attrs) if f.state == CLASS else None
            # Classes worst first; an "area not included" piece after every class.
            rank = LEVELS.index(level) if level else -1
            g = groups[key] = Group(f.state, f.code, f.label, None if spec.list_features else (f.attrs or None), rank)
        g.feats.append(f)
    return sorted(groups.values(), key=lambda g: (-g.rank, str(g.code), str(g.label), json.dumps(g.attrs, sort_keys=True, default=str)))


def _features_detail(feats: Sequence[Feature]) -> dict[str, Any]:
    seen: dict[str, dict[str, Any]] = {}
    for f in feats:
        if f.attrs:
            seen.setdefault(json.dumps(f.attrs, sort_keys=True, default=str), f.attrs)
    listed = list(seen.values())
    return {"feature_count": len(listed), "features": listed[:MAX_FEATURES]}


def measure_area(
    spec: LayerSpec,
    lot: Any,
    lot_area: float,
    feats: Sequence[Feature],
    coverage: Any | None = None,
    *,
    min_piece_sqft: float = MIN_PIECE_SQFT,
) -> list[dict[str, Any]]:
    """One area layer on one lot: the rows (``state``, ``class_code``,
    ``class_label``, ``area_sqft``, ``detail``) that sum to ``lot_area``.

    ``coverage`` is the union of the layer's coverage polygons near the lot
    (None when none touch it); with ``coverage_mode`` inside, the rest of the
    lot is ``outside``; with outside, the covered part is ``superseded``.
    """
    import shapely

    domain = lot
    off_state, off_area = None, 0.0
    if spec.coverage_mode:
        inside = shapely.intersection(lot, coverage) if coverage is not None else None
        in_area = min(float(shapely.area(inside)) if inside is not None else 0.0, lot_area)
        if spec.coverage_mode == "inside":
            domain = inside
            off_state, off_area = OUTSIDE, lot_area - in_area
        else:
            domain = shapely.difference(lot, coverage) if coverage is not None else lot
            off_state, off_area = SUPERSEDED, in_area
    domain_area = max(0.0, lot_area - off_area)
    found: list[dict[str, Any]] = []
    taken = None
    if domain is not None and domain_area > 0 and feats:
        # Worst class first: where classes overlap, the worse one takes the ground.
        for g in _group(spec, feats):
            parts = []
            for f in g.feats:
                if shapely.contains_properly(f.geom, domain):
                    parts = [domain]
                    break
                piece = shapely.intersection(domain, f.geom)
                if not shapely.is_empty(piece):
                    parts.append(piece)
            if not parts:
                continue
            geom = parts[0] if len(parts) == 1 else shapely.union_all(parts)
            if taken is not None:
                geom = shapely.difference(geom, taken)
            area = float(shapely.area(geom))
            if area <= 0:
                continue
            taken = geom if taken is None else shapely.union(taken, geom)
            if area < min_piece_sqft:
                continue  # falls to the remainder
            detail = _features_detail(g.feats) if spec.list_features else g.attrs
            found.append({"state": g.state, "class_code": g.code, "class_label": g.label, "area_sqft": area, "detail": detail})
    # The remainder is whatever the map did not class, so the rows sum to the lot.
    remainder = max(0.0, domain_area - sum(r["area_sqft"] for r in found))
    out = sorted((r for r in found if r["state"] == CLASS), key=lambda r: -r["area_sqft"])
    if off_state and off_area >= min_piece_sqft:
        out.append({"state": off_state, "class_code": None, "class_label": None, "area_sqft": off_area, "detail": None})
    out.extend(r for r in found if r["state"] == OUTSIDE)
    if remainder >= min_piece_sqft or not out:
        out.append({"state": NOT_MAPPED, "class_code": None, "class_label": None, "area_sqft": remainder, "detail": None})
    for r in out:
        r["share"] = r["area_sqft"] / lot_area if lot_area else 0.0
    return out


def measure_count(spec: LayerSpec, lot: Any, feats: Sequence[Feature]) -> list[dict[str, Any]]:
    """A line or point layer on one lot: one row, the features touching or on it."""
    import shapely

    hits = [f for f in feats if shapely.intersects(lot, f.geom)]
    if not hits:
        return [{"state": NOT_MAPPED, "class_code": None, "class_label": None, "area_sqft": 0.0, "share": 0.0,
                 "detail": {"count": 0}}]
    detail = _features_detail(hits)
    detail["count"] = len(hits)
    if spec.kind == "line":
        detail["length_ft"] = round(sum(float(shapely.length(shapely.intersection(lot, f.geom))) for f in hits), 1)
    return [{"state": CLASS, "class_code": spec.code, "class_label": spec.code, "area_sqft": 0.0, "share": 0.0,
             "detail": detail}]


def measure_nearest(spec: LayerSpec, shape: Any, near: Sequence[Feature]) -> list[dict[str, Any]]:
    """One ``nearest`` row per class of a ``nearest_ft`` layer: the distance in
    feet from ``shape`` to the nearest feature of that class (0 when one touches
    or covers it), or None when none lies within ``spec.nearest_ft``.

    ``near`` holds the layer's features within the search distance."""
    import shapely

    best: dict[str | None, float] = {}
    for f in near:
        d = float(shapely.distance(shape, f.geom))
        if spec.nearest_ft is not None and d > spec.nearest_ft:
            continue
        if f.code not in best or d < best[f.code]:
            best[f.code] = d
    out = []
    for code, label in spec.nearest_classes():
        d = best.get(code)
        out.append({
            "state": NEAREST, "class_code": code, "class_label": label, "area_sqft": 0.0, "share": 0.0,
            "detail": {
                "distance_ft": round(d, 1) if d is not None else None,
                "on_shape": d is not None and d == 0.0,
                "searched_ft": spec.nearest_ft,
            },
        })
    return out


class VectorLayer:
    """A layer's classed features with a spatial index."""

    def __init__(self, spec: LayerSpec, feats: Sequence[Feature]):
        import numpy as np
        import shapely

        self.spec = spec
        self.feats = list(feats)
        self._geoms = np.array([f.geom for f in self.feats], dtype=object)
        self._tree = shapely.STRtree(self._geoms)
        shapely.prepare(self._geoms)

    def features(self, lot: Any) -> list[Feature]:
        return [self.feats[int(i)] for i in self._tree.query(lot, predicate="intersects")]

    def within(self, shape: Any, distance_ft: float) -> list[Feature]:
        """The features within ``distance_ft`` of ``shape`` (touching included)."""
        return [self.feats[int(i)] for i in self._tree.query(shape, predicate="dwithin", distance=distance_ft)]

    def union_for(self, lot: Any) -> Any | None:
        import shapely

        found = self.features(lot)
        if not found:
            return None
        return found[0].geom if len(found) == 1 else shapely.union_all([f.geom for f in found])


class RasterLayer:
    """A classed raster, cut cell-exact under each lot (module docstring).

    ``path`` is anything rasterio opens: a GeoTIFF, or a raster inside a file
    geodatabase (``OpenFileGDB:/path/x.gdb:Name``). Opened lazily, so a forked
    worker opens its own handle.
    """

    def __init__(self, spec: LayerSpec, path: str, *, working_srid: int = 2913):
        self.spec = spec
        self.path = path
        self.working_srid = working_srid
        self._ds = None
        self._fwd = None
        self._inv = None

    def _open(self) -> Any:
        if self._ds is None:
            import rasterio
            from pyproj import Transformer

            self._ds = rasterio.open(self.path)
            self._fwd = Transformer.from_crs(self.working_srid, self._ds.crs, always_xy=True)
            self._inv = Transformer.from_crs(self._ds.crs, self.working_srid, always_xy=True)
        return self._ds

    @staticmethod
    def _apply(transformer: Any) -> Any:
        import numpy as np

        def fn(coords: Any) -> Any:
            x, y = transformer.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])

        return fn

    def features(self, lot: Any) -> list[Feature]:
        import numpy as np
        import shapely
        from rasterio.features import shapes
        from rasterio.windows import Window
        from shapely.geometry import shape

        ds = self._open()
        g = shapely.transform(lot, self._apply(self._fwd))
        minx, miny, maxx, maxy = g.bounds
        inv = ~ds.transform
        c0, r0 = inv * (minx, maxy)
        c1, r1 = inv * (maxx, miny)
        col0 = max(0, math.floor(min(c0, c1)) - 1)
        col1 = min(ds.width, math.ceil(max(c0, c1)) + 1)
        row0 = max(0, math.floor(min(r0, r1)) - 1)
        row1 = min(ds.height, math.ceil(max(r0, r1)) + 1)
        if col1 <= col0 or row1 <= row0:
            return []
        win = Window(col0, row0, col1 - col0, row1 - row0)
        arr = ds.read(1, window=win)
        if arr.dtype not in (np.uint8, np.int16, np.uint16, np.int32, np.float32):
            arr = arr.astype(np.int32)
        # The dataset's validity mask: its nodata value, or the per-dataset mask
        # a geodatabase raster carries (copied into the GeoTIFF) -- never a class.
        mask = ds.read_masks(1, window=win) > 0
        if not mask.any():
            return []
        out = []
        for geojson, value in shapes(arr, mask=mask, transform=ds.window_transform(win)):
            poly = shapely.transform(shape(geojson), self._apply(self._inv))
            code = printed_code(value)
            found = self.spec.class_def(code)
            out.append(Feature(CLASS, code, found.label if found else None, {}, poly))
        return out


def measure_lots(
    lots: Sequence[Mapping[str, Any]],
    layers: Sequence[VectorLayer | RasterLayer],
    coverages: Mapping[str, VectorLayer],
    *,
    min_piece_sqft: float = MIN_PIECE_SQFT,
) -> Iterator[dict[str, Any]]:
    """Every layer on every lot; yields lot rows (:data:`LOT_COLUMNS`).

    ``lots`` carry ``county``, ``tlid``, ``geom`` (shapely, EPSG:2913) and
    optionally ``jurisdiction``; a layer that serves named places only is
    skipped on a lot elsewhere (no rows: not this layer's ground).
    """
    import shapely

    for lot in lots:
        geom = lot.get("geom")
        if geom is None or shapely.is_empty(geom):
            continue
        lot_area = float(shapely.area(geom))
        if lot_area <= 0:
            continue
        base = {"county": lot["county"], "tlid": lot["tlid"], "lot_area_sqft": round(lot_area, 1)}
        for r in measure_shape(geom, layers, coverages, jurisdiction=lot.get("jurisdiction"), min_piece_sqft=min_piece_sqft):
            yield {
                **base,
                **r,
                "area_sqft": round(r["area_sqft"], 1),
                "share": round(r["share"], 5),
                "detail": json.dumps(r["detail"], sort_keys=True, default=str) if r["detail"] is not None else "",
            }


def measure_shape(
    shape: Any,
    layers: Sequence[VectorLayer | RasterLayer],
    coverages: Mapping[str, VectorLayer],
    *,
    jurisdiction: str | None = None,
    min_piece_sqft: float = MIN_PIECE_SQFT,
) -> Iterator[dict[str, Any]]:
    """Every layer on any polygon in EPSG:2913 -- a lot, or a placed building
    footprint: rows of ``hazard``, ``layer``, ``state``, ``class_code``,
    ``class_label``, ``area_sqft``, ``share`` (of the shape) and ``detail`` (a
    dict). A layer that serves named places only is skipped elsewhere."""
    import shapely

    if shape is None or shapely.is_empty(shape):
        return
    area = float(shapely.area(shape))
    if area <= 0:
        return
    for layer in layers:
        spec = layer.spec
        if not spec.covers(jurisdiction):
            continue
        feats = layer.features(shape)
        if spec.kind in ("line", "point"):
            rows = measure_count(spec, shape, feats)
        else:
            coverage = coverages[spec.coverage].union_for(shape) if spec.coverage else None
            rows = measure_area(spec, shape, area, feats, coverage, min_piece_sqft=min_piece_sqft)
        if spec.rule == "fema":
            for r in rows:
                if r["state"] == CLASS:
                    r["detail"] = {**(r["detail"] or {}), "in_100_year": fema_in_100_year(r["class_code"])}
        if spec.nearest_ft is not None and isinstance(layer, VectorLayer):
            rows = [*rows, *measure_nearest(spec, shape, layer.within(shape, spec.nearest_ft))]
        for r in rows:
            yield {"hazard": spec.hazard, "layer": spec.key, **r}


# --- words -----------------------------------------------------------------------


def _pct(share: float) -> str:
    pct = share * 100
    if 0 < pct < 1:
        return "under 1"
    return f"{pct:.0f}"


def fema_words(code: str | None, label: str | None, detail: Mapping[str, Any] | None) -> str:
    """A FEMA zone in words, its static base flood elevation and datum where given."""
    words = f"zone {code}" if code else "zone not stated"
    if label:
        words += f" ({label.lower()})"
    detail = detail or {}
    bfe = detail.get("STATIC_BFE")
    try:
        bfe_num = float(bfe) if bfe not in (None, "") else None
    except (TypeError, ValueError):
        bfe_num = None
    if bfe_num is not None and bfe_num > -9000:
        unit = (detail.get("LEN_UNIT") or "").lower() or "units not stated"
        datum = detail.get("V_DATUM") or "datum not held"
        words += f", base flood elevation {bfe_num:g} {unit} ({datum})"
    depth = detail.get("DEPTH")
    try:
        depth_num = float(depth) if depth not in (None, "") else None
    except (TypeError, ValueError):
        depth_num = None
    if depth_num is not None and depth_num > -9000:
        words += f", flood depth {depth_num:g} {(detail.get('LEN_UNIT') or '').lower() or 'units not stated'}"
    return words


def class_words(spec: LayerSpec, code: str | None, label: str | None, detail: Mapping[str, Any] | None) -> str:
    if spec.rule == "fema":
        return fema_words(code, label, detail)
    if code is None:
        return f"no class printed ({spec.class_field} empty)"
    if label:
        return label
    return f"value {code}, not in the publication's legend"


def _detail(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def describe_layer(spec: LayerSpec, rows: Sequence[Mapping[str, Any]], registry: Registry) -> dict[str, Any]:
    """One layer on one lot, in words and with its technical fields."""
    pub = registry.publications[spec.publication]
    base = {
        "layer": spec.key,
        "hazard": spec.hazard,
        "title": spec.title,
        "kind": spec.kind,
        "publication": pub.as_dict(),
        "read_from": registry.publications[spec.source_publication].as_dict() if spec.download_from else None,
        "class_field": spec.class_field,
        "label_field": spec.label_field,
    }
    if spec.nearest_ft is not None:
        base["nearest"] = None
    if spec.rule == "fema":
        base["in_100_year_zone"] = None
        base["zones"] = []
    if not rows:
        return {**base, "status": "not_loaded", "words": "Not loaded yet.", "classes": [], "worst": None}
    near_rows = [r for r in rows if r["state"] == NEAREST]
    rows = [r for r in rows if r["state"] != NEAREST]
    near_words = ""
    if spec.nearest_ft is not None and near_rows:
        base["nearest"] = [
            {"class_code": r.get("class_code"), "class_label": r.get("class_label"), **(_detail(r.get("detail")) or {})}
            for r in near_rows
        ]
        bits = []
        for n in base["nearest"]:
            name = (n["class_label"] or n["class_code"] or "feature").lower()
            if n.get("distance_ft") is None:
                bits.append(f"no mapped {name} within {n['searched_ft']:,.0f} ft")
            elif n["distance_ft"] == 0:
                bits.append(f"a mapped {name} touches or covers it")
            else:
                bits.append(f"nearest mapped {name} {n['distance_ft']:,.0f} ft away")
        joined = "; ".join(bits)
        near_words = " " + joined[0].upper() + joined[1:] + "."
    entries = []
    for r in sorted(rows, key=lambda r: (-float(r.get("area_sqft") or 0), r.get("state") != CLASS)):
        detail = _detail(r.get("detail"))
        state = r["state"]
        level = level_of(spec, r.get("class_code"), r.get("class_label"), detail) if state == CLASS else None
        share = float(r.get("share") or 0)
        entries.append({
            "state": state,
            "class_code": r.get("class_code"),
            "class_label": r.get("class_label"),
            "words": class_words(spec, r.get("class_code"), r.get("class_label"), detail) if state == CLASS else None,
            "level": level,
            "level_words": LEVEL_WORDS.get(level or "", None),
            "area_sqft": float(r.get("area_sqft") or 0),
            "share": share,
            "share_pct": _pct(share),
            "detail": detail,
        })
    classes = [e for e in entries if e["state"] == CLASS]
    worst = max(classes, key=lambda e: (LEVELS.index(e["level"]), e["share"])) if classes else None
    if spec.rule == "fema" and classes:
        # The plain 100-year answer from the zone letter, the letters beside it.
        flags = [(e["detail"] or {}).get("in_100_year", fema_in_100_year(e["class_code"])) for e in classes]
        base["zones"] = sorted({e["class_code"] for e in classes if e["class_code"]})
        base["in_100_year_zone"] = True if any(f is True for f in flags) else (False if all(f is False for f in flags) else None)
    if spec.kind in ("line", "point"):
        noun = "scarp" if spec.kind == "line" else "historic landslide point"
        if worst is None:
            words = f"No mapped {noun} {'touches' if spec.kind == 'line' else 'lies on'} the lot."
            return {**base, "status": "none_found", "words": words + near_words, "classes": entries, "worst": None}
        d = worst["detail"] or {}
        count = int(d.get("count") or 0)
        words = f"{count} mapped {noun}{'s' if count != 1 else ''} {'touch' if count != 1 else 'touches'} the lot"
        if spec.kind == "point":
            words = f"{count} {noun}{'s' if count != 1 else ''} on the lot"
        if d.get("length_ft") is not None:
            words += f" ({d['length_ft']:,.0f} ft of scarp inside it)"
        return {**base, "status": "found", "words": words + "." + near_words, "classes": entries, "worst": worst}
    parts = []
    for e in entries:
        if e["state"] == CLASS:
            parts.append(f"{e['share_pct']}% {e['words']}")
        elif e["state"] == OUTSIDE:
            parts.append(f"{e['share_pct']}% outside this map's coverage")
        elif e["state"] == SUPERSEDED:
            parts.append(f"{e['share_pct']}% covered by the detailed lidar map instead")
        else:
            parts.append(f"{e['share_pct']}% not mapped")
    states = {e["state"] for e in entries}
    if classes:
        status = "mapped_low" if all(e["level"] in LOW_LEVELS for e in classes) else "mapped"
    elif states == {SUPERSEDED}:
        status = "superseded"
    elif states <= {OUTSIDE, SUPERSEDED}:
        status = "outside"
    else:
        status = "not_mapped"
    words = "; ".join(parts) + "."
    if status == "mapped_low":
        words = "Mapped as: " + words
    elif status == "outside":
        words = "This lot is outside this map's coverage."
    elif status == "superseded":
        words = "Not used here: the detailed lidar map covers the whole lot."
    elif status == "not_mapped":
        words = "This map shows nothing on the lot (not the same as no hazard)."
    return {**base, "status": status, "words": words + near_words, "classes": entries, "worst": worst}


def describe(
    rows: Sequence[Mapping[str, Any]],
    *,
    jurisdiction: str | None = None,
    registry: Registry | None = None,
) -> dict[str, Any]:
    """Every hazard layer on one lot, grouped by hazard, for the lot page and the
    lot report. ``rows`` are the lot's ``flats.lot_hazards`` rows (``layer``,
    ``state``, ``class_code``, ``class_label``, ``area_sqft``, ``share``,
    ``detail``); a layer with none reads "not loaded yet". A note, never a colour.
    """
    registry = registry or load_registry()
    by_layer: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by_layer[r["layer"]].append(r)
    groups = []
    for hazard in HAZARDS:
        layers = [
            describe_layer(spec, by_layer.get(spec.key, []), registry)
            for spec in registry.measured()
            if spec.hazard == hazard and spec.covers(jurisdiction)
        ]
        # The coarse overview says nothing where the detailed map covers the whole lot.
        shown = [x for x in layers if x["status"] != "superseded"]
        groups.append({"hazard": hazard, "title": HAZARD_TITLES[hazard], "layers": layers, "shown": shown})
    return {
        "measured": bool(rows),
        "never_a_colour": True,
        "caveat": registry.caveat,
        "groups": groups,
    }
