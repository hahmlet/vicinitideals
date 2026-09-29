"""What a design needs from a lot, before any lot is looked at.

The screen answers "does this pod fit *here*". This answers the question that
comes before it: **what would a lot have to be** for this pod to be legal in
this zone at all. Nothing here touches parcel data — it is the design and the
zone's numbers, and it is arithmetic.

Two things make it worth its own module.

It is the design catalog's product surface. A pod is 80 ft wide or it is 56;
one of those clears a zone requiring 10 ft side setbacks on a 55 ft lot and one
does not, and that is decided by the rule set and the footprint alone. Laid out
per zone, this says which markets a design can play in before a single parcel
is screened — and, run across designs, which design opens the most zones.

And it is where the plat path stops being a decision buried in a rule file. A
four-unit attached building can be permitted as a quadplex on one lot or as
four townhouse lots, and cities state different standards for each. That is a
property of the *building* — of how it is being brought to market — so it lives
on the design, and the two paths are two designs producing two answers side by
side rather than one answer somebody had to choose.

What this deliberately does not do: decide GREEN or RED. A lot that clears
every number here can still fail on slope, sewer, access, or the site plan.
Paper fit is necessary, never sufficient — and every answer carries which of
the standards behind it a reviewer has actually signed, so a planning view
built on draft encoding is legible as one rather than mistaken for a verdict.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field as _dc_field
from typing import TYPE_CHECKING

from flats.designs.model import Design, Orientation, ParkingConfig, Plat

if TYPE_CHECKING:  # pragma: no cover - typing only
    from flats.rules.resolver import ZoneResolution

#: What sets the area floor. Named rather than inferred so the page can say
#: which standard is the one to argue with.
BY_MIN_LOT = "min_lot_sqft"
BY_COVERAGE = "max_coverage_pct"
BY_ENVELOPE = "envelope"

#: What sets the width, for the same reason. The building with the lane
#: beside it, the row of stalls behind it, or a lot-width standard above both.
ACROSS_BUILDING = "building"
ACROSS_COURT = "parking_court"
ACROSS_MIN_WIDTH = "min_lot_width_ft"


@dataclass(frozen=True, slots=True)
class PaperFit:
    """The smallest lot this design could be legal on in this zone."""

    design: str
    jurisdiction: str
    zone: str
    #: Frontage the envelope plus its side setbacks consumes. The envelope
    #: across is the footprint with the drive lane beside it, or the row of
    #: stalls behind it, whichever is wider; a lot-width standard can then
    #: raise the whole.
    min_width_ft: float | None = None
    #: Front lot line to rear: footprint, front setback, and whichever is
    #: deeper of the rear setback and the parking court behind the building.
    min_depth_ft: float | None = None
    #: What the parking asks of the lot behind the building — the standoff
    #: off the rear wall, a row of stalls and the aisle serving them, the
    #: design's own geometry raised by any figure the zone states. 0.0 where
    #: the design parks nowhere the lot has to give depth for.
    parking_depth_ft: float = 0.0
    #: What that row of stalls asks across the lot: the design's floor,
    #: raised to the zone's legal minimum and cut to its cap, each the
    #: design's stall width or the zone's if wider. 0.0 with no rear court.
    parking_width_ft: float = 0.0
    #: The drive lane beside the building that reaches the court, the design's
    #: figure raised by the zone's two-way driveway minimum. 0.0 with no court.
    lane_ft: float = 0.0
    #: How many stalls the court was drawn with, after the zone's floor and cap.
    stalls: int = 0
    #: Which of the three set ``min_width_ft`` in the reported orientation.
    width_binding: str = ""
    #: The binding area floor across every standard that states one.
    min_area_sqft: float | None = None
    #: Which standard set that floor.
    binding: str = ""
    #: None where the zone states no height standard we hold. False where it
    #: states one the design misses -- a ceiling it exceeds, or a floor it
    #: does not reach. A mixed-use district that writes a minimum is keeping a
    #: single-storey box off a main street, and that is a standard about this
    #: building, so the two bounds answer one question rather than two.
    height_ok: bool | None = None
    #: Which orientation these numbers are for — the less demanding one.
    orientation: str = ""
    #: Which plat path was costed. The same building on the same zone answers
    #: differently under the two, which is the point of asking.
    plat: str = ""
    #: Standards this calculation needed and cannot get for this plat path —
    #: either the zone does not state them, or it states them for the other
    #: path and the number on file is about a different thing. A number
    #: computed without one is a lower bound: the real requirement can only be
    #: larger.
    unknown: tuple[str, ...] = ()
    #: Standards used here that no reviewer has signed. Separate from
    #: ``unknown`` on purpose. A screening verdict may not rest on these — that
    #: is what the signature exists for — but a planning question ("which
    #: markets could this pod play in") is worth answering from the encoding we
    #: have, as long as the answer says what it rests on. Refusing to compute
    #: would not be caution; it would be a blank page describing a corpus of
    #: 650 encoded standards as though it held none.
    unsigned: tuple[str, ...] = ()
    #: Standards left out on purpose, with why. A street-side setback binds
    #: corner lots only, and applying it to every lot would overstate the
    #: frontage this design needs everywhere.
    excluded: tuple[str, ...] = _dc_field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        """Whether every standard this needs was there to read."""
        return not self.unknown

    @property
    def signed(self) -> bool:
        """Whether every standard behind this has been through review."""
        return not self.unsigned

    @property
    def certain(self) -> bool:
        """Complete and signed — the only state a decision may rest on."""
        return self.complete and self.signed

    @property
    def fits_height(self) -> bool:
        """False only where a height standard is held and the design misses it.

        Missing one is now two things, not one: over the ceiling, or under the
        floor. A zone stating no height standard at all still reads True here
        -- unasked is not the same as failed, and ``height_ok is None`` is
        where that distinction is kept.
        """
        return self.height_ok is not False


def _height_ok(
    design, ceiling: float | None, floor: float | None, storeys: float | None
) -> bool | None:
    """Whether the design clears every height standard the zone states.

    ``None`` where it states none of the three, which is not the same as
    passing: a zone with no height on file has not been asked the question.
    """
    bounds = [
        ceiling is None or design.height_ft <= ceiling,
        floor is None or design.height_ft >= floor,
        storeys is None or float(design.stories) >= storeys,
    ]
    if ceiling is None and floor is None and storeys is None:
        return None
    return all(bounds)


def _number(rules: "ZoneResolution", name: str) -> float | None:
    """A standard's number, or None where the zone does not state one."""
    got = rules.get(name)
    return float(got) if isinstance(got, (int, float)) else None


