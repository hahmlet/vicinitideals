"""What is true of this lot and this pod, in the words the rule layer knows.

:meth:`flats.rules.resolver.RuleSet.resolve` takes two things besides a zone: a
set of condition names, and what has been measured about the lot. Both were
being assembled by hand at every call site, which is three separate places to
mistype ``affordable`` and one silent way to lose ``multi_story`` — and a lost
condition does not error, it quietly resolves the wrong number.

This module is the one place that assembly happens. It answers one question:
given a design, a measured lot, and whatever has been observed about the site,
which conditions hold?

Three sources, and they are believed differently:

*The design.* Two storeys or one is a fact about the building, read off the
catalog entry. Known outright — see :attr:`flats.designs.model.Design.conditions`.

*Observation.* A corner, an alley, a sanitary main in the street. Where a data
layer answered, the answer is used. Where nothing answered and the registry
states an assumption, the assumption is used **and named**: a GREEN resting on
one is our belief, not a fact, and FLATS_PLAN section 13 says such a lot may not
be GREEN. Where nothing answered and the registry declines to assume — sewer is
the case that matters — the condition is neither held nor denied, and its name
goes in :attr:`Configuration.unknown` so the screen can route the lot to UNKNOWN
rather than guess in either direction.

*Election.* What the developer commits to. Never assumed, because assuming an
incentive means assuming a covenant nobody signed.

The refusals matter as much as the assembly. An unregistered name is refused, an
elective offered as an observation is refused, and a relief is refused outright:
relief is priced after the standard is missed, not folded into which standard
applies, and letting ``adjustment`` in here would resolve a lot against the
setback it wants rather than the one the code states.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import TYPE_CHECKING, Collection, Mapping

from flats.designs.model import Design
from flats.rules.conditions import CONDITIONS, condition
from flats.rules.model import LOT_MEASURES

if TYPE_CHECKING:  # screen imports this module, so the arrow points one way
    from flats.score.screen import LotFacts


@dataclass(frozen=True, slots=True)
class Configuration:
    """The configuration one screening run answers under."""

    #: Every condition that holds, sorted. What ``resolve`` takes.
    conditions: tuple[str, ...] = ()
    #: What was measured, in the units the bands are written in.
    measures: Mapping[str, float] = _dc_field(default_factory=dict)
    #: Conditions held on the registry's assumption rather than on evidence.
    #: A verdict that leans on one of these may not be GREEN.
    assumed: tuple[str, ...] = ()
    #: Site facts nobody answered and the registry refuses to guess. If a
    #: standard turns on one of these, the lot is UNKNOWN.
    unknown: tuple[str, ...] = ()

    def leans_on(self, levers: Collection[str]) -> tuple[str, ...]:
        """Which of this configuration's guesses this standard actually turns on.

        The distinction that keeps assumptions from poisoning every verdict:
        assuming a lot is not a corner matters only where some standard states
        a different number for corners. Everywhere else the assumption is
        inert, and downgrading the lot for holding it would bury real GREENs.
        """
        held = set(levers)
        return tuple(n for n in self.assumed + self.unknown if n in held)


def configure(
    lot: "LotFacts",
    design: Design,
    *,
    observed: Mapping[str, bool] | None = None,
    elect: Collection[str] = (),
) -> Configuration:
    """Assemble the conditions and measurements one lot × design resolves under.

    ``observed`` is what the data layers answered about the parcel, by
    condition name — ``{"corner_lot": True, "public_sewer": False}``. A name
    absent from it is a question nobody asked, which is different from an
    answer of False and is treated differently.

    ``elect`` is what the developer commits to. Explicit on purpose: nothing
    infers an incentive.
    """
    seen = dict(observed or {})
    for name in seen:
        kind = condition(name).kind
        if kind != "site_fact":
            raise ValueError(
                f"{name} is {kind}, not something observed about the parcel — "
                f"pass an elective to 'elect', and never pass relief here"
            )
    for name in elect:
        kind = condition(name).kind
        if kind != "elective":
            raise ValueError(f"{name} is {kind}, not the developer's to elect")

    held: set[str] = set(design.conditions) | {n for n, v in seen.items() if v}
    assumed: list[str] = []
    unknown: list[str] = []
    for name, defn in CONDITIONS.items():
        if defn.kind != "site_fact" or name in seen:
            continue
        if defn.assume is None:
            # Nobody asked and the registry will not guess. Naming it is the
            # whole point: silence here is what turns into a false GREEN.
            unknown.append(name)
            continue
        assumed.append(name)
        if defn.assume:
            held.add(name)
    held.update(elect)

    measures = {"lot_sqft": float(lot.lot_sqft)}
    if lot.lot_width_ft is not None:
        measures["lot_width_ft"] = float(lot.lot_width_ft)
    measures = {k: v for k, v in measures.items() if k in LOT_MEASURES and v > 0}

    return Configuration(
        conditions=tuple(sorted(held)),
        measures=measures,
        assumed=tuple(sorted(assumed)),
        unknown=tuple(sorted(unknown)),
    )


__all__ = ["Configuration", "configure"]
