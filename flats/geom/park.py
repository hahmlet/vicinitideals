"""What open land lies across each lot line, read into ``abuts_park``.

Troutdale's mixed-use table (TDC 3.230.A) states one setback per neighbour:
20 feet against a residential district, none against a non-residential one,
and 10 feet "when abutting a park (regardless of zoning district)" in MU-3.
The neighbour-zoning facts (:mod:`flats.geom.neighbour`) read the zone
across a line; they cannot say whether the land there is a park, and a park
zoned commercial or open space would otherwise hand an MU-3 lot the zero its
zone gives. quadfit's s4 now looks the same five points per non-street line
up in Metro's ORCA layer (``park_across_json``: per edge, every ORCA unit
type a point stood in and how many stood in none), and this module turns
that record into the fact, against the layer's own statement of which unit
types its code calls a park (``Layer.parks``).

**ANY line settles True; False needs every line read.** A park beside one
line is a park the building must stand off, so a single point in a
``true_for`` unit is enough. False -- the relaxing answer, which lets the
zone's own number stand -- needs every non-street line fully read with
nothing across it but land the layer rules out: no ORCA unit at all, or a
``false_for`` one. A line across a unit type in neither list (a natural area
where the code asks who owns the land) leaves the fact unstated rather than
guessed, and the lot screens UNKNOWN on it exactly as before the reading.

**No ORCA unit is read as no park.** ORCA is Metro's inventory of the
region's parks and open space, registered to the taxlots. A city park the
inventory has never recorded would read False here; that reliance is the
reading's one assumption, and it is named rather than hidden.

**A lot with no non-street line abuts no park.** s4 traced it and classed
every edge a street edge -- a whole block -- so there is no lot line for a
park to be across; the same reading :func:`observed_neighbours` gives such a
lot, on the same trust in s4's street classes. It needs no ORCA layer, so it
is answered even from a stage file written before the column existed. An
untraced or irregular lot is not answered at all.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from flats.rules.conditions import PARK_CONDITIONS
from flats.rules.model import ParkRule

#: The park facts, in the order they are reported.
PARK_FACTS: tuple[str, ...] = PARK_CONDITIONS


def observed_parks(
    across: Iterable[Mapping[str, object] | None] | None,
    rules: Mapping[str, ParkRule],
    *,
    all_street: bool = False,
) -> dict[str, bool]:
    """The park facts for one lot, as ``configure`` takes them.

    ``across`` is s4's ``park_across_json`` decoded (``None`` per street
    edge, else ``{"k": [unit types], "none": n}``), or ``None`` where s4 ran
    without the ORCA layer. ``rules`` is the lot's layer's ``parks`` block; a
    condition the layer has not declared is never answered. A key is present
    only where the lines settle the fact.
    """
    out: dict[str, bool] = {}
    for name, rule in rules.items():
        if name not in PARK_FACTS:
            continue
        if all_street:
            out[name] = False
            continue
        if across is None:
            continue
        lines = [e for e in across if e is not None]
        if not lines:
            # Traced lots with no non-street line arrive as all_street; an
            # empty record here is a lot s4 never traced.
            continue
        yes = set(rule.true_for)
        no = set(rule.false_for)
        any_yes = False
        all_settled = True
        for line in lines:
            kinds = {str(k) for k in (line.get("k") or ())}
            if kinds & yes:
                any_yes = True
            elif not kinds <= no:
                all_settled = False
        if any_yes:
            out[name] = True
        elif all_settled:
            out[name] = False
    return out


__all__ = ["PARK_FACTS", "observed_parks"]
