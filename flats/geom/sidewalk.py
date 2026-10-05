"""How far a sidewalk easement may reach into the lot, where nothing can
measure whether one does.

Gresham's Table 4.0131 note 1: "In cases where sidewalk access is provided by
easement, the setback shall be measured from the easement line closest to the
house or garage per Table 4.0131." The note sits over the whole setback block,
so every Gresham setback carried the fact ``sidewalk_easement`` as a question
nobody answered, and no lot under it could be GREEN.

**Nothing measures it.** Gresham publishes no sidewalk, right-of-way or
easement layer. Metro's sidewalk file (RLIS 2851) is the street centrelines
tagged with whether a side has a walk, not where the walk runs, and the lot
lines are drawn to +/- 10 ft -- twice the five feet that tell a walk inside the
right-of-way from one on an easement. Only a plat or a title report says.

**So the screen assumes the worst** (Steph, 2026-10-05: "Measure exact,
fallback to pessimistic"): every lot is read as though its sidewalk ran on an
easement as deep as the city's standards could put one, and its street
setbacks start that much further in. Gresham's Public Works Standards (July
2026) place the walk "6 inches inside the right-of-way" and let it "meander
... outside of the right-of-way within an easement with the approval of the
Engineer" (6.05.01), and state no width for that easement. The depth taken is
the walk plus the strip behind it, wholly on the lot:

* :attr:`EasementDepth.local_ft` -- 7 ft on a line every sample of which
  abuts a street Metro types local (:data:`~flats.geom.street_class.RLIS_LOCAL`):
  a local street's 5 ft walk (Standard Detail 605) and its 6 in, rounded up,
  with room for a collector's 6 ft walk (Detail 606) where Metro calls a
  collector local, as it does about one time in seven;
* :attr:`EasementDepth.other_ft` -- 20 ft on every other street line, and on
  one no street runs beside: the only width the standards state for a
  walking route on an easement (6.06.02, a multi-use path's "right-of-way or
  easement width ... 20 feet"), wider than a Boulevard's 9 ft walk or a
  Multi-Use Path overlay's 14 ft one.

The lot takes the deepest of its street lines, on every street setback
(:data:`SHIFTED`): a corner of a local street and an arterial is set back 20
ft further on both. A rear or interior side line has no sidewalk; a through
lot's second street front is held open by its own note.

With the depth applied the fact is answered (True: the worst case), and the
cap lifts -- the setbacks the note moves now carry the move.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from flats.geom.corridor import STREET_CLASS, STREETS_KEY, SAMPLES, Lines, _dataset_path, _fronted
from flats.geom.edges import bearing_deg
from flats.geom.street_class import RLIS_LOCAL, _type_of

if TYPE_CHECKING:
    from flats.rules.resolver import ZoneResolution

#: The fact this module answers.
SIDEWALK_EASEMENT = "sidewalk_easement"

#: The setbacks a sidewalk easement along the street moves: each is measured
#: from a street lot line.
SHIFTED: tuple[str, ...] = (
    "setback_front_ft",
    "setback_street_side_ft",
    "setback_garage_entrance_ft",
)


@dataclass(frozen=True)
class EasementDepth:
    """The deepest sidewalk easement one code's standards allow, by street."""

    local_ft: float
    other_ft: float


#: Layer -> the worst-case depth. Only where a code measures a setback from a
#: sidewalk easement and no layer says where one runs.
DEPTHS: dict[str, EasementDepth] = {
    # GDC Table 4.0131 note 1; PWS 2026 6.05.01, 6.06.02, Details 605-607, 614.
    "or/multnomah/gresham": EasementDepth(local_ft=7.0, other_ft=20.0),
}


def depth_for(layer_id: str | None) -> EasementDepth | None:
    """The worst-case depth for ``layer_id``'s code, or None where none is held."""
    if not layer_id:
        return None
    for layer, depth in DEPTHS.items():
        if layer_id == layer or layer_id.startswith(f"{layer}/"):
            return depth
    return None


