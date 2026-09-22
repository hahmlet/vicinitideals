"""s5 — buildable envelope per lot: lot minus per-edge setback strips.

Tier A/B: envelope = lot − ⋃ edge.buffer(setback_for_class, square caps).
Square caps extend each strip past its endpoints, so corner wedges between
adjacent edges are always covered — the result is conservative (never larger
than the legal envelope; error bounded by the setback delta between adjacent
edges, confined to corner wedges).

Tier C (irregular/flag): uniform inward buffer by the max setback — strictly
conservative fallback. Tier D lots are excluded from fitting (envelope empty).

An alley edge (s4 class ``A``) is a rear lot line and takes the rear setback,
except where the code states a setback of its own from a line abutting an
alley: Portland states zero (33.110.220.D.9, 33.120.220.B.3.g), so on a
Portland R lot the envelope runs to the alley line and the court s6s draws
behind the pod can stand on it. `lot_setbacks` is the one place the four
numbers are decided, and s6s reads the same function so the strip it looks
for along the alley is the strip s5 actually left. The tier C inset is still
the largest of the four, alley included, so an irregular lot gets no relief
from a zero -- strict side, 228 Portland alley lots.

Envelope parts smaller than MIN_PART_SQFT are dropped (nothing fits there).

The stage also writes down what it cut: ``env_setbacks_json`` is the strip
each edge class actually lost, in feet (F, R, S, A), the uniform inset on
every class for a tier C lot, null for tier D. The numbers here are this
table's unconditioned setbacks; a reader that resolves a different rear
setback for the same lot -- FLATS, whose corpus says 0 ft against a
commercial neighbour where this table cut 10, or 20 ft against a house where
it cut 0 -- charges its parking court against the strip that is really
there, not the one it would have cut (`flats/score/screen.py`
``_court_beyond_rear``, 2026-09-22).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import load_rules, read_stage, write_stage

MIN_PART_SQFT = 200.0

SETBACK_FOR_CLASS = {"F": "setback_front_ft", "R": "setback_rear_ft", "S": "setback_side_ft"}


def lot_setbacks(rule, area_sqft: float, tier: str) -> dict[str, float]:
    """The setback each edge class of one lot owes, in feet, as s5 cuts it.

    Rear and side come through the step-back: five Gresham districts and two
    Milwaukie zones cap the roof at the setback line and make it rise a foot
    per foot beyond, so a 26 ft pod owes more yard than the district table
    prints (see ZoneRule.effective_setback_*). All of them come through the
    lot-size band: Wilsonville prints its residential setback table twice,
    once for lots over 10,000 sq ft and once for lots under, and neither
    column is "the zone's setback". The alley takes the rear unless the code
    states its own (`ZoneRule.setback_alley_ft`). Corner lots (tier B): we
    can't tell which street edge is the legal front, so every street edge
    takes max(front, street_side) -- conservative when the street-side
    setback exceeds the front.
    """
    setbacks = {
        "F": rule.effective_setback_front_ft(area_sqft),
        "R": rule.effective_setback_rear_ft(lot_area_sqft=area_sqft),
        "S": rule.effective_setback_side_ft(lot_area_sqft=area_sqft),
        "A": rule.effective_setback_alley_ft(lot_area_sqft=area_sqft),
    }
    if tier == "B" and rule.setback_street_side_ft:
        setbacks["F"] = max(setbacks["F"], rule.setback_street_side_ft)
    return setbacks


def cuts_made(setbacks: dict[str, float], edges: list, tier: str) -> dict[str, float] | None:
    """The strip each edge class actually loses in `build_envelope`, in feet.

    Tier A/B with edges: the class's own setback. Tier C, or no edges to
    trace: the uniform inset, which is the largest of the four on every
    class. Tier D: nothing is cut because nothing is kept -- ``None``.
    """
    if tier == "D":
        return None
    if tier == "C" or not edges:
        inset = max(setbacks.values())
        return {cls: round(inset, 2) for cls in setbacks}
    return {cls: round(float(d), 2) for cls, d in setbacks.items()}


def build_envelope(geom, edges: list, setbacks: dict[str, float], tier: str):
    """Returns MultiPolygon envelope (possibly empty)."""
    import shapely
    from shapely.geometry import LineString, MultiPolygon

    if tier == "D":
        return MultiPolygon([])
    if tier == "C" or not edges:
        env = geom.buffer(-max(setbacks.values()))
    else:
        strips = []
        for x1, y1, x2, y2, cls in edges:
            d = setbacks[cls]
            if d <= 0:
                continue
            strips.append(
                LineString([(x1, y1), (x2, y2)]).buffer(
                    d, cap_style="square", join_style="mitre"
                )
            )
        env = geom.difference(shapely.union_all(strips)) if strips else geom
    parts = [
        p for p in shapely.get_parts(env)
        if p.geom_type == "Polygon" and p.area >= MIN_PART_SQFT
    ]
    return MultiPolygon(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    rules = load_rules()
    lots = read_stage("s4_lots")
    print(f"s5: computing envelopes for {len(lots):,} lots")

    envs = []
    env_area = []
    cuts = []
    for n, row in enumerate(lots.itertuples(index=False)):
        j = rules.jurisdictions[row.jurisdiction]
        rule = j.rule_for(row.zone_raw)
        # An alley edge is a rear lot line -- Gresham 3.0100 and Oregon City
        # 17.04.1000 say so in those words, Wilsonville 4.113 measures "Rear
        # Setback ... from the rear lot line abutting the alley" -- and takes
        # the rear setback unless the code states its own from an alley
        # (Portland: none). Fairview lets a garage sit on the alley line and
        # reads an alley as a street, so it has no A edge to relieve.
        setbacks = lot_setbacks(rule, float(row.area_sqft), row.tier)
        edges = json.loads(row.edges_json)
        env = build_envelope(row.geom, edges, setbacks, row.tier)
        envs.append(env)
        env_area.append(env.area)
        made = cuts_made(setbacks, edges, row.tier)
        cuts.append(json.dumps(made) if made is not None else None)
        if n and n % 20000 == 0:
            print(f"  {n:,}/{len(lots):,}")

    out = lots.drop(columns=["geom"]).copy()
    out["geom"] = envs  # envelope becomes the stage geometry
    out["envelope_sqft"] = env_area
    out["env_setbacks_json"] = cuts
    empty = sum(1 for e in envs if e.is_empty)
    print(f"s5: {empty:,} lots have an empty envelope (setbacks consume the lot)")
    write_stage(out, "s5_lots")
    print("s5 done.")


if __name__ == "__main__":
    main()
