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
Neither ever produces a GREEN.

*A standard nobody encoded is not a standard that passes.* Skipping a check the
code plainly imposes would manufacture GREENs. Any skipped check drops the lot
out of GREEN and names itself, which is how the coverage ledger gets its work.

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
from flats.rules.conditions import Tier
from flats.rules.fields import REQUIRED_FIELDS
from flats.rules.resolver import Verdict as RuleVerdict, ZoneResolution
from flats.score.configure import Configuration
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
    "density_du_per_acre": "max_density_du_per_acre",
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
    # A ceiling on units per acre, measured on the lot in front of us. An acre
    # is 43,560 sq ft, and the arithmetic is done here rather than in the rule
    # file because the code states the ceiling in acres and the parcel layer
    # holds square feet.
    check(
        "density_du_per_acre",
        design.units / (lot.lot_sqft / 43_560.0),
        rules.get("max_density_du_per_acre"),
        is_maximum=True,
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


def _unconfirmed(outcomes: Sequence[ReliefOutcome]) -> tuple[str, ...]:
    """Whether this answer leans on a relief path nobody has read.

    A yellow resting on an assumed adjustment chapter is still the right
    colour — assuming relief exists is the recall-biased default — but it is a
    claim, and a claim has to say so.
    """
    leaning = any(o.available and not o.confirmed for o in outcomes)
    return (RELIEF_UNCONFIRMED,) if leaning else ()


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
    checks, unchecked = _checks(rules, lot, design, fit, policy)
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
        "fit_slack_ft": fit.slack_ft,
        "ask": hardest.tier if hardest else Tier.as_of_right,
        "relief": tuple(outcomes),
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
    if any(CHECK_FIELD.get(name, name) in REQUIRED_FIELDS for name in unchecked):
        reasons.append(STANDARD_NOT_ENCODED)

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

    if reasons or any(c.verdict is Verdict.tolerated for c in checks):
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
