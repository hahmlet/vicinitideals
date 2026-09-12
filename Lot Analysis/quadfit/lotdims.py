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
    16.12, Portland 33.930.100.B (every zone but the single-dwelling ones),
    and the second of West Linn's two width rows.

    On a corner lot the "side lot lines" are read from the chosen front --
    the longer street edge becomes a side, as Happy Valley's glossary says
    outright -- rather than from s4's ``S`` class, which on a corner lot is
    empty. Until 2026-09-11 that emptiness was refusing every corner lot in
    Oregon City, 2,724 of them, for want of a line the city had already named.

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

    Gresham too, and it is worth saying why, because Gresham's glossary reads
    like ``side_midpoints``: 3.0100 defines *Lot Width* as "the perpendicular
    distance measured between the mid-points of the two principal opposite
    side lot lines". But every table that states the standard -- 4.0130 E,
    4.1130 and Springwater's 4.1508 D -- heads the row **"Width at building
    line"**, and 3.0100 defines *Building Line* as "a line parallel to the
    front lot line and passing through the most forward point or plane of a
    building". The table is the more specific statement about where THIS
    standard is taken, so it governs; on a vacant lot the most forward legal
    building line is the front setback, which is the same line Milwaukie
    measures at. The two forms agree on a rectangle and differ on a wedge,
    where the table's line sits nearer the street and is the stricter of the
    two -- the conservative direction.

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

One zone is not served either. Tualatin's RML table (TDC 41.220) heads its
row "Minimum AVERAGE lot width", and 31.060 defines that as "the sum of the
length of the front lot line and the rear lot line divided by 2" -- a seventh
form, on two lines neither ``center_parallel`` nor anything else here draws.
RML has no mapped lots, so no form was built for it; its standard is left
unset in rules.yaml with the reason beside it.

Checked against a second implementation
---------------------------------------

Run on 2026-09-11 over the 6,931 Milwaukie parcels in ``s4_lots.parquet``,
against ``/root/milw_dims.py`` on LXC 137 -- an implementation of the same two
MMC 19.200 sentences, written the day before this module existed and sharing no
code with it.

``building_line`` **width agreed on 4,178 of 4,212 single-front parcels within
1 ft, median 0.03 ft.** Two readings of one sentence, arriving at the same line.

``average`` depth agreed to a median of **0.004 ft on 3,132 parcels** and then
parted company on 1,080, and the disagreement is worth more than the agreement
because it found a bug -- in the other one, twice:

* **971 parcels, this module reading higher by ~1/41 of the depth.** The other
  implementation samples 41 columns across the front lot line and counts the
  degenerate one at the far corner -- where the cut touches a single point --
  as a *zero-depth* sample. One zero in a mean of forty-one: 199.98 ft against
  195.11, 202.82 against 197.88. :func:`_column` returns ``None`` there
  instead, which is why. Pinned by
  ``test_a_lot_line_a_thousandth_of_a_foot_out_of_square_is_still_100_ft_deep``.
* **A rounded frame, worth 2.387 ft of median error.** The other implementation
  buckets street-facing edges to 5 degrees and then rotates the lot by the
  *bucket*, up to 2.50 degrees off the real bearing. Re-run on the true bearing
  its median disagreement with this module fell from 2.387 ft to 0.004 ft,
  which is what identifies the frame as the cause rather than the arithmetic.

The 109 still apart by over 5 ft are flag lots and parcels whose body is not
attached to their own frontage, where this module measures only the piece
standing on the front lot line and the other measures to the far side of the
parcel. That is the conservative direction and it is deliberate.

On Milwaukie's own standards the two methods do not deliver the same verdict:
291 R-MD parcels fail ``min_lot_depth_ft`` here against the reference's 411,
and 264 of the 291 fail facing *every* street they touch.
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

#: How far off parallel a lot line can be and still be "the opposite" one. A
#: rear lot line faces the front; a side lot line does not, and on a corner lot
#: the difference is the whole measurement. The same 30 degrees s4 uses to
#: class an edge ``R``, so a lot with one street reads the same here as there.
_OPPOSITE_TOL_DEG = 30.0