def _pair(side: float | None, total: float | None) -> float | None:
    """What both side yards take off the width, from whichever the code states.

    Neither stated is None -- an unknown requirement, not a free one. Both
    stated is the larger, because a combined minimum and a per-side floor are
    two standards and a lot has to meet both.
    """
    doubled = None if side is None else 2 * side
    if total is None:
        return doubled
    return total if doubled is None else max(total, doubled)


def lot_standard(
    rules: "ZoneResolution", name: str, *, per_unit: bool, lots: int
) -> tuple[float | None, bool]:
    """A lot standard for this plat path, and whether the encoding answers.

    ``min_lot_sqft`` is defined as the minimum lot area *for a fourplex*, so on
    the split path there are three things it could mean, and only one of them
    is right.

    It is not four of them. Multiplying a 7,000 sq ft minimum by four invents a
    28,000 sq ft requirement out of a standard that says nothing of the kind.

    It is not a per-child-lot number either, in Oregon. A middle housing land
    division is judged against the land use regulations "applicable to the
    original lot or parcel" (ORS 92.031(2)(b)), and a city may not add approval
    criteria of its own for the resulting lots (92.031(4)(c)). The parent lot
    meets the zone; the children inherit no standards to meet. So where a layer
    encodes ``land_division_parent_standards``, the split path reads the same
    number as the one-lot path — which is what the statute says, and why 76 of
    86 fourplex zones were reporting a hole that was never in the code.

    Where a jurisdiction is outside that regime, or states its own townhouse
    lot standards for a conventional subdivision, it encodes them by carrying
    the ``unit_lots`` condition on a variant, and those *are* per-lot: four of
    them side by side. Where neither is true this returns nothing and reports
    the standard as one we do not have, which is honest and is an encoding task.
    """
    got = rules.values.get(name)
    value = getattr(got, "value", None)
    if not isinstance(value, (int, float)):
        return None, True
    if not per_unit:
        return float(value), True
    if "unit_lots" in tuple(getattr(got, "when", ()) or ()):
        return float(value) * lots, True
    if rules.get("land_division_parent_standards") is True:
        return float(value), True
    return None, False


#: Parking configurations that put a row of stalls and its drive aisle behind
#: the building. ``tuck_under`` is inside the footprint and ``street_only``
#: provides none, so neither asks the lot for depth or width the footprint
#: does not already show. ``side_drive`` costs width and no depth; no catalog
#: design uses it, and charging it is a separate piece of work.
_COURT_CONFIGS = frozenset({ParkingConfig.rear_court})


@dataclass(frozen=True, slots=True)
class Alley:
    """An alley along the lot, as quadfit's s4 measured it, and which line it is.

    Handed to :func:`court_depth` and :func:`court_across` only for a lot
    with an alley edge (``alley_at_rear`` / ``alley_at_side``); the paper
    lot, which has no lot, never passes one.
    """

    #: The alley's width in feet -- s4's gap in the taxlot fabric from this
    #: lot to the first private lot across the alley, the narrowest where
    #: the lot has two. ``None`` where nothing is on record, which counts as
    #: no width at all: the strict reading, the one s6s draws.
    width_ft: float | None = None
    #: The alley runs along the rear lot line, behind the court.
    at_rear: bool = True
    #: The alley runs along a side lot line, beside the court.
    at_side: bool = False
    #: The rear alley runs the WHOLE rear lot line (s4's cover, FOLLOWUPS
    #: 3(d)), so the row of stalls along it may back straight out into it
    #: wherever along the line the court stands. ``at_rear`` alone -- s4's
    #: three rays of five -- reaches the court (:func:`alley_fed`), and the
    #: court keeps its own aisle. False unless a caller says so: an alley
    #: stub may leave the court backing into the neighbour's yard.
    rear_whole: bool = False

    @property
    def rear_aisle(self) -> bool:
        """The alley behind the court is its aisle's ground: at the rear and
        along the whole rear line."""
        return self.at_rear and self.rear_whole


