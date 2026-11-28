"""Buffers owed along the lot lines that are not streets by the NEIGHBOUR'S
use, measured against the drawn plan (FOLLOWUPS 222; fg5 round 5, F1).

Gresham 9.0110(A) requires the buffers of the matrix in Table 9.0111(A); its
row for "Single Detached Dwellings and Middle Housing" -- the quadplex and
the townhouse -- owes standard A, a 10 ft buffer, beside every other use
(``9/9.0100.buffering.txt#L224-L228,L254-L257``), and nothing but plants,
fences, walkways and the like may stand in it (#L26-L37). The fit knows
nothing of it: the side setbacks are 5 ft and the lane and court may stand
anywhere inside the envelope. On the fg5 read a Gresham CMF lot's drawn lane
and court stood 4-5 ft off a multi-family line.

The matrix keys on use; the only per-line record is the ZONE quadfit's s4
reads across each line (:class:`flats.geom.neighbour.Line`). A place's
``not_owed_beside`` list names the neighbour zones read as owing nothing;
every other zone, and every line not read wholly into the lot's own city's
codes, owes the buffer. :func:`checked` holds a GREEN out of GREEN (YELLOW,
MEASURE-LOT-LINE-BUFFER) where a drawn building, lane or court stands inside
the width of such a line. It never moves a lot toward GREEN and never makes
one RED: another placement may hold the plan clear, which this does not
search. The figures live in ``flats/config/lot_line_buffers.yaml``.
"""

from __future__ import annotations

import dataclasses
import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

from flats.geom.edges import Edge, EdgeClass

CONFIG = Path(__file__).resolve().parents[1] / "config" / "lot_line_buffers.yaml"

#: The flag a held plan carries.
FLAG = "MEASURE-LOT-LINE-BUFFER"
#: The drawn parts a place may keep out of its buffer.
PARTS = frozenset({"building", "lane", "court"})
#: How far inside the buffer a drawn part may stand before it is in it, feet:
#: the drawing rounds its rings to 0.1 ft.
TOL_FT = 0.1


@dataclass(frozen=True, slots=True)
class Place:
    """One place's buffer, as printed."""

    width_ft: float
    keeps_out: tuple[str, ...]
    not_owed_beside: frozenset[str]
    quote: str
    #: The lot's zones the check runs in; empty means every zone.
    zones: frozenset[str] = frozenset()


def _place(layer: str, body: Any) -> Place:
    if not isinstance(body, dict):
        raise ValueError(f"{layer}: a mapping")
    width = body.get("width_ft")
    if isinstance(width, bool) or not isinstance(width, (int, float)) or width <= 0:
        raise ValueError(f"{layer}.width_ft: a positive length")
    keeps = tuple(str(p) for p in body.get("keeps_out") or ())
    if not keeps or not set(keeps) <= PARTS:
        raise ValueError(f"{layer}.keeps_out: some of {sorted(PARTS)}")
    quote = str(body.get("quote") or "")
    if "#L" not in quote:
        raise ValueError(f"{layer}.quote: a path#Lnn into the stored code text")
    return Place(
        width_ft=float(width),
        keeps_out=keeps,
        not_owed_beside=frozenset(str(z) for z in body.get("not_owed_beside") or ()),
        quote=quote,
        zones=frozenset(str(z) for z in body.get("zones") or ()),
    )


