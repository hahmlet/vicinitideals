"""s4 — classify each eligible lot's edges as front / rear / side and assign a
geometry-confidence tier.

Method: simplify the lot's exterior ring (merges collinear vertices), then for
each remaining edge measure distance from its midpoint to the nearest street
centerline. Edges within street_threshold_ft are frontage. Rear = non-front
edges roughly parallel (±30° mod 180) to a front bearing; sides = the rest.

Tiers:
  A  clean, near-convex, one street frontage direction
  B  corner (2+ distinct frontage directions) — both bearings kept for fit
  C  irregular / flag / concave — s5 uses the conservative uniform envelope
  D  landlocked (no street within threshold) — excluded from headline stats

RLIS taxlots exclude right-of-way, so lot lines genuinely abut ROW gaps and
centerline distance is a reliable frontage proxy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import load_rules, read_stage, write_stage

PARALLEL_TOL_DEG = 30.0
BEARING_CLUSTER_TOL_DEG = 20.0
CONVEXITY_IRREGULAR = 0.80
MAX_EDGES_REGULAR = 10
POLE_TEST_BUFFER_FT = -7.5  # flag-lot pole thinner than 15 ft collapses


def bearing_deg(x1: float, y1: float, x2: float, y2: float) -> float:
    """Edge bearing in [0, 180)."""
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def bearing_delta(a: float, b: float) -> float:
    """Smallest angular difference mod 180."""
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def cluster_bearings(bearings_lengths: list[tuple[float, float]]) -> list[float]:
    """Greedy length-weighted clustering of bearings (mod 180).

    Returns cluster centers sorted by total member length (desc).
    """
    clusters: list[list[float]] = []  # [center, total_len]
    for b, ln in sorted(bearings_lengths, key=lambda t: -t[1]):
        for c in clusters:
            if bearing_delta(b, c[0]) <= BEARING_CLUSTER_TOL_DEG:
                # length-weighted running center (small-angle ok at this tol)
                w = c[1] + ln
                delta = b - c[0]
                if delta > 90:
                    delta -= 180
                elif delta < -90:
                    delta += 180
                c[0] = (c[0] + delta * ln / w) % 180.0
                c[1] = w
                break
        else:
            clusters.append([b, ln])
    clusters.sort(key=lambda c: -c[1])
    return [c[0] for c in clusters]


def classify_lot(geom, street_tree, street_geoms, threshold_ft: float,
                 simplify_tol: float) -> dict:
    """Classify one lot polygon. Returns dict of edge/tier attributes."""
    import shapely
    from shapely.geometry import LineString, Point

    simplified = geom.simplify(simplify_tol, preserve_topology=True)
    ring = list(simplified.exterior.coords)
    edges = []  # (x1, y1, x2, y2, length, bearing)
    for (x1, y1), (x2, y2) in zip(ring[:-1], ring[1:]):
        ln = math.hypot(x2 - x1, y2 - y1)
        if ln < 1.0:
            continue
        edges.append((x1, y1, x2, y2, ln, bearing_deg(x1, y1, x2, y2)))
    if not edges:
        return {"tier": "D", "edges": [], "front_bearings": [], "frontage_ft": 0.0}

    # Frontage test: midpoint distance to nearest street centerline.
    front_flags = []
    for x1, y1, x2, y2, ln, _b in edges:
        mid = Point((x1 + x2) / 2, (y1 + y2) / 2)
        nearest_idx = street_tree.nearest(mid)
        dist = mid.distance(street_geoms[nearest_idx])
        front_flags.append(dist <= threshold_ft)

    if not any(front_flags):
        return {"tier": "D", "edges": [], "front_bearings": [], "frontage_ft": 0.0}

    front_bearings = cluster_bearings(
        [(e[5], e[4]) for e, f in zip(edges, front_flags) if f]
    )
    frontage_ft = sum(e[4] for e, f in zip(edges, front_flags) if f)

    # Edge classes.
    classed = []
    for (x1, y1, x2, y2, ln, b), is_front in zip(edges, front_flags):
        if is_front:
            cls = "F"
        elif any(bearing_delta(b, fb) <= PARALLEL_TOL_DEG for fb in front_bearings):
            cls = "R"
        else:
            cls = "S"
        classed.append([round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2), cls])

    # Tier.
    hull_area = geom.convex_hull.area
    convexity = geom.area / hull_area if hull_area > 0 else 0.0
    shrunk = geom.buffer(POLE_TEST_BUFFER_FT)
    parts = shapely.get_parts(shrunk) if not shrunk.is_empty else []
    pole_like = len(parts) > 1 and max((p.area for p in parts), default=0) < 0.8 * sum(
        p.area for p in parts
    )
    irregular = (
        convexity < CONVEXITY_IRREGULAR
        or len(edges) > MAX_EDGES_REGULAR
        or pole_like
    )
    if irregular:
        tier = "C"
    elif len(front_bearings) >= 2:
        tier = "B"
    else:
        tier = "A"

    return {
        "tier": tier,
        "edges": classed,
        "front_bearings": [round(b, 2) for b in front_bearings[:2]],
        "frontage_ft": round(frontage_ft, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    import numpy as np
    from shapely.strtree import STRtree

    rules = load_rules()
    lots = read_stage("s3_lots")
    streets = read_stage("s1_streets")
    street_geoms = np.array(list(streets["geom"]), dtype=object)
    tree = STRtree(street_geoms)
    thr = rules.defaults.street_threshold_ft
    tol = rules.defaults.simplify_tolerance_ft

    print(f"s4: classifying {len(lots):,} lots against {len(street_geoms):,} street segments")
    results = []
    for n, geom in enumerate(lots["geom"]):
        results.append(classify_lot(geom, tree, street_geoms, thr, tol))
        if n and n % 20000 == 0:
            print(f"  {n:,}/{len(lots):,}")

    lots["tier"] = [r["tier"] for r in results]
    lots["edges_json"] = [json.dumps(r["edges"]) for r in results]
    lots["front_bearings_json"] = [json.dumps(r["front_bearings"]) for r in results]
    lots["frontage_ft"] = [r["frontage_ft"] for r in results]

    from collections import Counter

    print("s4 tier distribution:", dict(Counter(lots["tier"])))
    write_stage(lots, "s4_lots")
    print("s4 done.")


if __name__ == "__main__":
    main()
