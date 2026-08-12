"""GREEN, REVIEW, or RED — and what the binding constraint was.

Everything upstream measures. This is where measurements become an answer, and
the rules for turning one into the other are deliberately asymmetric:

*Only a trusted rule set may produce a verdict.* If any standard governing the
lot is draft, stale, or missing, the lot is REVIEW — not RED. A wrong number in
a rule file must never delete an acquisition target, and it is the encoding
lifecycle, not the geometry, that decides whether a number can be believed.

*A tolerated miss is REVIEW, never GREEN.* Tolerance exists for measurement
noise. It can rescue a lot from RED so a human looks at it; it can never
certify one.

*A standard nobody encoded is not a standard that passes.* Skipping a check the
code plainly imposes would manufacture GREENs. Any skipped check drops the lot
to REVIEW and names itself, which is how the coverage ledger gets its work.

Some checks are honest approximations rather than measurements — leftover lot
area is an upper bound on qualifying open space, not the open space itself.
Those are listed in :attr:`Screening.optimistic` so a reviewer can see which
numbers were assumed in the lot's favour.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field as _dc_field
from typing import Any, Sequence

from flats.designs.model import Design
from flats.fit.rectangle import Fit
from flats.geom.edges import Tier as GeometryTier
from flats.rules.fields import REQUIRED_FIELDS
from flats.rules.resolver import Verdict as RuleVerdict, ZoneResolution
from flats.score.slack import CheckResult, SlackPolicy, Verdict, binding, dominant


class Triage(str, enum.Enum):
    """The traffic light."""

    #: Every standard encoded, verified, and cleared. Buildable by right.
    green = "green"
    #: Something needs a human — an unverified rule, a miss inside tolerance,
    #: an unreadable lot shape, or a standard nobody has encoded yet.
    review = "review"
    #: A verified standard the lot cannot meet, by more than measurement noise.
    red = "red"


#: Reasons a lot lands in REVIEW that are not a failed check.
NO_FRONTAGE = "NO_FRONTAGE"
GEOMETRY_UNREADABLE = "GEOMETRY_UNREADABLE"
STANDARD_NOT_ENCODED = "STANDARD_NOT_ENCODED"
USE_NOT_ENCODED = "USE_NOT_ENCODED"

#: Hard exclusion: the zone forbids the use outright.
USE_PROHIBITED = "USE_PROHIBITED"

#: Checks computed from a proxy that runs in the lot's favour.
OPTIMISTIC_CHECKS = frozenset({"open_space_pct"})

#: Which rule field each check reads. A check with no value goes unrun, but only
#: an unrun check backed by a *required* field means the encoding is incomplete
#: — many zones genuinely impose no FAR, and treating that silence as a gap
#: would bury the real gaps under thousands of false ones. Whether a standard is
#: absent by fact or by omission is the clause ledger's question, not this one's.
CHECK_FIELD: dict[str, str] = {
    "min_lot_area_sqft": "min_lot_sqft",
    "min_frontage_ft": "min_frontage_ft",
    "min_lot_width_ft": "min_lot_width_ft",
    "coverage_pct": "max_coverage_pct",
    "far": "max_far",
    "height_ft": "max_height_ft",
    "max_units": "max_units",
    "min_units": "min_units_at_trigger",
    "parking_stalls": "parking_min_per_unit",
    "open_space_pct": "open_space_min_pct",
}


@dataclass(frozen=True, slots=True)
class LotFacts:
    """What the geometry stage measured about one parcel."""

    lot_sqft: float
    frontage_ft: float = 0.0
    lot_width_ft: float | None = None
    geometry: GeometryTier = GeometryTier.clean

    @property
    def landlocked(self) -> bool:
        return self.geometry is GeometryTier.landlocked


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
    #: Feet of margin on the fit itself, kept out front because it is the
    #: number a developer argues with.
    fit_slack_ft: float | None = None

    #: The blocker that most explains the outcome — largest proportional
    #: shortfall, not the tightest. This is what the rule-cost ledger counts;
    #: `binding` is the human work queue.
    dominant: str | None = None

    @property
    def head(self) -> str | None:
        """The tightest blocker: what is nearly solved on this lot."""
        return self.binding[0].check if self.binding else None


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
) -> tuple[list[CheckResult], list[str]]:
    """Every numeric standard this lot can be measured against."""
    out: list[CheckResult] = []
    unchecked: list[str] = []
    where = rules.jurisdiction

    def check(name: str, observed: float, threshold: float | None, *, is_maximum: bool) -> None:
        if threshold is None:
            unchecked.append(name)
            return
        out.append(policy.evaluate(name, observed, threshold, is_maximum=is_maximum, jurisdiction=where))

    # Fitment. The threshold is the design's depth; the observation is the
    # deepest rectangle of that width the envelope holds.
    out.append(
        policy.evaluate(
            "fit_ft", fit.best_depth_ft, fit.depth_ft, is_maximum=False, jurisdiction=where
        )
    )

    check("min_lot_area_sqft", lot.lot_sqft, rules.get("min_lot_sqft"), is_maximum=False)
    if lot.landlocked:
        # No street was found, so the frontage measurement is zero by default
        # rather than by observation. Failing the lot on a number nobody
        # measured is precisely the false RED this project exists to avoid.
        unchecked.append("min_frontage_ft")
    else:
        check("min_frontage_ft", lot.frontage_ft, rules.get("min_frontage_ft"), is_maximum=False)
    if lot.lot_width_ft is not None:
        check("min_lot_width_ft", lot.lot_width_ft, rules.get("min_lot_width_ft"), is_maximum=False)
    else:
        unchecked.append("min_lot_width_ft")

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

    check(
        "far",
        design.ground_sqft * design.stories / lot.lot_sqft,
        rules.get("max_far"),
        is_maximum=True,
    )
    check("height_ft", design.height_ft, rules.get("max_height_ft"), is_maximum=True)
    check("max_units", float(design.units), rules.get("max_units"), is_maximum=True)

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

    per_unit = rules.get("parking_min_per_unit")
    if per_unit is None:
        unchecked.append("parking_stalls")
    else:
        out.append(
            policy.evaluate(
                "parking_stalls",
                design.stalls_required,
                float(per_unit) * design.units,
                is_maximum=False,
                jurisdiction=where,
            )
        )

    open_space = rules.get("open_space_min_pct")
    if open_space is not None:
        # Leftover area is an upper bound on qualifying open space — real codes
        # impose dimensions and location. Flagged as optimistic, never silent.
        out.append(
            policy.evaluate(
                "open_space_pct",
                (lot.lot_sqft - design.ground_sqft) / lot.lot_sqft * 100.0,
                float(open_space),
                is_maximum=False,
                jurisdiction=where,
            )
        )

    return out, unchecked


def screen(
    rules: ZoneResolution,
    lot: LotFacts,
    design: Design,
    fit: Fit,
    *,
    policy: SlackPolicy,
) -> Screening:
    """Turn measurements into GREEN / REVIEW / RED for one lot and one design."""
    reasons: list[str] = []

    if lot.lot_sqft <= 0:
        return Screening(triage=Triage.review, reasons=(GEOMETRY_UNREADABLE,))

    checks, unchecked = _checks(rules, lot, design, fit, policy)
    blockers = tuple(binding(checks))
    optimistic = tuple(sorted({c.check for c in checks} & OPTIMISTIC_CHECKS))
    worst = dominant(checks)
    common: dict[str, Any] = {
        "checks": tuple(checks),
        "binding": blockers,
        "dominant": worst.check if worst else None,
        "unchecked": tuple(unchecked),
        "optimistic": optimistic,
        "fit_slack_ft": fit.slack_ft,
    }

    # The use gate is categorical, not a margin: a zone that forbids fourplexes
    # forbids them by any amount of slack.
    allowed = rules.get("quadplex_allowed")
    if allowed is False and rules.trusted:
        return Screening(triage=Triage.red, reasons=(USE_PROHIBITED,), **common)

    if not rules.trusted:
        # An unverified standard may not delete a lot. Whatever the checks say,
        # this is a question for a human.
        reason = rules.reason
        return Screening(
            triage=Triage.review, reasons=tuple(r for r in (reason,) if r), **common
        )

    if allowed is None:
        reasons.append(USE_NOT_ENCODED)
    if lot.landlocked:
        reasons.append(NO_FRONTAGE)
    if lot.geometry is GeometryTier.irregular:
        reasons.append(GEOMETRY_UNREADABLE)
    if any(CHECK_FIELD.get(name, name) in REQUIRED_FIELDS for name in unchecked):
        reasons.append(STANDARD_NOT_ENCODED)

    if any(c.verdict is Verdict.fails for c in checks):
        return Screening(triage=Triage.red, reasons=tuple(reasons), **common)
    if reasons or any(c.verdict is Verdict.tolerated for c in checks):
        return Screening(triage=Triage.review, reasons=tuple(reasons), **common)
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


__all__ = [
    "GEOMETRY_UNREADABLE",
    "NO_FRONTAGE",
    "OPTIMISTIC_CHECKS",
    "STANDARD_NOT_ENCODED",
    "USE_NOT_ENCODED",
    "USE_PROHIBITED",
    "BindingHistogram",
    "LotFacts",
    "RuleVerdict",
    "Screening",
    "Triage",
    "histogram",
    "screen",
]