@functools.lru_cache(maxsize=1)
def places(path: Path = CONFIG) -> dict[str, Place]:
    """Every place's buffer, keyed by corpus layer id."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): _place(str(k), v) for k, v in (raw.get("places") or {}).items()}


def owed(place: Place, line: Any | None, jurisdiction: str) -> str | None:
    """Why ``line`` owes the buffer, or None where it is read as owing none.

    ``line`` is s4's reading across it (:class:`flats.geom.neighbour.Line`),
    None where nothing read it. Only a line read wholly -- every sample on a
    zoned lot in the lot's own city, every code on ``not_owed_beside`` --
    owes nothing."""
    if line is None:
        return "neighbour unread"
    if line.unresolved or not line.zones:
        return "neighbour unread"
    for juris, code in line.zones:
        if juris != jurisdiction:
            return f"neighbour in {juris}"
        if code not in place.not_owed_beside:
            return f"beside {code}"
    return None


def measured_lines(
    edges: Sequence[Edge], neighbour_lines: Sequence[Any | None]
) -> list[tuple[Edge, Any | None]]:
    """The lines a buffer may be owed on, each with what was read across it.

    Where s4 recorded a reading per edge, a street edge is the one it left
    None (9.0110(F): no buffer across a street for this use); an alley line
    keeps the zone across the alley. Where it recorded none, the rear and
    side lines no street is ranked on, each unread."""
    if neighbour_lines and len(neighbour_lines) == len(edges):
        return [(e, n) for e, n in zip(edges, neighbour_lines, strict=True) if n is not None]
    return [
        (e, None)
        for e in edges
        if e.cls in (EdgeClass.rear, EdgeClass.side) and e.street_rank is None
    ]


def breaches(
    place: Place,
    lines: Sequence[tuple[Edge, Any | None]],
    drawing: dict[str, Any] | None,
    jurisdiction: str,
) -> list[str]:
    """What stands inside the buffer, in words; empty where nothing does."""
    owing = [(e, why) for e, n in lines if (why := owed(place, n, jurisdiction)) is not None]
    if not owing:
        return []
    if not drawing or not drawing.get("fits"):
        return ["no fitting plan drawn"]
    from shapely.geometry import LineString, Polygon

    shapes = []
    for name in place.keeps_out:
        ring = drawing.get(name)
        if not ring or len(ring) < 4:
            continue
        shape = Polygon(ring)
        shapes.append((name, shape if shape.is_valid else shape.buffer(0)))
    out: list[str] = []
    for edge, why in owing:
        seg = LineString(((edge.x1, edge.y1), (edge.x2, edge.y2)))
        for name, shape in shapes:
            gap = shape.distance(seg)
            if gap + TOL_FT < place.width_ft:
                out.append(f"{name} {gap:.1f} ft off a {edge.cls.value} line ({why})")
    return out


def checked(s: Any, lot: Any) -> Any:
    """``s`` held out of GREEN where its drawn plan stands in a buffer the
    neighbour's use is owed, or may be (see the module). Only a GREEN (on
    either reading) is asked; a lot in a place with no buffer is untouched.
    No traced edges on a GREEN that owes: held (nothing showed it clear)."""
    from flats.score import flags as flag_plan
    from flats.score.screen import CLOSER_LOOK_LOT_LINE_BUFFER, Triage

    place = places().get(lot.layer_id or "")
    if place is None or (place.zones and lot.zone not in place.zones):
        return s
    if Triage.green not in (s.screening.triage, s.signed.triage):
        return s
    if lot.edges is None:
        found = ["no lot lines traced"]
    else:
        lines = measured_lines(lot.edges.edges, lot.neighbour_lines)
        found = breaches(place, lines, s.drawing, lot.jurisdiction)
    if not found:
        return s
    flag = flag_plan.Flag(
        FLAG,
        flag_plan.LOT,
        CLOSER_LOOK_LOT_LINE_BUFFER,
        source=(
            f"{place.width_ft:g} ft buffer owed by the neighbour's use ({place.quote}): "
            + "; ".join(found)
        ),
    )

    def ask(x: Any) -> Any:
        reasons = (
            x.reasons
            if CLOSER_LOOK_LOT_LINE_BUFFER in x.reasons
            else (*x.reasons, CLOSER_LOOK_LOT_LINE_BUFFER)
        )
        triage = Triage.yellow if x.triage is Triage.green else x.triage
        flags = x.flags if any(f.code == FLAG for f in x.flags) else (*x.flags, flag)
        return dataclasses.replace(x, triage=triage, reasons=reasons, flags=flags)

    return dataclasses.replace(s, screening=ask(s.screening), signed=ask(s.signed))


__all__ = ["CONFIG", "FLAG", "Place", "breaches", "checked", "measured_lines", "owed", "places"]
