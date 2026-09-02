"""s5 — buildable envelope per lot: lot minus per-edge setback strips.

Tier A/B: envelope = lot − ⋃ edge.buffer(setback_for_class, square caps).
Square caps extend each strip past its endpoints, so corner wedges between
adjacent edges are always covered — the result is conservative (never larger
than the legal envelope; error bounded by the setback delta between adjacent
edges, confined to corner wedges).

Tier C (irregular/flag): uniform inward buffer by the max setback — strictly
conservative fallback. Tier D lots are excluded from fitting (envelope empty).

Envelope parts smaller than MIN_PART_SQFT are dropped (nothing fits there).
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
    for n, row in enumerate(lots.itertuples(index=False)):
        j = rules.jurisdictions[row.jurisdiction]
        rule = j.rule_for(row.zone_raw)
        # Rear and side come through the step-back: five Gresham districts
        # and two Milwaukie zones cap the roof at the setback line and make it
        # rise a foot per foot beyond, so a 26 ft pod owes more yard than the
        # district table prints. See ZoneRule.effective_setback_*.
        # ...and all three come through the lot-size band: Wilsonville prints
        # its residential setback table twice, once for lots over 10,000 sq ft
        # and once for lots under, and neither column is "the zone's setback".
        area = float(row.area_sqft)
        setbacks = {
            "F": rule.effective_setback_front_ft(area),
            "R": rule.effective_setback_rear_ft(lot_area_sqft=area),
            "S": rule.effective_setback_side_ft(lot_area_sqft=area),
        }
        # Corner lots (tier B): we can't tell which street edge is the legal
        # front, so every street edge takes max(front, street_side) —
        # conservative when the street-side setback exceeds the front.
        if row.tier == "B" and rule.setback_street_side_ft:
            setbacks["F"] = max(setbacks["F"], rule.setback_street_side_ft)
        env = build_envelope(row.geom, json.loads(row.edges_json), setbacks, row.tier)
        envs.append(env)
        env_area.append(env.area)
        if n and n % 20000 == 0:
            print(f"  {n:,}/{len(lots):,}")

    out = lots.drop(columns=["geom"]).copy()
    out["geom"] = envs  # envelope becomes the stage geometry
    out["envelope_sqft"] = env_area
    empty = sum(1 for e in envs if e.is_empty)
    print(f"s5: {empty:,} lots have an empty envelope (setbacks consume the lot)")
    write_stage(out, "s5_lots")
    print("s5 done.")


if __name__ == "__main__":
    main()
