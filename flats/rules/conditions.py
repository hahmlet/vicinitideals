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
        "flag_lot",
        "site_fact",
        "Reaches the street by a pole, so frontage and access are measured "
        "differently and the buildable area is the flag, not the parcel.",
        evidence="parcel geometry — pole detection in flats.geom",
        assume=False,
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
        "unit_lots",
        "design_fact",
        "The four units are being platted onto lots of their own rather than "
        "sharing one. Cities state different standards for the two paths — a "
        "townhouse lot width where the quadplex row states the parcel's — and "
        "which set governs is decided by how the product is brought to "
        "market, not by the parcel.",
        evidence="the design catalog entry — Design.plat",
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
