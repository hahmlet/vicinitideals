"""Public sewer service: whether a lot lies outside it (Steph 2026-11-10).

Steph's ruling (rulings.yaml ``2026-11-10-no-public-sewer-red``): "red with no
public sewer." A lot SHOWN to lie outside public sewer service is RED; where a
place has no sewer service data, the lot is not RED on this ground and carries
an unmeasured-sewer flag instead. Found by false-green round 4: 6055 SW
Shakespeare St (unincorporated Clackamas, outside every sanitary district, the
nearest mapped main 7,546 ft off) and lots on the Lake Oswego edge.

:func:`read_lots` answers one of three states per lot, off the layers
``flats/config/sewer.yaml`` names in an acquire snapshot:

* ``served`` -- a public main of the lot's own provider lies within the reach
  (OAR 340-071-0160(4)(f)(A): 200 ft per dwelling, 800 ft for the pod's four),
  or the lot touches a sewer service area or district polygon (pooled: any
  district that reaches the lot).
* ``outside`` -- neither, no other provider's main in the lot's own street
  (``front_ft``), in a place whose provider's system is mapped here
  (``measured``). RED, reason :data:`NO_PUBLIC_SEWER`. Another city's main
  farther off does not serve: a city is not obliged to serve outside its
  limits (OAR 340-071-0160(4)(f)(B)), and Steph's own example was the Lake
  Oswego edge.
* ``street_main`` -- neither, in a measured place, but another provider's
  main lies in the lot's own street (``front_ft``). A city may serve outside
  its limits by contract or after annexation, and no layer says where it
  does. Steph 2026-11-11 (rulings.yaml ``2026-11-11-sewer-pipe-in-street-yellow``,
  FOLLOWUPS 182): YELLOW with :data:`STREET_MAIN_FLAG` ("sewer hook-up needs
  the provider's agreement or annexation"), reason :data:`STREET_MAIN_REASON`;
  never RED on this ground and never GREEN.
* ``unmeasured`` -- neither, in a place whose sewer is not mapped here. The
  :data:`UNMEASURED_FLAG` rides along below the yellow line, so the colour
  does not move.

This is not the ``public_sewer`` condition fact (:mod:`flats.ingest.quadfit`),
which some standards turn on and which keeps quadfit's 50 ft meaning. A lot
can be ``served`` here and still have no main fronting it.

The bridge refuses a ``--sources`` snapshot missing any layer named here
(:func:`missing`), as it does the corridor and curb maps.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from flats.score import flags as flag_plan

CONFIG = Path(__file__).resolve().parents[1] / "config" / "sewer.yaml"

SERVED = "served"
OUTSIDE = "outside"
UNMEASURED = "unmeasured"
STREET_MAIN = "street_main"
STATES: tuple[str, ...] = (SERVED, OUTSIDE, STREET_MAIN, UNMEASURED)

#: Row keys the bridge writes (:func:`with_sewer`) and the lot reads back.
ROW_STATE = "sewer_service"
ROW_MAIN_FT = "sewer_service_main_ft"
ROW_WHY = "sewer_service_why"

#: The check a RED lot binds on, and the screen reason it carries.
CHECK = "public_sewer_service"
NO_PUBLIC_SEWER = "NO_PUBLIC_SEWER"
#: The reason the unmeasured flag stands for; below the yellow line it is
#: never added to a lot's reasons, but the flag registry names it.
UNMEASURED_REASON = "SEWER_UNMEASURED"
UNMEASURED_FLAG = "SEWER-UNMEASURED"
#: Outside every district, another provider's main in the street: YELLOW
#: (Steph 2026-11-11). The flag sits at or above the yellow line.
STREET_MAIN_REASON = "SEWER_STREET_MAIN"
STREET_MAIN_FLAG = "SEWER-STREET-MAIN"
REASONS: tuple[str, ...] = (NO_PUBLIC_SEWER, STREET_MAIN_REASON, UNMEASURED_REASON)

RULING = "Steph 2026-11-10, rulings.yaml 2026-11-10-no-public-sewer-red: red with no public sewer"
STREET_RULING = (
    "Steph 2026-11-11, rulings.yaml 2026-11-11-sewer-pipe-in-street-yellow: yellow + flag, "
    "hook-up needs the provider's agreement or annexation"
)


@dataclass(frozen=True, slots=True)
class Spec:
    """``flats/config/sewer.yaml``, read."""

    reach_ft: float
    reach_quote: str
    #: Another provider's main this close holds a lot back from RED.
    front_ft: float
    #: Mains layer key -> {field: values that drop a feature}.
    mains: Mapping[str, Mapping[str, frozenset[str]]]
    #: Mains layer key -> the place paths its provider serves.
    serves: Mapping[str, tuple[str, ...]]
    areas: tuple[str, ...]
    #: Place path prefix -> what maps it.
    measured: Mapping[str, str]

    @property
    def keys(self) -> tuple[str, ...]:
        return (*self.mains, *self.areas)

    def measures(self, layer_id: str | None) -> bool:
        """Whether a place's sewer is mapped here: the place itself, or a
        county path above it, is in ``measured``."""
        return _under(layer_id, self.measured)

    def own(self, key: str, layer_id: str | None) -> bool:
        """Whether mains layer ``key`` is the place's own provider's."""
        return _under(layer_id, self.serves.get(key, ()))


def _under(layer_id: str | None, places: Iterable[str]) -> bool:
    if not layer_id:
        return False
    return any(layer_id == p or layer_id.startswith(p.rstrip("/") + "/") for p in places)


def parse(doc: Mapping[str, Any]) -> Spec:
    per = float(doc["reach_ft_per_dwelling"])
    dwellings = int(doc["dwellings"])
    if per <= 0 or dwellings <= 0:
        raise ValueError("sewer reach must be positive")
    mains = {
        str(k): {str(f): frozenset(str(v).upper() for v in vals) for f, vals in ((v or {}).get("exclude") or {}).items()}
        for k, v in (doc.get("mains") or {}).items()
    }
    serves = {
        str(k): tuple(str(p) for p in ((v or {}).get("serves") or ())) for k, v in (doc.get("mains") or {}).items()
    }
    areas = tuple(str(k) for k in (doc.get("areas") or {}))
    if not mains:
        raise ValueError("sewer.yaml names no mains")
    if lacking := sorted(k for k, v in serves.items() if not v):
        raise ValueError(f"sewer.yaml: mains that serve no place: {lacking}")
    return Spec(
        reach_ft=per * dwellings,
        reach_quote=str(doc.get("reach_quote") or ""),
        front_ft=float(doc["front_ft"]),
        mains=mains,
        serves=serves,
        areas=areas,
        measured={str(k): str(v) for k, v in (doc.get("measured") or {}).items()},
    )


@lru_cache(maxsize=1)
def load_spec(path: Path = CONFIG) -> Spec:
    return parse(yaml.safe_load(path.read_text(encoding="utf-8")))


def _manifest(sources: Path) -> dict[str, Any]:
    path = sources / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _dataset_path(sources: Path, manifest: Mapping[str, Any], key: str) -> Path:
    entry = (manifest.get("datasets") or {}).get(key) or {}
    return sources / str(entry.get("file") or f"{key}.geojson")


def missing(sources: Path | None, spec: Spec | None = None) -> tuple[str, ...]:
    """The sewer layers an acquire snapshot lacks -- every one where there is
    no snapshot. Without one a lot outside sewer would pass GREEN unread, so
    the bridge refuses a snapshot missing any."""
    spec = spec or load_spec()
    if sources is None:
        return spec.keys
    manifest = _manifest(sources)
    return tuple(k for k in spec.keys if not _dataset_path(sources, manifest, k).is_file())


def _kept(props: Mapping[str, Any], exclude: Mapping[str, frozenset[str]]) -> bool:
    return not any(str(props.get(f) or "").strip().upper() in vals for f, vals in exclude.items())


@dataclass(frozen=True)
class Maps:
    """Every public main and service polygon a snapshot holds, indexed."""

    #: Mains layer key -> STRtree over its lines (a layer with none is left out).
    mains: Mapping[str, Any]
    areas: Any  # shapely STRtree over polygons, or None
    main_count: int
    area_count: int


def load_maps(sources: Path, spec: Spec | None = None) -> Maps:
    import shapely
    from shapely.geometry import shape
    from shapely.strtree import STRtree

    from flats.ingest.delta import iter_features

    spec = spec or load_spec()
    manifest = _manifest(sources)
    trees: dict[str, Any] = {}
    count = 0
    for key, exclude in spec.mains.items():
        lines: list[Any] = []
        path = _dataset_path(sources, manifest, key)
        for f in iter_features(path) if path.is_file() else ():
            if f.get("geometry") and _kept(f.get("properties") or {}, exclude):
                g = shape(f["geometry"])
                if not g.is_empty:
                    lines.append(g)
        if lines:
            trees[key] = STRtree(lines)
            count += len(lines)
    polys: list[Any] = []
    for key in spec.areas:
        path = _dataset_path(sources, manifest, key)
        for f in iter_features(path) if path.is_file() else ():
            if f.get("geometry"):
                g = shapely.make_valid(shape(f["geometry"]))
                if not g.is_empty:
                    polys.append(g)
    return Maps(
        mains=trees,
        areas=STRtree(polys) if polys else None,
        main_count=count,
        area_count=len(polys),
    )


@dataclass(frozen=True, slots=True)
class Reading:
    state: str
    #: Feet from the lot to the nearest public main of its own provider;
    #: None where the snapshot holds none for its place.
    main_ft: float | None
    why: str


def judge(
    own_ft: float | None, other_ft: float | None, in_area: bool, layer_id: str | None, spec: Spec
) -> Reading:
    """One lot's state from its nearest own-provider main, its nearest other
    provider's main, and whether it touches a service area or district."""
    reach = spec.reach_ft
    if own_ft is not None and own_ft <= reach:
        return Reading(SERVED, own_ft, f"a public main within {reach:,.0f} ft ({own_ft:,.0f} ft)")
    if in_area:
        return Reading(SERVED, own_ft, "inside a sewer service area or district")
    near = (
        f"its provider's nearest public main is {own_ft:,.0f} ft off"
        if own_ft is not None
        else "no public main of its provider is mapped"
    )
    measured = spec.measures(layer_id)
    if other_ft is not None and other_ft <= spec.front_ft:
        street = (
            f"outside every sewer service area and district, but another provider's main is "
            f"{other_ft:,.0f} ft off, in its street"
        )
        if measured:
            # Steph 2026-11-11: YELLOW + flag, not RED and not colour kept.
            return Reading(
                STREET_MAIN,
                own_ft,
                f"{street}: hooking up needs that provider's agreement or annexation",
            )
        return Reading(UNMEASURED, own_ft, f"{street}, and this place's own sewer is not mapped")
    if measured:
        cite = f" ({spec.reach_quote})" if spec.reach_quote else ""
        return Reading(
            OUTSIDE,
            own_ft,
            f"outside every sewer service area and district, and {near}: public sewer counts as "
            f"available within {reach:,.0f} ft for four homes{cite}",
        )
    return Reading(UNMEASURED, own_ft, f"no sewer service data for this place, and {near}")