def alley_fed(rules: "ZoneResolution", alley: Alley | None) -> bool:
    """Whether this lot's parking is reached from its alley.

    Only where the code sends the driveway there
    (``parking_alley_access_required``), from an alley at the rear or at a
    side. The court spans the lot behind the building, so an alley along
    either line meets it: from the rear the stalls face it, from a side the
    court's own aisle runs out into it at its end. Neither needs a lane down
    the building's flank from the street -- which the code forbids besides.
    Steph, 2026-09-25: *"Alleys along side yards is important."* Until then
    a side alley was not read and the lot kept its street lane.
    """
    return (
        alley is not None
        and (alley.at_rear or alley.at_side)
        and rules.get("parking_alley_access_required") is True
    )


#: ``corner_access_street`` values that let a corner lot's driveway come in
#: from the side street: ``any`` names no street, ``side`` names that one.
#: ``lowest_class`` asks for the street of the lowest functional class, which
#: nothing measures yet, so it keeps the lane beside the building -- the
#: conservative reading, where quadfit's drawing treats it as ``any``.
SIDE_STREET_ACCESS = frozenset({"any", "side"})


def front_lot_line_rule(rules: "ZoneResolution") -> str | None:
    """How this code names a corner lot's front (``front_lot_line_corner``).

    ``shortest``, ``owner``, ``entrance`` or ``both``; None where unread.
    :func:`flats.geom.corner.front_bearings` turns it into the streets a
    corner lot is screened as fronting.
    """
    got = rules.get("front_lot_line_corner")
    return got if isinstance(got, str) else None


def side_street_fed(rules: "ZoneResolution", alley: Alley | None, corner: bool) -> bool:
    """Whether this corner lot's court is reached straight off the side street.

    The court spans the lot behind the building and its end meets the second
    street, as a side alley's does (:func:`alley_fed`): a curb cut there and
    a short drive across the street-side yard reach it, and no lane runs
    down the building's flank. Quadfit's s6s draws that plan
    (``townhome_rear_court_side_street``, 9522942d) on 14,778 corner lots.
    Only on a real corner (:func:`flats.geom.corner.is_corner`), only where
    the code lets the driveway use that street, and never where it sends the
    driveway to the alley instead -- the alley answer comes first.
    """
    return (
        corner
        and not alley_fed(rules, alley)
        and rules.get("corner_access_street") in SIDE_STREET_ACCESS
    )


def _backout_shortfall(rules: "ZoneResolution", alley: Alley | None) -> float | None:
    """What the alley leaves short of the room a car needs to back out.

    ``None`` where the alley is not the aisle here: no alley, a code that
    does not send the driveway to it, or one that states no back-out room
    (``parking_alley_backout_ft`` -- Portland by Steph's ruling, Gresham by
    Figure 9.0825A). Paved on the lot, between the stall and the alley line.
    """
    backout = _number(rules, "parking_alley_backout_ft")
    if backout is None or not alley_fed(rules, alley):
        return None
    assert alley is not None
    return max(0.0, backout - (alley.width_ft or 0.0))


def side_column(
    design: Design,
    rules: "ZoneResolution",
    alley: Alley | None,
    stalls: int | None = None,
) -> tuple[float, tuple[str, ...]] | None:
    """The court's depth when its stalls stand in a column along a side alley.

    THE ALLEY IS THE AISLE, from the side (Steph 2026-09-25). A row of stalls
    behind the building needs its own aisle; beside a side alley the stalls
    can instead stand nose-in to the building's side of the court, one behind
    another along the alley line, and back straight out into the alley --
    s6s's ``townhome_rear_court_alley_aisle`` turns its boxes the same way on
    a side alley. The column is the stalls' WIDTHS deep (four at 9 ft are
    36), plus the gap off the rear wall; across the lot it is one stall's
    depth plus the back-out room the alley leaves short.

    Returned only where that crossing fits inside the building's NARROWER
    side, so it stands inside the fit rectangle in either orientation
    without the rectangle being searched wider; a narrow alley whose
    shortfall pushes the column wider than that is not offered it -- the
    conservative side. ``None`` where the alley is not at a side, is not the
    aisle here, or the design has no court.

    ``stalls`` is the count to stand in the column; the charged floor
    (:func:`court_across`) when omitted.
    """
    if (
        alley is None
        or not alley.at_side
        or not design.parking.court_depth_ft
        or design.parking.config not in _COURT_CONFIGS
    ):
        return None
    shortfall = _backout_shortfall(rules, alley)
    if shortfall is None:
        return None
    used = ["parking_alley_access_required", "parking_alley_backout_ft"]
    gap = design.parking.building_gap_ft
    stall = design.parking.stall_depth_ft
    if (stated := _number(rules, "parking_building_buffer_ft")) is not None:
        used.append("parking_building_buffer_ft")
        gap = max(gap, stated)
    if (stated := _number(rules, "parking_stall_depth_ft")) is not None:
        used.append("parking_stall_depth_ft")
        stall = max(stall, stated)
    narrow = min(design.footprint.width_ft, design.footprint.depth_ft)
    if stall + shortfall > narrow:
        return None
    across = court_across(design, rules, alley)
    count = across.stalls if stalls is None else stalls
    if not count:
        return None
    return gap + count * across.stall_ft, tuple(used + list(across.from_code))


