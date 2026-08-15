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
Paper fit is necessary, never sufficient.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import TYPE_CHECKING

from flats.designs.model import Design, Orientation, Plat

if TYPE_CHECKING:  # pragma: no cover - typing only
    from flats.rules.resolver import ZoneResolution

#: What sets the area floor. Named rather than inferred so the page can say
#: which standard is the one to argue with.
BY_MIN_LOT = "min_lot_sqft"
BY_COVERAGE = "max_coverage_pct"
BY_ENVELOPE = "envelope"


@dataclass(frozen=True, slots=True)
class PaperFit:
    """The smallest lot this design could be legal on in this zone."""

    design: str
    jurisdiction: str
    zone: str
    #: Frontage the footprint plus its side setbacks consumes.
    min_width_ft: float | None = None
    #: Front lot line to rear, footprint plus front and rear setbacks.
    min_depth_ft: float | None = None
    #: The binding area floor across every standard that states one.
    min_area_sqft: float | None = None
    #: Which standard set that floor.
    binding: str = ""
    #: None where the zone states no height limit we hold.
    height_ok: bool | None = None
    #: Which orientation these numbers are for — the less demanding one.
    orientation: str = ""
    #: Which plat path was costed. The same building on the same zone answers
    #: differently under the two, which is the point of asking.
    plat: str = ""
    #: Standards this calculation needed and the zone does not supply, or
    #: supplies at a status nothing may be decided on. A number here is a
    #: lower bound: the real requirement can only be larger.
    unknown: tuple[str, ...] = ()
    #: Standards left out on purpose, with why. A street-side setback binds
    #: corner lots only, and applying it to every lot would overstate the
    #: frontage this design needs everywhere.
    excluded: tuple[str, ...] = _dc_field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        """Whether every standard this needs was there to read."""
        return not self.unknown

    @property
    def fits_height(self) -> bool:
        """False only where a height limit is held and the design exceeds it."""
        return self.height_ok is not False


def _number(rules: "ZoneResolution", name: str) -> float | None:
    """A standard's number, or None where nothing usable answers.

    Untrusted is treated as absent on purpose. This module reports a
    requirement to somebody deciding where to buy; a draft number quoted as a
    requirement is the same mistake as a draft number producing a RED.
    """
    if name in rules.untrusted:
        return None
    got = rules.get(name)
    return float(got) if isinstance(got, (int, float)) else None


def paper_fit(design: Design, rules: "ZoneResolution") -> PaperFit:
    """The lot this design needs in this zone, on paper.

    Both orientations are costed and the less demanding one is reported: a pod
    that will not fit broadside may fit end-on, and a requirement stated for
    the worse orientation is a requirement nobody has to meet.
    """
    per_unit = design.plat is Plat.unit_lots
    # Under unit lots the lot-size and lot-width standards read once per
    # dwelling, so the project needs that many of them side by side. Setbacks
    # do not scale: the walls between units are shared, and only the two ends
    # of the row see a side yard either way.
    lots = design.units if per_unit else 1

    front = _number(rules, "setback_front_ft")
    rear = _number(rules, "setback_rear_ft")
    side = _number(rules, "setback_side_ft")
    min_lot = _number(rules, "min_lot_sqft")
    min_width = _number(rules, "min_lot_width_ft")
    coverage = _number(rules, "max_coverage_pct")
    height = _number(rules, "max_height_ft")

    if min_lot is not None:
        min_lot *= lots
    if min_width is not None:
        min_width *= lots

    unknown = tuple(
        name
        for name, got in (
            ("setback_front_ft", front),
            ("setback_rear_ft", rear),
            ("setback_side_ft", side),
        )
        if got is None
    )

    best: PaperFit | None = None
    for orientation, width_ft, depth_ft in design.oriented():
        needed_width = width_ft + 2 * side if side is not None else None
        if needed_width is not None and min_width is not None:
            needed_width = max(needed_width, min_width)
        needed_depth = (
            depth_ft + front + rear if front is not None and rear is not None else None
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
            min_area_sqft=area,
            binding=binding,
            height_ok=None if height is None else design.height_ft <= height,
            orientation=orientation.value,
            plat=design.plat.value,
            unknown=unknown,
            excluded=(
                "setback_street_side_ft (corner lots only)",
                "min_frontage_ft (measured at the street, not the envelope)",
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