@dataclass(frozen=True)
class Streets:
    """Metro's street centrelines near the lots asked, with their TYPE."""

    lines: Lines
    types: tuple[int | None, ...]


def build(lines: Sequence[Any], names: Sequence[object], types: Sequence[int | None]) -> Streets:
    keep = [i for i, g in enumerate(lines) if g is not None and not g.is_empty]
    return Streets(Lines.build([lines[i] for i in keep], [names[i] for i in keep]), tuple(types[i] for i in keep))


def load_streets(sources: Path, bounds: tuple[float, float, float, float]) -> Streets | None:
    """The snapshot's RLIS streets inside ``bounds`` (minx, miny, maxx, maxy,
    in the lots' feet), or None where the snapshot holds none."""
    from shapely.geometry import box, shape

    from flats.ingest.delta import iter_features

    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    path = _dataset_path(sources, manifest, STREETS_KEY)
    if not path.is_file():
        return None
    area = box(*bounds)
    lines, types = [], []
    for f in iter_features(path):
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if g.intersects(area):
            lines.append(g)
            types.append(_type_of(f.get("properties") or {}))
    return build(lines, [""] * len(lines), types)


def _local_line(edge: Sequence[Any], streets: Streets) -> bool:
    """Whether every sample of a street lot line abuts a street Metro types local."""
    from shapely.geometry import Point

    x1, y1, x2, y2 = (float(v) for v in edge[:4])
    if x1 == x2 and y1 == y2:
        return False
    own = bearing_deg(x1, y1, x2, y2)
    k = SAMPLES + 1
    for i in range(1, k):
        s = _fronted(Point(x1 + (x2 - x1) * i / k, y1 + (y2 - y1) * i / k), own, streets.lines)
        if s is None or streets.types[s] not in RLIS_LOCAL:
            return False
    return True


def easement_depth_ft(
    edges: Iterable[Sequence[object]], depth: EasementDepth, streets: Streets | None
) -> float | None:
    """The deepest worst-case easement over the lot's street lines (s4
    edges, ``[x1, y1, x2, y2, cls]``); None on a lot with no street line."""
    got: list[float] = []
    for e in edges:
        if len(e) < 5 or e[4] != STREET_CLASS:
            continue
        local = streets is not None and _local_line(e, streets)
        got.append(depth.local_ft if local else depth.other_ft)
    return max(got) if got else None


def observed_sidewalk_easement(depth_ft: float | None) -> dict[str, bool]:
    """The fact, answered at its worst wherever a depth was taken."""
    return {SIDEWALK_EASEMENT: True} if depth_ft is not None else {}


def easement_shifted(rules: "ZoneResolution", depth_ft: float | None) -> "ZoneResolution":
    """``rules`` with every street setback (:data:`SHIFTED`) measured from
    the easement line ``depth_ft`` inside the lot line: the number grows by
    the depth, the code's own kept as ``shadowed``.

    The note then has its number, so no value carries the fact as
    unencoded any more (:func:`flats.score.screen.held_open` would hold a
    lot with the fact True open on one that did): the street setbacks
    carry the move, and a rear or interior side line has no sidewalk to
    measure from. A street setback the code states as no plain number
    keeps the mark, and holds the lot open as before."""
    if not depth_ft:
        return rules
    values = dict(rules.values)
    for name, held in rules.values.items():
        if SIDEWALK_EASEMENT not in held.unencoded:
            continue
        if name in SHIFTED:
            if isinstance(held.value, bool) or not isinstance(held.value, (int, float)):
                continue
            held = dataclasses.replace(held, value=held.value + depth_ft, shadowed=held.value)
        values[name] = dataclasses.replace(held, unencoded=held.unencoded - {SIDEWALK_EASEMENT})
    return dataclasses.replace(rules, values=values)


__all__ = [
    "DEPTHS",
    "SHIFTED",
    "SIDEWALK_EASEMENT",
    "EasementDepth",
    "Streets",
    "build",
    "depth_for",
    "easement_depth_ft",
    "easement_shifted",
    "load_streets",
    "observed_sidewalk_easement",
]