def read_lots(
    geoms: Sequence[Any], layer_ids: Sequence[str | None], maps: Maps, spec: Spec | None = None
) -> list[Reading]:
    """Each lot's :class:`Reading`, lots in EPSG:2913 feet."""
    import numpy as np

    spec = spec or load_spec()
    n = len(geoms)
    inf = float("inf")
    own = np.full(n, inf)
    other = np.full(n, inf)
    in_area = np.zeros(n, dtype=bool)
    arr = np.array(list(geoms), dtype=object)
    for key, tree in maps.mains.items() if n else ():
        idx, dist = tree.query_nearest(arr, return_distance=True, all_matches=False)
        d = np.full(n, inf)
        d[idx[0]] = dist
        mine = np.array([spec.own(key, j) for j in layer_ids], dtype=bool)
        own = np.where(mine, np.minimum(own, d), own)
        other = np.where(mine, other, np.minimum(other, d))
    if n and maps.areas is not None:
        hit = maps.areas.query(arr, predicate="intersects")
        in_area[np.unique(hit[0])] = True

    def ft(v: float) -> float | None:
        return None if v == inf else float(v)

    return [judge(ft(own[i]), ft(other[i]), bool(in_area[i]), layer_ids[i], spec) for i in range(n)]


def with_sewer(rows: Iterable[dict[str, Any]], sources: Path | None, layer_id_of: Any) -> dict[str, int]:
    """Write :data:`ROW_STATE`, :data:`ROW_MAIN_FT` and :data:`ROW_WHY` onto
    every row with a shape, in place; the count per state. Nothing without a
    snapshot (the bridge refuses one missing a layer)."""
    import shapely

    counts = dict.fromkeys(STATES, 0)
    if sources is None:
        return counts
    spec = load_spec()
    maps = load_maps(sources, spec)
    if not maps.mains and maps.areas is None:
        # A snapshot holding none of the layers: the bridge refuses it before
        # this (missing), so only a test gets here, and nothing is read.
        return counts
    shaped = [r for r in rows if r.get("lot_wkb")]
    readings = read_lots(
        [shapely.from_wkb(r["lot_wkb"]) for r in shaped], [layer_id_of(r) for r in shaped], maps, spec
    )
    for row, got in zip(shaped, readings, strict=True):
        row[ROW_STATE] = got.state
        row[ROW_MAIN_FT] = got.main_ft
        row[ROW_WHY] = got.why
        counts[got.state] += 1
    return counts


