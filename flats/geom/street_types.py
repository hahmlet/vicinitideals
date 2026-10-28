"""Whether a Gresham Downtown lot's townhouses are barred by its street types.

GDC 4.1140 sorts every Downtown street into a type on **Map 4.1140**, and
three of the types take the townhouse back:

* Table 4.1130 prints "Not allowed on this street type" for a townhouse on
  **Main Avenue** (Powell to NE 4th), and 4.1142(D)(3) allows no parking
  access from it;
* 4.1142(A)(6) prohibits townhouse access from an **Urban Boulevard**, and
  (C)(9) from **Beech** (NE 3rd to NE 7th): "Access from rear alleys or side
  streets is allowed";
* 4.1142(E)(4) allows no parking access from **Stanley**.

Downtown Local and Cleveland bar nothing, and 4.1140 makes "any
unclassified or future street" inside the map's frame Downtown Local.

The city publishes the map only as a picture (PDF page 23, [4.1100]-23), so
the layer traces it: ``flats/config/areas/or/multnomah/gresham/
downtown-street-types.geojson`` holds every RLIS centreline near the
Downtown zones, each typed as the map draws it (the file's ``source`` says
how). A lot line takes the type of the centreline it abuts, read the way
:mod:`flats.geom.corridor` reads which street a line abuts: at
:data:`~flats.geom.corridor.SAMPLES` points, the nearest parallel centreline
within :data:`~flats.geom.corridor.FRONT_REACH_FT`; a line is of a type when
at least :data:`~flats.geom.corridor.MIN_SHARE` of its points agree on it,
and unplaced otherwise.

**The answer, per lot of DMU, DEM and DCL** (``gresham_downtown_barred_street``):

* any street line on Main -- True when every street line is on Main (the
  townhouse is not allowed on that street type and cannot enter from it),
  else unanswered: whether a townhouse on a Main corner "is on" Main is not
  something the map settles;
* else False where an alley edge or a street line of a type that bars
  nothing gives the townhouses a way in -- the side street or rear alley
  4.1142 itself points to;
* else True when every street line is of a barring type;
* else unanswered: a street line no traced centreline explains (Stanley,
  which RLIS does not carry; the stretches of Beech it does not).

False is the expensive answer, since it lets the townhouse variant stand,
so it needs a whole line read surely as a street that bars nothing.
Unanswered leaves the lot out of GREEN on the fact, as before the trace.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from flats.geom.alley import ALLEY_CLASS
from flats.geom.corridor import MIN_SHARE, SAMPLES, STREET_CLASS, Lines, _fronted
from flats.geom.edges import bearing_deg
from flats.rules.loader import AREAS_ROOT

#: The fact this map answers.
CONDITION = "gresham_downtown_barred_street"
#: The layer it serves and the zones whose townhouse permission reads it.
SERVES = "or/multnomah/gresham"
ZONES = frozenset({"DMU", "DEM", "DCL"})
#: The traced map, under ``flats/config/areas``.
TRACED = "or/multnomah/gresham/downtown-street-types.geojson"

#: The street type a townhouse is not allowed on (Table 4.1130).
USE_BARRED = frozenset({"main"})
#: Street types the townhouses may not take access from (4.1142).
ACCESS_BARRED = frozenset({"urban_boulevard", "beech", "main", "stanley"})
#: Street types that bar nothing.
OPEN = frozenset({"downtown_local", "cleveland"})
#: Every type the tracing may carry.
TYPES = ACCESS_BARRED | OPEN


@dataclass(frozen=True)
class StreetTypes:
    """The traced centrelines and the street type of each."""

    streets: Lines
    types: tuple[str, ...]

    @classmethod
    def build(cls, lines: Iterable[Any], names: Iterable[str], types: Iterable[str]) -> StreetTypes:
        geoms, labels, kinds = list(lines), list(names), list(types)
        unknown = sorted(set(kinds) - TYPES)
        if unknown:
            raise ValueError(f"unknown Downtown street type(s): {unknown}")
        if not (len(geoms) == len(labels) == len(kinds)):
            raise ValueError("every traced line needs a name and a street type")
        streets = Lines.build(geoms, labels)
        # Lines.build drops empty geometries; keep the types in step with it.
        kept = [k for g, k in zip(geoms, kinds) if g is not None and not g.is_empty]
        return cls(streets, tuple(kept))

    def edge_type(self, edge: Sequence[object]) -> str | None:
        """The street type of one street line ``(x1, y1, x2, y2, ...)``: the
        type of the centreline it abuts at :data:`MIN_SHARE` or more of its
        sample points, else None."""
        from shapely.geometry import Point

        x1, y1, x2, y2 = (float(v) for v in edge[:4])  # type: ignore[arg-type]
        if x1 == x2 and y1 == y2:
            return None
        own = bearing_deg(x1, y1, x2, y2)
        seen: Counter[str] = Counter()
        for k in range(1, SAMPLES + 1):
            p = Point(x1 + (x2 - x1) * k / (SAMPLES + 1), y1 + (y2 - y1) * k / (SAMPLES + 1))
            s = _fronted(p, own, self.streets)
            if s is not None:
                seen[self.types[s]] += 1
        if not seen:
            return None
        kind, hits = seen.most_common(1)[0]
        return kind if hits / SAMPLES >= MIN_SHARE else None

    def barred(self, edges: Sequence[Sequence[object]]) -> bool | None:
        """``gresham_downtown_barred_street`` for one lot's s4 edges (see the
        module docstring); None where it cannot say."""
        street = [e for e in edges if len(e) >= 5 and e[4] == STREET_CLASS]
        if not street:
            return None
        kinds = [self.edge_type(e) for e in street]
        if any(k in USE_BARRED for k in kinds):
            return True if all(k in USE_BARRED for k in kinds) else None
        if any(len(e) >= 5 and e[4] == ALLEY_CLASS for e in edges):
            return False
        if any(k in OPEN for k in kinds):
            return False
        if all(k in ACCESS_BARRED for k in kinds):
            return True
        return None


@lru_cache(maxsize=None)
def load_street_types(file: str = TRACED) -> StreetTypes:
    """The traced map in ``file`` (under ``flats/config/areas``)."""
    from shapely.geometry import shape

    data = json.loads((AREAS_ROOT / file).read_text(encoding="utf-8"))
    feats = [f for f in data["features"] if f.get("geometry")]
    return StreetTypes.build(
        (shape(f["geometry"]) for f in feats),
        (str(f["properties"].get("name") or "") for f in feats),
        (str(f["properties"]["street_type"]) for f in feats),
    )


def observed_street_types(
    edges: Sequence[Sequence[object]], layer_id: str | None, zone: object
) -> dict[str, bool]:
    """``{CONDITION: answer}`` for a lot of :data:`ZONES` on Gresham's layer
    with edges, where the traced map answers it; ``{}`` otherwise."""
    if layer_id != SERVES or zone is None or str(zone) not in ZONES or not edges:
        return {}
    got = load_street_types().barred(edges)
    return {} if got is None else {CONDITION: got}
