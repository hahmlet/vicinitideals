"""Is tier D really landlocked, or is the street layer just missing?

s4 gives a lot tier D when no edge midpoint falls within 50 ft of a street
centerline, and a tier-D lot is dropped for good: no envelope, no fit test, red
forever. That is 7,499 lots, and the header of s4_edges.py justified it with an
assertion nobody had measured -- "RLIS taxlots exclude right-of-way, so lot
lines genuinely abut ROW gaps and centerline distance is a reliable frontage
proxy."

The first thing that looks wrong with it: **98.4% of tier-D lots have a street
address and 4,491 of them have a house on them.** A landlocked lot with a house
and an address is a strange object. Distance alone does not settle it either --
the median tier-D lot is 93 ft from the nearest centerline, which is too far for
a wide arterial to explain and about right for a lot sitting one row back.

So this asks the question that actually decides it: **between the lot and the
street, is there another taxlot?** RLIS taxlots exclude right-of-way, so a lot
that fronts even a 120 ft arterial has nothing but ROW in the gap, while a lot
reached by an easement over a neighbour's land has the neighbour in it.

    behind another taxlot (genuinely landlocked): 6,947   92.6%
    gap to the street is not private land       :   552    7.4%
        ... of which within 60 ft: 252   within 80 ft: 378

**The rule is sound.** Nine in ten tier-D lots are reached over somebody else's
land, and every code in the corpus requires a lot to abut a public street --
Tualatin TDC 36.410(5) states it outright. A pod's driveway cannot be assumed
across a neighbour's parcel, so red is the right answer and the addresses are
explained: these are houses on old easements.

The residue is ~250-550 lots whose gap is open ROW, which is what a lot fronting
a very wide right-of-way looks like. Raising `street_threshold_ft` would pick
them up and would also start calling a street 93 ft away, across a neighbour's
front garden, this lot's frontage -- 6,947 false frontages to recover 552. The
fix, if it is ever worth it, is this test rather than a bigger number: front the
lot when the gap contains no other taxlot, whatever its width.

Reads s4_lots and s1_streets, so it runs after s4 and needs the gis extra:

    uv run --extra tools --extra gis python "Lot Analysis/quadfit/audit_landlocked.py"
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import load_rules, read_stage

#: An intersection shorter than this is a shared boundary or a corner clip, not
#: a parcel standing in the way.
CROSSING_MIN_FT = 5.0


def _nearest_edge_to_street(geom, street_geoms, tree, tol):
    """The edge midpoint closest to a centerline, and that centerline."""
    from shapely.geometry import Point

    ring = list(geom.simplify(tol, preserve_topology=True).exterior.coords)
    best = (math.inf, None, None)
    for (x1, y1), (x2, y2) in zip(ring[:-1], ring[1:]):
        if math.hypot(x2 - x1, y2 - y1) < 1.0:
            continue
        mid = Point((x1 + x2) / 2, (y1 + y2) / 2)
        line = street_geoms[tree.nearest(mid)]
        dist = mid.distance(line)
        if dist < best[0]:
            best = (dist, mid, line)
    return best


def _is_blocked(seg, geom, all_geoms, lot_tree) -> bool:
    """Does another taxlot stand between this lot and the street?"""
    for idx in lot_tree.query(seg):
        other = all_geoms[idx]
        if other is geom or other.equals(geom):
            continue
        if other.intersects(seg) and other.intersection(seg).length > CROSSING_MIN_FT:
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Why tier-D lots have no street.")
    ap.parse_args()

    import numpy as np
    from shapely.ops import nearest_points
    from shapely.geometry import LineString
    from shapely.strtree import STRtree

    rules = load_rules()
    tol = rules.defaults.simplify_tolerance_ft
    thr = rules.defaults.street_threshold_ft

    lots = read_stage("s4_lots")
    streets = read_stage("s1_streets")
    street_geoms = np.array(list(streets["geom"]), dtype=object)
    street_tree = STRtree(street_geoms)
    all_geoms = np.array(list(lots["geom"]), dtype=object)
    lot_tree = STRtree(all_geoms)

    tier_d = lots[lots["tier"] == "D"]
    print(f"{len(tier_d):,} tier-D lots, rejected by the {thr:.0f} ft frontage test")

    blocked = 0
    open_gaps: list[float] = []
    for geom in tier_d["geom"]:
        dist, mid, line = _nearest_edge_to_street(geom, street_geoms, street_tree, tol)
        if mid is None:
            continue
        seg = LineString(nearest_points(mid, line))
        if _is_blocked(seg, geom, all_geoms, lot_tree):
            blocked += 1
        else:
            open_gaps.append(dist)

    total = blocked + len(open_gaps)
    gaps = np.array(open_gaps) if open_gaps else np.array([0.0])
    print(f"  behind another taxlot (genuinely landlocked): {blocked:6,}  "
          f"{100 * blocked / max(total, 1):5.1f}%")
    print(f"  gap to the street is not private land       : {len(open_gaps):6,}  "
          f"{100 * len(open_gaps) / max(total, 1):5.1f}%")
    print("\n  the open-gap lots, by distance to the centerline:")
    for cut in (60, 80, 100, 150):
        print(f"    within {cut:3d} ft: {int((gaps <= cut).sum()):5,}")
    print(f"    median: {np.median(gaps):.1f} ft")


if __name__ == "__main__":
    main()
