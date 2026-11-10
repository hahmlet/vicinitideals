"""Whether a mapped trail runs beside a lot, read into ``abuts_trail``.

Tigard's downtown standard (CDC 18.650.070.B.3) screens parking to S-4 "when
abutting a public right-of-way, pedestrian paths and trails in a public
easement, or a public park". The alley and the park are read elsewhere
(:mod:`flats.geom.alley`, :mod:`flats.geom.park`); this module reads the
trail, off Metro's regional trails layer (RLIS ``TRANSIT/trails.shp``,
pipeline key ``rlis_trails``): every trail segment in the region, open,
planned or private, registered to the taxlots.

**What counts as a trail.** Every segment but three kinds: a ``Conceptual``
one (its alignment is not set, so its line says nothing about any lot), a
``Decommissioned`` one (removed from service), and the ``Other`` system type,
which the layer's own metadata reserves for "GIS trail features that do not
exist on the ground" (routing connectors). ``Planned`` and
``Restricted_Private`` segments COUNT: a planned trail's alignment is
adopted, and whether a private trail stands in a public easement is not in
the data -- both are taken on the side that charges the strip.

**What counts as beside.** A trail line that crosses the lot, or comes within
:data:`REACH_FT` of a line that is not a street lot line. The layer holds
centre lines, not easements: a 10-14 ft trail in its easement reaches past
its centre line by half its width, and the layer is registered to the
taxlots at +/- 5 ft in Tigard (metadata). A street line is not measured -- a
trail in the street right-of-way is that right-of-way, which the zone's
street setback already covers.

**ANY line settles True; False needs the lot read.** A lot with no outline
or no s4 edges is not answered, and without the snapshot's trails layer no
lot is: an unread trail is an unanswered lever, and the lot holds out of
GREEN rather than take the narrower number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: The site fact this module answers.
TRAIL_FACT = "abuts_trail"

#: The snapshot key (``flats/config/pipeline.yaml``) the trails are read from.
TRAILS_KEY = "rlis_trails"

#: The layers whose code screens parking beside a trail. Only these rows are
#: read; every other layer leaves the fact unasked.
SERVES: frozenset[str] = frozenset({"or/washington/tigard"})

#: How near a non-street lot line a trail centre line must come to abut it.
REACH_FT = 15.0

#: The statuses (``STATUS``) whose line places no trail on the ground or in
#: an adopted alignment (the layer's metadata, TRANSIT/trails.shp.xml).
NOT_A_TRAIL_STATUS: frozenset[str] = frozenset({"conceptual", "decommissioned"})

#: The system type (``SYSTEMTYPE``) the layer reserves for features that "do
#: not exist on the ground but serve to connect trail segments to the GIS
#: routable streets network".
NOT_A_TRAIL_TYPE: frozenset[str] = frozenset({"other"})

#: s4's class for a street lot line.
STREET_CLASS = "F"


def counts(props: Mapping[str, Any]) -> bool:
    """Whether one trail record places a trail the code would screen against."""
    status = str(props.get("STATUS") or "").strip().lower()
    kind = str(props.get("SYSTEMTYPE") or "").strip().lower()
    return status not in NOT_A_TRAIL_STATUS and kind not in NOT_A_TRAIL_TYPE


@dataclass(frozen=True)
class Trails:
    """The counted trail lines, with a spatial index."""

    lines: tuple[Any, ...]
    tree: Any

    def near(self, geom: Any, distance: float) -> list[Any]:
        if not self.lines:
            return []
        idx = self.tree.query(geom.buffer(distance))
        return [self.lines[int(i)] for i in idx]


def build(lines: Sequence[Any]) -> Trails:
    from shapely import STRtree

    lines = tuple(lines)
    return Trails(lines, STRtree(list(lines)) if lines else None)


def _dataset_path(sources: Path, key: str) -> Path:
    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    entry = (manifest.get("datasets") or {}).get(key) or {}
    return sources / str(entry.get("file") or f"{key}.geojson")


def load(sources: Path, bounds: tuple[float, float, float, float]) -> Trails | None:
    """The snapshot's counted trails inside ``bounds`` (minx, miny, maxx,
    maxy, in the lots' feet), or None where the snapshot holds no trails
    layer -- which leaves every lot unanswered, never False."""
    from shapely.geometry import box, shape

    from flats.ingest.delta import iter_features

    path = _dataset_path(sources, TRAILS_KEY)
    if not path.is_file():
        return None
    area = box(*bounds)
    lines = []
    for f in iter_features(path):
        if not f.get("geometry") or not counts(f.get("properties") or {}):
            continue
        g = shape(f["geometry"])
        if g.intersects(area):
            lines.append(g)
    return build(lines)


def abuts(lot: Any, edges: Sequence[Sequence[Any]] | None, trails: Trails) -> bool | None:
    """``abuts_trail`` for one lot: True where a counted trail crosses the
    lot or comes within :data:`REACH_FT` of a non-street line, False where
    none does, None where the lot cannot be read (no outline, no edges)."""
    from shapely.geometry import LineString

    if lot is None or not edges:
        return None
    for t in trails.near(lot, 0.0):
        if t.intersects(lot):
            return True
    for e in edges:
        if len(e) < 5 or str(e[4]) == STREET_CLASS:
            continue
        line = LineString([(float(e[0]), float(e[1])), (float(e[2]), float(e[3]))])
        if any(t.distance(line) <= REACH_FT for t in trails.near(line, REACH_FT)):
            return True
    return False


def observed_trail(answer: object) -> dict[str, bool]:
    """The fact from the row's stored answer (``trail_abuts_obs``)."""
    return {TRAIL_FACT: answer} if isinstance(answer, bool) else {}


def bounds_of(edges: Iterable[Sequence[Iterable[Any]]]) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for e in edges:
        for line in e:
            xs += [float(line[0]), float(line[2])]
            ys += [float(line[1]), float(line[3])]
    if not xs:
        return None
    return (min(xs) - REACH_FT, min(ys) - REACH_FT, max(xs) + REACH_FT, max(ys) + REACH_FT)