def court_depth(
    design: Design, rules: "ZoneResolution", alley: Alley | None = None
) -> tuple[float, tuple[str, ...]]:
    """How much depth this design's own parking needs behind the building.

    A rear court is a row of stalls plus the aisle that serves them, and until
    2026-09-08 nothing here charged a lot for either: ``min_depth_ft`` was the
    footprint plus its two setbacks, as though six cars parked nowhere. In most
    of Oregon that court is about 42 ft — deeper than the building itself — so
    leaving it out was the largest single overstatement of what a lot can hold.
    The strip between the rear wall and the first stall is charged too, since
    2026-09-17: the county drawing has always stood the court 5 ft off the
    building (``SiteplanSpec.building_parking_gap_ft``), and a court that
    starts at the wall is 5 ft shallower than any site plan we would draw.
    Fairview is the one city that states its own buffer, and its 4 ft does
    not raise the design's 5.

    **A missing aisle width is not a missing standard.** Portland, Milwaukie and
    Wilsonville each dimension a parking space for this building and state no
    aisle, every one of them on the record with the exclusion sentence quoted,
    and refusing to answer for them would be the wrong kind of caution: the pod
    still needs somewhere to turn round. So the design carries its own court
    geometry and a code that states more raises it. Where the code states
    nothing, the answer rests on the design's assumption and says so.

    The aisle read is the **two-way** figure, because ``townhome_rear_court``
    enters and leaves the court forward. A one-way court is a different site
    plan and would be a different typology, so the narrower number is never
    substituted for it.

    This is the court's *depth* only. What it asks across the lot — the row
    of stalls side by side, and the lane down the building's flank that
    reaches them — is :func:`court_across`, and the two are charged on the two
    axes they occupy.

    Returns ``(depth, from_code)``, where ``from_code`` names the standards the
    zone actually supplied. An empty tuple against a non-zero depth means the
    number is the design's assumption and nothing in the code raised it.
    """
    court = design.parking.court_depth_ft
    if not court or design.parking.config not in _COURT_CONFIGS:
        return 0.0, ()
    used: list[str] = []
    gap = design.parking.building_gap_ft
    stall = design.parking.stall_depth_ft
    aisle = design.parking.aisle_ft
    if (stated := _number(rules, "parking_building_buffer_ft")) is not None:
        used.append("parking_building_buffer_ft")
        gap = max(gap, stated)
    if (stated := _number(rules, "parking_stall_depth_ft")) is not None:
        used.append("parking_stall_depth_ft")
        stall = max(stall, stated)
    if (stated := _number(rules, "parking_aisle_two_way_ft")) is not None:
        used.append("parking_aisle_two_way_ft")
        aisle = max(aisle, stated)
    # THE ALLEY AS THE AISLE (FOLLOWUPS 4(b)). On a lot the code sends to its
    # rear alley, where the code also lets the alley serve as the aisle
    # (``parking_alley_backout_ft``), the row of stalls along the alley backs
    # straight out into it: the court is the stall plus whatever the alley's
    # measured width leaves short of the room a car needs, paved on the lot.
    # Taken only where it is shallower, as s6s takes it only where it buys a
    # stall -- a lot deep enough for the court's own aisle keeps it.
    # Only where the alley runs the WHOLE rear line (``Alley.rear_whole``,
    # FOLLOWUPS 3(d)): the court stands somewhere along that line, nothing
    # says where, and a stub along part of it would back the row out into
    # the neighbour's yard. The alley at a side is not this: its column is
    # :func:`side_column`, charged on its own fit.
    shortfall = _backout_shortfall(rules, alley) if alley is not None and alley.rear_aisle else None
    if shortfall is not None:
        if gap + stall + shortfall < gap + stall + aisle:
            used += ["parking_alley_access_required", "parking_alley_backout_ft"]
            return gap + stall + shortfall, tuple(used)
    return gap + stall + aisle, tuple(used)


@dataclass(frozen=True, slots=True)
class Across:
    """What a rear court asks of the lot's width, and where the figures came from."""

    #: Stalls the court is charged at: the design's floor, raised to the
    #: zone's legal minimum, cut to its cap.
    stalls: int = 0
    #: Those stalls side by side, each the wider of the design's and the zone's.
    width_ft: float = 0.0
    #: The two-way lane beside the building from the street to the court.
    lane_ft: float = 0.0
    #: One stall's width in this zone -- what one more seat costs across.
    stall_ft: float = 0.0
    #: The most stalls this zone lets the design draw: its preferred count,
    #: cut to the cap. Where the seat count reported beside the colour
    #: stops; never what a lot is charged for.
    most: int = 0
    #: Standards the zone actually supplied. Empty against non-zero figures
    #: means the numbers are the design's own.
    from_code: tuple[str, ...] = ()


