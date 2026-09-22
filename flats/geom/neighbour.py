"""What zone lies across each lot line, read into the three neighbour-zoning facts.

The registry has carried ``abuts_residential_zone``,
``abuts_lower_density_zone`` and ``abuts_nonresidential_zone`` since the
commercial chapters were encoded, and until 2026-09-21 nothing filled them:
every value that turned on one -- Portland's ten feet against an R zone
that is nothing against a C zone, Oregon City's twenty against a
residential zone that is nothing otherwise, Troutdale's and Fairview's
twins -- resolved on an unknown, and every lot in those zones screened
UNKNOWN with the fact named. quadfit's s4 now reads the fabric across every
lot line that is not a street lot line (`Lot Analysis/quadfit/s4_edges.py`
``neighbour_zones``: five points along the edge, two feet out, the
jurisdiction and zone s2 gave whatever private lot they stand in; across
the alley for an alley line) and records, per line, every zone seen, the
points that stood on a split-zone neighbour, and the points that found no
zoned private land at all. This module turns that record into the three
facts, against the layer's own statement of which of its codes are which
(``Layer.neighbours``, read from the code section that draws the line).

**The reading is per line and the fact is per lot, and the two meet on the
conservative side.** Each condition has a direction: the answer that
relaxes a standard and the answer that tightens it.

* ``abuts_residential_zone`` and ``abuts_lower_density_zone`` are true of a
  lot when ANY line has such a zone across it -- the code buys the
  neighbour a buffer wherever the neighbour is -- so a single point on a
  residential lot settles True, and False needs every line fully resolved
  with nothing residential across it. True is the tightening answer
  (twenty feet where zero was offered), so the cheap answer is the safe
  one and the expensive answer is the permissive one.
* ``abuts_nonresidential_zone`` is Portland's "every lot line that is not a
  street lot line abuts an OS, RX, C, E or CI zone": True needs every line
  fully resolved and nothing but such zones across any of them, and a
  single residential point settles False. Here True is the relaxing answer
  (no setback at all), and again the permissive answer is the one that
  needs every line answered.

A line the fabric could not read -- a park, water, rail, a split-zone
neighbour, a neighbour in another city, a code the layer's lists do not
place -- is never counted for the permissive side, and the fact is left
unstated (not False: ``configure`` treats silence as a question nobody
asked) where that leaves it open. The lot then screens UNKNOWN on the fact
exactly as it did before the measurement, which is the correct answer for
a line nobody could read.

A neighbour across a city line is unresolved on purpose. Portland's
section lists Portland's codes; Gresham's LDR-7 is residential in Gresham's
code and nothing in Portland's, and the corpus has refused to let one
jurisdiction's definitions speak for another since the corner-lot work
(:mod:`flats.rules.definitions`). The lots affected are the ones along
city lines, and their loss is the honest one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from flats.rules.conditions import NEIGHBOUR_ZONE_CONDITIONS
from flats.rules.model import NeighbourRule

#: The three facts, in the order they are reported.
NEIGHBOUR_FACTS: tuple[str, ...] = NEIGHBOUR_ZONE_CONDITIONS

#: Conditions true of a lot only when EVERY non-street line has the zone
#: across it; the rest are true when ANY line does.
EVERY_LINE: frozenset[str] = frozenset({"abuts_nonresidential_zone"})


@dataclass(frozen=True, slots=True)
class Line:
    """One lot line that is not a street lot line, as s4 read it."""

    #: Every (jurisdiction, zone code) seen across the line, the code as the
    #: rules spell it -- the caller normalises the map's spelling.
    zones: tuple[tuple[str, str], ...]
    #: Sample points that stood on nothing the reading can use: a split-zone
    #: neighbour, public land, a gap, an unzoned lot.
    unresolved: int


def lines_from_quadfit(
    across: Iterable[Mapping[str, object] | None],
    normalise: Callable[[str, str], str | None],
) -> tuple[Line, ...]:
    """s4's ``neighbour_zones_json`` decoded, into the lines that are asked.

    ``across`` is the per-edge list (``None`` for a street edge, else
    ``{"z": [[jurisdiction, zone_raw], ...], "split": n, "none": m}``).
    ``normalise(jurisdiction, zone_raw)`` spells the neighbour's code the way
    its own layer's rules do (Portland's lowercase suffix off), or returns
    None for a code that cannot be spelled, which counts as unresolved.
    """
    out: list[Line] = []
    for edge in across:
        if edge is None:
            continue
        zones: list[tuple[str, str]] = []
        unresolved = int(edge.get("split", 0) or 0) + int(edge.get("none", 0) or 0)
        for pair in edge.get("z") or ():
            juris, raw = str(pair[0]), pair[1]
            code = normalise(juris, str(raw)) if raw is not None else None
            if code is None:
                unresolved += 1
            else:
                zones.append((juris, code))
        out.append(Line(zones=tuple(dict.fromkeys(zones)), unresolved=unresolved))
    return tuple(out)


def observed_neighbours(
    lines: Sequence[Line],
    rules: Mapping[str, NeighbourRule],
    jurisdiction: str,
) -> dict[str, bool]:
    """The neighbour-zoning facts for one lot, as ``configure`` takes them.

    ``rules`` is the lot's layer's ``neighbours`` block; a condition the
    layer has not declared is never answered. ``jurisdiction`` is the
    lot's, in quadfit's spelling, the same the fabric names neighbours by:
    only a neighbour in it is looked up in the lists. A key is present only
    where the lines settle the fact; a lot with no non-street line (an
    island, a lot s4 could not trace) answers nothing.
    """
    out: dict[str, bool] = {}
    if not lines:
        return out
    for name, rule in rules.items():
        if name not in NEIGHBOUR_FACTS:
            continue
        yes = set(rule.true_for)
        no = set(rule.false_for)
        any_yes = any_no = False
        all_settled = True
        for line in lines:
            if line.unresolved or not line.zones:
                all_settled = False
            for juris, code in line.zones:
                if juris != jurisdiction:
                    all_settled = False
                elif code in yes:
                    any_yes = True
                elif code in no:
                    any_no = True
                else:
                    all_settled = False
        if name in EVERY_LINE:
            if any_no:
                out[name] = False
            elif all_settled and any_yes:
                out[name] = True
        else:
            if any_yes:
                out[name] = True
            elif all_settled and any_no:
                out[name] = False
    return out


__all__ = [
    "EVERY_LINE",
    "Line",
    "NEIGHBOUR_FACTS",
    "lines_from_quadfit",
    "observed_neighbours",
]
