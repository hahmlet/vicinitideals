"""Lot width and lot depth, each measured the way the code asking for it defines it.

s4 measures *frontage*: the run of boundary that touches a street, summed over
every street-facing edge. That is not a width and it is not a depth, and the
distance between those three things is where this module lives.

Thirteen jurisdictions in this corpus state a minimum lot width, a minimum lot
depth, or both. Their glossaries were read end to end before a line of this was
written, because a measurement built before the definitions are read is one
city's definition applied to another city's rule. What came back is **six width
forms and three depth forms** -- fewer than thirteen, far more than one -- plus
a second axis nobody would guess from the standards themselves: *which edge is
the front*, which several cities answer differently and two of them hand to the
applicant.

The two axes are independent, so they are separate here. A city names a front
rule and a measure; an orientation is a candidate front; a measurement is a
measure taken in the frame that front defines.

Width forms
-----------

``side_midpoints``
    "The perpendicular distance measured between the midpoints of the two
    principal opposite side lot lines and generally at approximately right
    angles to the lot depth." Oregon City OCMC 17.04.700, Happy Valley MC
    16.12, Gresham 3.0100, Portland 33.930.100.B (every zone but the
    single-dwelling ones), and the second of West Linn's two width rows.

``midway_front_rear``
    "The horizontal distance between the side lot lines, measured at right
    angles to the lot depth **at a point midway between the front and rear lot
    lines**." Multnomah unincorporated 39.2000, Fairview 19.13, Troutdale
    1.020, Wood Village 720.030 -- four cities sharing one sentence.

    It is a near neighbour of ``side_midpoints`` and it is not the same line.
    That form joins the midpoints of the two sides, which on a lot with one
    long side and one short one is a skewed chord; this one is square to the
    depth axis at the halfway mark. They agree on a rectangle and part company
    on exactly the parcels a width rule is written for.

``center_parallel``
    "Parallel to the front lot line, at the center of the lot." Tualatin TDC
    31.060. Its second half -- "or, in the case of a corner lot, the horizontal
    distance between the front lot line and a side lot line" -- is a different
    measurement on a different pair of lines, so corner lots are refused rather
    than measured wrong.

``building_line``
    "The horizontal distance between side lot lines measured **at the Building
    line**." Milwaukie MMC 19.200. At the setback, not at the kerb, which on
    anything that tapers toward the road is the difference between a refusal
    and a pass.

``mean_width``
    "The **mean** horizontal distance between the side lot lines of a lot
    measured within the lot boundaries." Wilsonville 4.planning. Not a line at
    all -- an average of every line.

``setback_rectangle``
    Portland 33.930.100.A, single-dwelling zones, and the only one of the six
    that is not a distance: "lot width is measured by placing a rectangle along
    the minimum front building setback line ... minimum depth of 40 feet, or
    extend to the rear property line, whichever is less. The rectangle must fit
    entirely within the lot." It is a fit test, so what is returned is the
    widest rectangle that fits -- a number the zone's standard can still be
    compared against, obtained the way the city obtains it.

Depth forms
-----------

``midpoints``
    "From the mid-point of the front lot line to the mid-point of the opposite,
    usually the rear, lot line." Oregon City, Gresham, Happy Valley, Portland
    33.930.103.

``average``
    "The **average** horizontal distance between the front lot line and the
    rear lot line." Milwaukie MMC 19.200, West Linn CDC 02.030, Wilsonville
    ("mean average ... measured within the lot boundaries"), and Fairview and
    Wood Village, whose term is *"Lot depth, average"* and whose wording -- "the
    average distance from the **narrowest frontage** to the lot line opposite"
    -- also settles their front rule.

``mid_width``
    "The horizontal distance measured midway between the front and rear lot
    lines. In the case of a corner lot, the depth shall be the length of its
    longest side lot line." Troutdale 1.020. One line up the middle, with an
    explicit corner override that is a different measurement again.

Front lot line rules
--------------------

``narrowest``
    The shortest street-facing run is the front. Oregon City ("for corner lots,
    the front lot line is that with the narrowest frontage"), Portland ("the
    shortest of the lot lines that abut a street"), West Linn ("the shortest
    lot line along a street"), Wilsonville ("the shortest lot line along a
    tract with a pathway, street, or private drive"), Fairview and Wood Village
    (by their depth definition, "from the narrowest frontage"), and Happy
    Valley, whose front-lot-line entry offers the applicant the choice but
    whose side-lot-line entry states flatly that "on a corner lot, the longer
    lot line that abuts a street is a side lot line". Those two sentences are
    in tension; ``narrowest`` is the subset of the applicant's options, so it
    is the reading that cannot be more generous than the city allows.

    Wilsonville states the rule twice and only one of them is this. Item 121
    opens "for purposes of the solar access regulations" and is scoped to them;
    item 161 is the general definition. Taking the first would be the
    catalogued **wrong scope** shape.

``applicant_choice``
    Every street-facing direction is a candidate and the lot conforms if any
    one of them satisfies the standards. Milwaukie ("the street on which the
    existing or contemplated development will face"), Troutdale ("front lot
    lines on corner lots may face either street"), Portland where two street
    lot lines tie -- and Gresham, which describes :func:`pick` outright:

        "For a corner lot where there is no existing building, the front lot
        line is determined by the orientation necessary to achieve minimum
        required lot depth. If lot depth may be met in both directions, then
        the applicant may determine which lot line is the front lot line."

``None``
    The city does not say. The measurement is then taken only on a lot with one
    street-facing direction, where the question cannot arise, and a corner lot
    is refused. A city that states no rule must not be handed one.

This is the catalogued **applicant's choice** false-positive shape arriving as
a measurement rule rather than a reading one, and it is why this module returns
*every* orientation rather than a number. Width and depth have to be satisfied
by **one** front, not by the best front for each: a lot that is wide enough
facing north and deep enough facing east conforms to neither standard. Taking
the maximum of each independently would be an amnesty, and it is the specific
error :func:`pick` exists to prevent.

The refusals
------------

Every function returns ``None`` for "I could not take this measurement", and a
``None`` is a lot held for review. That is the shape of the whole module: it
converts *unmeasured* into *measured* where it honestly can, and leaves the
rest where it was. A dimension this module invents is worse than one it
declines, because a declined lot goes in front of a person and an invented one
can go green.

Two cities are deliberately not served. **Lake Oswego** states a width and
declares no definitions chapter, and is switched off in this screen anyway.
**West Linn**'s first width row is headed "Minimum lot width AT FRONT LOT
LINE", so its number is the street edge s4 already measures and nothing here
may touch it; only its *average* row is measured here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Two side lines are "opposite" if the segment joining their midpoints stays
#: inside the parcel. A wedge's sides converge and are nowhere near parallel,
#: which is the whole reason this measurement exists, so parallelism cannot be
#: the test. Containment can: on an L-shaped lot the join between the midpoints
#: of two sides that do not face each other leaves the polygon.
_INSIDE_TOL_FT = 0.5

#: A side line shorter than this against its opposite number is a chamfered
#: corner or a jog, not a principal side lot line.
_PRINCIPAL_RATIO = 0.40

#: How far the chord is thrown before being clipped to the parcel.
_CHORD_REACH = 4.0

#: Street-facing edges within this many degrees of each other are one front.
#: A surveyed frontage on a curve is a chain of short segments a fraction of a
#: degree apart, and calling each of them a separate candidate front would turn
#: one decision into forty identical ones.
_FRONT_BUCKET_DEG = 5.0

#: How many lines an averaged measurement is taken from. The forms that say
#: "average" or "mean" do not say over what, so they are sampled evenly across
#: the run being averaged. 41 puts a sample every 2.5% of the span, which on a
#: 60 ft frontage is every 18 inches.
_SAMPLES = 41

#: Portland's rectangle is 40 ft deep "or extend to the rear property line,
#: whichever is less" (33.930.100.A).
_PORTLAND_RECT_DEPTH_FT = 40.0

_EPS = 1e-6

WIDTH_MEASURES = frozenset({
    "side_midpoints", "midway_front_rear", "center_parallel",
    "building_line", "mean_width", "setback_rectangle",
})

DEPTH_MEASURES = frozenset({"midpoints", "average", "mid_width"})

FRONT_RULES = frozenset({"narrowest", "applicant_choice"})

#: A dimension is only taken on a lot whose shape the screen trusts. Tier C is
#: the irregular/flag pile, where "the two principal opposite side lot lines"
#: is a phrase without a referent, and tier D has no street to measure from.
MEASURABLE_TIERS = frozenset({"A", "B"})


@dataclass(frozen=True)
class Orientation:
    """One candidate front lot line, and what the lot measures facing it.

    ``front_ft`` is the length of *that* front -- one street's worth -- and is
    deliberately not s4's ``frontage_ft``, which sums every street-facing edge
    on the parcel and is therefore a number no single line is.
    """

    bearing: float
    front_ft: float
    width_ft: float | None
    depth_ft: float | None


# --- the frame ---------------------------------------------------------------


def _length(e) -> float:
    return math.hypot(e[2] - e[0], e[3] - e[1])


def _midpoint(e) -> tuple[float, float]:
    return ((e[0] + e[2]) / 2.0, (e[1] + e[3]) / 2.0)


def _bearing(e) -> float:
    return math.degrees(math.atan2(e[3] - e[1], e[2] - e[0])) % 180.0


def _offset(b: float, base: float) -> float:
    """How far bearing ``b`` is from ``base``, signed, in (-90, 90].

    Bearings are taken modulo 180, so 179 degrees and 1 degree are two degrees
    apart and not 178. Every comparison and every average in this module goes
    through here for that reason.
    """
    return ((b - base + 90.0) % 180.0) - 90.0


def front_groups(edges) -> list[tuple[float, list]]:
    """The distinct street-facing runs of this lot's boundary, longest first.

    Each run is one candidate front lot line. They are found by walking the
    boundary in order and breaking where the street stops or the boundary
    turns, rather than by bucketing every street-facing segment by bearing,
    because the two answers differ on exactly the parcel this has to get right.

    A frontage on a curve is surveyed as a chain of short near-collinear
    pieces. Bucketing splits that chain the moment its total sweep exceeds the
    tolerance, handing back three or four candidate fronts where the city sees
    one -- and then "the front lot line is the narrowest" picks a ten-foot
    surveyor's segment and measures the whole lot square to it. Oregon City
    settles this in the text: "when the lot line abutting a street is curved,
    the front lot line follows the curve" (OCMC 17.04.490). A run does.

    A corner, by contrast, turns through something near a right angle in one
    step, which breaks the run and gives the two fronts a corner lot has.
    """
    n = len(edges)
    is_front = [
        bool(len(e) > 4 and e[4] == "F" and _length(e) > _EPS) for e in edges
    ]
    if not any(is_front):
        return []
    runs: list[list] = []
    prev_i = None
    for i, e in enumerate(edges):
        if not is_front[i]:
            prev_i = None
            continue
        if (
            runs
            and prev_i == i - 1
            and abs(_offset(_bearing(e), _bearing(edges[prev_i]))) <= _FRONT_BUCKET_DEG
        ):
            runs[-1].append(e)
        else:
            runs.append([e])
        prev_i = i
    # The boundary is a ring, so a run can straddle the start of the list.
    if (
        len(runs) > 1
        and is_front[0]
        and is_front[n - 1]
        and abs(_offset(_bearing(edges[0]), _bearing(edges[n - 1])))
        <= _FRONT_BUCKET_DEG
    ):
        runs[0] = runs[-1] + runs[0]
        runs.pop()
    groups = []
    for members in runs:
        total = sum(_length(e) for e in members)
        base = _bearing(members[0])
        mean = base + sum(
            _length(e) * _offset(_bearing(e), base) for e in members
        ) / total
        groups.append((mean % 180.0, members))
    return sorted(
        groups, key=lambda g: sum(_length(e) for e in g[1]), reverse=True
    )


@dataclass(frozen=True)
class _Frame:
    """The lot seen from one candidate front: that line on y=``fy``, body above.

    ``origin`` and ``angle`` are carried so that other edges of the same parcel
    can be brought into the same frame afterwards. That is not housekeeping --
    it is what lets the depth forms ask whether a lot line classified ``R`` is
    actually *opposite this front*, which on a corner lot it is not.
    """

    rg: object
    fy: float
    fx0: float
    fx1: float
    origin: object
    angle: float


def _frame(geom, members, bearing_deg) -> "_Frame | None":
    """Rotate the lot so this front lot line is horizontal and the body is above it.

    Every form but ``side_midpoints`` and ``center_parallel`` is stated as a
    distance along, or across, the axis running from the front lot line to the
    rear one. Putting that axis on y once means each of them is two lines of
    geometry instead of its own trigonometry, and means they are all wrong in
    the same way if the frame is wrong -- which a test can pin.
    """
    from shapely import affinity
    from shapely.geometry import MultiLineString

    origin = geom.centroid
    segs = MultiLineString([[(e[0], e[1]), (e[2], e[3])] for e in members])
    for turn in (0.0, 180.0):
        angle = -bearing_deg + turn
        rg = affinity.rotate(geom, angle, origin=origin)
        rf = affinity.rotate(segs, angle, origin=origin)
        total = sum(p.length for p in rf.geoms)
        if total <= _EPS:
            return None
        fy = sum(
            p.length * ((p.coords[0][1] + p.coords[-1][1]) / 2.0) for p in rf.geoms
        ) / total
        if rg.centroid.y > fy:
            xs = [c[0] for p in rf.geoms for c in p.coords]
            return _Frame(rg, fy, min(xs), max(xs), origin, angle)
    return None


def _in_frame(edges, frame: _Frame) -> list[tuple[float, float, float, float]]:
    """The same lot lines, seen from the same front."""
    from shapely import affinity
    from shapely.geometry import MultiLineString

    if not edges:
        return []
    segs = affinity.rotate(
        MultiLineString([[(e[0], e[1]), (e[2], e[3])] for e in edges]),
        frame.angle,
        origin=frame.origin,
    )
    return [
        (p.coords[0][0], p.coords[0][1], p.coords[-1][0], p.coords[-1][1])
        for p in segs.geoms
    ]


def _row_intervals(rg, y) -> list[tuple[float, float]]:
    """Where the lot is, along the line at height ``y``."""
    import shapely
    from shapely.geometry import LineString

    minx, miny, maxx, maxy = rg.bounds
    if y < miny - _EPS or y > maxy + _EPS:
        return []
    line = LineString([(minx - 1.0, y), (maxx + 1.0, y)])
    out = []
    for p in shapely.get_parts(shapely.intersection(rg, line)):
        if p.length > _EPS:
            xs = [c[0] for c in p.coords]
            out.append((min(xs), max(xs)))
    return sorted(out)


def _row(rg, y) -> float | None:
    """The lot's width at height ``y`` -- the longest single piece.

    Longest rather than summed, and this is the same rule ``center_parallel``
    already applies for the same reason: a lot that wraps around a neighbour is
    re-entered by the line further along, and that second piece is somebody
    else's width.
    """
    parts = _row_intervals(rg, y)
    return max((b - a for a, b in parts), default=None)


def _column(rg, x, fy) -> float | None:
    """How deep the lot runs at ``x``, measured back from the front lot line.

    The piece taken is the one standing on the front line. A lot with a body
    detached from its frontage in this column has no depth here, and returns
    ``None`` so the sample is skipped rather than counted as zero.
    """
    import shapely
    from shapely.geometry import LineString

    minx, miny, maxx, maxy = rg.bounds
    if x < minx - _EPS or x > maxx + _EPS:
        return None
    line = LineString([(x, miny - 1.0), (x, maxy + 1.0)])
    for p in shapely.get_parts(shapely.intersection(rg, line)):
        if p.length <= _EPS:
            continue
        ys = [c[1] for c in p.coords]
        lo, hi = min(ys), max(ys)
        if lo <= fy + _INSIDE_TOL_FT <= hi:
            return hi - fy
    return None


def _samples(lo: float, hi: float) -> list[float]:
    if hi - lo <= _EPS:
        return [lo]
    step = (hi - lo) / (_SAMPLES - 1)
    return [lo + i * step for i in range(_SAMPLES)]


# --- width forms -------------------------------------------------------------


def side_midpoints_width_ft(geom, edges) -> float | None:
    """Oregon City: the distance between the midpoints of the two principal
    opposite side lot lines.

    "Principal" is read as the longest, and "opposite" as facing each other
    across the parcel rather than as parallel -- the lots this measurement is
    for are the ones whose sides converge. The pair is the longest two side
    lines whose join stays inside the lot; a lot offering no such pair is not
    measured.
    """
    import shapely
    from shapely.geometry import LineString

    if geom is None or geom.is_empty:
        return None
    sides = sorted(
        (e for e in edges if len(e) > 4 and e[4] == "S"), key=_length, reverse=True
    )
    if len(sides) < 2:
        return None
    inside = geom.buffer(_INSIDE_TOL_FT)
    longest = _length(sides[0])
    best = None
    # Only the principal sides are candidates, and among those the longest pair
    # that actually faces each other. Pairs are few -- a lot with more than a
    # handful of side lines is tier C and never reaches here.
    principal = [e for e in sides[:6] if _length(e) >= _PRINCIPAL_RATIO * longest]
    for i in range(len(principal)):
        for j in range(i + 1, len(principal)):
            a, b = _midpoint(principal[i]), _midpoint(principal[j])
            join = LineString([a, b])
            if join.length <= 0 or not shapely.covers(inside, join):
                continue
            weight = _length(principal[i]) + _length(principal[j])
            if best is None or weight > best[0]:
                best = (weight, join.length)
    return None if best is None else round(best[1], 2)


def center_parallel_width_ft(geom, front_bearings) -> float | None:
    """Tualatin: the distance between the side lot lines, measured parallel to
    the front lot line, at the center of the lot.

    The chord is thrown through the centre of the parcel along the street's
    bearing and clipped to it, and what is returned is the piece of it the
    centre stands on -- not the total clipped length, because on a lot that
    wraps around a neighbour the chord can re-enter further along and that
    second piece is somebody else's width.
    """
    import shapely
    from shapely.geometry import LineString, Point

    if geom is None or geom.is_empty or not front_bearings:
        return None
    # A corner lot measures something else entirely under this definition.
    if len(front_bearings) > 1:
        return None
    centre = geom.centroid
    if not geom.covers(centre):
        centre = geom.representative_point()
    x0, y0, x1, y1 = geom.bounds
    reach = _CHORD_REACH * max(math.hypot(x1 - x0, y1 - y0), 1.0)
    theta = math.radians(float(front_bearings[0]))
    dx, dy = math.cos(theta) * reach, math.sin(theta) * reach
    chord = LineString(
        [(centre.x - dx, centre.y - dy), (centre.x + dx, centre.y + dy)]
    )
    clipped = shapely.intersection(geom, chord)
    if clipped.is_empty:
        return None
    here = Point(centre.x, centre.y)
    on = [
        p for p in shapely.get_parts(clipped)
        if p.length > 0 and p.distance(here) <= _INSIDE_TOL_FT
    ]
    # Exactly one piece of the chord contains the centre, and that piece is the
    # width. The clipped chord's total length is not: on a lot that wraps a
    # neighbour it crosses the neighbour's ground and comes back, and the sum
    # of the two arms is a number no line on the parcel is that long.
    if len(on) != 1:
        return None
    return round(on[0].length, 2)


def midway_front_rear_width_ft(rg, fy) -> float | None:
    """Troutdale, Fairview, Wood Village, Multnomah unincorporated: the width
    at right angles to the depth axis, halfway between front and rear."""
    _, _, _, maxy = rg.bounds
    w = _row(rg, (fy + maxy) / 2.0)
    return None if w is None else round(w, 2)


def building_line_width_ft(rg, fy, setback_ft) -> float | None:
    """Milwaukie: the width at the building line, which is the front setback.

    Without a setback there is no building line, so the measurement is refused
    rather than quietly taken at the kerb -- the kerb is the line this whole
    module exists because the screen was using.
    """
    if setback_ft is None:
        return None
    w = _row(rg, fy + float(setback_ft))
    return None if w is None else round(w, 2)


def mean_width_ft(rg, fy) -> float | None:
    """Wilsonville: the mean horizontal distance between the side lot lines."""
    _, _, _, maxy = rg.bounds
    widths = [w for y in _samples(fy, maxy) if (w := _row(rg, y)) is not None]
    if not widths:
        return None
    return round(sum(widths) / len(widths), 2)


def setback_rectangle_width_ft(rg, fy, setback_ft) -> float | None:
    """Portland, single-dwelling zones: the widest rectangle that fits.

    33.930.100.A places a rectangle on the minimum front building setback line,
    40 ft deep or to the rear property line, whichever is less, and requires it
    to fit entirely within the lot. So the answer is not a distance across the
    parcel but the largest width that clears -- which is what a zone's minimum
    lot width is being compared against, and is never larger than the chord at
    the setback line would be.

    The band is sampled and the x-intervals intersected across the samples,
    which is the same thing as asking where the rectangle could stand.
    """
    if setback_ft is None:
        return None
    _, _, _, maxy = rg.bounds
    y0 = fy + float(setback_ft)
    if y0 > maxy - _EPS:
        return None
    y1 = min(y0 + _PORTLAND_RECT_DEPTH_FT, maxy)
    common: list[tuple[float, float]] | None = None
    for y in _samples(y0, y1):
        rows = _row_intervals(rg, y)
        if not rows:
            return None
        if common is None:
            common = rows
            continue
        merged = []
        for a, b in common:
            for c, d in rows:
                lo, hi = max(a, c), min(b, d)
                if hi - lo > _EPS:
                    merged.append((lo, hi))
        if not merged:
            return None
        common = merged
    if not common:
        return None
    return round(max(b - a for a, b in common), 2)


# --- depth forms -------------------------------------------------------------


#: How far off parallel a lot line can be and still be "the opposite" one. A
#: rear lot line faces the front; a side lot line does not, and on a corner lot
#: the difference is the whole measurement.
_OPPOSITE_TOL_DEG = 30.0


def midpoints_depth_ft(edges, frame: _Frame) -> float | None:
    """Oregon City, Gresham, Happy Valley, Portland: mid-point of the front lot
    line to mid-point of the rear lot line.

    The rear lot line is taken from the edges classified ``R``, but only those
    that are *opposite this front* -- beyond it, and within 30 degrees of
    parallel to it. A corner lot has two candidate fronts and one rear edge,
    and that edge is the rear of only one of them; measuring to it from the
    other is a diagonal across the parcel, which is longer than either
    dimension and would pass a depth standard on a lot that fails it.

    Where no rear edge qualifies the measurement is refused rather than
    substituted with the far boundary, because "the opposite, usually the rear,
    lot line" names a line, and a lot whose classification does not offer one
    is not a lot this module may second-guess.
    """
    rears = [e for e in edges if len(e) > 4 and e[4] == "R" and _length(e) > _EPS]
    if not rears:
        return None
    opposite = []
    for e in _in_frame(rears, frame):
        run = math.hypot(e[2] - e[0], e[3] - e[1])
        if run <= _EPS:
            continue
        tilt = abs(math.degrees(math.atan2(e[3] - e[1], e[2] - e[0]))) % 180.0
        if min(tilt, 180.0 - tilt) > _OPPOSITE_TOL_DEG:
            continue
        if (e[1] + e[3]) / 2.0 <= frame.fy + _INSIDE_TOL_FT:
            continue
        opposite.append((run, (e[0] + e[2]) / 2.0, (e[1] + e[3]) / 2.0))
    if not opposite:
        return None
    total = sum(r for r, _, _ in opposite)
    rx = sum(r * mx for r, mx, _ in opposite) / total
    ry = sum(r * my for r, _, my in opposite) / total
    return round(math.hypot(rx - (frame.fx0 + frame.fx1) / 2.0, ry - frame.fy), 2)


def average_depth_ft(rg, fy, fx0, fx1) -> float | None:
    """Milwaukie, West Linn, Wilsonville, Fairview, Wood Village: the average
    horizontal distance between the front lot line and the rear lot line.

    Averaged across the run of the front lot line, which is what "between the
    front lot line and the rear lot line" is a distance from. Columns where the
    lot does not stand on the front line are skipped, not counted as zero.
    """
    depths = [d for x in _samples(fx0, fx1) if (d := _column(rg, x, fy)) is not None]
    if not depths:
        return None
    return round(sum(depths) / len(depths), 2)


def mid_width_depth_ft(rg, fy, fx0, fx1) -> float | None:
    """Troutdale: the depth taken up the middle of the lot."""
    d = _column(rg, (fx0 + fx1) / 2.0, fy)
    return None if d is None else round(d, 2)


# --- the two axes, put together ----------------------------------------------


def orientations(
    geom,
    edges,
    front_bearings,
    tier: str,
    *,
    width_measure: str | None = None,
    depth_measure: str | None = None,
    front_setback_ft: float | None = None,
) -> tuple[Orientation, ...]:
    """Every front this lot could be built to face, and what it measures facing it.

    Returns an empty tuple where nothing could be measured -- an unmeasured lot,
    not a failing one.
    """
    if geom is None or geom.is_empty or tier not in MEASURABLE_TIERS:
        return ()
    if width_measure is not None and width_measure not in WIDTH_MEASURES:
        raise ValueError(f"unknown lot width measure: {width_measure!r}")
    if depth_measure is not None and depth_measure not in DEPTH_MEASURES:
        raise ValueError(f"unknown lot depth measure: {depth_measure!r}")
    if width_measure is None and depth_measure is None:
        return ()

    out: list[Orientation] = []
    for bearing, members in front_groups(edges):
        f = _frame(geom, members, bearing)
        if f is None:
            continue
        w = d = None
        if width_measure == "side_midpoints":
            w = side_midpoints_width_ft(geom, edges)
        elif width_measure == "center_parallel":
            w = center_parallel_width_ft(geom, front_bearings)
        elif width_measure == "midway_front_rear":
            w = midway_front_rear_width_ft(f.rg, f.fy)
        elif width_measure == "building_line":
            w = building_line_width_ft(f.rg, f.fy, front_setback_ft)
        elif width_measure == "mean_width":
            w = mean_width_ft(f.rg, f.fy)
        elif width_measure == "setback_rectangle":
            w = setback_rectangle_width_ft(f.rg, f.fy, front_setback_ft)

        if depth_measure == "midpoints":
            d = midpoints_depth_ft(edges, f)
        elif depth_measure == "average":
            d = average_depth_ft(f.rg, f.fy, f.fx0, f.fx1)
        elif depth_measure == "mid_width":
            d = mid_width_depth_ft(f.rg, f.fy, f.fx0, f.fx1)

        if w is None and d is None:
            continue
        out.append(
            Orientation(
                bearing=round(bearing, 2),
                front_ft=round(sum(_length(e) for e in members), 2),
                width_ft=w,
                depth_ft=d,
            )
        )
    return tuple(out)


def pick(
    orients: tuple[Orientation, ...],
    front_rule: str | None,
    *,
    min_width_ft: float | None = None,
    min_depth_ft: float | None = None,
) -> Orientation | None:
    """The one orientation this lot is judged on.

    Where the city states no rule, ``None``, the measurement is taken only on a
    lot with a single street-facing direction -- where the question does not
    arise. A corner lot is refused rather than assigned a front by this module,
    because on a corner lot the choice of front is the difference between a
    depth of 40 ft and a depth of 100 ft and nobody here is entitled to make it.

    Under ``narrowest`` the city has already chosen and the standards have no
    say: the front is the shortest street-facing run, and whatever it measures
    is the answer.

    Under ``applicant_choice`` the applicant chooses, so the lot conforms if
    **one** front satisfies **both** standards -- and that is why the standards
    are arguments here rather than something applied afterwards to a pair of
    scalars. Taking the widest orientation and the deepest orientation
    separately would pass a lot that is wide facing north and deep facing east
    and conforming facing neither. Where no orientation satisfies both, the one
    that comes closest is returned, so the reported numbers are a pair the lot
    actually has rather than two numbers from two different buildings.
    """
    if not orients:
        return None
    if front_rule is None:
        return orients[0] if len(orients) == 1 else None
    if front_rule not in FRONT_RULES:
        raise ValueError(f"unknown front lot line rule: {front_rule!r}")
    if front_rule == "narrowest":
        return min(orients, key=lambda o: (o.front_ft, o.bearing))

    def _slack(o: Orientation) -> float:
        ratios = []
        if min_width_ft:
            ratios.append(
                -1.0 if o.width_ft is None else o.width_ft / float(min_width_ft)
            )
        if min_depth_ft:
            ratios.append(
                -1.0 if o.depth_ft is None else o.depth_ft / float(min_depth_ft)
            )
        # No standard to rank against: fall back to the most generous pair, so
        # a reported number is still one building's.
        if not ratios:
            return (o.width_ft or 0.0) + (o.depth_ft or 0.0)
        return min(ratios)

    return max(orients, key=lambda o: (_slack(o), o.width_ft or 0.0))


def dimensions(
    geom,
    edges,
    front_bearings,
    tier: str,
    *,
    width_measure: str | None = None,
    depth_measure: str | None = None,
    front_rule: str | None = None,
    front_setback_ft: float | None = None,
    min_width_ft: float | None = None,
    min_depth_ft: float | None = None,
) -> Orientation | None:
    """This lot's width and depth, as the city that asks for them defines them.

    ``None`` is "not measured", which is a lot held for review, and is the
    answer wherever the shape declines, the city states no definition, or the
    tier is one this screen does not trust to carry the phrase "side lot line".
    """
    return pick(
        orientations(
            geom, edges, front_bearings, tier,
            width_measure=width_measure,
            depth_measure=depth_measure,
            front_setback_ft=front_setback_ft,
        ),
        front_rule,
        min_width_ft=min_width_ft,
        min_depth_ft=min_depth_ft,
    )


def width_ft(measure: str | None, geom, edges, front_bearings, tier: str):
    """The lot's width under one city's definition, or ``None`` if unmeasured.

    Kept at its original signature because s4 and s7 both call it per lot and
    neither has a setback or a standard to hand at that point. The two forms
    that need one -- Milwaukie's building line and Portland's rectangle -- are
    refused here and taken through :func:`dimensions` instead.
    """
    if not measure or tier not in MEASURABLE_TIERS:
        return None
    if measure not in WIDTH_MEASURES:
        raise ValueError(f"unknown lot width measure: {measure!r}")
    if measure == "side_midpoints":
        return side_midpoints_width_ft(geom, edges)
    if measure == "center_parallel":
        return center_parallel_width_ft(geom, front_bearings)
    o = dimensions(
        geom, edges, front_bearings, tier,
        width_measure=measure, front_rule="narrowest",
    )
    return None if o is None else o.width_ft