def court_across(
    design: Design,
    rules: "ZoneResolution",
    alley: Alley | None = None,
    *,
    corner: bool = False,
) -> Across:
    """How much width this design's own parking needs, and where.

    A rear court is one row of stalls side by side behind the building, and a
    lane down one flank of the building to reach it. Until 2026-09-17 the
    paper lot charged the court's depth and not its width, and said so in its
    own docstring: six stalls at 9 ft are 54 ft across, wider than the 36 ft
    end of the pod in front of them, so every zone where the pod fit end-on
    was reading about 18 ft narrower than the county pipeline draws it.
    quadfit's s6s has always placed the stalls by width inside the envelope,
    so no county verdict rested on the gap; this is the paper answer catching
    up with the drawing.

    **How many stalls.** The design's floor (``stalls_required`` -- one per
    home, the least the pod is built with), raised to the zone's legal
    minimum where it states one, then cut to the zone's cap where it states
    one — a court the code will not permit is not a court the lot has to be
    wide enough for. Fractions round up: half a car still needs a whole cell.
    A cap below the legal minimum would be a code at war with itself and is
    not resolved here. Until 2026-09-18 the count charged was the design's
    1.5-per-home *target* -- six stalls, a 54 ft row wider than the pod's
    36 ft end -- and 4,977 of the county map's 20,125 greens seated four or
    five and could never have been green here whatever the drawing did.
    Steph's ruling that day, *"same as the county map. 4 is enough to
    sell"*, made the floor the charge and the rest a report: ``most`` is the
    preferred count cut to the same cap, and the screen counts how many of
    them the lot seats and says so beside the colour
    (:attr:`flats.score.screen.Screening.stalls_seated`).

    **How wide each.** The design's stall width, raised by the zone's. Gresham
    dimensions a stall at 8.5 ft and that does not shrink the court, for the
    same reason its narrower aisle does not deepen it — the design is drawn to
    a 9 ft cell and a smaller one is a different drawing.

    **The lane.** The design's 12 ft, raised by the zone's two-way driveway
    minimum where it states one (Happy Valley 20, Tualatin 22, West Linn 24).
    The two-way figure, as with the aisle: the court is entered and left
    forward. The lane runs beside the building, so it is charged with the
    building's width, not with the court's — the court is behind both.

    On a corner lot whose code lets the driveway use the side street
    (:func:`side_street_fed`) there is no lane beside the building either:
    the court is reached from the street along its end.

    What this does not read, and why: ``parking_maneuvering_max_width_ft``,
    the 10 or 12 ft six cities state for townhouse lots. Until 2026-09-17 this
    docstring called it a ceiling on the lane and said a ceiling below the
    lane was a site plan nobody could draw. It is not a ceiling on this lane.
    In every one of the six codes the sentence is one of the conditions a
    townhouse project must meet **to be allowed a garage on the front facade,
    parking in the front yard or a driveway in front of a townhouse**
    (Milwaukie 19.505.5.F.1, Gresham 7.0431(B)(3)(a), Fairview 19.30.050(D)(1),
    Wilsonville 4.113(.14)E.5.b, Oregon City 17.16.040.A, Clackamas
    845.03(E)(1) -- the state model code's shape). A project that parks in a
    rear court off one consolidated side driveway is on the other branch
    (F.2 / (b) / (D)(2) / c. / B / (E)(2)), which asks exactly that of it and
    states no width. The cap never reaches this design, and reading it as one
    would have refused Milwaukie's townhouse plat for a plan its code
    describes. Declared in ``excluded``, bound to the catalog by
    ``test_the_townhouse_lane_ceiling_is_a_condition_of_a_branch_the_pod_does_not_take``.
    """
    if not design.parking.court_depth_ft or design.parking.config not in _COURT_CONFIGS:
        return Across()
    used: list[str] = []
    units = design.units
    stalls = math.ceil(round(design.stalls_required, 6))
    most = math.ceil(round(design.stalls_preferred, 6))
    if (floor := _number(rules, "parking_min_per_unit")) is not None:
        used.append("parking_min_per_unit")
        stalls = max(stalls, math.ceil(round(floor * units, 6)))
    if (cap := _number(rules, "parking_max_per_unit")) is not None:
        used.append("parking_max_per_unit")
        stalls = min(stalls, math.floor(round(cap * units, 6)))
        most = min(most, math.floor(round(cap * units, 6)))
    most = max(most, stalls)
    stall = design.parking.stall_width_ft
    if (stated := _number(rules, "parking_stall_width_ft")) is not None:
        used.append("parking_stall_width_ft")
        stall = max(stall, stated)
    lane = design.parking.lane_width_ft
    if alley_fed(rules, alley):
        # The court is reached from the alley behind it or beside it, and the
        # code forbids the street lane besides (Portland 33.266.120.C.3,
        # Gresham 7.0420(B)(1), Wilsonville, West Linn): no lane beside the
        # building.
        used.append("parking_alley_access_required")
        lane = 0.0
    elif side_street_fed(rules, alley, corner):
        used.append("corner_access_street")
        lane = 0.0
    elif (stated := _number(rules, "driveway_min_width_two_way_ft")) is not None:
        used.append("driveway_min_width_two_way_ft")
        lane = max(lane, stated)
    return Across(
        stalls=stalls,
        width_ft=stalls * stall,
        lane_ft=lane,
        stall_ft=stall,
        most=most,
        from_code=tuple(used),
    )


