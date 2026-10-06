"""Institutional land: which lots are schools, parks, hospitals, utilities...

Steph RULED 2026-10-06 (FOLLOWUPS 47) that a lot used by an institution is
RED and never scanned: nobody sells a pod site out of a school campus, and a
44-acre campus held the analysis machine for over an hour finding that out.
Churches and charities are NOT in it -- they do sell land -- so nothing here
reads a place of worship, a nonprofit owner or a tax exemption.

**The reading.** Each category of ``flats/config/institutional.yaml`` is the
union of the OpenStreetMap outlines its tags select (``osm_land_use``) and
the Metro ORCA units of its types held by a public owner (``rlis_orca``). A
lot belongs to the category that covers the most of it, when that share is
at least ``min_share``; a line (a railway) is widened first; a lone point
covers nothing. The share is of the lot's own area, so a house lot that a
park outline brushes is not a park, and a campus split into four taxlots is
four campus lots.

**What it cannot see.** Land nobody has drawn: an institution OpenStreetMap
holds only as a point, or not at all, is screened like any other lot -- the
cost is scan time and a lot the page shows that nobody can buy, never a
false GREEN, because the screen still measures it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config" / "institutional.yaml"
OSM_KEY = "osm_land_use"
#: The tag value meaning "any value, as long as the tag is there".
ANY = "*"
ORCA_KEY = "rlis_orca"


@dataclass(frozen=True)
class Category:
    key: str
    words: str
    #: Each a set of tags that must all match; a value set matches any member.
    osm: tuple[Mapping[str, frozenset[str]], ...] = ()
    orca: frozenset[str] = frozenset()
    #: Tag sets that take an element back out: a park behind a gate, a
    #: railway in a tunnel.
    unless: tuple[Mapping[str, frozenset[str]], ...] = ()

    def takes_osm(self, props: Mapping[str, Any]) -> bool:
        return any(_matches(m, props) for m in self.osm) and not any(_matches(m, props) for m in self.unless)


def _matches(m: Mapping[str, frozenset[str]], props: Mapping[str, Any]) -> bool:
    """Every tag of ``m`` matches; the value ``*`` asks only that the tag is there."""
    return all(
        (props.get(k) not in (None, "")) if ANY in vals else str(props.get(k)) in vals
        for k, vals in m.items()
    )


@dataclass(frozen=True)
class Rules:
    min_share: float
    line_half_width_ft: float
    orca_owners: frozenset[str]
    categories: tuple[Category, ...]

    def osm_category(self, props: Mapping[str, Any]) -> str | None:
        """The first category whose tags the element carries, in file order."""
        for c in self.categories:
            if c.takes_osm(props):
                return c.key
        return None

    def orca_category(self, props: Mapping[str, Any]) -> str | None:
        if str(props.get("OWNLEV1")) not in self.orca_owners:
            return None
        unit = str(props.get("UNITTYPE"))
        for c in self.categories:
            if unit in c.orca:
                return c.key
        return None

    def words(self, key: str) -> str:
        return next((c.words for c in self.categories if c.key == key), key)


def _values(v: Any) -> frozenset[str]:
    if isinstance(v, (list, tuple)):
        return frozenset(str(x) for x in v)
    return frozenset({str(v)})


def load_rules(path: Path = CONFIG) -> Rules:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    cats = []
    for key, body in (doc.get("categories") or {}).items():
        for m in [*(body.get("osm") or ()), *(body.get("unless") or ())]:
            if any(isinstance(v, bool) for v in m.values()) or any(
                isinstance(x, bool) for v in m.values() if isinstance(v, list) for x in v
            ):
                raise ValueError(f"{path}: {key}: quote yes/no tag values -- YAML reads them as true/false")
        cats.append(
            Category(
                key=key,
                words=str(body.get("words") or key),
                osm=tuple({k: _values(v) for k, v in m.items()} for m in body.get("osm") or ()),
                orca=frozenset(body.get("orca") or ()),
                unless=tuple({k: _values(v) for k, v in m.items()} for m in body.get("unless") or ()),
            )
        )
    if not cats:
        raise ValueError(f"{path}: no categories")
    return Rules(
        min_share=float(doc["min_share"]),
        line_half_width_ft=float(doc["line_half_width_ft"]),
        orca_owners=frozenset(doc.get("orca_owners") or ()),
        categories=tuple(cats),
    )


@dataclass(frozen=True)
class Reading:
    """Why a lot is institutional."""

    category: str
    #: Share of the lot's area the category's land covers, 0..1.
    share: float
    #: The feature covering the most of it: ``osm:way/123`` or ``orca:<site>``.
    source: str
    name: str | None = None


@dataclass
class Land:
    """Every category's outlines in the working CRS."""

    rules: Rules
    shapes: dict[str, list[Any]] = field(default_factory=dict)
    labels: dict[str, list[tuple[str, str | None]]] = field(default_factory=dict)

    def add(self, category: str, geom: Any, source: str, name: str | None) -> None:
        self.shapes.setdefault(category, []).append(geom)
        self.labels.setdefault(category, []).append((source, name))

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in sorted(self.shapes.items())}


