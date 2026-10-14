"""Lots that lie in more than one zoning district (FOLLOWUPS 76(b)).

The join in quadfit s2 gives a lot the one district covering most of it
(``zone_frac``; under 90 % is ``split_zone``) and every standard is then read
from that district alone. Where the lot's building or its parking stands on
the ground of another district the answer was read from the wrong code.
Steph 2026-10-14: "first check if the city has a rule on this. If no, I would
say yellow." Where a city's code has a rule it is applied
(``flats/config/split_zone.yaml``, with the line it stands on); where none was
found the lot is yellow and says which district lies across the line.

This module reads nothing it was not handed: the zoning maps quadfit s1
stored beside the lot file, and the corpus's own spelling of each map code.
It answers its questions in steps, because the last needs the drawing:

* :func:`with_split_zones` (before the screen, per row): the pieces of the lot
  that lie in a district other than the one the lot is screened under, and how
  far each reaches from it -- or, where no map code can be matched to that
  district, that its own ground could not be found (``unresolved``).
* :func:`governed`: whether the city's rule puts the whole lot in the
  screened district anyway.
* :func:`reached` (after the screen drew the plan): which districts the
  building, its lane or its court stand on.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "split_zone.yaml"

#: A piece of another district smaller than this is the zoning map's line
#: failing to meet the taxlot fabric (a few feet either way along a lot line),
#: not a district the lot lies in; quadfit s2 reads the same noise with its
#: 90 % rule. Square feet of the lot.
PIECE_MIN_SQFT = 100.0

#: The plan standing on a piece of another district by less than this is the
#: same noise. Square feet of the plan.
REACH_MIN_SQFT = 10.0

#: Spacing the far edge of a piece is sampled at when its reach is measured.
REACH_STEP_FT = 2.0

#: Joined into the row, one JSON document per split-zoned lot.
ROW_KEY = "split_zones_json"


@dataclass(frozen=True, slots=True)
class Piece:
    """The part of a lot in one district other than the lot's own."""

    #: The block the district is screened under where the corpus holds it,
    #: else its map code as spelled.
    zone: str
    #: Square feet of the lot in it.
    sqft: float
    #: Where, in the lot's coordinates (shapely geometry).
    geom: Any
    #: How far the farthest ground of the piece lies from the lot's own
    #: district, in feet: how far the zone line would have to be moved to take
    #: the whole piece in (what a "boundary adjustment" rule measures).
    reach_ft: float = 0.0


@dataclass(frozen=True, slots=True)
class Split:
    """What the maps say about one lot lying in more than one district."""

    pieces: tuple[Piece, ...] = ()
    #: No polygon's code could be matched to the district the lot screens
    #: under (a spelling the corpus does not hold, or no map over the lot):
    #: nothing says where its own ground ends, so every plan is in doubt --
    #: the worst case, named (Steph 2026-10-14: "unmeasured = worst case").
    unresolved: bool = False
    #: Square feet of the lot in its own (screened) district.
    own_sqft: float = 0.0

    def __bool__(self) -> bool:
        return bool(self.pieces) or self.unresolved


def zoning_layers(rules_yaml: Path) -> dict[str, str]:
    """Which s1 zoning stage each quadfit jurisdiction's lots were joined to."""
    doc = yaml.safe_load(rules_yaml.read_text(encoding="utf-8"))
    return {
        key: str(j["zoning_layer"])
        for key, j in (doc.get("jurisdictions") or {}).items()
        if isinstance(j, Mapping) and j.get("zoning_layer")
    }


def _reach_ft(piece: Any, own_ground: Any) -> float:
    """How far the farthest point of ``piece`` lies from ``own_ground``, feet
    (the directed distance, sampled along the piece's outline). Infinite
    where the lot has no ground of its own district to measure from."""
    import shapely

    if own_ground is None or own_ground.is_empty:
        return float("inf")
    dense = shapely.segmentize(piece, REACH_STEP_FT)
    pts = shapely.points(shapely.get_coordinates(dense))
    if not len(pts):
        return 0.0
    return float(shapely.distance(pts, own_ground).max())


