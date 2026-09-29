"""GREEN, YELLOW, RED or UNKNOWN — and what the binding constraint was.

Everything upstream measures. This is where measurements become an answer, and
the rules for turning one into the other are deliberately asymmetric.

Four outcomes, and the split that matters is **whose queue the lot lands in**:

``GREEN``    clears as-of-right. Nobody's queue.
``YELLOW``   clears, but only with an approval somebody has to apply for. The
             developer's queue, labelled with which approval and how deep.
``RED``      a verified standard the lot cannot meet, with no relief the code
             offers. Nobody's queue. Dead.
``UNKNOWN``  we could not answer. **Ours** — encode it, fetch it, verify it.

The last two used to be one colour called REVIEW, and merging them hid the
useful half. A pod one foot over a setback is not an uncertain lot; it is a
certain lot with an adjustment application attached, and Oregon cities grant
those routinely. Filing it under the same label as an unencoded standard buries
a real and usually-granted path behind "we are still working on it". See
FLATS_PLAN section 14.

The asymmetries this enforces:

*Only a trusted rule set may produce a verdict.* If any standard governing the
lot is draft, stale, or missing, the lot is UNKNOWN — never RED. A wrong number
in a rule file must never delete an acquisition target, and it is the encoding
lifecycle, not the geometry, that decides whether a number can be believed.

*Tolerance and relief are different uncertainties.* A miss inside tolerance is
epistemic — the raster is conservative to about half a foot — so it lands in
UNKNOWN. A miss the code offers a path around is legal, and lands in YELLOW.
The one exception is the fit itself: Steph ruled 2026-09-25 that a fit within
its tolerance either way is GREEN with a ``tight_fit`` flag, because every
acquisition is surveyed and the county's lot lines are coarser than the
tolerance (:attr:`Screening.tight_fit`). Every other tolerated check still
holds the lot out of GREEN.

*A standard nobody encoded is not a standard that passes.* Skipping a check the
code plainly imposes would manufacture GREENs. Any skipped check drops the lot
out of GREEN and names itself, which is how the coverage ledger gets its work.

A check computed from a proxy that runs in the lot's favour is listed in
:attr:`Screening.optimistic` so a reviewer can see which numbers were assumed
in the lot's favour. Open space and landscaping were the two until
2026-09-28, read against the lot less the building with the parking left in;
they now come off the lot less the building and its pavement, and where the
pavement cannot be drawn the lot less the building is used only as the upper
bound it is -- enough to fail a lot, never to pass one.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from dataclasses import dataclass, field as _dc_field
from typing import Any, Sequence

from flats.designs.model import Design, Orientation, Plat
from flats.fit.rectangle import Fit, Fitter
from flats.geom.edges import Tier as GeometryTier
from flats.rules.conditions import Tier
from flats.rules.fields import REQUIRED_FIELDS
from flats.rules.resolver import ALTERNATIVES, Verdict as RuleVerdict, ZoneResolution
from flats.score.configure import Configuration
from flats.score.paper import (
    Alley,
    Beside,
    court_across,
    court_depth,
    lot_standard,
    paved,
    side_column,
    side_court,
)
from flats.score.relief import (
    RELIEF_UNCONFIRMED,
    ReliefOutcome,
    ReliefPolicy,
    worst as _hardest_ask,
)
from flats.score.slack import CheckResult, SlackPolicy, Verdict, binding, dominant


class Triage(str, enum.Enum):
    """The traffic light."""

    #: Every standard encoded, verified, and cleared with nothing to ask for.
    green = "green"
    #: Clears, but a standard is missed by an amount the code offers relief
    #: for. A real path, priced in applications rather than in doubt.
    yellow = "yellow"
    #: A verified standard the lot cannot meet, and no relief exists for it.
    red = "red"
    #: We could not answer: an unverified rule, an unreadable lot shape, a
    #: standard nobody has encoded, or a miss inside measurement noise. Our
    #: backlog, not the lot's problem — this is the colour that should shrink.
    unknown = "unknown"

    @property
    def buildable(self) -> bool:
        """Whether some legal path exists, with or without an application."""
        return self in (Triage.green, Triage.yellow)


#: Reasons a lot lands in UNKNOWN that are not a failed check.
NO_FRONTAGE = "NO_FRONTAGE"
GEOMETRY_UNREADABLE = "GEOMETRY_UNREADABLE"
STANDARD_NOT_ENCODED = "STANDARD_NOT_ENCODED"
USE_NOT_ENCODED = "USE_NOT_ENCODED"
#: A standard here is written per corner, per alley, per slope — and the
#: fact deciding which number applies was assumed rather than observed.
FACT_ASSUMED = "FACT_ASSUMED"
#: The same, except nobody would even assume it. Sewer is the case: a
#: standard turns on it, no layer answered, and guessing either way is
#: wrong in a different direction.
FACT_UNOBSERVED = "FACT_UNOBSERVED"

#: The zone forbids the use outright and lists no conditional-use path.
USE_PROHIBITED = "USE_PROHIBITED"
#: The fit was searched at the building's width alone, and what this zone's
#: parking asks across the lot -- the lane beside the building, or the row of
#: stalls behind it -- is wider. Whatever depth that search found is not
#: evidence the pod fits with its cars, and no verdict may rest on it. Our
#: backlog: the caller has to search again at the width `fit_for` asks.
COURT_WIDTH_UNMEASURED = "COURT_WIDTH_UNMEASURED"
#: A line the geometry called a street is one only because a private drive
#: runs near it -- through the lot itself, or across a school, a park or a
#: mobile-home park beyond the fence. No code counts a drive the lot does not
#: abut, and the reading moves the answer both ways: the setback on that line
#: is too big, and the corner, the lane and the side-street driveway it
#: grants are not there. A person has to look at the lot (FOLLOWUPS 4).
STREET_UNCONFIRMED = "STREET_UNCONFIRMED"

#: Checks computed from a proxy that runs in the lot's favour. Empty since
#: 2026-09-28 (FOLLOWUPS 7(a)): the two it held, open space and landscaping
#: as a share of the lot, were read against the lot less the building alone,
#: and now come off the lot less the building and its pavement
#: (:func:`flats.score.paper.paved`) -- the amount the code asks about. Kept,
#: and kept empty, so the next check that has to lean on a favourable proxy
#: has somewhere to say so; a proxy nobody labels is a false GREEN nobody sees.
OPTIMISTIC_CHECKS: frozenset[str] = frozenset()

#: The quantity a leftover check is stated net of when the design's pavement
#: could not be drawn (:func:`flats.score.paper.paved` returned None). Joins
#: the ``measured_on`` denominators in ``_checks``'s ``unmeasured``, and so
#: reports as ``FACT_UNOBSERVED``: the code names ground nobody measured.
UNPAVED = "parking_pavement"

#: The shape a code asks the open space to take (a square that fits inside
#: it, a patio off each home) where the fit's window does not prove it and
#: the ground outside that window was never measured (:func:`_outdoor_shape`).
UNSHAPED = "outdoor_area_shape"

#: Which rule field each check reads. A check with no value goes unrun, but only
#: an unrun check backed by a *required* field means the encoding is incomplete
#: — many zones genuinely impose no FAR, and treating that silence as a gap
#: would bury the real gaps under thousands of false ones. Whether a standard is
#: absent by fact or by omission is the clause ledger's question, not this one's.
CHECK_FIELD: dict[str, str] = {
    "min_lot_area_sqft": "min_lot_sqft",
    "min_frontage_ft": "min_frontage_ft",
    "min_lot_width_ft": "min_lot_width_ft",
    "min_average_lot_width_ft": "min_average_lot_width_ft",
    "min_lot_depth_ft": "min_lot_depth_ft",
    "max_lot_depth_ratio": "max_lot_depth_ratio",
    "coverage_pct": "max_coverage_pct",
    "far": "max_far",
    "height_ft": "max_height_ft",
    "stories": "max_height_stories",
    "min_height_ft": "min_building_height_ft",
    "min_stories": "min_building_height_stories",
    "max_units": "max_units",
    "min_units": "min_units_at_trigger",
    "density_du_per_acre": "max_density_du_per_acre",
    "min_density_du_per_acre": "min_density_du_per_acre",
    "parking_stalls": "parking_min_per_unit",
    "parking_cap": "parking_max_per_unit",
    "open_space_pct": "open_space_min_pct",
    "open_space_sqft": "open_space_min_sqft",
    "open_space_shape": "open_space_min_dimension_ft",
    "private_open_space_shape": "private_open_space_min_dimension_ft",
    "landscaped_pct": "min_landscaped_pct",
}


@dataclass(frozen=True, slots=True)
class LotFacts:
    """What the geometry stage measured about one parcel."""

    lot_sqft: float
    frontage_ft: float = 0.0
    lot_width_ft: float | None = None
    #: The same axis, measured the other way the codes ask for. West Linn
    #: CDC 02.030 states both: lot width is "the horizontal distance between
    #: side lot lines, measured at right angles to the lot depth", and
    #: "average lot width is measured at the midpoints of opposite lot lines".
    #: On a rectangle they are one number; on anything that tapers toward the
    #: street they are two, which is the whole reason the city prints two rows.
    #: Left ``None`` where nothing took the measurement, and a ``None`` leaves
    #: the standard unchecked rather than failing a lot on a number nobody
    #: measured -- the same bargain ``lot_width_ft`` already strikes.
    avg_lot_width_ft: float | None = None
    #: Front lot line to rear lot line, measured the way the city that asks
    #: for it defines that. Thirty-eight zones in eight jurisdictions state a
    #: minimum lot depth and until this was measured not one of them was ever
    #: tested -- the standard was encoded, cited and silently skipped.
    #:
    #: It is not derivable from the two numbers already here. `area /
    #: frontage_ft` looks like a depth and is not one, because ``frontage_ft``
    #: is the SUM of every street-facing edge: a corner lot carries two and one
    #: parcel in Milwaukie carried seven, so the quotient is a fraction of the
    #: real depth on exactly the lots most likely to be corners. That proxy
    #: forecast 38 Milwaukie lots failing on width or depth. Measured, it was
    #: six. ``None`` where nothing took the measurement, on the same bargain as
    #: the two rows above.
    lot_depth_ft: float | None = None
    geometry: GeometryTier = GeometryTier.clean
    #: The rear setback the envelope was CUT with, in feet, when the envelope
    #: came from somewhere other than these rules -- quadfit's s5 carves the
    #: unconditioned number from its own zone table, and the screen resolves
    #: the corpus, whose variants can say something else about the same lot
    #: (no setback from a non-residential neighbour, none from an alley, 20
    #: ft against a house). The court charge (:func:`_court_beyond_rear`)
    #: needs the strip that is really there, not the one the rules would
    #: have cut: charging the court against a 0 ft rear setback when the
    #: envelope had already lost 10 ft to it took 10 ft off every Portland
    #: commercial lot the moment its neighbour was read (2026-09-22, 14,782
    #: rows). ``None`` means the envelope was cut with these rules' own
    #: number, which is what every caller but the bridge does.
    envelope_rear_ft: float | None = None
    #: An alley along the rear lot line and one along a side (s4's alley
    #: edges, named by bearing -- :func:`flats.geom.alley.observed_alley`),
    #: and the measured width, the narrowest where there are two. Read by
    #: the court only where the code sends the driveway to the alley and,
    #: for the depth, where it lets the alley be the aisle
    #: (:func:`flats.score.paper.court_depth`,
    #: :func:`flats.score.paper.side_column`). False and None where nothing
    #: measured the lot, which leaves the court as the street-fed one.
    #: ``alley_at_side`` is stricter than the registry fact of that name:
    #: the bridge sets it only where the alley runs the side line end to
    #: end (:func:`flats.geom.alley.side_alley_along`, FOLLOWUPS 3(c)),
    #: because the court stands somewhere along that line and the fit does
    #: not say where. ``alley_at_rear`` is s4's reading (three rays of five)
    #: and reaches the court; ``alley_rear_whole`` -- the alley runs the whole
    #: rear line (:func:`flats.geom.alley.rear_alley_along`, FOLLOWUPS 3(d))
    #: -- is what lets the row of stalls back out into it. False where
    #: nothing measured the stretch: the court keeps its own aisle.
    #: ``alley_rear_run_ft`` is the longest stretch of a PART-covered rear
    #: line with the envelope behind it (Steph's ruling 2026-09-28): a row
    #: no wider backs out into it too
    #: (:meth:`flats.score.paper.Alley.rear_aisle_for`). The bridge sets it
    #: per envelope; None where nothing measured it.
    alley_at_rear: bool = False
    alley_at_side: bool = False
    alley_rear_whole: bool = False
    alley_rear_run_ft: float | None = None
    alley_width_ft: float | None = None
    #: Two streets on the lot that really are two (bearings 45 degrees or
    #: more apart, :func:`flats.geom.corner.is_corner`). Read by the court
    #: where the code lets a corner lot's driveway use the side street
    #: (:func:`flats.score.paper.side_street_fed`). False where nothing
    #: measured the lot, which keeps the lane beside the building.
    corner: bool = False
    #: One of the lot's street lines rests only on a private drive the lot
    #: does not abut (:data:`STREET_UNCONFIRMED`,
    #: :func:`flats.ingest.quadfit.street_unconfirmed`). False where nothing
    #: read the road types, which is every caller but the bridge.
    street_unconfirmed: bool = False

    @property
    def landlocked(self) -> bool:
        return self.geometry is GeometryTier.landlocked

    @property
    def alley(self) -> Alley | None:
        if not (self.alley_at_rear or self.alley_at_side):
            return None
        return Alley(
            self.alley_width_ft,
            at_rear=self.alley_at_rear,
            at_side=self.alley_at_side,
            rear_whole=self.alley_at_rear and self.alley_rear_whole,
            rear_run_ft=self.alley_rear_run_ft if self.alley_at_rear else None,
        )


@dataclass(frozen=True, slots=True)
class Screening:
    """One (lot × design) answer, with everything behind it."""

    triage: Triage
    checks: tuple[CheckResult, ...] = ()
    #: Blocking checks, tightest shortfall first. The head is the constraint
    #: worth arguing about, and the histogram of heads is how a rule quietly
    #: costing thousands of lots becomes visible.
    binding: tuple[CheckResult, ...] = ()
    #: Non-check reasons: unverified rules, unreadable geometry, gaps.
    reasons: tuple[str, ...] = ()
    #: Standards the code may impose that nothing encoded supplies.
    unchecked: tuple[str, ...] = ()
    #: Checks whose observed value is a favourable approximation.
    optimistic: tuple[str, ...] = ()
    #: Feet of margin on the fit check, kept out front because it is the
    #: number a developer argues with — so it is the check's slack, which
    #: counts the parking court and the orientation the pod actually stood in,
    #: not the raw geometry's, which counts neither.
    fit_slack_ft: float | None = None
    #: Stalls the colour was charged for: the design's floor (one per home),
    #: raised to the zone's legal minimum, cut to its cap. 0 for a design
    #: with no court.
    stalls_charged: int = 0
    #: How many stalls the lot seats, floor to the design's preferred count
    #: (or the zone's cap), in one row behind the building at the depth the
    #: parking needs, or beside it where the code allows a court there
    #: (:func:`seats`). The number beside the colour, never inside it -- Steph
    #: 2026-09-18, *"same as the county map. 4 is enough to sell"*: a lot
    #: seating four is green on parking, and this says whether it seats
    #: six or eight. 0 where not even the floor holds; ``None`` where the fit
    #: was built without looking (:attr:`flats.fit.rectangle.Fit.stalls`).
    stalls_seated: int | None = None
    #: Which of the design's bands ``stalls_seated`` lands in -- ``minimum``,
    #: ``target`` or ``preferred``, the county map's own names -- and
    #: ``None`` where there is no count to band or the count is under the
    #: design's floor (a cap cut it, and ``parking_cap`` says so).
    parking_band: str | None = None
    #: The fit is inside the measurement's own step either way: it clears by
    #: no more than the ``fit_ft`` tolerance, or misses by no more than it.
    #: Steph, 2026-09-25: *"plus or minus 6 in it goes into the green
    #: category. Every acquisition is going to have a survey anyways.
    #: However, some sort of flag to be brought to the human's attention
    #: when they're reviewing green lots for acquisition."* A miss inside the
    #: tolerance therefore no longer holds a lot out of GREEN on its own; it
    #: carries this flag instead, and so does a pass as thin. The county's
    #: lot lines are good to about a foot, so the lot's survey decides it,
    #: and a colour that flipped on the next map's redraw would be noise.
    tight_fit: bool = False

    #: The blocker that most explains the outcome — largest proportional
    #: shortfall, not the tightest. This is what the rule-cost ledger counts;
    #: `binding` is the human work queue.
    dominant: str | None = None

    #: What clearing this lot would take: the deepest approval any failing
    #: check needs. Populated whatever the colour, so a lot held in UNKNOWN by
    #: an unrelated gap still shows the application it would need.
    ask: Tier = Tier.as_of_right
    #: One entry per failing check: which procedure covers it, and whether
    #: anybody has read the chapter granting that procedure.
    relief: tuple[ReliefOutcome, ...] = ()

    @property
    def head(self) -> str | None:
        """The tightest blocker: what is nearly solved on this lot."""
        return self.binding[0].check if self.binding else None

    @property
    def needs_ask(self) -> bool:
        return self.ask.needs_ask


def _coverage_allowed_sqft(rules: ZoneResolution, lot_sqft: float) -> tuple[float | None, str]:
    """Maximum building footprint, from a flat percentage or a tiered table."""
    curve = rules.get("coverage_curve")
    if curve:
        allowed = None
        for floor, base, pct_over in curve:
            if lot_sqft >= floor:
                allowed = base + (lot_sqft - floor) * pct_over / 100.0
        if allowed is not None:
            return allowed, "coverage_curve"
    pct = rules.get("max_coverage_pct")
    if pct is not None:
        return lot_sqft * pct / 100.0, "max_coverage_pct"
    return None, ""


def _checks(
    rules: ZoneResolution,
    lot: LotFacts,
    design: Design,
    fit: Fit,
    policy: SlackPolicy,
) -> tuple[list[CheckResult], list[str], set[str]]:
    """Every numeric standard this lot can be measured against."""
    out: list[CheckResult] = []
    unchecked: list[str] = []
    #: Quantities a standard here is stated per, which nothing surveyed and
    #: the lot's own area could not settle.
    unmeasured: set[str] = set()
    where = rules.jurisdiction

    def check(name: str, observed: float, threshold: float | None, *, is_maximum: bool) -> None:
        if threshold is None:
            unchecked.append(name)
            return
        out.append(policy.evaluate(name, observed, threshold, is_maximum=is_maximum, jurisdiction=where))

    def rate(name: str, observed: float, field: str, *, is_maximum: bool) -> None:
        """A rate check, aware of which area the code divides by.

        Nearly every Oregon city states density per *net acre* -- the lot less
        rights-of-way, floodplain, slopes over 25 percent, wetlands and Goal 5
        resources -- and nothing here surveys any of that. Portland is the
        exception that makes the distinction worth carrying: Table 120-4 says
        "of site area", which is the lot, so that one is simply run.

        Not only densities. A floor area ratio is the same shape of number and
        takes the same subtraction: West Linn's zone chapters all print "Type I
        and II lands shall not be counted toward lot area when determining
        allowable floor area ratio", so the FAR that governs there is the pod's
        floor area over something smaller than the lot. Any standard whose
        value carries a `measured_on` comes through here.

        Where the denominator is a net area the lot's own area is still a
        bound on it, and a bound settles half the question. Net area is never
        more than gross, so the rate computed on the whole lot is the *lowest*
        the development could be scored at:

        * a floor cleared on the whole lot is cleared on any net area, so a
          pass is certain and the check stands;
        * a ceiling exceeded on the whole lot is exceeded on any net area, so
          a failure is certain and the check stands;
        * the other outcome in each pair depends on a survey nobody ran, and
          the honest answer is that the comparison did not happen.

        That asymmetry is worth the code. Minimum density binds only on large
        lots and maximum density only on small ones, so the certain half is
        the common case both times: most lots get a real answer here, and only
        the genuinely marginal ones fall through to the fact.
        """
        held = rules.values.get(field)
        threshold = rules.get(field)
        if held is None or held.measured_on is None or threshold is None:
            check(name, observed, threshold, is_maximum=is_maximum)
            return
        result = policy.evaluate(
            name, observed, threshold, is_maximum=is_maximum, jurisdiction=where
        )
        settled = result.verdict is (Verdict.fails if is_maximum else Verdict.passes)
        if settled:
            out.append(result)
            return
        unchecked.append(name)
        unmeasured.add(held.measured_on)

    # Fitment. The observation is the deepest run the envelope holds at the
    # width the winning orientation asked for; the threshold is what that
    # orientation had to find, plus whatever the design's own parking needs
    # behind it that the rear setback does not already give it.
    #
    # `fit.required_ft`, not `fit.depth_ft`: where the pod fits only end-on the
    # search was run against its width, and comparing the found depth to the
    # unrotated `depth_ft` passed lots that hold no run long enough for the
    # building. See :attr:`flats.fit.rectangle.Fit.required_ft`.
    #
    # The court sits between the building's rear wall and the rear lot line,
    # and the envelope has already had a rear strip taken off it -- so that
    # strip is land the court may use, and only the excess is charged
    # (`_court_beyond_rear`), against the strip the envelope really lost
    # where the lot says what that was.
    #
    # A court BESIDE the building (`fit.beside`, FOLLOWUPS 4(a)) asks past
    # the rear wall only what its row runs beyond it (`_beside_beyond`).
    beside = _beside_for(design, rules, lot) if fit.beside else None
    fitted = policy.evaluate(
        "fit_ft",
        fit.best_depth_ft,
        fit.required_ft
        + (
            _beside_beyond(beside, fit.required_ft, rules, lot.envelope_rear_ft)
            if beside is not None
            else _court_beyond_rear(
                design, rules, lot.envelope_rear_ft, lot.alley, column=fit.column
            )
        ),
        is_maximum=False,
        jurisdiction=where,
    )
    out.append(fitted)
    # And across. The court's width and the lane beside the building are
    # not a second check: they are what the envelope had to be searched FOR,
    # and `fit_for` asks the search at that width. A fit searched narrower --
    # a bare footprint, or a court sized by some other zone's stall width --
    # measured a rectangle this zone does not accept, so the depth it found is
    # no evidence either way. That is a hole in the measurement, not a miss
    # on the lot, and it is reported as one rather than scored.
    if _searched_narrower_than(
        fit, design, rules, lot.alley, corner=lot.corner, frontage_ft=lot.frontage_ft
    ):
        unchecked.append("fit_across_ft")

    # Lot area and lot width are the two standards the plat path changes, and
    # they are read through the same helper the paper fit uses. A rule file
    # that carries a townhouse lot standard on a `unit_lots` variant states it
    # per child lot, so four of them side by side is what the parent has to
    # hold; comparing the parent against one of them is the false GREEN that
    # asks a 1,500 sq ft floor of a four-unit project. Nothing in the shipped
    # catalog takes the split path today, so this moves no verdict -- it stops
    # the screen and the paper fit from answering the question differently the
    # day something does.
    per_unit = design.plat is Plat.unit_lots
    min_lot, lot_answered = lot_standard(
        rules, "min_lot_sqft", per_unit=per_unit, lots=design.units
    )
    if lot_answered:
        check("min_lot_area_sqft", lot.lot_sqft, min_lot, is_maximum=False)
    else:
        unchecked.append("min_lot_area_sqft")
    if lot.landlocked:
        # No street was found, so the frontage measurement is zero by default
        # rather than by observation. Failing the lot on a number nobody
        # measured is precisely the false RED this project exists to avoid.
        unchecked.append("min_frontage_ft")
    else:
        check("min_frontage_ft", lot.frontage_ft, rules.get("min_frontage_ft"), is_maximum=False)
    min_width, width_answered = lot_standard(
        rules, "min_lot_width_ft", per_unit=per_unit, lots=design.units
    )
    if lot.lot_width_ft is not None and width_answered:
        check("min_lot_width_ft", lot.lot_width_ft, min_width, is_maximum=False)
    else:
        unchecked.append("min_lot_width_ft")
    # And the same axis measured at the midpoints, where a code states that
    # standard too. It is not a stricter reading of the row above: a lot can
    # clear the front-line figure and fail this one, or the reverse, and a
    # screen holding one number for both would be wrong in whichever direction
    # the lot happens to taper. Unmeasured stays unchecked, so this can refuse
    # a lot that was measured narrow across the middle and can never refuse one
    # nobody measured.
    min_avg, avg_answered = lot_standard(
        rules, "min_average_lot_width_ft", per_unit=per_unit, lots=design.units
    )
    if lot.avg_lot_width_ft is not None and avg_answered:
        check("min_average_lot_width_ft", lot.avg_lot_width_ft, min_avg, is_maximum=False)
    else:
        unchecked.append("min_average_lot_width_ft")
    # The other axis. Thirty-eight zones state a minimum lot depth and nothing
    # had ever compared a lot against one, so every last one of them arrived
    # here as an unchecked standard -- encoded, cited, and never asked.
    min_depth, depth_answered = lot_standard(
        rules, "min_lot_depth_ft", per_unit=per_unit, lots=design.units
    )
    if lot.lot_depth_ft is not None and depth_answered:
        check("min_lot_depth_ft", lot.lot_depth_ft, min_depth, is_maximum=False)
    else:
        unchecked.append("min_lot_depth_ft")
    # And a ceiling on the same number, stated as a multiple of the width
    # rather than in feet: Fairview 19.30 refuses a lot more than three times
    # deeper than it is wide. It needs BOTH measurements, so a lot holding one
    # of them leaves this unchecked rather than assuming the other.
    max_ratio, ratio_answered = lot_standard(
        rules, "max_lot_depth_ratio", per_unit=per_unit, lots=design.units
    )
    if (
        ratio_answered
        and lot.lot_depth_ft is not None
        and lot.lot_width_ft is not None
        and lot.lot_width_ft > 0
    ):
        check(
            "max_lot_depth_ratio",
            lot.lot_depth_ft / lot.lot_width_ft,
            max_ratio,
            is_maximum=True,
        )
    else:
        unchecked.append("max_lot_depth_ratio")

    allowed_sqft, _source = _coverage_allowed_sqft(rules, lot.lot_sqft)
    if allowed_sqft is None:
        unchecked.append("coverage_pct")
    else:
        out.append(
            policy.evaluate(
                "coverage_pct",
                design.ground_sqft / lot.lot_sqft * 100.0,
                allowed_sqft / lot.lot_sqft * 100.0,
                is_maximum=True,
                jurisdiction=where,
            )
        )

    rate(
        "far",
        design.ground_sqft * design.stories / lot.lot_sqft,
        "max_far",
        is_maximum=True,
    )
    check("height_ft", design.height_ft, rules.get("max_height_ft"), is_maximum=True)
    # The same ceiling counted the other way, where the code counts that way.
    # Both run when a zone states both: they are two standards, and a building
    # has to clear each of them.
    check(
        "stories",
        float(design.stories),
        rules.get("max_height_stories"),
        is_maximum=True,
    )
    # And the floor. A mixed-use district that writes one is keeping a
    # single-storey box off a main street, so it is a standard about this
    # building and not about its neighbours. Both catalogued pods clear every
    # instance in the corpus; a one-storey design would not.
    check(
        "min_height_ft",
        design.height_ft,
        rules.get("min_building_height_ft"),
        is_maximum=False,
    )
    check(
        "min_stories",
        float(design.stories),
        rules.get("min_building_height_stories"),
        is_maximum=False,
    )
    check("max_units", float(design.units), rules.get("max_units"), is_maximum=True)
    # A ceiling on units per acre, measured on the lot in front of us. An acre
    # is 43,560 sq ft, and the arithmetic is done here rather than in the rule
    # file because the code states the ceiling in acres and the parcel layer
    # holds square feet.
    rate(
        "density_du_per_acre",
        design.units / (lot.lot_sqft / 43_560.0),
        "max_density_du_per_acre",
        is_maximum=True,
    )

    # A density floor, compared as a density rather than converted to a unit
    # count. Codes state the conversion differently -- Fairview rounds the
    # required units down, others round to nearest -- and a rounding rule
    # applied to the wrong jurisdiction turns a marginal lot the wrong colour
    # in whichever direction it was borrowed from. Compared this way the margin
    # is slack, and slack is what the triage bands already know how to read.
    rate(
        "min_density_du_per_acre",
        design.units / (lot.lot_sqft / 43_560.0),
        "min_density_du_per_acre",
        is_maximum=False,
    )

    # Minimum density only bites above the lot size that triggers it.
    trigger = rules.get("min_density_trigger_lot_sqft")
    required_units = rules.get("min_units_at_trigger")
    if trigger is not None and required_units is not None and lot.lot_sqft >= trigger:
        out.append(
            policy.evaluate(
                "min_units",
                float(design.units),
                float(required_units),
                is_maximum=False,
                jurisdiction=where,
            )
        )

    # The stalls the design provides against what the law asks. For a rear
    # court that is the charged count -- the design's floor raised to this
    # minimum -- so the only way it fails is a cap below the minimum, a code
    # at war with itself; the lot's own room for the row is the fit check
    # above, searched at exactly this width. A design that parks nowhere the
    # lot has to give room for (under the building, on the street) provides
    # its floor. Kept as a check so a zone that states a minimum reads as
    # measured against it, and one that states none reads as the hole it is.
    per_unit = rules.get("parking_min_per_unit")
    if per_unit is None:
        unchecked.append("parking_stalls")
    else:
        provided = court_across(design, rules).stalls or math.ceil(design.stalls_required)
        out.append(
            policy.evaluate(
                "parking_stalls",
                float(provided),
                float(per_unit) * design.units,
                is_maximum=False,
                jurisdiction=where,
            )
        )

    # And the other way round: a ceiling below the least this product is
    # built with. Portland's EX permits half a stall per home -- two on a
    # fourplex -- and a court of two is not this design whatever the lot
    # holds; the county map refuses the same plan as ``too_few_stalls``.
    # Read against the design's floor, not the zone's minimum: Portland
    # states no minimum, so the check above never runs there, and until
    # 2026-09-18 a lot under that cap screened GREEN on a court the code
    # will not permit. A design that parks nothing on the lot has no floor
    # a cap can undercut.
    cap = rules.get("parking_max_per_unit")
    if cap is not None and design.parking.parks:
        out.append(
            policy.evaluate(
                "parking_cap",
                float(math.floor(round(cap * design.units, 6))),
                float(math.ceil(round(design.stalls_required, 6))),
                is_maximum=False,
                jurisdiction=where,
            )
        )

    # What the lot has left over for the open space and landscaping a code
    # asks of it: the lot less the building AND less the pavement its parking
    # takes -- the court, the way in to it, the back-out room an alley leaves
    # short (:func:`flats.score.paper.paved`). Every code that asks for either
    # says pavement does not count towards it: Portland 33.110.240's outdoor
    # area may not be vehicle area, Happy Valley 16.42.030(A)(8) names
    # driveways and parking outright. Until 2026-09-28 (FOLLOWUPS 7(a)) this
    # was the lot less the building alone, and labelled optimistic for it: on
    # the pod's court and lane that credited some 2,500 sq ft of asphalt as
    # garden on every lot, so the check could only ever fail a lot with no
    # room by the building alone. The county map has always subtracted the
    # pavement (s6s ``offer``) and found none of its 46,212 drawn plans short
    # on amount, so this is expected to move few colours or none -- but a
    # screen answering a looser question than the code's is the false-GREEN
    # shape, whatever it happens to cost today.
    #
    # Where the pavement is unknown -- a design parked in a way nothing draws,
    # or a way in whose yard the code does not state -- the lot less the
    # building is still an UPPER bound on the leftover, and a bound settles
    # half the question, as it does for a density on a net acre (`rate`): a
    # standard missed with nothing paved is missed with anything paved, so a
    # failure stands; a pass is not evidence, so the check goes unrun and the
    # lot is held out of GREEN on the fact nobody measured. Never a pass on a
    # leftover larger than the one a plan could leave.
    #
    # The SHAPE -- Portland's 12 by 12 square outside the front setback,
    # Milwaukie's 96 sq ft patio off each ground-floor home -- is a different
    # question from the amount answered here, and `_outdoor_shape` asks it.
    pavement = paved(
        design,
        rules,
        lot.alley,
        corner=lot.corner,
        column=fit.column,
        beside=beside,
        deep_ft=fit.required_ft,
    )
    bound_sqft = lot.lot_sqft - design.ground_sqft

    def leftover(name: str, field: str, *, share: bool) -> None:
        threshold = rules.get(field)
        if threshold is None:
            return
        room = bound_sqft if pavement is None else bound_sqft - pavement
        result = policy.evaluate(
            name,
            room / lot.lot_sqft * 100.0 if share else room,
            float(threshold),
            is_maximum=False,
            jurisdiction=where,
        )
        if pavement is None and result.verdict is not Verdict.fails:
            unchecked.append(name)
            unmeasured.add(UNPAVED)
            return
        out.append(result)

    # Landscaping is distinct from open space -- nobody has to be able to sit
    # in it, and it is written against the whole site -- but it is the same
    # ground, and the same pavement comes off it. Portland asks 30 percent in
    # RM1; Happy Valley, Oregon City, Fairview and Wilsonville state it too.
    leftover("landscaped_pct", "min_landscaped_pct", share=True)
    leftover("open_space_pct", "open_space_min_pct", share=True)
    # And open space stated as an area rather than a share: Portland asks 250
    # sq ft whatever the lot (200 in R2.5, 48 a home in RM1), Milwaukie 96 per
    # ground-floor home, Multnomah LR-7 300 a home. A city stating both means
    # both. Encoded, cited, and read by nothing until 2026-09-28 -- the reach
    # ledger carried it in `SILENTLY_UNREAD` from the day that set was
    # written. A per-dwelling figure arrives multiplied out by the loader, so
    # the threshold is what the four homes owe together.
    leftover("open_space_sqft", "open_space_min_sqft", share=False)
    _outdoor_shape(rules, lot, design, fit, fitted, policy, out, unchecked, unmeasured)

    return out, unchecked, unmeasured


def _outdoor_shape(
    rules: ZoneResolution,
    lot: LotFacts,
    design: Design,
    fit: Fit,
    fitted: CheckResult,
    policy: SlackPolicy,
    out: list[CheckResult],
    unchecked: list[str],
    unmeasured: set[str],
) -> None:
    """Whether the open space the amount check counted comes in the SHAPE asked.

    FOLLOWUPS 7(b). Two codes state a shape beside the amount, and an amount
    is no evidence of either: a lot with thousands of square feet left over
    can hold no 12 ft square once a turned pod, its lane and its court stand
    on it.

    * **One square, anywhere legal** (``open_space_min_dimension_ft``):
      Portland 33.110.240 -- 250 sq ft (200 in R2.5) in one piece that a 12
      by 12 square (10 by 10) fits inside, off vehicle area, outside the
      front building setback, allowed into the side and rear setbacks.
    * **A patio off each home** (``private_open_space_min_dimension_ft``):
      Milwaukie 19.505.3.D.1 -- 96 sq ft per ground-floor home, 5 ft its
      least dimension, directly accessible from the unit.

    What the screen knows of the ground is the fit: a window ``across_ft``
    wide and ``best_depth_ft`` deep, the building at its front, the court
    behind, and how far the court could still slide back (the fit check's
    slack, which already counts the rear strip the court may use). Nothing
    here knows the lot outside that window. So a shape found inside the
    window is PROVEN and the check passes; a shape not found there may still
    exist beside it, and the honest answer is that nobody measured it -- the
    lot is held out of GREEN on the fact (``UNSHAPED``), never failed on it.
    Measured on run 0928, that holds some 4,200 Portland single-dwelling
    greens (a pod turned end-on on a 50 ft lot, where the court fills the
    window) and no Milwaukie lot, where nothing is green today.
    """
    where = rules.jurisdiction
    parks = design.parking.parks
    across = court_across(design, rules, lot.alley, corner=lot.corner)
    # Ground behind the court the court need not use: the fit's own spare
    # depth, across the whole searched width. Never negative.
    behind = max(0.0, fitted.observed - fitted.threshold)

    def proven(name: str, observed: float | None, threshold: float) -> None:
        if observed is not None and observed >= threshold:
            out.append(
                policy.evaluate(name, observed, threshold, is_maximum=False, jurisdiction=where)
            )
            return
        unchecked.append(name)
        unmeasured.add(UNSHAPED)

    area = rules.get("open_space_min_sqft")
    side = rules.get("open_space_min_dimension_ft")
    if side is not None:
        side = float(side)
        need = float(area) if area is not None else side * side
        best: float | None = None
        if fit.across_ft is not None and fit.orientation is not None:
            regions = [(fit.across_ft, behind)]
            if not fit.column:
                # Beside the court, behind the building: the window's width
                # less the paved row (or the lane reaching it, if wider), as
                # deep as the window runs past the building's rear wall.
                paved_w = max(across.width_ft, across.lane_ft) if parks else 0.0
                regions.append(
                    (fit.across_ft - paved_w, max(0.0, fit.best_depth_ft - fit.required_ft))
                )
            for w, d in regions:
                if w > 0 and w * d >= need:
                    shape = min(w, d)
                    best = shape if best is None else max(best, shape)
        proven("open_space_shape", best, side)

    patio = rules.get("private_open_space_min_dimension_ft")
    if patio is not None:
        patio = float(patio)
        each = float(area) / design.units if area is not None else patio * patio
        unit_w = design.footprint.width_ft / design.units
        deep: float | None = None
        if fit.across_ft is not None and fit.orientation is Orientation.width_facing:
            # Behind each home's rear wall: the standoff before the first
            # stall is not pavement, and the court can slide back by the
            # fit's spare depth. The front yard is not counted -- whether a
            # patio may stand in Milwaukie's 20 ft front setback is a ruling
            # nobody has made.
            gap = design.parking.building_gap_ft if parks else 0.0
            if parks and (stated := rules.get("parking_building_buffer_ft")) is not None:
                gap = max(gap, float(stated))
            deep = gap + behind
        elif fit.across_ft is not None and fit.orientation is Orientation.depth_facing:
            # Turned end-on, each home opens on a flank; the only flank strip
            # the window holds is what the court's row left beside the
            # building on the side away from the lane.
            deep = max(0.0, fit.across_ft - fit.depth_ft - across.lane_ft)
        got = min(unit_w, deep) if deep is not None and unit_w * deep >= each else None
        proven("private_open_space_shape", got, patio)


def _unconfirmed(outcomes: Sequence[ReliefOutcome]) -> tuple[str, ...]:
    """Whether this answer leans on a relief path nobody has read.

    A yellow resting on an assumed adjustment chapter is still the right
    colour — assuming relief exists is the recall-biased default — but it is a
    claim, and a claim has to say so.
    """
    leaning = any(o.available and not o.confirmed for o in outcomes)
    return (RELIEF_UNCONFIRMED,) if leaning else ()


def _unencoded(field: str, rules: ZoneResolution) -> bool:
    """Whether a standard the screen could not measure against is a hole.

    Only a required field nothing supplies is one. Two other silences look
    the same from the check's side and are answers, not holes, and the
    resolver already tells them apart when it counts ``missing_required``:
    the code was read and states no such standard (``exempt: true`` --
    Portland has no parking minimum), or states it in the other unit (a
    storey cap where the chapter prints no height in feet). Reporting either
    as "we never encoded it" sends somebody to look for a number that does
    not exist, and -- found by the first county run, 2026-09-17 -- left every
    Portland lot uncertifiable however many signatures it collected.
    """
    if field not in REQUIRED_FIELDS or field in rules.exempted:
        return False
    alternative = ALTERNATIVES.get(field)
    return alternative is None or alternative not in rules.values


def _court_beyond_rear(
    design: Design,
    rules: ZoneResolution,
    carved_rear_ft: float | None = None,
    alley: Alley | None = None,
    *,
    column: bool = False,
    stalls: int | None = None,
) -> float:
    """Depth the parking court needs past the envelope's rear edge, in feet.

    The court sits between the building's rear wall and the rear lot line,
    and the envelope has already had a rear setback taken off it -- so that
    strip is land the court may use, and only the excess is charged. This is
    the same overlap ``paper_fit`` states as ``max(rear, court)``; where a
    jurisdiction bars parking from a required rear yard the two would stack
    instead, which is an unmeasured condition on the human list rather than a
    thing assumed away here. A zone stating no rear setback charges the whole
    court, which is both conservative and correct: no yard, no shared ground.

    ``carved_rear_ft`` is the strip the envelope actually lost, when that is
    not the number these rules resolve (:attr:`LotFacts.envelope_rear_ft`).
    The building must stand the RESOLVED rear setback off the line and the
    court needs its own depth behind the wall, so the ground behind the wall
    is ``max(court, rear)`` either way; what the envelope still owes of it is
    that less the strip already cut. With the two numbers equal this is the
    old ``max(0, court - rear)``. With the rules relaxing the rear below the
    cut (Portland's 0 ft against a commercial neighbour, envelope cut at 10)
    the strip is wider than the rules ask and the court parks in it; with the
    rules tightening above the cut (Oregon City's 20 ft against a house,
    envelope cut at 0) the wall has to move that much deeper into the
    envelope, and the charge says so. Never negative: a strip deeper than the
    court hands the building back no depth.

    ``alley`` is the lot's alley, where it has one: the court it feeds from
    the rear may be a stall and a back-out shortfall rather than a stall and
    an aisle (:func:`flats.score.paper.court_depth`). ``column`` charges the
    other plan a side alley allows, ``stalls`` of them standing along it
    (:func:`flats.score.paper.side_column`); the caller asks for it only
    where that plan exists. For the row, ``stalls`` is the count a
    part-covered rear alley has to be long enough for before it serves as
    the aisle (:meth:`flats.score.paper.Alley.rear_aisle_for`); the charged
    floor when omitted.
    """
    if column:
        got = side_column(design, rules, alley, stalls)
        assert got is not None, "a column court was charged where no side alley offers one"
        court = got[0]
    else:
        court, _court_from_code = court_depth(design, rules, alley, stalls)
    rear_held = rules.get("setback_rear_ft")
    rear_ft = float(rear_held) if isinstance(rear_held, (int, float)) else 0.0
    carved = rear_ft if carved_rear_ft is None else float(carved_rear_ft)
    return max(0.0, max(court, rear_ft) - carved)


def _beside_for(design: Design, rules: ZoneResolution, lot: LotFacts) -> Beside:
    """The court beside the building that :func:`fit_for` searched for this lot."""
    got = side_court(design, rules, lot.alley, corner=lot.corner, frontage_ft=lot.frontage_ft)
    assert got is not None, "a court beside the building was charged where none is offered"
    return got


def _beside_beyond(
    beside: Beside,
    deep_ft: float,
    rules: ZoneResolution,
    carved_rear_ft: float | None = None,
) -> float:
    """Depth a court BESIDE a building ``deep_ft`` deep needs past the
    envelope's rear edge (:func:`flats.score.paper.side_court`).

    The court behind the building needs its whole depth behind the wall
    (:func:`_court_beyond_rear`); this one stands beside the building and
    needs behind the wall only what its row runs past it
    (:meth:`flats.score.paper.Beside.overhang_ft`) -- nothing where the row
    is no longer than the building is deep. The building itself still has to
    stand the RESOLVED rear setback off the line, and that part runs past
    the wall into the same yard, so the two share it on the court-behind
    bargain: the ground behind the wall is the deeper of the overhang and
    the rear setback, less the strip the envelope already lost. ``inf``
    where the row may not run past the wall and would.
    """
    overhang = beside.overhang_ft(deep_ft)
    if math.isinf(overhang):
        return math.inf
    rear_held = rules.get("setback_rear_ft")
    rear_ft = float(rear_held) if isinstance(rear_held, (int, float)) else 0.0
    carved = rear_ft if carved_rear_ft is None else float(carved_rear_ft)
    return max(0.0, max(overhang, rear_ft) - carved)


def seats(
    fitter: Fitter,
    design: Design,
    rules: ZoneResolution,
    *,
    axis_required: bool = False,
    carved_rear_ft: float | None = None,
    alley: Alley | None = None,
    corner: bool = False,
    frontage_ft: float | None = None,
    street_deg: tuple[float, ...] = (),
) -> int | None:
    """How many stalls the lot seats -- the number beside the colour.

    Counts up from the charged floor to the most the zone lets the design
    draw (:attr:`flats.score.paper.Across.most`), asking the envelope at
    each count for a row that wide beside the building, at the depth the
    building and its court need past the rear yard, in every orientation
    the zone allows, and keeps the best. Same shape as the county map's
    ``stalls_provided`` since 2026-07-28: a lot is green at the floor and
    the count says how much more it holds. Steph, 2026-09-18: *"same as the
    county map. 4 is enough to sell."*

    Cheap on purpose. A count whose row is no wider than the building and
    its lane costs nothing -- the floor's search already found that window
    -- and each wider one is a single yes/no over the grids
    (:meth:`flats.fit.rectangle.Fitter.holds`), stopping at the first no.
    The pod's 56 ft side and 12 ft lane are 68 ft across, which seats seven
    at 9 ft for free; only the eighth is a question.

    Beside a side alley the stalls may stand in a column along it instead
    (:func:`flats.score.paper.side_column`): no wider than the building, one
    stall's width deeper per car. Each count is asked of both plans and the
    lot seats the most either holds.

    Where the code leaves the side of the building open to a court
    (:func:`flats.score.paper.side_court`) the row may stand BESIDE the
    building instead, along the lot: the building's side plus the court's
    band across, and one stall's width further along per car, charged past
    the rear wall only where the row outruns the building, searched only
    along the street (``street_deg``, :meth:`Fitter.fit_beside`). The same
    count, asked of that plan too.

    Still one row, behind or beside. The county map also draws two rows
    either side of one aisle where the room behind is deep enough, and
    counts more on those lots than this does (FOLLOWUPS 4(a)); the colour
    is charged at the floor and does not move on it.

    Returns 0 where not even the floor holds at that depth, and ``None``
    for a design with no court to count.
    """
    across = court_across(design, rules, alley, corner=corner)
    if not across.stalls:
        return None
    # The depth behind the building per count: a row longer than the stretch
    # a part-covered rear alley runs keeps its own aisle (Steph 2026-09-28).
    behind = {
        n: _court_beyond_rear(design, rules, carved_rear_ft, alley, stalls=n)
        for n in range(across.stalls, across.most + 1)
    }
    column = side_column(design, rules, alley) is not None
    best = 0
    for _orientation, side, deep in design.oriented(axis_required=axis_required):
        seated = 0
        held: tuple[float, float] | None = None
        for n in range(across.stalls, across.most + 1):
            ask = (max(side + across.lane_ft, n * across.stall_ft), deep + behind[n])
            if ask != held and not fitter.holds(*ask):
                break
            held = ask
            seated = n
        if column:
            for n in range(max(seated + 1, across.stalls), across.most + 1):
                along = deep + _court_beyond_rear(
                    design, rules, carved_rear_ft, alley, column=True, stalls=n
                )
                if not fitter.holds(side + across.lane_ft, along):
                    break
                seated = n
        for n in range(max(seated + 1, across.stalls), across.most + 1):
            if not street_deg:
                break
            row = side_court(design, rules, alley, corner=corner, frontage_ft=frontage_ft, stalls=n)
            if row is None:
                break
            extra = _beside_beyond(row, deep, rules, carved_rear_ft)
            if math.isinf(extra) or not fitter.holds(
                side + row.band_ft, deep + extra, angles=street_deg
            ):
                break
            seated = n
        best = max(best, seated)
    return best


def _searched_narrower_than(
    fit: Fit,
    design: Design,
    rules: ZoneResolution,
    alley: Alley | None = None,
    *,
    corner: bool = False,
    frontage_ft: float | None = None,
) -> bool:
    """Whether the fit's search was narrower than this zone's parking asks.

    The width asked is the paper lot's (:func:`flats.score.paper.court_across`):
    the building in the orientation that won, plus its lane, or the court,
    whichever is wider. A fit that never recorded a search width
    (``across_ft`` is None) was built around the bare footprint, and reads as
    searched at the building's own side.
    """
    across = court_across(design, rules, alley, corner=corner)
    facing = fit.orientation or Orientation.width_facing
    side = (
        design.footprint.width_ft
        if facing is Orientation.width_facing
        else design.footprint.depth_ft
    )
    # A column along a side alley stands inside the building's side
    # (:func:`flats.score.paper.side_column`), so that plan asks no more.
    # A court beside the building asks its band beside it, and no lane.
    if fit.beside:
        got = side_court(design, rules, alley, corner=corner, frontage_ft=frontage_ft)
        if got is None:
            return True
        asked = side + got.band_ft
    elif fit.column:
        asked = side + across.lane_ft
    else:
        asked = max(side + across.lane_ft, across.width_ft)
    searched = side if fit.across_ft is None else fit.across_ft
    return searched + 1e-9 < asked


def fit_for(
    fitter: Fitter,
    design: Design,
    rules: ZoneResolution,
    *,
    placement: bool = True,
    carved_rear_ft: float | None = None,
    alley: Alley | None = None,
    corner: bool = False,
    frontage_ft: float | None = None,
    street_deg: tuple[float, ...] = (),
) -> Fit:
    """The fit :func:`screen` expects for this design in this zone.

    The envelope is searched at what the zone's parking asks across the lot
    -- the design's lane and court, raised by the city's driveway minimum and
    stall width and cut by its parking cap, exactly as the paper lot charges
    them -- and the flip is forbidden where the code makes the building face
    the street. A fit built any other way is reported by the screen as
    ``COURT_WIDTH_UNMEASURED`` wherever it was searched too narrow.

    ``carved_rear_ft`` is the rear strip the envelope was cut with when that
    was not these rules' number (:attr:`LotFacts.envelope_rear_ft`); the
    seat count charges the court against it the way the fit check does.

    ``alley`` is the lot's alley (:attr:`LotFacts.alley`): where the code
    sends the driveway to it there is no lane beside the building to search
    for, and where the alley is the aisle the court is shallower. Beside a
    side alley that lets the stalls stand in a column along it
    (:func:`flats.score.paper.side_column`) the lot is searched a second
    time for that plan, at the building's own side, and the fit with more
    room to spare past its court is the one the screen reads
    (:attr:`flats.fit.rectangle.Fit.column` says which).

    ``corner`` is :attr:`LotFacts.corner`: where the code lets a corner
    lot's driveway use the side street there is no lane to search for
    either (:func:`flats.score.paper.side_street_fed`).

    THE COURT'S SHAPE (FOLLOWUPS 4(a)). Where the row behind the building
    does not fit, and the code leaves the side of the building open to a
    court (:func:`flats.score.paper.side_court`, which also reads
    ``frontage_ft`` against a cap on parking along the street), the lot is
    searched once more for the court BESIDE the building -- the stalls
    along the lot, the aisle along the building's wall and in from the
    street, so searched only at the street's directions (``street_deg``;
    none known, no court beside) -- and that fit is read where it clears
    with its court
    (:attr:`flats.fit.rectangle.Fit.beside`). A lot the row already fits
    keeps the row: the drawing every code here describes, and the one this
    screen has always charged; so does a lot neither arrangement fits, whose
    near miss was always measured on the row.
    """
    across = court_across(design, rules, alley, corner=corner)
    axis_required = rules.get("orientation_constraint") == "axis_required"
    fit = fitter.fit_design(
        design,
        axis_required=axis_required,
        placement=placement,
        lane_ft=across.lane_ft,
        court_width_ft=across.width_ft,
    )
    if side_column(design, rules, alley) is not None:
        beside = fitter.fit_design(
            design,
            axis_required=axis_required,
            placement=placement,
            lane_ft=across.lane_ft,
            court_width_ft=0.0,
        )
        row_room = fit.slack_ft - _court_beyond_rear(design, rules, carved_rear_ft, alley)
        column_room = beside.slack_ft - _court_beyond_rear(
            design, rules, carved_rear_ft, alley, column=True
        )
        if column_room > row_room:
            fit = dataclasses.replace(beside, column=True)
    room = fit.slack_ft - _court_beyond_rear(
        design, rules, carved_rear_ft, alley, column=fit.column
    )
    court = (
        side_court(design, rules, alley, corner=corner, frontage_ft=frontage_ft)
        if room < 0
        else None
    )
    if court is not None:
        got = fitter.fit_beside(
            design.footprint.width_ft,
            design.footprint.depth_ft,
            band_ft=court.band_ft,
            beyond=lambda deep: _beside_beyond(court, deep, rules, carved_rear_ft),
            angles=street_deg,
            allow_flip=not axis_required,
            placement=placement,
        )
        # Taken only where it CLEARS: a lot neither arrangement fits keeps
        # the court behind, the one its near-miss and relief were read on.
        if got is not None and (
            got.slack_ft - _beside_beyond(court, got.required_ft, rules, carved_rear_ft) >= 0
        ):
            fit = got
    # And how many more the lot seats, floor to preferred: the number the
    # screen reports beside the colour (:func:`seats`).
    return dataclasses.replace(
        fit,
        stalls=seats(
            fitter,
            design,
            rules,
            axis_required=axis_required,
            carved_rear_ft=carved_rear_ft,
            alley=alley,
            corner=corner,
            frontage_ft=frontage_ft,
            street_deg=street_deg,
        ),
    )


def screen(
    rules: ZoneResolution,
    lot: LotFacts,
    design: Design,
    fit: Fit,
    *,
    policy: SlackPolicy,
    relief: ReliefPolicy | None = None,
    config: Configuration | None = None,
) -> Screening:
    """Turn measurements into GREEN / YELLOW / RED / UNKNOWN for one lot and design.

    ``config`` is what the resolution was asked under — see
    :func:`flats.score.configure.configure`. Passing it is what lets the
    verdict tell a number the code states from a number that depended on a
    site fact we guessed at. Omitting it does not change any check; it only
    means the guesses go unreported, which is why every batch caller should
    pass one.
    """
    reasons: list[str] = []
    paths = relief if relief is not None else ReliefPolicy()

    if lot.lot_sqft <= 0:
        return Screening(triage=Triage.unknown, reasons=(GEOMETRY_UNREADABLE,))

    where = rules.jurisdiction
    across = court_across(design, rules, lot.alley, corner=lot.corner)
    checks, unchecked, unmeasured = _checks(rules, lot, design, fit, policy)
    blockers = tuple(binding(checks))
    optimistic = tuple(sorted({c.check for c in checks} & OPTIMISTIC_CHECKS))
    worst_check = dominant(checks)

    # Every definite failure gets a second question: what would it take to
    # clear this anyway? A miss with a path is an application, not a wall.
    failing = [c for c in checks if c.verdict is Verdict.fails]
    outcomes = [
        paths.for_check(
            c.check, shortfall=c.shortfall, threshold=c.threshold, jurisdiction=where
        )
        for c in failing
    ]

    # The use gate is categorical, not a margin: a zone that forbids fourplexes
    # forbids them by any amount of slack. Its only exit is a conditional use,
    # and unlike an adjustment that exit has to be enumerated to exist.
    allowed = rules.get("quadplex_allowed")
    use_blocked = allowed is False and rules.trusted
    if use_blocked:
        outcomes.append(paths.for_use(where))

    hardest = _hardest_ask(outcomes)
    common: dict[str, Any] = {
        "checks": tuple(checks),
        "binding": blockers,
        "dominant": worst_check.check if worst_check else None,
        "unchecked": tuple(unchecked),
        "optimistic": optimistic,
        # The fit check's own slack, not the raw geometry's: the number a
        # developer argues with is the one that includes the ground the cars
        # need and the orientation the pod actually stood in. `fit.slack_ft`
        # knows about neither.
        "fit_slack_ft": next((c.slack for c in checks if c.check == "fit_ft"), fit.slack_ft),
        "stalls_charged": across.stalls,
        "stalls_seated": fit.stalls,
        # A band only from the design's floor up: below it the count is
        # the charge a cap cut short (parking_cap says so) or a row the
        # lot does not hold (fit_ft does), and the colour already speaks.
        "parking_band": (
            design.parking_band(fit.stalls)
            if fit.stalls is not None
            and fit.stalls >= across.stalls > 0
            and fit.stalls >= design.stalls_required
            else None
        ),
        "ask": hardest.tier if hardest else Tier.as_of_right,
        "relief": tuple(outcomes),
        "tight_fit": any(
            c.check == "fit_ft" and c.tolerance > 0 and abs(c.slack) <= c.tolerance
            for c in checks
        ),
    }

    if use_blocked:
        if not paths.for_use(where).available:
            return Screening(triage=Triage.red, reasons=(USE_PROHIBITED,), **common)
        return Screening(
            triage=Triage.yellow, reasons=(USE_PROHIBITED, *_unconfirmed(outcomes)), **common
        )

    if not rules.trusted:
        # An unverified standard may not delete a lot, and a failure measured
        # against one is not a definite failure. Whatever the checks say, this
        # is a question for a human.
        reason = rules.reason
        return Screening(
            triage=Triage.unknown, reasons=tuple(r for r in (reason,) if r), **common
        )

    if allowed is None:
        reasons.append(USE_NOT_ENCODED)
    if config is not None:
        # An assumption only matters where a standard here turns on it.
        # Wilsonville states no corner-lot exception in most zones, so
        # assuming a lot is not a corner changes nothing there and must not
        # cost it a GREEN; where the exception exists, the same assumption is
        # load-bearing and the lot cannot be certified on it.
        leaning = config.leans_on(rules.levers)
        if any(name in config.unknown for name in leaning):
            reasons.append(FACT_UNOBSERVED)
        if any(name in config.assumed for name in leaning):
            reasons.append(FACT_ASSUMED)
    if lot.landlocked:
        reasons.append(NO_FRONTAGE)
    if lot.geometry is GeometryTier.irregular:
        reasons.append(GEOMETRY_UNREADABLE)
    if lot.street_unconfirmed:
        reasons.append(STREET_UNCONFIRMED)
    if "fit_across_ft" in unchecked:
        reasons.append(COURT_WIDTH_UNMEASURED)
    if any(_unencoded(CHECK_FIELD.get(name, name), rules) for name in unchecked):
        reasons.append(STANDARD_NOT_ENCODED)
    if unmeasured and FACT_UNOBSERVED not in reasons:
        # A standard stated per a quantity nobody surveyed, on a lot whose own
        # area could not settle it either way. Reported whether or not the
        # caller passed a configuration: this one is not an assumption the
        # caller made, it is the code naming a denominator this project does
        # not hold.
        reasons.append(FACT_UNOBSERVED)

    if any(not o.available for o in outcomes):
        # A verified standard the code offers no way around. Nothing still
        # unencoded can rescue this — missing rules only ever add constraints.
        return Screening(triage=Triage.red, reasons=tuple(reasons), **common)

    if outcomes:
        # Definite failures, every one of them with a path. That is an answer,
        # so it outranks whatever else is still missing: the gaps ride along in
        # `reasons` and can only add asks, never remove this one.
        return Screening(
            triage=Triage.yellow, reasons=(*reasons, *_unconfirmed(outcomes)), **common
        )

    # A fit inside its tolerance is GREEN with the flag (``tight_fit``, Steph
    # 2026-09-25); any other check inside its tolerance still holds the lot.
    if reasons or any(
        c.verdict is Verdict.tolerated and c.check != "fit_ft" for c in checks
    ):
        # Nothing definitely failed, and nothing can be certified either.
        return Screening(triage=Triage.unknown, reasons=tuple(reasons), **common)

    return Screening(triage=Triage.green, reasons=(), **common)


@dataclass(frozen=True, slots=True)
class BindingHistogram:
    """How often each constraint was the tightest one — the rule-cost ledger."""

    counts: dict[str, int] = _dc_field(default_factory=dict)

    def ranked(self) -> list[tuple[str, int]]:
        return sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0]))


def histogram(results: Sequence[Screening]) -> BindingHistogram:
    """Count the head constraint across a run.

    The point is not the total. It is seeing that one setback line costs eight
    thousand lots, which turns an encoded number into an argument worth having
    with a planning department.
    """
    counts: dict[str, int] = {}
    for r in results:
        if r.dominant is not None:
            counts[r.dominant] = counts.get(r.dominant, 0) + 1
    return BindingHistogram(counts)


def backlog(results: Sequence[Screening]) -> dict[str, int]:
    """Reason codes across a run, most common first — the encoding work queue.

    Counted from ``reasons`` rather than from the UNKNOWN colour on purpose. A
    lot can be YELLOW on a definite miss and still be missing an encoded
    parking standard, and that gap is just as much work as one holding a lot in
    UNKNOWN. Counting colours would hide it.
    """
    counts: dict[str, int] = {}
    for r in results:
        for reason in r.reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


__all__ = [
    "GEOMETRY_UNREADABLE",
    "NO_FRONTAGE",
    "OPTIMISTIC_CHECKS",
    "RELIEF_UNCONFIRMED",
    "STANDARD_NOT_ENCODED",
    "STREET_UNCONFIRMED",
    "USE_NOT_ENCODED",
    "USE_PROHIBITED",
    "BindingHistogram",
    "LotFacts",
    "ReliefPolicy",
    "RuleVerdict",
    "Screening",
    "Tier",
    "Triage",
    "backlog",
    "histogram",
    "screen",
]
