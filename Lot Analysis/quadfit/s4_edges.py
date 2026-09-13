"""s4 — classify each eligible lot's edges as front / rear / side and assign a
geometry-confidence tier.

Method: simplify the lot's exterior ring (merges collinear vertices), then for
each remaining edge measure distance from its midpoint to the nearest street
centerline. Edges within street_threshold_ft are frontage. Rear = non-front
edges roughly parallel (±30° mod 180) to a front bearing; sides = the rest.

Edge classes:
  F  street frontage -- within the threshold of a street centerline
  A  alley -- within the threshold of an alley and of no street, AND with
     the alley actually across it (`_alley_width`: the gap between this
     lot and the first private lot beyond, with the alley's centreline
     inside that gap; the right-of-way polygon, where the taxlot file
     draws one, is looked through, and where the land beyond is public
     as far as the ray reaches -- I-5, the St. Johns rail cut -- the
     centreline's offset stands in, doubled). An edge that abuts a
     neighbour's lot
     with the centreline running behind THAT lot is not on the alley
     however near the centreline runs -- 937 such edges, 82 of them under
     a green, before 2026-09-13. Not frontage, not a candidate front lot
     line, set back as a rear lot line by s5, and not a street the site
     plan faces. Only produced in cities whose code says an alley is not a
     street (`JurisdictionRules.alley_is_street` is False); where it says
     the opposite the alley is read as any other street and classes F. A
     lot whose only street-facing line is an alley keeps it as F in every
     city -- see the same field for why. The width of the gap is written
     to `alley_width_ft` (the narrowest, where a lot has more than one
     alley edge), and the site plan asks the city's back-out room of it.
  R  rear -- not a street, roughly parallel to a front bearing
  S  side -- the rest

Tiers:
  A  clean, near-convex, one street frontage direction
  B  corner (2+ distinct frontage directions) — both bearings kept for fit
  C  irregular / flag / concave — s5 uses the conservative uniform envelope
  D  landlocked (no street within threshold) — excluded from headline stats

RLIS taxlots hold MOST of the right-of-way as polygons of their own
(Multnomah's `-STR` lots, one per quarter-section; Clackamas's `ROADS`; s3
drops them) and draw the rest as nothing -- a gap in the fabric, which is
how some 180 of Portland's alleys come (the first alley run demoted every
one of them). Either way a private lot line genuinely abuts the ROW's edge and
centerline distance is a reliable frontage proxy. That was an assertion until 2026-09-01;
`audit_landlocked.py` measured it. Of 7,499 tier-D lots, **6,947
(92.6%) have another taxlot standing between them and the nearest street** --
reached over a neighbour's land, which is not frontage any code in the corpus
would accept. The other 552 have an open right-of-way in the gap and are the
error this test makes: mostly lots on very wide arterials, 252 of them within
60 ft. Raising the threshold to collect them would buy 552 at the cost of
calling a street 93 ft away, across somebody's front garden, frontage for the
other 6,947. If it is ever worth closing, the audit's test is the way -- front
the lot when nothing private is in the gap, whatever its width.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import NOT_A_TAXLOT_RE, load_rules, read_stage, write_stage
from lotdims import dimensions

PARALLEL_TOL_DEG = 30.0
BEARING_CLUSTER_TOL_DEG = 20.0
CONVEXITY_IRREGULAR = 0.80
MAX_EDGES_REGULAR = 10
POLE_TEST_BUFFER_FT = -7.5  # flag-lot pole thinner than 15 ft collapses

# The alley's width, measured across the gap in the taxlot fabric (see
# `_alley_width`).
ALLEY_RAY_FT = 80.0        # how far past the edge the far side is looked for
ALLEY_WIDTH_MIN_FT = 8.0   # narrower than this is a sliver, or no gap at all
ALLEY_WIDTH_MAX_FT = 40.0  # wider than this is a ray down the alley, not across
ALLEY_CL_TOL_FT = 3.0      # the centreline may sit this far past the far side
ALLEY_CL_ALONG_FT = 50.0   # ... and this far along the alley from the ray
ALLEY_SAMPLES = (0.1, 0.3, 0.5, 0.7, 0.9)   # where along the edge a ray is cast
ALLEY_SAMPLES_MIN_HIT = 3  # at least this many of the five must find the alley


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


def _alley_width(x1: float, y1: float, x2: float, y2: float, outward: float,
                 lot_tree, lot_geoms, lot_private, alley_tree, alley_geoms,
                 ) -> float | None:
    """The width of the alley across one lot edge, in feet, or None where
    no alley is across it.

    The alley is the gap in the taxlot fabric: a ray cast outward from the
    edge runs until it enters the first PRIVATE lot beyond (any row of the
    file but the right-of-way, river, rail and water -- `NOT_A_TAXLOT_RE`
    -- and not this lot itself, nor anything stacked on it), and that
    distance is the alley's width, PROVIDED it is an alley's (between
    `ALLEY_WIDTH_MIN_FT` and `ALLEY_WIDTH_MAX_FT`) and the alley's
    centreline runs in the gap: across the ray, or, within
    `ALLEY_CL_ALONG_FT` of it along the gap, past the ray's end -- RLIS
    draws a platted alley's centreline shorter than its right-of-way, and
    the 2026-09-13 run that wanted the crossing itself demoted 170 lots
    on a 16 ft strip whose centreline stopped 26 to 38 ft short of them,
    52 of them greens. The file draws most alleys as a `-STR` polygon and
    some as nothing at all; the ray looks through both, so the two
    measure alike, and the 179 Portland alleys drawn as nothing
    (neighbour 12-20 ft out, centreline 5-10) are alleys. An edge with a
    neighbour's lot directly across it and the centreline behind that lot
    measures a gap of zero, which is no alley's width, and is not on the
    alley; nor is the lot line an alley easement runs along, nor a public
    strip under `ALLEY_WIDTH_MIN_FT` (Portland holds 4 to 7 ft strips
    with an alley centreline down them; no car backs into one).

    Where the ray finds no private land at all -- the alley runs along
    I-5, or the St. Johns rail cut, and the right-of-way beyond is public
    for a hundred feet (89 lots on the third 2026-09-13 run, 69 of them
    greens) -- the fabric has no far side to measure to, and the
    centreline stands in for it: the width is twice its offset, provided
    the lot line itself is on public land (the ray starts in a
    right-of-way polygon) and a centreline crosses the ray.

    Rays go out from five points along the edge, not one, because at a T
    the midpoint's ray can run down the alley's length into the street
    beyond (145 such chords over 40 ft on the 2026-09-13 probe of 11,733
    lots; anything past `ALLEY_WIDTH_MAX_FT` is that, not a width, and the
    other four rays are the measurement); the width is the NARROWEST, and
    an edge is on the alley only where at least `ALLEY_SAMPLES_MIN_HIT` of
    the five find it, so the lot at an alley's dead end, whose rear line
    touches it for fourteen feet of fifty, does not park four cars in the
    neighbour's yard. `outward` is +1 or -1 and turns the edge's
    right-hand normal to point out of the lot.
    """
    from shapely.geometry import LineString, Point, Polygon

    ln = math.hypot(x2 - x1, y2 - y1)
    ex, ey = (x2 - x1) / ln, (y2 - y1) / ln       # along the edge
    nx, ny = outward * ey, -outward * ex           # out of the lot
    widths = []
    for t in ALLEY_SAMPLES:
        px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
        p = Point(px, py)
        inside = Point(px - 0.5 * nx, py - 0.5 * ny)    # half a foot into this lot
        outside = Point(px + 0.5 * nx, py + 0.5 * ny)   # ... and half a foot out of it
        ray = LineString([(px, py), (px + ALLEY_RAY_FT * nx, py + ALLEY_RAY_FT * ny)])
        # The far side: where private land begins again along the ray.
        far, on_public = None, False
        for j in lot_tree.query(ray):
            g = lot_geoms[j]
            if not lot_private[j]:
                on_public = on_public or g.intersects(outside)
                continue
            if g.intersects(inside) or not ray.intersects(g):
                continue
            d = ray.intersection(g).distance(p)
            far = d if far is None else min(far, d)
        if far is None and on_public:
            # Public land as far as the ray reaches (a freeway, a rail
            # cut): the centreline's crossing is the alley's middle.
            d_cl = None
            for j in alley_tree.query(ray):
                xx = ray.intersection(alley_geoms[j])
                if not xx.is_empty:
                    d = xx.distance(p)
                    d_cl = d if d_cl is None else min(d_cl, d)
            far = None if d_cl is None else 2.0 * d_cl
        if far is None or not ALLEY_WIDTH_MIN_FT <= round(far, 1) <= ALLEY_WIDTH_MAX_FT:
            continue
        # The centreline must run in the gap, or the gap is not this alley:
        # the band is the gap's depth (a foot into the lot, the tolerance
        # past the far side) for `ALLEY_CL_ALONG_FT` either way along it.
        a, b = ALLEY_CL_ALONG_FT, far + ALLEY_CL_TOL_FT
        band = Polygon([(px - a * ex - nx, py - a * ey - ny),
                        (px + a * ex - nx, py + a * ey - ny),
                        (px + a * ex + b * nx, py + a * ey + b * ny),
                        (px - a * ex + b * nx, py - a * ey + b * ny)])
        if not any(band.intersects(alley_geoms[j]) for j in alley_tree.query(band)):
            continue
        widths.append(far)
    if len(widths) < ALLEY_SAMPLES_MIN_HIT:
        return None
    return round(min(widths), 1)


def classify_lot(geom, street_tree, street_geoms, threshold_ft: float,
                 simplify_tol: float, *, alley_tree=None, alley_geoms=None,
                 lot_tree=None, lot_geoms=None, lot_private=None) -> dict:
    """Classify one lot polygon. Returns dict of edge/tier attributes.

    ``alley_tree``/``alley_geoms`` hold the alley centerlines separately from
    the streets. An edge near an alley and near no street classes ``A``; an
    edge near both is a street edge, because the street is the one the code
    cares about. Pass neither and every segment given is a street, which is
    how the two cities whose code says an alley is a street are run.

    ``lot_tree``/``lot_geoms``/``lot_private`` hold every polygon of the
    taxlot file (s1, not s3: the neighbours and the right-of-way included)
    and which of them are private land. Given, an ``A`` edge must have the
    alley actually across it (`_alley_width`) or it is not an alley edge at
    all -- it is whatever the bearing test makes of it -- and the narrowest
    alley across the lot's alley edges is returned as ``alley_width_ft``.
    Not given, the centreline alone decides, as it did until 2026-09-13,
    and the width is None.
    """
    import shapely
    from shapely.geometry import LineString, Point

    simplified = geom.simplify(simplify_tol, preserve_topology=True)
    ring = list(simplified.exterior.coords)
    # The edge's right-hand normal points out of a counter-clockwise ring
    # and into a clockwise one; `_alley_width` casts its rays outward.
    outward = 1.0 if shapely.is_ccw(simplified.exterior) else -1.0
    edges = []  # (x1, y1, x2, y2, length, bearing)
    for (x1, y1), (x2, y2) in zip(ring[:-1], ring[1:]):
        ln = math.hypot(x2 - x1, y2 - y1)
        if ln < 1.0:
            continue
        edges.append((x1, y1, x2, y2, ln, bearing_deg(x1, y1, x2, y2)))
    none = {"tier": "D", "edges": [], "front_bearings": [], "frontage_ft": 0.0,
            "alley_width_ft": None, "alley_edges_demoted": 0}
    if not edges:
        return none

    # Frontage test: midpoint distance to nearest street centerline, and
    # failing that to the nearest alley -- which, where the taxlot fabric
    # is given, must then actually lie across the edge.
    front_flags = []
    alley_flags = []
    alley_widths = []
    demoted = 0
    for x1, y1, x2, y2, ln, _b in edges:
        mid = Point((x1 + x2) / 2, (y1 + y2) / 2)
        nearest_idx = street_tree.nearest(mid)
        dist = mid.distance(street_geoms[nearest_idx])
        is_front = dist <= threshold_ft
        front_flags.append(is_front)
        is_alley = False
        width = None
        if not is_front and alley_tree is not None and len(alley_geoms):
            a_idx = alley_tree.nearest(mid)
            is_alley = mid.distance(alley_geoms[a_idx]) <= threshold_ft
            if is_alley and lot_tree is not None:
                width = _alley_width(x1, y1, x2, y2, outward, lot_tree, lot_geoms,
                                     lot_private, alley_tree, alley_geoms)
                if width is None:
                    is_alley = False
                    demoted += 1
        alley_flags.append(is_alley)
        alley_widths.append(width)

    # A lot with an alley and no street: the alley is its frontage, as it
    # was before alleys were told apart. Demoting it would make the lot
    # landlocked, which a lot on a public way is not.
    if not any(front_flags) and any(alley_flags):
        front_flags, alley_flags = alley_flags, [False] * len(edges)

    if not any(front_flags):
        return {**none, "alley_edges_demoted": demoted}
    alley_width = min((w for w, a in zip(alley_widths, alley_flags) if a and w is not None),
                      default=None)

    front_bearings = cluster_bearings(
        [(e[5], e[4]) for e, f in zip(edges, front_flags) if f]
    )
    frontage_ft = sum(e[4] for e, f in zip(edges, front_flags) if f)

    # Edge classes.
    classed = []
    for (x1, y1, x2, y2, ln, b), is_front, is_alley in zip(
        edges, front_flags, alley_flags
    ):
        if is_front:
            cls = "F"
        elif is_alley:
            cls = "A"
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
        "alley_width_ft": alley_width,
        "alley_edges_demoted": demoted,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    import numpy as np
    from shapely.strtree import STRtree

    rules = load_rules()
    lots = read_stage("s3_lots")
    streets = read_stage("s1_streets")
    # Alleys are told apart from streets (s1 flags them from RLIS TYPE 1600)
    # and classified against separately, except in the cities whose code
    # says an alley is a street, which are run against the whole file.
    if "alley" not in streets.columns:
        raise SystemExit(
            "s1_streets has no 'alley' column -- re-run s1_normalize.py --only streets"
        )
    is_alley = streets["alley"].fillna(False).astype(bool).to_numpy()
    all_geoms = np.array(list(streets["geom"]), dtype=object)
    street_geoms = all_geoms[~is_alley]
    alley_geoms = all_geoms[is_alley]
    tree_all = STRtree(all_geoms)
    tree_streets = STRtree(street_geoms)
    tree_alleys = STRtree(alley_geoms) if len(alley_geoms) else None
    # The whole taxlot fabric -- every neighbour, and the right-of-way
    # polygons s3 dropped -- read out of s1 so an alley edge can be asked
    # whether the alley actually lies across it, and how wide it is.
    s1 = read_stage("s1_lots")[["TLID", "geom"]]
    lot_geoms = np.array(list(s1["geom"]), dtype=object)
    lot_private = ~s1["TLID"].astype(str).str.contains(NOT_A_TAXLOT_RE, regex=True).to_numpy()
    del s1
    tree_lots = STRtree(lot_geoms)
    thr = rules.defaults.street_threshold_ft
    tol = rules.defaults.simplify_tolerance_ft
    alley_is_street = {
        name: j.alley_is_street for name, j in rules.jurisdictions.items()
    }

    print(
        f"s4: classifying {len(lots):,} lots against {len(street_geoms):,} street "
        f"segments and {len(alley_geoms):,} alley segments; the alley edges are "
        f"measured against {int(lot_private.sum()):,} private lots, looking through "
        f"{int((~lot_private).sum()):,} right-of-way polygons"
    )
    results = []
    for n, (geom, juris) in enumerate(zip(lots["geom"], lots["jurisdiction"])):
        if alley_is_street.get(juris, False):
            results.append(classify_lot(geom, tree_all, all_geoms, thr, tol))
        else:
            results.append(classify_lot(
                geom, tree_streets, street_geoms, thr, tol,
                alley_tree=tree_alleys, alley_geoms=alley_geoms,
                lot_tree=tree_lots, lot_geoms=lot_geoms, lot_private=lot_private,
            ))
        if n and n % 20000 == 0:
            print(f"  {n:,}/{len(lots):,}")

    lots["tier"] = [r["tier"] for r in results]
    lots["edges_json"] = [json.dumps(r["edges"]) for r in results]
    lots["front_bearings_json"] = [json.dumps(r["front_bearings"]) for r in results]
    lots["frontage_ft"] = [r["frontage_ft"] for r in results]
    # The alley's width, and the edges that were near an alley's centreline
    # with no alley across them. Printed per city so a city whose alleys
    # the file draws strangely would show as one that lost every alley.
    lots["alley_width_ft"] = [
        float("nan") if r["alley_width_ft"] is None else r["alley_width_ft"]
        for r in results
    ]
    _w = lots["alley_width_ft"].to_numpy(dtype=float)
    _dem = np.array([r["alley_edges_demoted"] for r in results])
    if np.isfinite(_w).any():
        print(f"s4 alley width measured on {int(np.isfinite(_w).sum()):,} lots: "
              f"p10 {np.nanpercentile(_w, 10):.0f}, p50 {np.nanpercentile(_w, 50):.0f}, "
              f"p90 {np.nanpercentile(_w, 90):.0f} ft; under 20 ft on "
              f"{int((_w < 20).sum()):,}")
    if _dem.any():
        per = (lots.assign(_d=_dem).groupby("jurisdiction")["_d"]
               .agg(["sum", lambda s: int((s > 0).sum())]))
        print("s4 alley edges demoted (near a centreline, no alley across the edge): "
              + ", ".join(f"{j} {int(r['sum']):,} on {int(r.iloc[1]):,} lots"
                          for j, r in per[per["sum"] > 0].iterrows()))

    # Lot WIDTH and lot DEPTH, where a city's code defines them -- two
    # different lines on the same parcel from the frontage measured above, and
    # from each other. Taken here because this is where the edges are
    # classified; NaN where the city defines no measure, or where the shape
    # declines to be measured. `lotdims.py` carries the definitions, the
    # citations and the refusals.
    #
    # One call per lot, not one per axis, and that is the point. Where the
    # city lets the applicant choose the front lot line, the lot conforms if
    # ONE front satisfies BOTH standards -- a corner lot that is wide enough
    # facing north and deep enough facing east conforms to neither -- so the
    # zone's width and depth floors go in with the geometry and `pick` chooses
    # a single front against both. The front setback goes in too, because two
    # of the six width forms are taken at the building line rather than the
    # kerb, and both are banded by lot area in the zones that state them.
    #
    # Until 2026-09-11 the width was taken in its own pass with no standard
    # and no setback, which refused Milwaukie's and Gresham's form outright
    # and, under `applicant_choice`, reported the most generous depth rather
    # than the depth of the front the lot would actually be built to face.
    widths, depths = [], []
    for juris, zraw, area, geom, r in zip(
        lots["jurisdiction"], lots["zone_raw"], lots["area_sqft"],
        lots["geom"], results,
    ):
        j = rules.jurisdictions.get(juris)
        if j is None or not (j.lot_width_measure or j.lot_depth_measure):
            widths.append(float("nan"))
            depths.append(float("nan"))
            continue
        rule = j.rule_for(zraw)
        a = None if area is None else float(area)
        o = dimensions(
            geom, r["edges"], r["front_bearings"], r["tier"],
            width_measure=j.lot_width_measure,
            depth_measure=j.lot_depth_measure,
            front_rule=j.front_lot_line_rule,
            front_setback_ft=(
                None if rule is None else rule.effective_setback_front_ft(a)
            ),
            min_width_ft=(
                None if rule is None else rule.banded("min_lot_width_ft", a)
            ),
            min_depth_ft=None if rule is None else rule.min_lot_depth_ft,
        )
        widths.append(
            float("nan") if o is None or o.width_ft is None else o.width_ft
        )
        depths.append(
            float("nan") if o is None or o.depth_ft is None else o.depth_ft
        )
    lots["lot_width_ft"] = widths
    lots["lot_depth_ft"] = depths
    measured = int(np.isfinite(np.array(widths, dtype=float)).sum())
    print(f"s4 lot width measured on {measured:,} lots")
    deep = int(np.isfinite(np.array(depths, dtype=float)).sum())
    print(f"s4 lot depth measured on {deep:,} lots")

    from collections import Counter

    print("s4 tier distribution:", dict(Counter(lots["tier"])))
    with_alley = sum(1 for r in results if any(e[4] == "A" for e in r["edges"]))
    print(f"s4 lots with an alley edge (class A): {with_alley:,}")
    write_stage(lots, "s4_lots")
    print("s4 done.")


if __name__ == "__main__":
    main()
