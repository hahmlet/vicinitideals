"""Condition registry — the single place FLATS names something a result depends on.

A screening result is never a bare verdict. It is a verdict *under a
configuration*: a building variant, plus whatever the developer elects, plus
whatever we believe about the lot. This module is the vocabulary for the second
and third of those, and it exists for the same reason
:mod:`flats.rules.fields` does — so that nothing invents a condition inline.
An unregistered condition is a typo waiting to split one concept into two.

Four kinds, and the difference is *who can change the answer*:

``elective``    the developer decides. Affordable units, ground-floor
                commercial, a bonus program. Electing one is a business
                decision with a cost, not a fact about the parcel.

``site_fact``   true or false about the parcel, whoever wants it otherwise. A
                corner, an alley, sewer in the street, a slope. We observe
                these, and on a single lot the user may override us, because
                they have stood on it and we have not.

``design_fact`` true of the building we are trying to place, and read off the
                catalog entry rather than the lot. Codes routinely state a
                deeper setback for the second storey — Wilsonville 4.113(.02)
                asks seven feet where one storey asks five. Nobody elects that
                and no survey settles it: the pod either has two storeys or it
                does not, and the same lot answers differently for two designs.
                Separate from ``elective`` because choosing a different pod is
                choosing a different screen, not taking an incentive within
                this one.

``relief``      an approval the developer applies for. An adjustment to a
                setback is elective in exactly the way affordability is — a
                choice with a cost and a risk — so it belongs here rather than
                in a special case inside the scoring stage.

Registering relief as a condition is what keeps the traffic light honest. A pod
one foot over a setback is not an uncertain lot; it is a certain lot with an
application attached, and the colour it earns is YELLOW, not RED. See
FLATS_PLAN section 14.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Iterable, Literal

Kind = Literal["elective", "site_fact", "design_fact", "relief"]


class Tier(str, enum.Enum):
    """How hard the ask is. Ordered from "no ask" to "nobody may waive this"."""

    #: Permitted outright. No application, no discretion.
    as_of_right = "as_of_right"
    #: A staff-level decision. No hearing, no notice, routinely granted.
    administrative = "administrative"
    #: Public review with a hearing and an appeal window. Slow and uncertain,
    #: but a real path — plenty of built projects went through one.
    discretionary = "discretionary"
    #: No procedure exists. State building code, fire apparatus access,
    #: federal floodplain rules. This is the only tier that earns a RED.
    unavailable = "unavailable"

    @property
    def rank(self) -> int:
        return _RANK[self]

    @property
    def needs_ask(self) -> bool:
        """True when clearing this way requires an application."""
        return self in (Tier.administrative, Tier.discretionary)

    @property
    def available(self) -> bool:
        """True when some path exists, however painful."""
        return self is not Tier.unavailable


_RANK: dict[Tier, int] = {
    Tier.as_of_right: 0,
    Tier.administrative: 1,
    Tier.discretionary: 2,
    Tier.unavailable: 3,
}

#: What to assume about a dimensional standard whose relief path nobody has
#: encoded yet. Assuming `unavailable` would turn every unencoded jurisdiction's
#: near-misses red, and a false red silently deletes an acquisition target. A
#: false yellow costs one review, so the default runs that way and the result
#: carries a reason code saying the claim is unconfirmed.
ASSUMED_TIER = Tier.discretionary

#: The exception. Codes enumerate conditional uses explicitly, so a zone that
#: does not list one has no conditional-use path — silence there is evidence of
#: absence in a way that silence about adjustments is not.
ASSUMED_USE_TIER = Tier.unavailable


@dataclass(frozen=True, slots=True)
class ConditionDef:
    """One named condition a screening result may depend on."""

    name: str
    kind: Kind
    describe: str
    #: What establishes this. For a site fact, the data layer that answers it;
    #: for an elective, what the developer commits to; for relief, the kind of
    #: code procedure. Empty means we have no source yet — which is a gap, and
    #: the screen reports it rather than guessing.
    evidence: str = ""
    #: What to assume for a site fact across a batch, where there is nobody to
    #: ask. ``None`` means do not assume: the lot is UNKNOWN if it matters.
    #: A relied-upon assumption never produces a GREEN — see FLATS_PLAN 13.
    assume: bool | None = None
    #: Procedure depth. Required for ``relief``, meaningless otherwise.
    tier: Tier | None = None

    def __post_init__(self) -> None:
        if self.kind == "relief" and self.tier is None:
            raise ValueError(f"{self.name}: a relief condition must state its tier")
        if self.kind != "relief" and self.tier is not None:
            raise ValueError(f"{self.name}: only relief conditions carry a tier")
        if self.kind != "site_fact" and self.assume is not None:
            raise ValueError(f"{self.name}: only a site fact can be assumed")


_C: tuple[ConditionDef, ...] = (
    # --- elective: the developer decides -------------------------------
    ConditionDef(
        "affordable",
        "elective",
        "Regulated affordable units, at the AMI level the incentive names. "
        "Footnotes routinely loosen a standard in exchange for this.",
        evidence="developer commitment, recorded as a covenant",
    ),
    ConditionDef(
        "mixed_use",
        "elective",
        "Ground-floor non-residential space, where a zone rewards or requires it.",
        evidence="developer commitment",
    ),
    ConditionDef(
        "bonus_program",
        "elective",
        "A named height/FAR bonus the code offers in exchange for something. "
        "Portland Table 110-4 footnote 3 points at one; the terms are unread.",
        evidence="developer commitment plus the bonus chapter own criteria",
    ),
    ConditionDef(
        "farm_labor_housing",
        "elective",
        "The four units are being built as registered farm labor housing "
        "rather than as market housing. Multnomah County's Exclusive Farm Use "
        "zone is the one resource district in this corpus that names this "
        "building's form: an accessory farm dwelling may be \"attached "
        "multi-unit residential structures allowed by the applicable state "
        "building code or similar types of farm labor housing\" registered "
        "with Oregon OSHA under ORS 658.750. The price is the whole "
        "proposition -- an existing primary farm dwelling on the tract, "
        "occupancy limited to people principally engaged in the farm use, and "
        "removal or conversion when the housing is no longer required -- "
        "which is why it is an elective and not a permission. Nobody takes it "
        "by accident.",
        evidence="registration with Oregon OSHA under ORS 658.750, plus the county's accessory-farm-dwelling findings",
    ),
    # --- site facts: true of the parcel, whoever wants otherwise -------
    ConditionDef(
        "corner_lot",
        "site_fact",
        "Abuts a street on two or more sides, which swaps an interior side "
        "setback for a larger street-side one.",
        evidence="street centreline intersection with the parcel boundary",
        assume=False,
    ),
    ConditionDef(
        "abuts_alley",
        "site_fact",
        "Has alley access, which in most codes moves parking off the street "
        "frontage and relaxes the garage entrance setback.",
        evidence="alley centreline layer",
        assume=False,
    ),
    ConditionDef(
        "local_street",
        "site_fact",
        "The frontage is a local street rather than an arterial or collector. "
        "Street-side setbacks are routinely written per street class — Lake "
        "Oswego R-7.5 asks 20 ft on an arterial and 15 on a local — so a "
        "screen that picks one without knowing which is guessing. Assumed "
        "unknown, which makes the arterial number bind, because that is the "
        "half that cannot turn a RED lot green by mistake.",
        evidence="the jurisdiction functional classification layer",
        assume=None,
    ),
    ConditionDef(
        "beyond_ugb_mile",
        "site_fact",
        "The parcel is more than one mile from the Metro Urban Growth "
        "Boundary. Multnomah County's Rural Residential zone states two "
        "minimum lot sizes in one sentence -- five acres, and \"for "
        "properties within one mile of the Urban Growth Boundary ... as "
        "currently required in the Oregon Administrative Rules Chapter 660, "
        "Division 004 (20 acre minimum as of October 4, 2000)\" -- so which "
        "figure binds is a distance nobody has measured. Assumed unknown, "
        "which leaves the twenty-acre number in force, because that is the "
        "half that cannot turn a RED lot green by mistake. Being outside the "
        "UGB is not the same as being a mile from it, which is why the zone "
        "note saying RR is overwhelmingly rural does not settle this.",
        evidence="Metro UGB polygon, buffered one mile",
        assume=None,
    ),
    ConditionDef(
        "public_sewer",
        "site_fact",
        "A public sanitary main is close enough to connect to.",
        evidence="jurisdiction sanitary main layer; district polygon as fallback",
        assume=None,
    ),
    ConditionDef(
        "in_sewer_district",
        "site_fact",
        "Inside a sanitary district service boundary, where the mains "
        "themselves are not published.",
        evidence="district service-area polygons",
        assume=None,
    ),
    ConditionDef(
        "steep_slope",
        "site_fact",
        "Grade steep enough to trigger a hillside or geologic-hazard overlay.",
        evidence="DEM, 3 ft resolution — noisy to about 2 percentage points",
        assume=False,
    ),
    ConditionDef(
        "in_floodplain",
        "site_fact",
        "Inside a mapped special flood hazard area.",
        evidence="FEMA NFHL",
        assume=False,
    ),
    ConditionDef(
        "historic_resource",
        "site_fact",
        "Listed, or inside a historic district, which adds design review and "
        "can bar demolition outright.",
        evidence="jurisdiction historic inventory",
        assume=False,
    ),
    ConditionDef(
        "civic_corridor",
        "site_fact",
        "The site abuts a corridor the jurisdiction has mapped for more "
        "intensity. Portland raises RM2 building coverage from 60 percent to "
        "70 for sites on a Civic or Neighborhood Corridor and drops a setback "
        "there too, so the same zone screens two ways depending on a line on "
        "a map rather than on anything visible in the parcel record. Assumed "
        "unknown, which leaves the tighter number binding.",
        evidence="the jurisdiction corridor map -- Portland Map 120-1",
        assume=None,
    ),
    ConditionDef(
        "hillside_or_resource_overlay",
        "site_fact",
        "Some part of the lot lies inside a mapped hillside-risk or resource "
        "overlay. Gresham 7.0420(G)(1)(b) switches its rear roof height limit "
        "OFF where it does -- 'this rear roof height limit standard does not "
        "apply if any portion of the lot is located within the Hillside "
        "Geological Risk Area (HGRO) or Resource Area (RA)' -- which is a "
        "relief running the opposite way from every other overlay in this "
        "registry, where a mapped constraint tightens rather than releases. "
        "Nothing here cuts either boundary against a parcel, so it is assumed "
        "unknown and the step-back binds.",
        evidence="the jurisdiction's hillside and resource overlay boundaries, cut against the lot — neither held",
        assume=None,
    ),
    ConditionDef(
        "on_transit_street",
        "site_fact",
        "The frontage is on a transit street, or is a street lot line inside a "
        "Pedestrian District. Portland's maximum building setbacks apply there "
        "and nowhere else, and note [5] of Table 150-2 turns that into a "
        "relief: 'for frontages where the maximum building setback applies, "
        "there is no minimum setback'. So the frontage that must be built up "
        "to the street is the one released from standing back from it. "
        "Distinct from `civic_corridor`, which is a corridor the code maps to "
        "allow more intensity; this is a street classification carried in the "
        "Transportation System Plan, and nothing here reads either. Assumed "
        "unknown, which leaves the minimum binding.",
        evidence=(
            "Portland's transit street classification and Pedestrian District "
            "map, cut against the frontage — neither held"
        ),
        assume=None,
    ),
    ConditionDef(
        "adjacent_single_story_building",
        "site_fact",
        "An existing single-storey building 20 ft or less in height stands "
        "within 20 ft, measured horizontally, of where this one would. "
        "Fairview 19.30.030(E) makes a taller building step down to it, and "
        "the pod is 26 ft, so on an established street the standard can refuse "
        "the building outright rather than move it. Two things nothing here "
        "holds: the neighbouring structure's height and storey count, and the "
        "horizontal distance between two buildings rather than between a "
        "building and a line. Assumed unknown, which caps the verdict.",
        evidence=(
            "building footprints with heights or storey counts, cut against "
            "the pod's own footprint — no layer held records either"
        ),
        assume=None,
    ),
    ConditionDef(
        "inside_mapped_use_area",
        "site_fact",
        "The parcel lies inside a boundary the code draws INSIDE a zone to "
        "turn a use on or off. Gresham allows a plex in the Downtown "
        "Commercial Core only \"north of NE 8th Street\", which is not an "
        "overlay, not a plan district and not on the zoning map -- it is one "
        "sentence in a table note, and it decides the use outright for every "
        "lot on the wrong side of it. Distinct from `civic_corridor`, which "
        "relaxes a dimension along a mapped corridor, and from "
        "`site_specific_limitation`, which attaches to one parcel because of "
        "its own history. Assumed unknown, so a use the area switches ON "
        "stays off.",
        evidence="the boundary the citing rule names, cut against the parcel — none held",
        assume=None,
    ),
    ConditionDef(
        "narrow_frontage",
        "site_fact",
        "The lot's street frontage is at or below the figure the CITING rule "
        "names, the way `low_rise` asserts the pod clears whichever height a "
        "table steps at. Gresham's Downtown note reaches only lots with "
        "\"70 feet of street frontage or less\" -- a carve-out for the small "
        "legacy lot, and the whole reason a plex is allowed in the Commercial "
        "Core at all. It is a maximum, so it is the mirror of "
        "`min_frontage_ft` and cannot be folded into it: one says the lot is "
        "big enough to build on, the other says it is small enough to "
        "qualify. Assumed unknown, which keeps the narrow-lot permission "
        "shut rather than opening it on a measurement nobody took.",
        evidence="the parcel's street frontage against the cited threshold — the frontage measurement is not built",
        assume=None,
    ),
    ConditionDef(
        "abuts_nonresidential_zone",
        "site_fact",
        "Every lot line that is not a street lot line abuts a commercial, "
        "employment, industrial, open-space or central-residential zone. "
        "Portland's commercial zones require no setback at all from such a "
        "line and 10 feet from a line abutting anything more residential, so "
        "the same building is legal against one neighbour and illegal against "
        "the next. Assumed unknown, which leaves the 10 feet binding: reading "
        "it the other way is how a lot with a house behind it screens as "
        "buildable to its own rear lot line.",
        evidence="the zoning layer, read at the neighbouring parcels rather than at this one",
        assume=None,
    ),
    ConditionDef(
        "abuts_side_yard",
        "site_fact",
        "The lot's side lot line adjoins the SIDE yard of the neighbour "
        "rather than the neighbour's rear yard. Troutdale asks seven and a "
        "half feet of a two-storey building along a side lot line that "
        "adjoins another side yard and fifteen along one that adjoins a rear "
        "yard, which is the neighbouring lot's ORIENTATION rather than its "
        "zoning -- a different unmeasured fact from "
        "`abuts_nonresidential_zone`, and one the zoning layer cannot answer "
        "at all. Assumed unknown, which leaves the fifteen binding: a lot at "
        "the end of a row, backing onto the rear of the lots on the "
        "perpendicular street, is exactly the case the larger number is "
        "written for, and it is not visible from the parcel record.",
        evidence=(
            "the neighbouring lots' front lot lines, read against this lot's "
            "side lot line -- none held"
        ),
        assume=None,
    ),
    ConditionDef(
        "flag_lot",
        "site_fact",
        "Reaches the street by a pole, so frontage and access are measured "
        "differently and the buildable area is the flag, not the parcel.",
        evidence="parcel geometry — pole detection in flats.geom",
        assume=False,
    ),
    ConditionDef(
        "through_lot",
        "site_fact",
        "Street on two opposite sides. Gresham states the consequence plainly "
        "-- \"for double frontage lots, each street frontage shall be "
        "considered a front yard\" -- which turns the rear setback into a "
        "second front one and takes the depth a rear-court pod parks in. "
        "Assumed unknown, because the two ways of being wrong are not "
        "symmetric: treating a through lot as an ordinary one is how a lot "
        "with no room for the pod screens as buildable.",
        evidence="parcel geometry against the street centreline layer -- opposite frontages",
        assume=None,
    ),
    ConditionDef(
        "sidewalk_easement",
        "site_fact",
        "Sidewalk access is carried by an easement rather than by the "
        "right-of-way. Gresham then measures the setback from the easement "
        "line nearest the building rather than from the property line, which "
        "moves the whole envelope back by however wide the easement is.",
        evidence="jurisdiction recorded-easement layer -- none held",
        assume=None,
    ),
    ConditionDef(
        "access_easement",
        "site_fact",
        "A vehicular or pedestrian access easement crosses the lot, and the "
        "code measures the setback from its line rather than from the "
        "property line. Wilsonville's Table 8A note K does exactly that for "
        "the front setback in the Frog Pond neighborhoods, which starts the "
        "envelope somewhere inside the lot -- how far inside depends on an "
        "easement nothing here holds. Distinct from the sidewalk easement: "
        "that one carries a footpath at the frontage, this one can run "
        "anywhere and carries vehicles.",
        evidence="jurisdiction recorded-easement layer -- none held",
        assume=None,
    ),
    ConditionDef(
        "split_zone",
        "site_fact",
        "The lot carries more than one base zone. Lake Oswego's use table "
        "stamps its R-3 and R-0 columns \"if lot has multiple zones, e.g., "
        "R-0/EC, see LOC 50.02.002.2.e\", and what that section does is apply "
        "each zone to the part of the lot it covers -- so the pod is bound by "
        "whichever zone it sits in, and the buildable area is a fraction of "
        "the lot rather than the lot. Every screen here reads one zone per "
        "parcel, which for a split lot is a coin flip nobody is told about.",
        evidence="zoning polygons intersected against the parcel -- more than one hit",
        assume=None,
    ),
    ConditionDef(
        "site_specific_limitation",
        "site_fact",
        "A limitation attached to this parcel in particular rather than to "
        "its zone. Lake Oswego footnotes the R-0 column of both its use table "
        "and its dimensional table with \"site-specific standards, see LOC "
        "50.02.002.2.c\", which is a list of named properties carrying "
        "conditions from past approvals. Nothing here holds that list, and a "
        "parcel on it can be barred from a use its zone permits.",
        evidence="the jurisdiction's site-specific conditions list, keyed by parcel",
        assume=None,
    ),
    ConditionDef(
        "net_developable_area",
        "site_fact",
        "How much of the lot counts toward a density calculation once "
        "sensitive lands, right-of-way dedications and the rest are taken "
        "out. Minimum density is computed on it -- Lake Oswego asks a "
        "subdivision for 80 percent of the theoretical yield in R-7.5, R-5 "
        "and R-3, and 20 units per acre in R-0 -- so a four-unit plat on land "
        "that could hold six is short of the floor rather than over a "
        "ceiling. The lot's own square footage is an upper bound on it and "
        "nothing more: the deductions are a survey, not an attribute.",
        evidence="constrained-lands layers deducted from the parcel -- none held",
        assume=None,
    ),
    ConditionDef(
        "utility_easement",
        "site_fact",
        "A recorded public utility easement crosses the buildable area. "
        "Oregon City prints \"public utility easements may supersede the "
        "minimum setback\" under every dimensional table in Title 17, which "
        "makes the table's setback a floor rather than the answer: the "
        "easement can push the building further in and nothing in the zoning "
        "text says by how much. Assumed unknown, because a lot screened as if "
        "no easement existed is the one way this footnote produces a GREEN "
        "that a surveyor would not.",
        evidence="county recorded-easement layer -- none held",
        assume=None,
    ),
    ConditionDef(
        "abuts_lower_density_zone",
        "site_fact",
        "The site shares a boundary with a less intense residential zone. "
        "Codes buy the neighbours a buffer with it -- Oregon City requires a "
        "ten-foot landscaped yard on the side abutting R-10, R-8 or R-6 -- so "
        "the setback that binds is not the one in the row for this zone.",
        evidence="jurisdiction zoning polygons, adjacency on the shared edge",
        assume=None,
    ),
    ConditionDef(
        "protected_water_feature",
        "site_fact",
        "A stream, wetland or water body whose vegetated corridor eats the "
        "buildable area. The corridor is measured from the feature and runs to "
        "fifty feet and beyond on slopes, which can exceed every setback in "
        "the zone put together.",
        evidence="jurisdiction natural-resource overlay -- none held",
        assume=None,
    ),
    # --- design facts: true of the building, not of the parcel ---------
    ConditionDef(
        "multi_story",
        "design_fact",
        "The building is two storeys or more. Side and rear setbacks are "
        "commonly written per storey, and a pod screened against the "
        "single-storey column is screened against a standard it can never "
        "meet.",
        evidence="the design catalog entry — Design.stories",
    ),
    ConditionDef(
        "low_rise",
        "design_fact",
        "The building sits under the height at which a code steps a standard "
        "up. Portland RM3 and RM4 ask 5 feet of side and rear setback of "
        "buildings up to 55 feet tall and 10 feet of anything above that; "
        "Lake Oswego steps lot coverage instead, 45 percent at 22 feet down "
        "to 35 above 30. Either way the threshold is the code's, not ours -- "
        "what this condition asserts is that the pod clears whichever one "
        "the cited table names. A two-storey townhome clears most such "
        "thresholds in Oregon, so it is usually true; it is registered "
        "rather than assumed because the stricter number is the one that "
        "may not be dropped by accident, and because 22 feet is close "
        "enough to a two-storey building that the answer is a measurement "
        "rather than a shrug.",
        evidence="the design catalog entry -- Design.height_ft against the cited threshold",
    ),
    ConditionDef(
        "unit_lots",
        "design_fact",
        "The four units are being platted onto lots of their own rather than "
        "sharing one. Cities state different standards for the two paths — a "
        "townhouse lot width where the quadplex row states the parcel's — and "
        "which set governs is decided by how the product is brought to "
        "market, not by the parcel.",
        evidence="the design catalog entry — Design.plat",
    ),
    ConditionDef(
        "attached_wall",
        "design_fact",
        "The property line in question is the line a party wall stands on. "
        "Codes that permit attached housing say so in the setback cell rather "
        "than in prose — Lake Oswego R-3 and R-5 both read \"10 ft exterior "
        "wall, 0 ft attached wall\" — and the second number is the whole "
        "reason four units may touch. It is a design fact and not a site one "
        "because whether a side line carries a party wall is decided by how "
        "the four units are laid out, which is the pod, not the parcel.",
        evidence="the design catalog entry — which walls the pod shares",
    ),
    # --- relief: an approval the developer applies for ------------------
    ConditionDef(
        "adjustment",
        "relief",
        "A staff-level modification of a development standard. Oregon cities "
        "generally offer one; the size of miss it will carry is what varies.",
        evidence="the jurisdiction adjustment chapter",
        tier=Tier.administrative,
    ),
    ConditionDef(
        "variance",
        "relief",
        "A discretionary modification decided on criteria at a hearing. "
        "Slower and riskier than an adjustment, and not numerically capped — "
        "a variance is granted on findings, not on how small the miss was.",
        evidence="the jurisdiction variance chapter",
        tier=Tier.discretionary,
    ),
    ConditionDef(
        "conditional_use",
        "relief",
        "Permission for a use the zone lists as conditional rather than "
        "permitted. Only available where the code enumerates it.",
        evidence="the zone conditional use list",
        tier=Tier.discretionary,
    ),
    ConditionDef(
        "review_use",
        "relief",
        "Permission for a use a code lists as a REVIEW use -- a third "
        "category between permitted and conditional that Multnomah County's "
        "resource districts use throughout. MCC 39.4225 opens \"the following "
        "uses may be permitted when found by the approval authority to "
        "satisfy the applicable standards of this Chapter\", which is a "
        "decision on criteria rather than an over-the-counter permit. Kept "
        "separate from `conditional_use` because the code keeps them separate "
        "-- the same article lists both, with different sections and "
        "different findings -- and folding one into the other would report a "
        "cost the county does not charge. Tiered discretionary, the "
        "conservative of the two readings, until the Part 7 procedure is "
        "stored and says which it is.",
        evidence="the zone review-use list; MCC Chapter 39 Part 7 procedure is unread",
        tier=Tier.discretionary,
    ),
    ConditionDef(
        "planned_development",
        "relief",
        "Approval of a Planned Development overlay on the site. Multnomah "
        "County's PD, MCC 39.5300 through 39.5350, is the one place in this "
        "corpus where a rural residential zone names an attached dwelling: "
        "39.5350(A) says the housing types in a residential PD \"may include "
        "only duplexes and single family detached or attached dwellings\". "
        "It is expensive in exactly the way that sentence is cheap. A PD is a "
        "Planning Commission decision on a preliminary and then a final "
        "development plan; 39.5320 lets the PD's own standards override the "
        "base zone's on conflict, so nothing dimensional is fixed in advance; "
        "and 39.5340(A) computes the units the site may hold by dividing it "
        "by the underlying district's minimum lot area per dwelling, which in "
        "rural zones is acres. Tiered discretionary because it is a hearing "
        "with findings, not a permit counter.",
        evidence="a Planning Commission decision on a PD development plan and program",
        tier=Tier.discretionary,
    ),
)

CONDITIONS: dict[str, ConditionDef] = {c.name: c for c in _C}

#: Conditions whose truth we assert rather than observe. A configuration
#: leaning on one of these cannot be GREEN — it is our belief, not a fact.
ASSUMED = frozenset(c.name for c in _C if c.kind == "site_fact" and c.assume is not None)


def condition(name: str) -> ConditionDef:
    """Look up a condition, refusing anything unregistered.

    The refusal is the point. A screen that accepts ``"affordability"`` beside
    ``"affordable"`` silently splits one lever into two, and the batch view
    then offers the user both.
    """
    try:
        return CONDITIONS[name]
    except KeyError:
        raise KeyError(
            f"unknown condition {name!r} — register it in flats/rules/conditions.py"
        ) from None


def of_kind(kind: Kind) -> tuple[ConditionDef, ...]:
    return tuple(c for c in _C if c.kind == kind)


def electives() -> tuple[ConditionDef, ...]:
    """Conditions the developer chooses — the levers a batch view offers."""
    return of_kind("elective")


def site_facts() -> tuple[ConditionDef, ...]:
    """Conditions about the parcel — overridable on one lot, assumed on many."""
    return of_kind("site_fact")


def design_facts() -> tuple[ConditionDef, ...]:
    """Conditions about the building — settled by the catalog, not the lot."""
    return of_kind("design_fact")


def reliefs() -> tuple[ConditionDef, ...]:
    """Approvals the developer may apply for."""
    return of_kind("relief")


def deepest(tiers: Iterable[Tier]) -> Tier:
    """The hardest ask in a group — what the whole configuration costs.

    A configuration needing one administrative adjustment and one variance
    costs a variance. Taking the maximum rather than the count is deliberate:
    two staff-level asks are still a staff-level project, while one hearing
    makes it a hearing project.
    """
    found = list(tiers)
    return max(found, key=lambda t: t.rank) if found else Tier.as_of_right


__all__ = [
    "ASSUMED",
    "ASSUMED_TIER",
    "ASSUMED_USE_TIER",
    "CONDITIONS",
    "ConditionDef",
    "Kind",
    "Tier",
    "condition",
    "deepest",
    "design_facts",
    "electives",
    "of_kind",
    "reliefs",
    "site_facts",
]