def reading_of(row: Mapping[str, Any]) -> Reading | None:
    state = row.get(ROW_STATE)
    if state not in STATES:
        return None
    ft = row.get(ROW_MAIN_FT)
    try:
        main_ft = float(ft) if ft is not None else None
    except (TypeError, ValueError):
        main_ft = None
    if main_ft is not None and main_ft != main_ft:  # NaN
        main_ft = None
    return Reading(str(state), main_ft, str(row.get(ROW_WHY) or ""))


# --- the check ---------------------------------------------------------------


def checked(s: Any, reading: Reading | None) -> Any:
    """``s`` RED with :data:`NO_PUBLIC_SEWER` where the lot is outside public
    sewer; a GREEN lot YELLOW with :data:`STREET_MAIN_FLAG` where only another
    provider's main in its street could serve it (a worse colour stays); or
    the :data:`UNMEASURED_FLAG` beside its colour where its place has no data.
    Adds nothing twice; a served lot, or one nobody read, is unchanged."""
    if reading is None or reading.state == SERVED:
        return s
    from flats.score.screen import Triage

    if reading.state == OUTSIDE:
        reach = load_spec().reach_ft
        bind = flag_plan.Bind(
            CHECK,
            reading.main_ft,
            reach,
            None if reading.main_ft is None else round(reading.main_ft - reach, 1),
            source=f"{reading.why} -- {RULING}",
        )

        def red(x: Any) -> Any:
            if any(b.check == CHECK for b in x.binds):
                return x
            reasons = x.reasons if NO_PUBLIC_SEWER in x.reasons else (*x.reasons, NO_PUBLIC_SEWER)
            return dataclasses.replace(x, triage=Triage.red, binds=(*x.binds, bind), reasons=tuple(reasons))

        return dataclasses.replace(s, screening=red(s.screening), signed=red(s.signed))

    if reading.state == STREET_MAIN:
        held = flag_plan.Flag(
            STREET_MAIN_FLAG, flag_plan.LOT, STREET_MAIN_REASON, source=f"{reading.why} -- {STREET_RULING}"
        )

        def yellow(x: Any) -> Any:
            if any(f.code == STREET_MAIN_FLAG for f in x.flags):
                return x
            reasons = x.reasons if STREET_MAIN_REASON in x.reasons else (*x.reasons, STREET_MAIN_REASON)
            triage = Triage.yellow if x.triage is Triage.green else x.triage
            return dataclasses.replace(x, triage=triage, flags=(*x.flags, held), reasons=tuple(reasons))

        return dataclasses.replace(s, screening=yellow(s.screening), signed=yellow(s.signed))

    flag = flag_plan.Flag(UNMEASURED_FLAG, flag_plan.LOT, UNMEASURED_REASON, source=reading.why)

    def add(x: Any) -> Any:
        if any(f.code == UNMEASURED_FLAG for f in x.flags):
            return x
        return dataclasses.replace(x, flags=(*x.flags, flag))

    return dataclasses.replace(s, screening=add(s.screening), signed=add(s.signed))


__all__ = [
    "CHECK",
    "NO_PUBLIC_SEWER",
    "OUTSIDE",
    "REASONS",
    "SERVED",
    "STREET_MAIN",
    "STREET_MAIN_FLAG",
    "UNMEASURED",
    "UNMEASURED_FLAG",
    "Reading",
    "Spec",
    "checked",
    "judge",
    "load_maps",
    "load_spec",
    "missing",
    "read_lots",
    "reading_of",
    "with_sewer",
]