def _yard(rules: "ZoneResolution", name: str) -> float | None:
    """A setback's depth in feet: 0 where the code waives it, None where unread."""
    if name in rules.exempted:
        return 0.0
    return _number(rules, name)


def paved(
    design: Design,
    rules: "ZoneResolution",
    alley: Alley | None = None,
    *,
    corner: bool = False,
    column: bool = False,
    deep_ft: float,
) -> float | None:
    """Square feet this design's parking paves on the lot, or None if unknown.

    Every code that asks for open space or landscaping says the ground a car
    stands or drives on does not count towards it -- Portland 33.110.240's
    outdoor area may not be "vehicle area", Happy Valley 16.42.030(A)(8)
    names driveways and parking outright -- and until item 7(a) of the
    follow-up queue the screen measured both against the lot less the
    building alone, which credited the court and its lane as garden. This is
    what that leftover has to lose.

    It is the pavement of the plan the paper lot already charges the fit for,
    and it is counted the way quadfit's s6s counts it (``parking_area`` and
    ``driveway_area`` in ``offer``), so the two layers subtract the same
    ground:

    * **the court** -- the row of stalls at the charged count, each the
      zone's cell (:func:`court_across`, :func:`court_depth`), and the aisle
      serving them, paved across the row or across the lane that reaches
      it, whichever is wider. The standoff between the rear wall and the
      first stall is NOT pavement: it is the walk, the downspouts and the
      doors, and Fairview makes it a landscape strip in as many words. s6s
      leaves it in the leftover too.
    * **where the alley is the aisle**, the stalls and the back-out room the
      alley leaves short, paved between them and the alley line; no aisle of
      the lot's own. The same from a side alley, where the stalls stand in a
      column along it (:func:`side_column`).
    * **the way in** -- the lane beside the building from the street, the
      front setback plus the building's depth in the orientation that won
      (``deep_ft``) plus the standoff it runs past before it meets the aisle;
      or, where the code lets a corner lot's court be reached off the side
      street, a drive across the street-side yard; or, from a side alley that
      is not the aisle, the aisle carried on across the alley-side yard to the
      alley. From a rear alley the court meets the alley line and there is
      nothing to cross.

    Every figure is the least a legal plan could pave, which is the right
    quantity: the question is whether ANY plan leaves the amount, and the
    plan that paves least leaves most. The one way the real figure is larger
    is a building that cannot stand at the front setback line -- the lane
    then runs further -- and the fit does not record where the building
    stood. That is a strip of lane at most, against leftovers the county map
    measures in thousands of square feet; recorded here rather than assumed
    away.

    None -- unknown, never zero -- for a design parked in a way nothing here
    draws (``side_drive``, ``tuck_under``: a tuck-under's driveway still
    crosses the front yard, and nobody has drawn it), and for a way in whose
    yard the code does not state as a number. The screen then refuses to
    certify on the leftover rather than guessing it. A design that parks
    nothing on the lot paves nothing: 0.0.
    """
    parking = design.parking
    if not parking.parks or parking.config is ParkingConfig.street_only:
        return 0.0
    if parking.config not in _COURT_CONFIGS:
        return None
    across = court_across(design, rules, alley, corner=corner)
    if not across.stalls:
        # A cap of nothing: no row is drawn and nothing is paved for it. The
        # parking checks already say this design cannot be built here.
        return 0.0
    gap = parking.building_gap_ft
    if (stated := _number(rules, "parking_building_buffer_ft")) is not None:
        gap = max(gap, stated)
    stall = parking.stall_depth_ft
    if (stated := _number(rules, "parking_stall_depth_ft")) is not None:
        stall = max(stall, stated)
    aisle = parking.aisle_ft
    if (stated := _number(rules, "parking_aisle_two_way_ft")) is not None:
        aisle = max(aisle, stated)
    row = across.width_ft
    shortfall = _backout_shortfall(rules, alley)
    if column:
        # The column stands along the side alley: each stall one cell of the
        # row turned end-on, plus the back-out room paved beside it.
        assert shortfall is not None, "a column court was paved where no side alley offers one"
        return row * (stall + shortfall)
    if alley is not None and alley.rear_aisle and shortfall is not None and shortfall < aisle:
        # The same choice `court_depth` makes: the alley is the aisle.
        return row * (stall + shortfall)
    court = row * stall + aisle * max(row, across.lane_ft)
    if across.lane_ft:
        front = _yard(rules, "setback_front_ft")
        if front is None:
            return None
        return court + across.lane_ft * (front + deep_ft + gap)
    if alley_fed(rules, alley):
        assert alley is not None
        if alley.at_rear:
            return court
        # A side alley: the aisle runs on across the yard on that line. The
        # line's own setback where the code states one (Portland waives it);
        # otherwise the deeper of side and rear, the bridge's reading of a
        # city that calls the alley line a rear lot line.
        yard = _yard(rules, "setback_alley_side_ft")
        if yard is None:
            side, rear = _yard(rules, "setback_side_ft"), _yard(rules, "setback_rear_ft")
            if side is None or rear is None:
                return None
            yard = max(side, rear)
        return court + aisle * yard
    if side_street_fed(rules, alley, corner):
        yard = _yard(rules, "setback_street_side_ft")
        if yard is None:
            yard = _yard(rules, "setback_side_ft")
        if yard is None:
            return None
        drive = parking.lane_ft
        if (stated := _number(rules, "driveway_min_width_two_way_ft")) is not None:
            drive = max(drive, stated)
        return court + drive * yard
    # A court with no lane and no alley or side street to reach it from:
    # not a plan anything here draws.
    return None


