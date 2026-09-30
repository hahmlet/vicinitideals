"""How far each lot is from transit -- a standard per-lot fact.

Steph, 2026-09-30: "If we're building it for one, it's worth building it for
all and making it a standard part of our data collection/processing. However,
we don't need to re-run transit distance every single time." So the distances
are measured once per transit release, written to a file keyed by the lot's
shape (:mod:`flats.ingest.transit`), and read by every screen after that; the
monthly probe says when a layer's data changed and the file is due.

**What is measured.** Four distances, in feet, from the NEAREST POINT OF THE
LOT -- codes ask whether "any portion of the site" or "a lot or parcel that
includes lands within" a distance is, not where its middle is -- to:

* ``rail_stop_ft`` -- an existing MAX, Streetcar or WES station. The state's
  parking reform (OAR 660-012-0440(2), three-quarters of a mile; DLCD's
  guidance: "MAX light rail, streetcar, and WES services").
* ``lrt_station_ft`` -- an existing MAX station only. Hillsboro's station
  community zones (800, 1,300 and 2,600 ft of a "light rail station"),
  Beaverton's (400 ft of an "LRT station platform").
* ``transit_stop_ft`` -- any TriMet stop of any mode.
* ``frequent_route_ft`` -- the line of a route TriMet flags Frequent Service.
  Measured to the LINE, not to a stop: the state rule reaches "lands within
  one-half mile of frequent transit corridors", and DLCD reads it "to the
  corridor rather than the stop".

A lot touching or holding the thing is 0.0.

**What a measurement is worth.** A station is published as one point near
the middle of its platform, and codes measure to the station or the platform
(Portland 33.930.030.H: the platform's edge). A two-car MAX platform is some
200 ft long, so the platform's nearest end can be up to about 100 ft nearer
than the point. The route lines are centrelines; Beaverton measures to the
centreline OR the right-of-way edge, some 30-50 ft nearer. That uncertainty is
recorded per measure (:data:`MEASURE_SLACK_FT`) and a band on the measure
answers "cannot tell" for a lot inside it (:meth:`flats.rules.model.Band.holds`)
-- because the same rule can tighten near transit (Hillsboro SCC-SC's 30 ft
minimum height within 800 ft) or relax (a parking minimum waived within half
a mile), and an over-stated distance is a false GREEN in the first.

**What is not in it.** TriMet only: SMART (Wilsonville), Canby Area Transit,
Sandy Area Metro and South Clackamas are not in Metro's layers, so a lot
served by them reads as far from transit. That is the conservative side for
every rule that relaxes near transit, and no rule in the corpus tightens near
a non-TriMet stop (the tightening ones are all light rail). Walking distance
is not measured; where a code elects it, a straight line is the generous
reading, so a relaxing rule that says "walking" must not read these as its
distance. TriMet's Frequent Service flag is narrower than the state's "four
times an hour during peak service", so the frequent line can only under-count.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from flats.rules.model import MEASURE_SLACK as MEASURE_SLACK_FT
from flats.rules.model import TRANSIT_MEASURES as MEASURES

#: OAR 660-012-0440(2): a city may not mandate parking on "a lot or parcel
#: that includes lands within" three-quarters of a mile of a rail stop or
#: one-half mile of a frequent transit corridor.
RAIL_REACH_FT = 3_960.0
FREQUENT_REACH_FT = 2_640.0


def parking_reform_reach(rail_ft: float | None, frequent_ft: float | None) -> bool | None:
    """Is the lot inside the state parking reform's transit reach?

    True when either measured distance is inside its reach -- the true
    distance is never farther than the measured one, so that is certain.
    False when both were measured and both are beyond reach by more than the
    measurement's doubt -- beyond TriMet's rail and TriMet's Frequent Service
    lines, which is narrower than the state's "four times an hour", so a
    False means "not shown by these layers", never "the rule cannot reach
    it". None when a distance is missing or sits within the doubt.

    Shown on the lot page (Steph, 2026-09-30: "show it, don't screen it");
    the screen does not read it -- the pod parks four either way.
    """
    if rail_ft is not None and rail_ft <= RAIL_REACH_FT:
        return True
    if frequent_ft is not None and frequent_ft <= FREQUENT_REACH_FT:
        return True
    if rail_ft is None or frequent_ft is None:
        return None
    if rail_ft - MEASURE_SLACK_FT["rail_stop_ft"] > RAIL_REACH_FT and (
        frequent_ft - MEASURE_SLACK_FT["frequent_route_ft"] > FREQUENT_REACH_FT
    ):
        return False
    return None


#: Registry keys (flats/config/pipeline.yaml).
STATIONS_KEY = "transit_rail_stations"
STOPS_KEY = "transit_stops"
ROUTES_KEY = "transit_routes"

_RAIL_TYPES = frozenset({"MAX", "STREET CAR", "STREETCAR", "WES"})
_TRUE = frozenset({"TRUE", "T", "Y", "YES", "1"})


@dataclass(frozen=True)
class TransitSet:
    """The geometry each measure is taken to, in the working CRS (feet)."""

    rail: tuple[Any, ...]
    lrt: tuple[Any, ...]
    stops: tuple[Any, ...]
    frequent: tuple[Any, ...]
    #: A hash of the normalised geometry above: the transit version. Two
    #: copies of Metro's layers that differ only in when they were
    #: republished hash the same, so a republish is not a change.
    version: str

    def targets(self) -> dict[str, tuple[Any, ...]]:
        return {
            "rail_stop_ft": self.rail,
            "lrt_station_ft": self.lrt,
            "transit_stop_ft": self.stops,
            "frequent_route_ft": self.frequent,
        }


def _flag(value: Any) -> bool:
    return str(value).strip().upper() in _TRUE


def _version(parts: dict[str, Sequence[Any]]) -> str:
    import shapely

    h = hashlib.sha1()
    for name in sorted(parts):
        h.update(name.encode())
        wkbs = sorted(
            shapely.to_wkb(shapely.set_precision(shapely.normalize(g), 1.0)) for g in parts[name]
        )
        for w in wkbs:
            h.update(w)
    return h.hexdigest()[:16]


def build(
    stations: Iterable[dict[str, Any]],
    stops: Iterable[dict[str, Any]],
    routes: Iterable[dict[str, Any]],
) -> TransitSet:
    """The four target sets from the three layers' GeoJSON features.

    Stations are kept only where their STATUS is Existing (the registry also
    filters server-side). Stops appear once per route; they are deduplicated
    by position to the foot. A frequent line is any route line flagged
    FREQUENT, of any mode -- a MAX line is frequent service too.
    """
    import shapely
    from shapely.geometry import shape

    rail: list[Any] = []
    lrt: list[Any] = []
    for f in stations:
        p = f.get("properties") or {}
        if not f.get("geometry") or str(p.get("STATUS", "Existing")).strip().lower() != "existing":
            continue
        kind = str(p.get("TYPE") or "").strip().upper()
        if kind not in _RAIL_TYPES:
            continue
        g = shape(f["geometry"])
        rail.append(g)
        if kind == "MAX":
            lrt.append(g)
    seen: set[tuple[int, int]] = set()
    points: list[Any] = []
    for f in stops:
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        key = (round(g.x), round(g.y))
        if key in seen:
            continue
        seen.add(key)
        points.append(g)
    frequent = [
        shape(f["geometry"])
        for f in routes
        if f.get("geometry") and _flag((f.get("properties") or {}).get("FREQUENT"))
    ]
    parts = {"rail": rail, "lrt": lrt, "stops": points, "frequent": frequent}
    return TransitSet(
        rail=tuple(rail),
        lrt=tuple(lrt),
        stops=tuple(points),
        frequent=tuple(shapely.line_merge(g) if g.geom_type == "MultiLineString" else g for g in frequent),
        version=_version(parts),
    )


def load(sources: Path) -> TransitSet | None:
    """The transit set from an acquire snapshot, or None if it lacks a layer.

    All three layers or nothing: a snapshot holding stations but no stops
    would write "far from any stop" for every lot, which is a claim, not a
    gap.
    """
    from flats.ingest.delta import iter_features

    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    paths = {}
    for key in (STATIONS_KEY, STOPS_KEY, ROUTES_KEY):
        entry = (manifest.get("datasets") or {}).get(key) or {}
        if entry and entry.get("status") not in ("acquired", "present"):
            return None
        path = sources / str(entry.get("file") or f"{key}.geojson")
        if not path.is_file():
            return None
        paths[key] = path
    return build(
        iter_features(paths[STATIONS_KEY]),
        iter_features(paths[STOPS_KEY]),
        iter_features(paths[ROUTES_KEY]),
    )


def distances(lots: Sequence[Any], transit: TransitSet) -> dict[str, list[float | None]]:
    """Each measure for each lot geometry, in feet; None for a missing lot.

    One spatial index per measure and one nearest-neighbour query for all the
    lots together: 450,000 lots against a few thousand stops is seconds.
    """
    import numpy as np
    import shapely
    from shapely import STRtree

    geoms = np.asarray(lots, dtype=object)
    present = np.array([g is not None and not shapely.is_empty(g) for g in geoms], dtype=bool)
    out: dict[str, list[float | None]] = {}
    for measure, targets in transit.targets().items():
        col: list[float | None] = [None] * len(geoms)
        if targets and present.any():
            tree = STRtree(list(targets))
            idx = np.flatnonzero(present)
            (src, _dst), dist = tree.query_nearest(geoms[idx], return_distance=True, all_matches=False)
            for i, d in zip(src, dist):
                col[int(idx[i])] = round(float(d), 1)
        out[measure] = col
    return out


__all__ = [
    "FREQUENT_REACH_FT",
    "MEASURES",
    "MEASURE_SLACK_FT",
    "RAIL_REACH_FT",
    "parking_reform_reach",
    "TransitSet",
    "build",
    "distances",
    "load",
]