#: Street-facing lot line shorter than this, sitting between two other
#: street-facing runs that turn a corner between them, is the clipped corner
#: of a corner lot -- the chamfer or the surveyed arc where two rights-of-way
#: meet -- and not a front lot line. Fairview 19.165 asks a corner radius of
#: "not less than 20 feet" at an arterial and Wilsonville 4.237 "not less
#: than ten feet" anywhere; a 25 ft radius quarter-circle is 39 ft of lot
#: line, so the cap sits above it and under the narrowest real front any
#: city here allows (Portland R5 asks 36 ft of width). Gresham measures its
#: street frontage "from the corner radius end point to the property corner"
#: (4.0130 note 10), which is the same reading.
_CLIP_MAX_FT = 45.0

#: The narrowest lot any city here has on the ground: Portland's 25 ft
#: plats. A street-facing run at least this long may be a front; nothing
#: shorter is one on its own.
_NARROWEST_FRONT_FT = 25.0

#: Where the street ends inside the chain -- the lot's second street lies
#: past the 50 ft the edge classifier looks, so the arc has a street-facing
#: run on one side only -- nothing local tells a 33 ft chord from the 33 ft
#: front of a narrow corner lot with a street down its side, and a single
#: chord that long is left. Under this it is dropped: a 12.7 ft radius is
#: 20 ft of quarter-circle, and it sits under :data:`_NARROWEST_FRONT_FT`.
_END_CLIP_MAX_FT = 20.0

#: Two street-facing runs meet on a curve rather than at a corner when the
#: turn between them is gentle and the arc it implies is wide: radius = chord
#: / (2 sin(turn / 2)), on the shorter of the two edges meeting there, which
#: for chords surveyed on a circle is the circle's radius. Corner arcs are
#: surveyed at 10 to 25 ft radii (the two citations above); the lot line
#: around a cul-de-sac bulb is 38 to 55 ft (a West Linn bulb lot read at 38
#: to 50 across its four chords); a curving street is wider still. Measured
#: on every pair of adjacent street-facing edges in both counties on
#: 2026-09-12: joints turning 5 to 12 degrees imply a median radius of 130
#: to 280 ft, joints turning 20 to 45 degrees imply 14 to 31.
_CURVE_MIN_RADIUS_FT = 30.0

