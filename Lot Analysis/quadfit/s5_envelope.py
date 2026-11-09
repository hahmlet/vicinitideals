"""s5 — buildable envelope per lot: lot minus per-edge setback strips.

Tier A/B: envelope = lot − ⋃ setback_strip(edge, setback_for_class): every
point nearer a lot line than that line's setback. Each strip is the band
either side of the line closed by a half-disc round each end, drawn as a
polygon AROUND the circle (`setback_strip`), so it is never short of the
setback -- never larger than the legal envelope -- and it overshoots by at
most 0.12% of the setback. Until 2026-11-09 the strips had square caps,
which ran a full setback past each end: at an inward bend in a lot line they
took a sliver up to a setback long and ~1.5 ft deep past the bend (Tigard
2S103BA00137's 4.5 deg front bend), and at an obtuse corner the deeper
line's number ran along the shallower line's yard. The half-disc sits inside
the old square cap, so the envelope only grew back toward the legal one. The
same construction as FLATS' `flats.geom.envelope._strip`, kept here as its
own copy so a quadfit run does not move with FLATS' geometry.

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

#: Chords per half-disc at a strip's end. Even, so a chord's midpoint (not a
#: corner) sits straight off the line's end and the strip stays inside the
#: old square cap; 32 chords overshoot the circle by 1/cos(pi/64) - 1 = 0.12%.
ARC_SPLITS = 32

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


def setback_strip(x1: float, y1: float, x2: float, y2: float, d: float):
    """Every point within ``d`` of the segment, and no more than a sag beyond.

    The band ``d`` either side of the segment, closed at each end by a
    half-disc of radius ``d`` round the endpoint, drawn with `ARC_SPLITS`
    chords that touch the circle at their midpoints: the polygon holds the
    whole circle (never short of the setback) and sits inside the square
    cap this replaced (never more than it took). A segment of no length is
    the disc.
    """
    import math

    from shapely.geometry import Polygon

    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    ux, uy = (dx / length, dy / length) if length > 0 else (1.0, 0.0)
    nx, ny = -uy, ux  # the left normal
    step = math.pi / ARC_SPLITS
    corner = d / math.cos(step / 2)

    def arc(cx, cy, sx, sy, fx, fy):
        # The half-disc from side s round through forward f to -s: a
        # tangent point, the chord corners, a tangent point.
        pts = [(cx + d * sx, cy + d * sy)]
        for i in range(ARC_SPLITS):
            t = (i + 0.5) * step
            c, si = math.cos(t), math.sin(t)
            pts.append((cx + corner * (c * sx + si * fx), cy + corner * (c * sy + si * fy)))
        pts.append((cx - d * sx, cy - d * sy))
        return pts

    return Polygon(arc(x2, y2, nx, ny, ux, uy) + arc(x1, y1, -nx, -ny, -ux, -uy))


def build_envelope(geom, edges: list, setbacks: dict[str, float], tier: str):
    """Returns MultiPolygon envelope (possibly empty)."""
    import shapely
    from shapely.geometry import MultiPolygon

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
            strips.append(setback_strip(x1, y1, x2, y2, d))
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