def pieces_of(
    lot: Any,
    polygons: Sequence[Any],
    codes: Sequence[str],
    own: Callable[[str], bool],
    name: Callable[[str], str],
) -> Split:
    """Split ``lot`` against the zone ``polygons`` (``codes`` aligned).

    ``own(code)`` says whether a map code is the district the lot screens
    under -- by the corpus's spelling, not the map's -- and ``name(code)`` is
    what the district is called in the flag.
    """
    import shapely

    by_zone: dict[str, list[Any]] = {}
    own_parts: list[Any] = []
    for poly, code in zip(polygons, codes):
        got = lot.intersection(poly)
        if got.is_empty or got.area <= 0:
            continue
        if own(code):
            own_parts.append(got)
        else:
            by_zone.setdefault(name(code), []).append(got)
    own_ground = shapely.union_all(own_parts) if own_parts else None
    own_sqft = float(own_ground.area) if own_ground is not None else 0.0
    made = []
    for zone, parts in by_zone.items():
        ground = shapely.union_all(parts)
        if ground.area < PIECE_MIN_SQFT:
            continue
        made.append(Piece(zone, float(ground.area), ground, _reach_ft(ground, own_ground)))
    pieces = tuple(sorted(made, key=lambda p: (-p.sqft, p.zone)))
    # Nothing of the lot's own district on the maps while others lie on it:
    # the maps and the corpus disagree about what the lot is.
    return Split(pieces=pieces, unresolved=own_sqft <= 0.0 and bool(pieces), own_sqft=own_sqft)


def encode(split: Split) -> str:
    """The row's JSON for a :class:`Split` (geometry as hex WKB)."""
    import shapely

    return json.dumps(
        {
            "unresolved": split.unresolved,
            "own_sqft": round(split.own_sqft, 1),
            "pieces": [
                {
                    "zone": p.zone,
                    "sqft": round(p.sqft, 1),
                    "reach_ft": None if p.reach_ft == float("inf") else round(p.reach_ft, 1),
                    "wkb": shapely.to_wkb(p.geom).hex(),
                }
                for p in split.pieces
            ],
        }
    )


def decode(raw: str | None) -> Split:
    """The :class:`Split` a row carries; empty where it carries none."""
    import shapely

    if not raw:
        return Split()
    doc = json.loads(raw)
    return Split(
        pieces=tuple(
            Piece(
                p["zone"],
                float(p["sqft"]),
                shapely.from_wkb(bytes.fromhex(p["wkb"])),
                float("inf") if p.get("reach_ft") is None else float(p["reach_ft"]),
            )
            for p in doc.get("pieces", ())
        ),
        unresolved=bool(doc.get("unresolved")),
        own_sqft=float(doc.get("own_sqft", 0.0)),
    )


def with_split_zones(
    rows: Iterable[dict[str, Any]],
    stage_dir: Path,
    layer_of: Mapping[str, str],
    *,
    own: Callable[[Mapping[str, Any], str], bool],
    name: Callable[[Mapping[str, Any], str], str],
) -> int:
    """Join :data:`ROW_KEY` onto every split-zoned row, in place; say how many.

    ``layer_of`` is :func:`zoning_layers`. ``own(row, code)`` and
    ``name(row, code)`` are :func:`pieces_of`'s, per row, so the caller's
    corpus does the spelling. Each zoning map is read once, and only where a
    split-zoned lot needs it.
    """
    import pandas as pd
    import shapely
    from shapely.strtree import STRtree

    wanted: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if str(row.get("split_zone")).lower() not in ("true", "1") or not row.get("lot_wkb"):
            continue
        layer = layer_of.get(str(row.get("jurisdiction")))
        if layer:
            wanted.setdefault(layer, []).append(row)
    taken = 0
    for layer, members in sorted(wanted.items()):
        path = stage_dir / f"s1_{layer}.parquet"
        if not path.is_file():
            continue
        frame = pd.read_parquet(path, columns=["zone_raw", "wkb"])
        polys = shapely.from_wkb(frame["wkb"].to_numpy())
        codes = ["" if z is None else str(z) for z in frame["zone_raw"]]
        tree = STRtree(polys)
        for row in members:
            lot = shapely.from_wkb(row["lot_wkb"])
            near = sorted(int(i) for i in tree.query(lot, predicate="intersects"))
            split = pieces_of(
                lot,
                [polys[i] for i in near],
                [codes[i] for i in near],
                lambda c, r=row: own(r, c),
                lambda c, r=row: name(r, c),
            )
            if split:
                row[ROW_KEY] = encode(split)
                taken += 1
    return taken


