"""Whether a lot is plainly NOT a flag lot (FOLLOWUPS 205).

Portland writes its own standards for flag lots -- PCC 33.110.255 (the same
setback along every lot line, 15 ft in RF, R20 and R10 and 10 ft in R7, R5
and R2.5; a landscaped buffer round the flag; coverage on the flag alone; a
20 ft height on a small one) and 33.120.284 (10 ft along every line in RM1
to RM4, and a buffer). They turn on a fact about the lot's shape that nothing
measured: no zone held them, and a flag lot came out GREEN on five-foot side
and rear yards it does not have. The fact is ``pdx_flag_lot``, Portland's own
definition (33.910.030) and assumed unknown -- not the registry's older
``flag_lot``, which is assumed False wherever nobody looked.

This module answers the fact one way only. ``False`` where the lot's outline
is plainly an ordinary lot's, by the two tests ``flats/config/flag_lot.yaml``
states (a part at least the zone's minimum lot width across reaches the
street; or the outline is all but convex, with no ground in front of it for
another lot). Every other lot of a zone the file lists is left UNANSWERED,
and the screen then holds it out of GREEN on the fact by name: the zone's
side yard is ``qualified_by`` it, so no worst reading is tried
(:func:`flats.ingest.quadfit._bounded` skips an unencoded fact). ``True`` is
never answered. A lot of a city or zone the file does not list is not read.

The outline is the lot's own ring of edges (s4's ``edges_json``), the ring
the street classes are written on; a ring that does not close is unanswered.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

#: The registry's fact (:mod:`flats.rules.conditions`).
FACT = "pdx_flag_lot"

#: s4's class for a lot line on a street.
STREET_CLASS = "F"

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "flag_lot.yaml"


@dataclass(frozen=True)
class FlagLotRules:
    """One city's reading of a plainly ordinary lot."""

    layer: str
    #: The zone's minimum lot width -- what the code's pole is narrower than.
    widths: dict[str, float]
    #: How near the street the wide part of the lot must come, in feet.
    reach_ft: float
    #: The most ground the outline may leave inside its own convex hull.
    notch_sqft: float
    #: Taken off the width for the digitised line.
    tolerance_ft: float


@lru_cache(maxsize=4)
def load_rules(path: Path = CONFIG_PATH) -> dict[str, FlagLotRules]:
    """Every listed city's rules, by layer id."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, FlagLotRules] = {}
    for layer, body in (raw.get("jurisdictions") or {}).items():
        widths: dict[str, float] = {}
        for block in body.get("min_lot_width_ft") or []:
            for zone, ft in (block.get("zones") or {}).items():
                widths[str(zone)] = float(ft)
        out[layer] = FlagLotRules(
            layer=layer,
            widths=widths,
            reach_ft=float(body["reach_ft"]),
            notch_sqft=float(body["notch_sqft"]),
            tolerance_ft=float(body["tolerance_ft"]),
        )
    return out


def outline(edges: Sequence[Sequence[Any]]) -> Polygon | None:
    """The lot's ring as one polygon, None where the edges do not close."""
    lines = []
    for e in edges:
        x1, y1, x2, y2 = (float(v) for v in e[:4])
        if (x1, y1) != (x2, y2):
            lines.append(LineString([(x1, y1), (x2, y2)]))
    if len(lines) < 3:
        return None
    rings = list(polygonize(unary_union(lines)))
    if len(rings) != 1 or rings[0].is_empty or not rings[0].is_valid:
        return None
    return rings[0]


def street_lines(edges: Sequence[Sequence[Any]]) -> list[LineString]:
    """The lot lines on a street."""
    out = []
    for e in edges:
        if len(e) >= 5 and e[4] == STREET_CLASS:
            x1, y1, x2, y2 = (float(v) for v in e[:4])
            if (x1, y1) != (x2, y2):
                out.append(LineString([(x1, y1), (x2, y2)]))
    return out


def wide_at_street(lot: Polygon, street: Sequence[LineString], width_ft: float, reach_ft: float) -> bool:
    """Whether a part of ``lot`` at least ``width_ft`` across comes within
    ``reach_ft`` of a street line: a disc that wide fits inside the lot with
    its edge that near the street."""
    radius = width_ft / 2.0
    if radius <= 0 or not street:
        return False
    core = lot.buffer(-radius)
    if core.is_empty:
        return False
    return core.distance(unary_union(list(street))) - radius <= reach_ft


def notch_sqft(lot: Polygon) -> float:
    """The ground between the outline and its own convex hull."""
    return max(0.0, lot.convex_hull.area - lot.area)


def plainly_ordinary(edges: Sequence[Sequence[Any]], zone: str | None, rules: FlagLotRules) -> bool:
    """Whether the outline is plainly an ordinary lot's (the module docstring's
    two tests). False is NOT "a flag lot": it is "not shown to be ordinary"."""
    width = rules.widths.get(str(zone))
    lot = outline(edges)
    street = street_lines(edges)
    if width is None or lot is None or not street:
        return False
    if wide_at_street(lot, street, width - rules.tolerance_ft, rules.reach_ft):
        return True
    return notch_sqft(lot) < rules.notch_sqft


def observed_flag_lot(
    edges: Sequence[Sequence[Any]], layer_id: str | None, zone: str | None
) -> dict[str, bool]:
    """``{"pdx_flag_lot": False}`` on a plainly ordinary lot of a listed zone,
    else nothing: the fact is left unanswered, never answered True."""
    rules = load_rules().get(layer_id or "")
    if rules is None or str(zone) not in rules.widths:
        return {}
    return {FACT: False} if plainly_ordinary(edges, zone, rules) else {}