#: How far, end to end, one curved front lot line may turn before it is two.
#: A corner is 90. Summed joint by joint, not read off the two end bearings:
#: bearings here are modulo 180 and a difference between two of them is at
#: most 90, so a front wrapped 128 degrees round a lot read as 52 and passed.
#: Two West Linn lots on the outside of a hairpin had their whole street
#: line, seven and eight chords, joined into one 190 and 217 ft "front" that
#: way, and lost both their width and their depth to it.
_CURVE_MAX_SWEEP_DEG = 75.0

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

    A run is built in two steps. Pieces within :data:`_FRONT_BUCKET_DEG` of
    each other are one run outright. Then two runs that meet on a curve --
    turning no more than :data:`_OPPOSITE_TOL_DEG`, on an arc at least
    :data:`_CURVE_MIN_RADIUS_FT` wide, and not sweeping more than
    :data:`_CURVE_MAX_SWEEP_DEG` end to end once joined -- are joined too. A
    Fairview lot on a bend surveyed as five chords eleven to thirteen degrees
    apart is one front under that and five under the bucket alone; the bucket
    alone gave it a 13 ft front and a 20 ft depth on a 73,000 sq ft parcel.
    The radius is what keeps the corner out of it: a corner arc is drawn at
    ten to twenty-five feet, a bend in a street at a hundred or more.

    A corner, by contrast, turns through something near a right angle in one
    step, which breaks the run and gives the two fronts a corner lot has.

    And the corner itself is not a third one. Where two streets meet the lot
    line is usually clipped -- a chamfer, or an arc surveyed as a few short
    chords -- and each piece of that clip is a street-facing run in its own
    right, turning too sharply to join either neighbour. Under "the front lot
    line is the shortest lot line abutting a street" a ten-foot chamfer won
    against both streets on 3,995 lots the day the rule went live, and the
    whole parcel was then measured square to a line nobody would build to.
    So a chain of short runs between two street-facing runs that turn a
    corner between them is dropped from the candidates. Its length still
    counts in s4's frontage sum; it is only not a front. The two runs that
    bound the chain are the nearest on each side that are a street line in
    their own right: not short (:data:`_CLIP_MAX_FT`), or the run the
    street ends on when that is long enough to be a front by itself
    (:data:`_NARROWEST_FRONT_FT`), so a 35 ft front on a narrow corner lot
    bounds the arc beside it rather than being swallowed into it, while the
    22 ft second chord of a bent front does not, and stays in the chain
    with the first. Between two long runs the chain is
    the corner whatever its radius (Gresham 4.0130 note 10 measures frontage
    "from the corner radius end point"); between a long run and a short
    street, it is a clip only if it is short all told and not smooth at
    every joint, because a chain that is smooth from end to end and ends at
    a side lot line is the frontage of a lot on a cul-de-sac bulb, and that
    is a front.

    A corner arc at the end of the street -- a Portland lot with an 86 ft
    front, a 13 ft chord turning fifty degrees, then the side lot line,
    because its second street lies past the 50 ft the edge classifier looks
    -- has a bounding run on one side only, and nothing local tells a 33 ft
    chord there from the 33 ft front of a narrow corner lot with a street
    down its side. So off the end of a run that could be a front
    (:data:`_NARROWEST_FRONT_FT`) a chain that turns away and is not smooth
    is dropped when it is under :data:`_END_CLIP_MAX_FT` all told; or, up to
    :data:`_CLIP_MAX_FT`, when it is two or more chords on a circle tighter
    than any street bend (:data:`_CURVE_MIN_RADIUS_FT`), turning the same
    way at every joint and meeting the side lot line at a tangent as a
    corner arc does and a second street never does -- a Wilsonville lot
    read its 79 ft front as 7 ft on the 7 and 19 ft chords of a 24 ft
    radius. A 25 ft front, one chord, is never in reach of either.

    Nor is the last 50 ft of a side lot line a front. The edge classifier
    marks a lot line street-facing for lying within reach of a street, and
    the end of a side lot line where it meets the street qualifies; what
    gives it away is that it continues straight into a lot line that is not
    street-facing, and turns a corner into one that is. A Portland lot with
    a 62 ft front read its 30 ft of side line as the front and measured 200
    ft of width across it. Such an edge is dropped before the runs are
    built, unless the lot has no other street-facing edge.

    Clips are taken before the curves are joined, because the joint where a
    straight street meets its own corner arc turns half a chord's step and
    reads as an arc twice as wide as the corner really is; and taken again
    after, because a front surveyed as four chords of 12 ft is short in
    every piece and long as a run, and the corner beside it is only a clip
    once the run is one thing. The two passes alternate until nothing moves.
    The turn matters too: a 20 ft by 766 ft strip in Oregon City with a
    street along both long sides has a 20 ft end between two street-facing
    runs, and that end is its front, not a clip. Where every run on the lot
    would go that way nothing is dropped, because a lot has to have a front
    and a sliver made of clips is a shape for tier C, not for this.
    """
    n = len(edges)
    is_front = [
        bool(len(e) > 4 and e[4] == "F" and _length(e) > _EPS) for e in edges
    ]
    if not any(is_front):
        return []
    # The last 50 ft of a side lot line: straight on from a lot line that is
    # not street-facing, and turning a corner into one that is.
    tails = [
        i for i in range(n) if is_front[i] and any(
            not is_front[nb]
            and _length(edges[nb]) > _EPS
            and abs(_offset(_bearing(edges[nb]), _bearing(edges[i]))) <= _FRONT_BUCKET_DEG
            and is_front[other]
            and abs(_offset(_bearing(edges[other]), _bearing(edges[i]))) > _OPPOSITE_TOL_DEG
            for nb, other in (((i - 1) % n, (i + 1) % n), ((i + 1) % n, (i - 1) % n))
        )
    ]
    if len(tails) < sum(is_front):
        for i in tails:
            is_front[i] = False
    runs: list[list[int]] = []
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
            runs[-1].append(i)
        else:
            runs.append([i])
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

    def _run_len(idx: list[int]) -> float:
        return sum(_length(edges[i]) for i in idx)

    def _contiguous(a: list[int], b: list[int]) -> bool:
        return b[0] == (a[-1] + 1) % n

    def _on_a_curve(a: list[int], b: list[int]) -> bool:
        """Runs ``a`` then ``b``, consecutive on the ring, meet on a curve."""
        ea, eb = edges[a[-1]], edges[b[0]]
        turn = abs(_offset(_bearing(eb), _bearing(ea)))
        if turn > _OPPOSITE_TOL_DEG:
            return False
        radius = min(_length(ea), _length(eb)) / (2.0 * math.sin(math.radians(turn) / 2.0))
        if radius < _CURVE_MIN_RADIUS_FT:
            return False
        joined = a + b
        sweep = abs(sum(
            _offset(_bearing(edges[j]), _bearing(edges[i]))
            for i, j in zip(joined, joined[1:])
        ))
        return sweep <= _CURVE_MAX_SWEEP_DEG

    def _bounding(k: int, step: int) -> int | None:
        """The nearest run from ``runs[k]`` in direction ``step`` that is a
        street line a clip can hang from: one that is not short, or the run
        the street ends on when that is long enough to be a front by itself.
        None if the street ends at ``runs[k]``, or on something shorter."""
        j = k
        while True:
            j2 = (j + step) % len(runs)
            a, b = (runs[j], runs[j2]) if step > 0 else (runs[j2], runs[j])
            if j2 == k or not _contiguous(a, b):
                return None if j == k or _run_len(runs[j]) < _NARROWEST_FRONT_FT else j
            j = j2
            if _run_len(runs[j]) >= _CLIP_MAX_FT:
                return j

    def _tight_arc(path: list[int], step: int) -> bool:
        """``path`` is an anchor run and the chain off its end, in ring
        order. True when the chain is chords of a corner arc: turning the
        same way at every joint from the anchor on, on a circle under
        _CURVE_MIN_RADIUS_FT at every joint inside the chain (the anchor's
        own joint is left out, because a straight line meeting its arc turns
        half a chord's step and reads twice as wide), and meeting whatever
        lot line follows at a tangent."""
        joints = [(edges[runs[x][-1]], edges[runs[y][0]]) for x, y in zip(path, path[1:])]
        turns = [_offset(_bearing(eb), _bearing(ea)) for ea, eb in joints]
        if len({t > 0 for t in turns}) > 1 or any(abs(t) < _EPS for t in turns):
            return False
        anchor_joint = 0 if step > 0 else len(joints) - 1
        for q, ((ea, eb), t) in enumerate(zip(joints, turns)):
            if q == anchor_joint:
                continue
            radius = min(_length(ea), _length(eb)) / (2.0 * math.sin(math.radians(abs(t)) / 2.0))
            if radius >= _CURVE_MIN_RADIUS_FT:
                return False
        fi = runs[path[-1]][-1] if step > 0 else runs[path[0]][0]
        beyond = edges[(fi + step) % n]
        return abs(_offset(_bearing(beyond), _bearing(edges[fi]))) <= _OPPOSITE_TOL_DEG

    def _is_clip(k: int) -> bool:
        if _run_len(runs[k]) >= _CLIP_MAX_FT:
            return False
        before, after = _bounding(k, -1), _bounding(k, +1)
        if before == after:
            return False
        if before is not None and after is not None:
            chain, j = [], (before + 1) % len(runs)
            while j != after:
                chain.append(j)
                j = (j + 1) % len(runs)
            # Two streets meeting turn a corner. Two street-facing runs that
            # are parallel to each other are the long sides of a strip with a
            # street on three sides, and the short end between them is its
            # front.
            turn = abs(_offset(_mean_bearing(runs[after]), _mean_bearing(runs[before])))
            if turn <= _OPPOSITE_TOL_DEG:
                return False
            if _run_len(runs[before]) >= _CLIP_MAX_FT and _run_len(runs[after]) >= _CLIP_MAX_FT:
                return True
            if sum(_run_len(runs[j]) for j in chain) >= _CLIP_MAX_FT:
                return False
            # A chain that is smooth at every joint and reaches the end of
            # the street is a bend in one street, not the corner of two: the
            # lot line round a cul-de-sac bulb.
            path = [before, *chain, after]
            return not all(_on_a_curve(runs[x], runs[y]) for x, y in zip(path, path[1:]))
        # The street ends inside the chain. Off the end of a run that could
        # be a front, a chain that turns away from it and is not smooth
        # where it does is the corner arc of a lot whose second street was
        # not found: outright when it is shorter than any front, and up to
        # the clip cap when it is chords of a tight arc that runs tangent
        # into the side lot line.
        anchor, step = (before, +1) if before is not None else (after, -1)
        if _run_len(runs[anchor]) < _NARROWEST_FRONT_FT:
            return False
        chain, j = [], anchor
        while True:
            j2 = (j + step) % len(runs)
            a, b = (runs[j], runs[j2]) if step > 0 else (runs[j2], runs[j])
            if j2 == anchor or not _contiguous(a, b):
                break
            chain.append(j2)
            j = j2
        total = sum(_run_len(runs[j]) for j in chain)
        if total >= _CLIP_MAX_FT:
            return False
        turn = abs(_offset(
            _mean_bearing([i for j in chain for i in runs[j]]), _mean_bearing(runs[anchor])
        ))
        if turn <= _OPPOSITE_TOL_DEG:
            return False
        path = [anchor, *chain] if step > 0 else [*reversed(chain), anchor]
        if all(_on_a_curve(runs[x], runs[y]) for x, y in zip(path, path[1:])):
            return False
        if total < _END_CLIP_MAX_FT:
            return True
        return len(chain) >= 2 and _tight_arc(path, step)

    def _mean_bearing(idx: list[int]) -> float:
        members = [edges[i] for i in idx]
        total = sum(_length(e) for e in members)
        base = _bearing(members[0])
        return (base + sum(_length(e) * _offset(_bearing(e), base) for e in members) / total) % 180.0

    # Clips out, then curves joined, and again until nothing moves: the
    # joint where a straight street meets its corner arc turns only half a
    # chord's step and reads as an arc twice as wide as the corner really
    # is, so the clips go first; and a run that is short in every piece is
    # long once joined, and only then bounds the corner beside it.
    moved = True
    while moved:
        moved = False
        kept = [runs[k] for k in range(len(runs)) if not _is_clip(k)]
        if kept and len(kept) < len(runs):
            runs = kept
            moved = True
        joined_one = True
        while joined_one and len(runs) > 1:
            joined_one = False
            for k in range(len(runs)):
                a, b = runs[k], runs[(k + 1) % len(runs)]
                if a is b or not _contiguous(a, b) or not _on_a_curve(a, b):
                    continue
                if k + 1 < len(runs):
                    runs[k] = a + b
                    del runs[k + 1]
                else:
                    runs[0] = a + b
                    del runs[k]
                joined_one = moved = True
                break

    groups = [(_mean_bearing(idx), [edges[i] for i in idx]) for idx in runs]
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
    #: How far the front lot line itself stands above ``fy`` at its highest.
    #: Zero for a straight front. A front that is a chain of chords -- a
    #: curve, or a street that wobbles a degree or two between survey pins --
    #: is put on its mean line, and its chords sit a few feet either side of
    #: it. A column of the lot "stands on the front lot line" as far up as the
    #: front lot line itself goes.
    rise: float = 0.0


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
            rise = max(c[1] for p in rf.geoms for c in p.coords) - fy
            return _Frame(rg, fy, min(xs), max(xs), origin, angle, max(rise, 0.0))
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


def _column(rg, x, fy, rise: float = 0.0) -> float | None:
    """How deep the lot runs at ``x``, measured back from the front lot line.

    The piece taken is the one standing on the front line. A lot with a body
    detached from its frontage in this column has no depth here, and returns
    ``None`` so the sample is skipped rather than counted as zero.

    ``rise`` is how far the front lot line stands above its own mean line
    (:attr:`_Frame.rise`). A front surveyed as three chords that wobble two
    degrees between pins is put on one line, and at the middle of the lot
    that line can pass a few feet *below* the chord that is there, so the
    lot in that column starts above the line and, on a half-foot tolerance,
    stood on nothing. Troutdale's depth is one column up the middle, and 288
    of its lots lost their depth that way the day fronts were joined. The
    depth is still taken from the mean line; only the test of what stands on
    it reaches as high as the front itself does.
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
        if lo <= fy + rise + _INSIDE_TOL_FT <= hi:
            return hi - fy
    return None


def _samples(lo: float, hi: float) -> list[float]:
    if hi - lo <= _EPS:
        return [lo]
    step = (hi - lo) / (_SAMPLES - 1)
    return [lo + i * step for i in range(_SAMPLES)]


# --- width forms -------------------------------------------------------------


def _sides_facing(edges, members, frame: _Frame) -> list:
    """The side lot lines of a lot seen from one front.

    s4 classes an edge ``S`` only when it is off-parallel to EVERY street the
    lot touches, so a corner lot -- two streets at right angles, every other
    edge parallel to one of them -- has no ``S`` edges at all, and the
    midpoints form was refusing every corner lot in the city. But once a
    front is chosen the city has already said which edges are the sides:
    Happy Valley's glossary puts it flatly, "on a corner lot, the longer lot
    line that abuts a street is a side lot line", and Oregon City's and
    Portland's side lot line is any line that is neither front nor rear. So
    from a given front, a side is any edge that is not that front and not
    opposite it -- the same 30-degree test s4 uses for ``R``, taken in this
    front's frame rather than against every street at once. On a lot with one
    street the two readings are the same set of edges.
    """
    chosen = {tuple(e[:4]) for e in members}
    out = []
    for raw, e in zip(edges, _in_frame(edges, frame)):
        if tuple(raw[:4]) in chosen or _length(raw) <= _EPS:
            continue
        tilt = abs(math.degrees(math.atan2(e[3] - e[1], e[2] - e[0]))) % 180.0
        if min(tilt, 180.0 - tilt) <= _OPPOSITE_TOL_DEG:
            continue
        out.append(raw)
    return out


def side_midpoints_width_ft(geom, edges, front=None) -> float | None:
    """Oregon City: the distance between the midpoints of the two principal
    opposite side lot lines.

    "Principal" is read as the longest, and "opposite" as facing each other
    across the parcel rather than as parallel -- the lots this measurement is
    for are the ones whose sides converge. The pair is the longest two side
    lines whose join stays inside the lot; a lot offering no such pair is not
    measured.

    ``front`` is ``(members, frame)`` for the front lot line the lot is being
    judged from. With it, the side lot lines are read relative to that front
    (:func:`_sides_facing`), which is what lets a corner lot be measured;
    without it, they are the edges s4 classed ``S``, which on a corner lot is
    none.
    """
    import shapely
    from shapely.geometry import LineString

    if geom is None or geom.is_empty:
        return None
    if front is None:
        candidates = [e for e in edges if len(e) > 4 and e[4] == "S"]
    else:
        candidates = _sides_facing(edges, front[0], front[1])
    sides = sorted(candidates, key=_length, reverse=True)
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


def midpoints_depth_ft(edges, frame: _Frame, front=None) -> float | None:
    """Oregon City, Gresham, Happy Valley, Portland: mid-point of the front lot
    line to mid-point of the rear lot line.

    The rear lot line is whichever lot line is *opposite this front* -- beyond
    it, within 30 degrees of parallel to it, and not the front itself. That is
    the definition in every city that has one: Portland 33.910 "a lot line
    that is opposite a front lot line", Gresham 3.0100 and Oregon City
    17.04.1000 "opposite to and more distant from the front lot line". It is
    a property of the pair, front and rear, and not a label on the edge.

    Until 2026-09-11 it was read from s4's ``R`` class instead, which is the
    same set of edges on a lot with one street and a different one on every
    lot with two: s4 classes against every street the parcel touches, so on a
    corner lot the line opposite the side street is ``R`` and the line
    opposite the front is ``F`` if a second street or an alley runs behind
    it, or simply if the parcel is narrow enough for its rear line to sit
    within the street threshold of the side street -- and 8,505 corner lots
    had no depth at all. The one thing the label was guarding against -- the
    diagonal, measured from a front to the rear of the *other* front -- is
    what the parallel test refuses, so it is the parallel test that stays.
    ``front`` is the chosen front's members and is never its own rear.

    "Opposite" also means on the far side. A frontage that curves is a run
    of short street-facing lines each turning a few degrees from the last,
    and every one of them but the chosen run is parallel enough to pass the
    30-degree test and sits a foot or two beyond the chosen run's line.
    Averaged in with the true rear they dragged the "rear midpoint" up to the
    street on 13,904 lots the first time this ran without the ``R`` label,
    and a 239 ft lot came out 1.78 ft deep. So a candidate has to lie in the
    far half of the lot as seen from this front -- beyond the midline between
    the front lot line and the lot's furthest extent -- which is where a rear
    lot line is and where a bend in the front is not. The same test retires
    a jog in a side line near the street that the ``R`` label used to admit
    (a West Linn lot read 0.91 ft deep through one of those).

    Where no edge qualifies the measurement is refused rather than
    substituted with the far boundary, because "the opposite, usually the
    rear, lot line" names a line and a lot with none is held for a person.
    """
    chosen = {tuple(e[:4]) for e in (front or ())}
    rears = [
        e for e in edges if tuple(e[:4]) not in chosen and _length(e) > _EPS
    ]
    if not rears:
        return None
    far_side = frame.fy + max(_INSIDE_TOL_FT, (frame.rg.bounds[3] - frame.fy) / 2.0)
    opposite = []
    for e in _in_frame(rears, frame):
        run = math.hypot(e[2] - e[0], e[3] - e[1])
        if run <= _EPS:
            continue
        tilt = abs(math.degrees(math.atan2(e[3] - e[1], e[2] - e[0]))) % 180.0
        if min(tilt, 180.0 - tilt) > _OPPOSITE_TOL_DEG:
            continue
        if (e[1] + e[3]) / 2.0 <= far_side:
            continue
        opposite.append((run, (e[0] + e[2]) / 2.0, (e[1] + e[3]) / 2.0))
    if not opposite:
        return None
    total = sum(r for r, _, _ in opposite)
    rx = sum(r * mx for r, mx, _ in opposite) / total
    ry = sum(r * my for r, _, my in opposite) / total
    return round(math.hypot(rx - (frame.fx0 + frame.fx1) / 2.0, ry - frame.fy), 2)


def average_depth_ft(rg, fy, fx0, fx1, rise: float = 0.0) -> float | None:
    """Milwaukie, West Linn, Wilsonville, Fairview, Wood Village: the average
    horizontal distance between the front lot line and the rear lot line.

    Averaged across the run of the front lot line, which is what "between the
    front lot line and the rear lot line" is a distance from. Columns where the
    lot does not stand on the front line are skipped, not counted as zero.
    """
    depths = [
        d for x in _samples(fx0, fx1) if (d := _column(rg, x, fy, rise)) is not None
    ]
    if not depths:
        return None
    return round(sum(depths) / len(depths), 2)


def mid_width_depth_ft(rg, fy, fx0, fx1, rise: float = 0.0) -> float | None:
    """Troutdale: the depth taken up the middle of the lot."""
    d = _column(rg, (fx0 + fx1) / 2.0, fy, rise)
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
            w = side_midpoints_width_ft(geom, edges, front=(members, f))
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
            d = midpoints_depth_ft(edges, f, members)
        elif depth_measure == "average":
            d = average_depth_ft(f.rg, f.fy, f.fx0, f.fx1, f.rise)
        elif depth_measure == "mid_width":
            d = mid_width_depth_ft(f.rg, f.fy, f.fx0, f.fx1, f.rise)

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

    A convenience for tests and one-off probes, no longer on the pipeline's
    path: s4 takes width and depth in one :func:`dimensions` call per lot,
    with the zone's setback and standards to hand, because the two have to be
    satisfied by one front and this signature cannot say which. The forms that
    need a setback -- Milwaukie's and Gresham's building line, Portland's
    rectangle -- are refused here for that reason, and a corner lot under
    ``side_midpoints`` is refused too, because with no front rule there is no
    front to read the sides from.
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