def reached(split: Split, plan: Iterable[Any]) -> tuple[str, ...]:
    """The districts of ``split`` the plan's shapes stand on, by more than
    :data:`REACH_MIN_SQFT`, largest stretch first. ``plan`` is shapely
    geometries (building, lane, court); an empty plan reaches nothing."""
    import shapely

    shapes = [g for g in plan if g is not None and not g.is_empty]
    if not shapes:
        return ()
    stood = shapely.union_all(shapes)
    hit = [(p.zone, stood.intersection(p.geom).area) for p in split.pieces]
    return tuple(z for z, a in sorted(hit, key=lambda t: (-t[1], t[0])) if a > REACH_MIN_SQFT)


@dataclass(frozen=True, slots=True)
class Ruling:
    """What one layer's code says about a lot in two districts."""

    #: ``majority_within``, ``majority``, ``each_zone`` -- or ``silent``,
    #: where no rule was found (the yaml's header).
    rule: str
    ft: float | None = None
    inclusive: bool = True
    cite: str = ""
    section: str = ""
    quote: str = ""

    def says(self) -> str:
        """The cite a flag carries: the rule's section and where it stands,
        or the plain statement that the search found none."""
        if self.rule == "silent":
            return "no rule for a lot in two districts was found in this city's code"
        return f"{self.section}: {self.cite}"


SILENT = Ruling("silent")


@lru_cache(maxsize=None)
def rulings(path: Path = RULES_PATH) -> Mapping[str, Ruling]:
    """Layer id -> :class:`Ruling`, silent layers included."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[str, Ruling] = {}
    for layer, r in (raw.get("rulings") or {}).items():
        rule = str(r["rule"])
        if rule not in ("majority_within", "majority", "each_zone"):
            raise ValueError(f"{path}: {layer}: unknown rule {rule!r}")
        if rule == "majority_within" and not r.get("ft"):
            raise ValueError(f"{path}: {layer}: majority_within states a distance")
        out[layer] = Ruling(
            rule=rule,
            ft=None if r.get("ft") is None else float(r["ft"]),
            inclusive=bool(r.get("inclusive", True)),
            cite=str(r["cite"]),
            section=str(r.get("section", "")),
            quote=str(r.get("quote", "")),
        )
    for layer in raw.get("silent") or {}:
        if layer in out:
            raise ValueError(f"{path}: {layer} is both ruled and silent")
        out[layer] = SILENT
    return out


def ruling_for(layer_id: str | None, path: Path = RULES_PATH) -> Ruling:
    """The layer's ruling; a layer the file does not list is silent too --
    nothing was found, which is what silent says."""
    return SILENT if layer_id is None else rulings(path).get(layer_id, SILENT)


def governed(split: Split, ruling: Ruling) -> bool:
    """Whether the city's rule puts the whole lot in the district it was
    screened under, so that nothing lies across a line.

    ``majority`` always does (the screen's district IS the one with the
    greater area -- checked here, since an alias can make it otherwise).
    ``majority_within`` does where every other district's ground lies within
    the stated distance of the lot's own; further, the districts stand as
    mapped. ``each_zone`` and silence never do. A lot whose own district the
    maps cannot find (``unresolved``) is never governed: the worst case.
    """
    if split.unresolved or ruling.rule in ("each_zone", "silent"):
        return False
    if any(p.sqft > split.own_sqft for p in split.pieces):
        return False
    if ruling.rule == "majority":
        return True
    assert ruling.ft is not None
    if ruling.inclusive:
        return all(p.reach_ft <= ruling.ft for p in split.pieces)
    return all(p.reach_ft < ruling.ft for p in split.pieces)