def paper_fit(design: Design, rules: "ZoneResolution") -> PaperFit:
    """The lot this design needs in this zone, on paper.

    Both orientations are costed and the less demanding one is reported: a pod
    that will not fit broadside may fit end-on, and a requirement stated for
    the worse orientation is a requirement nobody has to meet.
    """
    # Under unit lots the lot-size and lot-width standards read once per
    # dwelling, so the project needs that many of them side by side. Setbacks
    # do not scale: the walls between units are shared, and only the two ends
    # of the row see a side yard either way. Nor does the coverage cap — the
    # same building over the same ground is the same share of it however the
    # ground is divided.
    per_unit = design.plat is Plat.unit_lots
    lots = design.units

    front = _number(rules, "setback_front_ft")
    rear = _number(rules, "setback_rear_ft")
    side = _number(rules, "setback_side_ft")
    side_total = _number(rules, "setback_side_total_ft")
    min_lot, lot_answered = lot_standard(rules, "min_lot_sqft", per_unit=per_unit, lots=lots)
    min_width, width_answered = lot_standard(
        rules, "min_lot_width_ft", per_unit=per_unit, lots=lots
    )
    # A code that states an average lot width beside the width at the front lot
    # line is stating two standards on one axis, and the screen measures them
    # on two different lines. The paper lot is a rectangle, where those two
    # lines are the same line, so here the two standards collapse into the
    # larger of them -- which is the honest answer for the question this
    # function asks: the smallest rectangle that satisfies everything written.
    min_avg, avg_answered = lot_standard(
        rules, "min_average_lot_width_ft", per_unit=per_unit, lots=lots
    )
    if min_avg is not None:
        min_width = min_avg if min_width is None else max(min_width, min_avg)
    coverage = _number(rules, "max_coverage_pct")
    height = _number(rules, "max_height_ft")
    min_height = _number(rules, "min_building_height_ft")
    min_stories = _number(rules, "min_building_height_stories")
    # A code that makes the building face the street has taken one of the
    # two orientations away, and the cheaper lot may have been that one.
    axis = rules.get("orientation_constraint") == "axis_required"

    # What the two side yards take off the width together. Where the code
    # states a combined figure it governs, and a per-side floor can only make
    # the pair wider -- 5 ft either side of a "total 15" cell is still 15, but
    # 8 ft either side of one would be 16.
    sides = _pair(side, side_total)
    court, court_from_code = court_depth(design, rules)
    across = court_across(design, rules)
    needed = (
        ("setback_front_ft", front),
        ("setback_rear_ft", rear),
        ("setback_side_ft", sides),
    )
    unknown = tuple(name for name, got in needed if got is None) + tuple(
        name
        for name, answered in (
            ("min_lot_sqft", lot_answered),
            ("min_lot_width_ft", width_answered),
            ("min_average_lot_width_ft", avg_answered),
        )
        if not answered
    )
    used = [name for name, got in needed if got is not None]
    if side_total is not None:
        used.append("setback_side_total_ft")
    used += list(court_from_code)
    used += list(across.from_code)
    used += [
        name
        for name, got in (
            ("min_lot_sqft", min_lot),
            ("min_lot_width_ft", min_width),
            ("min_average_lot_width_ft", min_avg),
            ("max_coverage_pct", coverage),
            ("max_height_ft", height),
            ("min_building_height_ft", min_height),
            ("min_building_height_stories", min_stories),
        )
        if got is not None
    ]
    unsigned = tuple(name for name in used if name in rules.untrusted)

    best: PaperFit | None = None
    for orientation, width_ft, depth_ft in design.oriented(axis_required=axis):
        # Across the lot the envelope is the building with its lane beside it,
        # or the row of stalls behind it, whichever is wider -- the court sits
        # behind both, so the lane is never added to the court. This is the
        # rectangle quadfit's site plan draws inside the setbacks, and it is
        # why the pod end-on is not a 36 ft question: six stalls are 54.
        building = width_ft + across.lane_ft
        if across.width_ft > building:
            envelope_ft, width_binding = across.width_ft, ACROSS_COURT
        else:
            envelope_ft, width_binding = building, ACROSS_BUILDING
        needed_width = envelope_ft + sides if sides is not None else None
        if needed_width is not None and min_width is not None and min_width > needed_width:
            needed_width, width_binding = min_width, ACROSS_MIN_WIDTH
        # The court sits between the building's rear wall and the rear lot
        # line, and a required rear yard is land you may drive and park on in
        # every Oregon code read for this — so the two overlap rather than
        # stack, and what the lot must give is the deeper of them. Where a
        # jurisdiction bars parking from a required rear yard this understates
        # by up to the setback; that is an unmeasured condition on the human
        # list, not a thing assumed away here.
        needed_depth = (
            depth_ft + front + max(rear, court)
            if front is not None and rear is not None
            else None
        )

        floors: list[tuple[float, str]] = []
        if min_lot is not None:
            floors.append((min_lot, BY_MIN_LOT))
        if coverage:
            # A coverage cap states the lot indirectly: the footprint may be at
            # most this share of it, so the lot is at least the footprint over
            # that share. A zero or absent cap states nothing.
            floors.append((design.ground_sqft * 100.0 / coverage, BY_COVERAGE))
        if needed_width is not None and needed_depth is not None:
            floors.append((needed_width * needed_depth, BY_ENVELOPE))

        area, binding = max(floors, default=(None, ""))
        candidate = PaperFit(
            design=design.key,
            jurisdiction=rules.jurisdiction,
            zone=rules.zone,
            min_width_ft=needed_width,
            min_depth_ft=needed_depth,
            parking_depth_ft=court,
            parking_width_ft=across.width_ft,
            lane_ft=across.lane_ft,
            stalls=across.stalls,
            width_binding=width_binding if needed_width is not None else "",
            min_area_sqft=area,
            binding=binding,
            height_ok=_height_ok(design, height, min_height, min_stories),
            orientation=orientation.value,
            plat=design.plat.value,
            unknown=unknown,
            unsigned=unsigned,
            excluded=(
                "setback_street_side_ft (corner lots only)",
                # The side setback on the one side line abutting an alley --
                # zero in Portland. The paper fit has no edges and asks both
                # side yards in full, which overstates the width an
                # alley-side lot needs by the waived yard: the conservative
                # direction. The envelope (`flats.geom.envelope`) applies it
                # to the alley edge alone.
                "setback_alley_side_ft (alley-side lots only; the paper fit has no edges)",
                # The street setback on a line off a Map 130-1 stretch --
                # zero in Portland's commercial zones, where the stretch's
                # line takes 10. The paper fit has no edges and so no line
                # to read off the corridor; it keeps the lot-level 10 on the
                # front, the conservative direction. The envelope applies it
                # to the street edge read off every stretch alone.
                "setback_street_off_corridor_ft (street lines off a mapped corridor; the paper fit has no edges)",
                "min_frontage_ft (measured at the street, not the envelope)",
                # Ruled 2026-09-08: the pod parks in a rear court and has no
                # garage, so a garage-entrance setback cannot reach it. This is
                # a statement about the product, not about Oregon — it holds
                # only while every catalog design is rear_court or street_only,
                # and `test_no_catalog_design_has_a_garage` fails the day one is not.
                "setback_garage_entrance_ft (the pod has no garage)",
                # `townhome_rear_court` enters and leaves the court forward, so
                # the two-way figure is the one that governs. Substituting the
                # narrower one-way aisle would understate the court on the
                # strength of a site plan nobody has drawn.
                "parking_aisle_one_way_ft (the court is two-way)",
                # The same reasoning for the lane beside the building.
                "driveway_min_width_one_way_ft (the lane is two-way)",
                # The 10 or 12 ft six cities state for townhouse lots is a
                # condition of the FRONT-parking option -- a garage on the
                # front facade, parking in the front yard, a driveway in
                # front of a townhouse -- and this design takes the other
                # branch: a rear court off one consolidated side driveway,
                # which is what that branch requires and which it caps at
                # nothing. See `court_across`. Holds only while every catalog
                # design parks behind or on the street; a tuck_under or
                # side_drive design would be on the front branch, and the
                # test named in `court_across` fails the day one lands.
                "parking_maneuvering_max_width_ft (a condition of the front-parking option; the pod parks behind)",
            ),
        )
        if best is None or _worse(best, candidate):
            best = candidate
    assert best is not None  # oriented() never returns empty
    return best


def _worse(current: PaperFit, other: PaperFit) -> bool:
    """Whether ``other`` asks less of a lot than ``current``.

    An orientation whose envelope could not be costed never wins: an unknown
    requirement is not a smaller one.
    """
    if other.min_area_sqft is None:
        return False
    if current.min_area_sqft is None:
        return True
    return other.min_area_sqft < current.min_area_sqft