def build(
    osm: Iterable[Mapping[str, Any]],
    orca: Iterable[Mapping[str, Any]],
    rules: Rules | None = None,
) -> Land:
    """The land from GeoJSON features (working CRS): OSM, then ORCA."""
    import shapely
    from shapely.geometry import shape

    rules = rules or load_rules()
    land = Land(rules)
    for f in osm:
        props = f.get("properties") or {}
        cat = rules.osm_category(props)
        if cat is None or not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if g.geom_type in ("LineString", "MultiLineString"):
            g = g.buffer(rules.line_half_width_ft, cap_style="flat")
        elif g.geom_type not in ("Polygon", "MultiPolygon"):
            continue  # a point covers nothing
        if not g.is_valid:
            g = shapely.make_valid(g)
        if g.is_empty or g.area <= 0:
            continue
        land.add(cat, g, f"osm:{props.get('osm')}", props.get("name"))
    for f in orca:
        props = f.get("properties") or {}
        cat = rules.orca_category(props)
        if cat is None or not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if not g.is_valid:
            g = shapely.make_valid(g)
        if g.is_empty or g.area <= 0:
            continue
        land.add(cat, g, f"orca:{props.get('UNITTYPE')}", props.get("SITENAME"))
    return land


def _path(sources: Path, manifest: Mapping[str, Any], key: str) -> Path | None:
    entry = (manifest.get("datasets") or {}).get(key) or {}
    if entry and entry.get("status") not in ("acquired", "present"):
        return None
    path = sources / str(entry.get("file") or f"{key}.geojson")
    return path if path.is_file() else None


def missing(sources: Path | None) -> list[str]:
    """The datasets a snapshot lacks for this reading; empty when it has both."""
    if sources is None:
        return [OSM_KEY, ORCA_KEY]
    mp = sources / "manifest.json"
    manifest = json.loads(mp.read_text(encoding="utf-8")) if mp.is_file() else {}
    return [k for k in (OSM_KEY, ORCA_KEY) if _path(sources, manifest, k) is None]


def load(sources: Path, rules: Rules | None = None) -> Land | None:
    """The land from an acquire snapshot, or None when it lacks either layer.

    Both or nothing: without the OpenStreetMap extract every school outside
    Metro's school-land list would be scanned and nobody told why.
    """
    from flats.ingest.delta import iter_features

    if missing(sources):
        return None
    manifest = json.loads((sources / "manifest.json").read_text(encoding="utf-8")) if (sources / "manifest.json").is_file() else {}
    osm = _path(sources, manifest, OSM_KEY)
    orca = _path(sources, manifest, ORCA_KEY)
    assert osm is not None and orca is not None
    return build(iter_features(osm), iter_features(orca), rules)


def classify(lots: Sequence[Any], land: Land) -> list[Reading | None]:
    """The reading for each lot geometry (working CRS); None where no category
    covers ``min_share`` of it, or the lot has no shape.

    One spatial index per category and one bulk query for all the lots; the
    pieces a lot shares with one category are unioned before they are
    measured, so an OpenStreetMap park drawn over Metro's park counts once.
    """
    import numpy as np
    import shapely
    from shapely import STRtree

    geoms = np.asarray(list(lots), dtype=object)
    n = len(geoms)
    best_share = np.zeros(n)
    best: list[Reading | None] = [None] * n
    valid = np.array([g is not None and not shapely.is_empty(g) for g in geoms], dtype=bool)
    if not valid.any():
        return best
    idx = np.flatnonzero(valid)
    lot_geoms = shapely.make_valid(geoms[idx].astype(object))
    areas = shapely.area(lot_geoms)
    for cat, shapes in land.shapes.items():
        targets = np.asarray(shapes, dtype=object)
        tree = STRtree(targets)
        li, ti = tree.query(lot_geoms, predicate="intersects")
        if not len(li):
            continue
        pieces = shapely.intersection(lot_geoms[li], targets[ti])
        piece_area = shapely.area(pieces)
        order = np.argsort(li, kind="stable")
        li, ti, pieces, piece_area = li[order], ti[order], pieces[order], piece_area[order]
        starts = np.flatnonzero(np.r_[True, li[1:] != li[:-1]])
        ends = np.r_[starts[1:], len(li)]
        for s, e in zip(starts, ends):
            k = li[s]
            if areas[k] <= 0:
                continue
            covered = piece_area[s] if e - s == 1 else shapely.area(shapely.union_all(pieces[s:e]))
            share = float(min(covered / areas[k], 1.0))
            at = idx[k]
            if share > best_share[at]:
                top = s + int(np.argmax(piece_area[s:e]))
                source, name = land.labels[cat][ti[top]]
                best_share[at] = share
                best[at] = Reading(cat, share, source, name)
    floor = land.rules.min_share
    return [r if r is not None and r.share >= floor else None for r in best]


__all__ = [
    "CONFIG",
    "Category",
    "Land",
    "ORCA_KEY",
    "OSM_KEY",
    "Reading",
    "Rules",
    "build",
    "classify",
    "load",
    "load_rules",
    "missing",
]
