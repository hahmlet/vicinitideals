"""Resolve a (jurisdiction, zone) pair into effective standards.

Resolution order, least specific to most::

    OAR 660-046 (state)  →  county  →  city base zone  →  overlay  →  bonus

A more specific layer overrides a less specific one, **except** where the less
specific value is marked ``preempts`` — that is how state law that caps a local
standard survives a city trying to exceed it. Preemption comes in two shapes
and the difference is load-bearing: ``preempts: true`` answers the question
outright, while ``preempts: cap`` states the *strictest* a local layer may be
and lets a looser local number through. OAR 660-046-0220 bars a city from
requiring more than one parking stall per unit; it does not oblige one to
require any, and Portland requires none. Which way "looser" runs is read off
the field rather than the preemption, because it is a property of the standard
— a minimum gets looser as it falls, a maximum as it rises.

Every resolved value remembers the layer and code section it came from, so the
UI can show *"front setback 10 ft — Portland 33.110 Table 110-4"* beside
*"parking 1/unit — OAR 660-046-0220 (state, preempts city 2/unit)"*.

A zone may also adopt another zone's standards wholesale (``like:``), which
some codes do instead of restating a table. The reference is followed, not
flattened: a value borrowed from R-6 still cites the R-6 section it was read
from, so amending R-6 moves every zone that adopted it and a reviewer can see
that it did.

Standards that carry exceptions ("5 ft., or 10 ft. where the development is
affordable") are resolved against the conditions passed in, so the number that
comes out is the one that applies to *this* lot with *these* elections — and
its provenance points at the sentence that number was read from, which is
often a different chapter from the table it modifies.

Nothing here decides GREEN/YELLOW/RED/UNKNOWN. It reports what the code says
and how much that answer can be trusted; the scoring stage acts on it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field as _dc_field, replace
from typing import Any, Collection, Mapping

from flats.rules.caps import caps_for
from flats.rules.definitions import Boundary, Definition, decide, unread
from flats.rules.fields import REQUIRED_FIELDS, field
from flats.rules.model import LIKE, Layer, Preempt, Provenance, Status, Value, Zone


class Verdict(str, enum.Enum):
    """How much the resolved rule set can be trusted for this pair."""

    #: Every value present and verified. The only state that may produce GREEN or RED.
    trusted = "trusted"
    #: Encoded, but at least one value is draft/encoded/stale. Routes to REVIEW.
    unverified = "unverified"
    #: Two exceptions applied equally well to at least one standard. Worse than
    #: unverified: a signature cannot fix it, because both numbers may be
    #: correctly transcribed and the encoding still not say which governs.
    ambiguous = "ambiguous"
    #: Jurisdiction is encoded, this zone is not. Routes to REVIEW, lands on the backlog.
    zone_not_encoded = "zone_not_encoded"
    #: This zone adopts another zone's standards and that zone is not encoded.
    #: A coverage gap, not an error: encode the referenced zone.
    zone_reference_missing = "zone_reference_missing"
    #: Two zones adopt each other. An encoding bug — no set of standards exists
    #: to resolve, and following it would not terminate.
    zone_reference_cycle = "zone_reference_cycle"
    #: No layer for this jurisdiction at all. Routes to REVIEW.
    jurisdiction_not_encoded = "jurisdiction_not_encoded"


#: Reason codes emitted alongside a non-trusted verdict.
REASON_FOR_VERDICT: dict[Verdict, str] = {
    Verdict.unverified: "RULE_UNVERIFIED",
    Verdict.ambiguous: "RULE_AMBIGUOUS",
    Verdict.zone_not_encoded: "ZONE_NOT_ENCODED",
    Verdict.zone_reference_missing: "ZONE_REFERENCE_MISSING",
    Verdict.zone_reference_cycle: "ZONE_REFERENCE_CYCLE",
    Verdict.jurisdiction_not_encoded: "JURISDICTION_NOT_ENCODED",
}


@dataclass(frozen=True, slots=True)
class Resolved:
    """One effective standard plus the layer that supplied it."""

    name: str
    value: Any
    status: Status
    prov: Provenance
    layer: str
    #: "zone" when the value came from the zone block, "defaults" when inherited.
    origin: str
    #: True when a less specific layer's ``preempts`` value beat a local one.
    preempted: bool = False
    #: The value this one displaced, if any — kept so the UI can explain itself.
    shadowed: Any = None
    #: The zone this value was read from, when it is not the lot's own — a
    #: borrowed standard still cites the section it actually lives in, and the
    #: detail page has to be able to say "VSF's front setback *is* R-6's".
    via: str | None = None
    #: Conditions that selected this number. Empty means the base standard.
    when: tuple[str, ...] = ()
    #: Every condition that would move this standard, whether or not it is
    #: active. This is what a batch view offers as a toggle: a lever is worth
    #: showing only where flipping it changes a number some lot is bound by.
    levers: frozenset[str] = frozenset()
    #: Populated when two exceptions applied equally well. The number carried is
    #: the base, and nothing may treat it as an answer.
    ambiguous: tuple[str, ...] = ()
    #: The quantity this rate is computed on, where the code names one nothing
    #: measures. Kept apart from ``levers`` -- which say the number could move
    #: -- because this says the comparison cannot be run at all, and the screen
    #: has to be able to tell those two apart.
    measured_on: str | None = None

    @property
    def trusted(self) -> bool:
        return self.status is Status.verified and not self.ambiguous

    @property
    def conditional(self) -> bool:
        return bool(self.when)


@dataclass(frozen=True, slots=True)
class ZoneResolution:
    jurisdiction: str
    zone: str
    verdict: Verdict
    values: dict[str, Resolved] = _dc_field(default_factory=dict)
    #: Fields carrying a non-verified status.
    untrusted: tuple[str, ...] = ()
    #: Required fields nothing in the chain supplies.
    missing_required: tuple[str, ...] = ()
    #: Layer ids consulted, most specific first.
    chain: tuple[str, ...] = ()
    #: Conditions this resolution was asked for.
    conditions: tuple[str, ...] = ()
    #: Fields where two exceptions tied. Encoding work, not review work.
    ambiguous: tuple[str, ...] = ()
    #: Standards the code switches off for this configuration. Absent from
    #: ``values`` on purpose: there is no number, and a None sitting in the
    #: dict is a number-shaped hole that something downstream will eventually
    #: subtract from. Named here so the screen can say "the code exempts this"
    #: rather than "we never encoded it", which is a different sentence with a
    #: different fix.
    exempted: tuple[str, ...] = ()
    #: Zone codes whose standards this resolution read through a reference,
    #: least authoritative first.
    borrowed_from: tuple[str, ...] = ()

    @property
    def trusted(self) -> bool:
        return self.verdict is Verdict.trusted

    @property
    def levers(self) -> frozenset[str]:
        """Conditions that would change something here.

        The batch view's whole offer: these are the toggles worth putting in
        front of somebody looking at this selection of lots.
        """
        return frozenset().union(*(r.levers for r in self.values.values())) if self.values else frozenset()

    @property
    def reason(self) -> str | None:
        return REASON_FOR_VERDICT.get(self.verdict)

    def get(self, name: str, default: Any = None) -> Any:
        r = self.values.get(name)
        return default if r is None else r.value


def _looser(name: str, local: Any, ceiling: Any) -> bool:
    """True when a local standard sits inside what an ancestor allows.

    "Looser" is a property of the standard, not of the preemption. A minimum
    gets looser as it falls -- no required parking is looser than one stall --
    and a maximum gets looser as it rises. A field that is neither, a boolean
    or an enum, has no such ordering, so a cap on one is meaningless and the
    ancestor simply wins; that is the conservative reading, and the loader has
    no business inventing an order for it.
    """
    which = field(name).is_maximum
    if which is None:
        return False
    try:
        return local > ceiling if which else local < ceiling
    except TypeError:
        # Two values of different shapes -- a curve against a number, say.
        # Not comparable, so not demonstrably looser.
        return False


class RuleSet:
    """Loaded hierarchy with resolution over it."""

    def __init__(self, layers: dict[str, Layer]) -> None:
        self.layers = layers

    # -- hierarchy ----------------------------------------------------

    def chain_for(self, layer_id: str) -> list[Layer]:
        """Layers from state root down to ``layer_id``, least specific first.

        Missing intermediate layers are skipped rather than fatal — a county
        with no county-level file is normal.
        """
        parts = layer_id.split("/")
        ids = ["/".join(parts[: i + 1]) for i in range(len(parts))]
        return [self.layers[i] for i in ids if i in self.layers]

    def definitions_for(self, layer_id: str) -> dict[str, Definition]:
        """What each term means *here*, and nowhere else by accident.

        Values inherit down the chain. Definitions deliberately do not. An
        incorporated Oregon city writes its own development code; the county
        code governs unincorporated land, so Milwaukie having no definition of
        a term is not Clackamas County speaking for Milwaukie. Silence is not
        adoption, and a borrowed test is a wrong answer wearing a citation.

        The one way a layer takes another's definitions is by saying so:
        ``definitions_from: <layer id>`` beside a quote of the clause that
        adopts them. That is followed for terms the layer has not defined
        itself, in the order declared, and the resulting definition still
        cites the code it was actually read from.
        """
        out: dict[str, Definition] = {}
        seen: set[str] = set()
        queue = [layer_id]
        while queue:
            current = queue.pop(0)
            if current in seen or current not in self.layers:
                continue
            seen.add(current)
            layer = self.layers[current]
            for term, defn in layer.definitions.items():
                out.setdefault(term, defn)
            queue.extend(layer.definitions_from)
        return out

    def defines(self, layer_id: str, term: str, boundary: Boundary) -> bool | None:
        """Answer one term for one lot under this jurisdiction's own reading.

        ``None`` means nobody in this jurisdiction's code has been read on the
        question, which the screen carries through as unknown.
        """
        return decide(self.definitions_for(layer_id), term, boundary)

    def undefined(self, layer_id: str) -> tuple[str, ...]:
        """Terms this jurisdiction has never defined. One gap each."""
        return unread(layer_id, self.definitions_for(layer_id))

    def find_zone(self, layer_id: str, zone: str) -> tuple[Layer, Zone] | None:
        """A zone code, looked up in this layer and then up the hierarchy.

        A city adopting a county zone is the same shape as adopting one of its
        own, so the search walks the same chain resolution already walks.
        """
        for candidate in reversed(self.chain_for(layer_id)):
            block = candidate.zones.get(zone)
            if block is not None:
                return candidate, block
        return None

    def zone_chain(self, layer_id: str, zone: str) -> tuple[list[tuple[Layer, Zone]], str | None]:
        """Zone blocks to apply in order, least authoritative first.

        Following the reference rather than flattening it is the whole point:
        a value borrowed from R-6 keeps R-6's citation, so amending R-6 moves
        every zone that adopted it and a reviewer can see that it did.

        Returns the blocks and, if the chain could not be built, a reason code.
        """
        found = self.find_zone(layer_id, zone)
        if found is None:
            return [], Verdict.zone_not_encoded.value

        blocks: list[tuple[Layer, Zone]] = []
        seen: set[tuple[str, str]] = set()

        def walk(layer: Layer, block: Zone) -> str | None:
            mark = (layer.layer, block.zone)
            if mark in seen:
                return Verdict.zone_reference_cycle.value
            seen.add(mark)

            if block.like is None:
                blocks.append((layer, block))
                return None

            parent = self.find_zone(layer.layer, block.like.zone)
            if parent is None:
                return Verdict.zone_reference_missing.value

            if block.like.wins == "referenced":
                # The code says the adopted chapter governs on disagreement, so
                # it is applied last and overwrites what this zone states.
                blocks.append((layer, block))
                return walk(*parent)
            problem = walk(*parent)
            if problem:
                return problem
            blocks.append((layer, block))
            return None

        problem = walk(*found)
        return blocks, problem

    def eligible(self, layer_id: str) -> bool:
        """Jurisdiction toggle. Report-time policy — never a structural drop."""
        layer = self.layers.get(layer_id)
        return bool(layer and layer.eligible)

    # -- resolution ---------------------------------------------------

    def resolve(
        self,
        layer_id: str,
        zone: str,
        conditions: Collection[str] = (),
        lot: Mapping[str, float] | None = None,
    ) -> ZoneResolution:
        """The standards that apply to a lot in this zone under these conditions.

        ``conditions`` is what the lot is and what the developer elects — a
        corner lot, an affordable project, a transit-served site. Each standard
        answers for itself which of its numbers that selects; most carry only
        one and ignore the question entirely.

        ``lot`` is what has been measured about it — ``{"lot_sqft": 4200}`` —
        for the zones whose tables are banded by lot size. Omitting it where a
        standard is banded is not a smaller answer but an ambiguous one: the
        base of a banded standard is the table's last column, and quietly
        handing a small lot the largest column's numbers is the error this
        whole path exists to prevent.
        """
        held = tuple(sorted(set(conditions)))
        chain = self.chain_for(layer_id)
        chain_ids = tuple(reversed([layer.layer for layer in chain]))

        target = self.layers.get(layer_id)
        if target is None:
            return ZoneResolution(
                layer_id, zone, Verdict.jurisdiction_not_encoded, chain=chain_ids, conditions=held
            )

        blocks, problem = self.zone_chain(layer_id, zone)
        if problem:
            return ZoneResolution(
                layer_id, zone, Verdict(problem), chain=chain_ids, conditions=held
            )

        resolved: dict[str, Resolved] = {}
        # field -> (how it preempts, the number the ancestor set). The
        # number is kept apart from `resolved`, because once a cap lets a
        # looser local value through, `resolved` holds the city's number
        # and a third layer must still be measured against the STATE's.
        locked: dict[str, tuple[Preempt, Any]] = {}
        # Fields an ancestor removed outright and locked. Separate from
        # `locked`, which carries a number a local layer is measured against;
        # there is no number here, and the question a local value has to answer
        # is not "how much" but "at all".
        locked_exempt: set[str] = set()
        exempted: set[str] = set()

        def apply(
            values: dict[str, Value], layer: str, origin: str, via: str | None = None
        ) -> None:
            for name, val in values.items():
                if val.unless and not set(val.unless).isdisjoint(held):
                    # This layer's rule addresses a building this configuration
                    # is not. Silence, not an exemption: a more specific layer
                    # may still have a standard, and cancelling it here would
                    # answer a question this rule never asked.
                    continue
                eff = val.under(held, lot)
                if eff.exempt:
                    # Not a pass by a wide margin -- the test does not exist
                    # here. Dropped so nothing can compare a lot against it,
                    # and remembered so the absence is explainable.
                    exempted.add(name)
                    resolved.pop(name, None)
                    if val.preempts is Preempt.always:
                        # An ancestor saying the standard does not apply, and
                        # that a local layer may not decide otherwise. OAR
                        # 660-046-0220(2)(b) is the case: a Large City applying
                        # density maximums in a zone "may not apply those
                        # maximums to the development of Quadplex and
                        # Triplexes". Without the lock the state exemption is
                        # written and then overwritten by the first city that
                        # prints a density row, which is the standard the rule
                        # exists to remove.
                        locked_exempt.add(name)
                    continue
                if name in locked_exempt:
                    continue
                exempted.discard(name)
                if name in locked:
                    # A preempting ancestor has already spoken. Whether that
                    # ends the matter depends on how it preempts.
                    prev = resolved[name]
                    mode, ceiling = locked[name]
                    if mode is Preempt.cap and _looser(name, eff.value, ceiling):
                        # The ancestor stated the strictest a local layer may
                        # be, and this one is inside it. Nothing to preempt --
                        # a cap does not become a requirement.
                        resolved[name] = Resolved(
                            name, eff.value, eff.status, eff.prov, layer, origin,
                            via=via, when=eff.when, levers=val.levers,
                            ambiguous=eff.ambiguous, measured_on=val.measured_on,
                        )
                        continue
                    # Either the ancestor wins outright, or the local number is
                    # stricter than the ancestor allows and is clipped back to
                    # it. Record what was displaced so the UI can say why.
                    resolved[name] = Resolved(
                        prev.name, prev.value, prev.status, prev.prov, prev.layer,
                        prev.origin, preempted=True, shadowed=eff.value, via=prev.via,
                        when=prev.when, levers=prev.levers, ambiguous=prev.ambiguous,
                        measured_on=prev.measured_on,
                    )
                    continue
                resolved[name] = Resolved(
                    name,
                    eff.value,
                    eff.status,
                    eff.prov,
                    layer,
                    origin,
                    via=via,
                    when=eff.when,
                    levers=val.levers,
                    ambiguous=eff.ambiguous,
                    measured_on=val.measured_on,
                )
                if val.preempts.binds:
                    locked[name] = (val.preempts, eff.value)

        # Least specific first so later layers override — except where locked.
        for layer in chain:
            apply(layer.defaults, layer.layer, "defaults")
        for owner, block in blocks:
            borrowed = None if (owner.layer == layer_id and block.zone == zone) else block.zone
            apply(block.values, owner.layer, "zone", via=borrowed)

        # A footnote somebody read and could not answer rides with the value it
        # qualifies. The fact it turns on becomes a lever, which is all the
        # screen needs: nothing measures it, so it resolves as unknown, and a
        # standard turning on an unknown may not be certified.
        for name, r in list(resolved.items()):
            where = r.via or (zone if r.origin == "zone" else "(defaults)")
            extra = caps_for(r.layer, where).get(name, ())
            if extra:
                resolved[name] = replace(r, levers=r.levers | frozenset(extra))

        untrusted = tuple(sorted(n for n, r in resolved.items() if not r.trusted))
        # A zone that forbids the building forbids it by any amount of slack.
        # The screen returns RED at the use gate without reading a setback, so
        # a setback nobody encoded there blocks nothing -- and reporting it as
        # missing sends a person to look up numbers for a building the code
        # does not allow. That is how an encoding queue fills with work that
        # cannot move a verdict.
        #
        # Only a settled prohibition counts. A `false` that some condition can
        # turn true -- LR-7's conditional use, a footnote nobody has answered --
        # still needs its dimensions, because the path that reaches them exists.
        use = resolved.get("quadplex_allowed")
        prohibited = use is not None and use.value is False and not use.levers
        # An exempted required field is answered, not missing. The code was
        # read, and what it said was that this standard does not apply.
        missing = (
            ()
            if prohibited
            else tuple(sorted(REQUIRED_FIELDS - set(resolved) - exempted))
        )
        ambiguous = tuple(sorted(n for n, r in resolved.items() if r.ambiguous))
        borrowed_from = tuple(b.zone for _, b in blocks if b.zone != zone)
        # The claim to borrow is a rule somebody read, and an unread one could
        # be pointing at the wrong zone entirely — which would hand a whole
        # zone the wrong numbers with nothing on screen to suggest it.
        unread = tuple(
            f"{b.zone}.{LIKE}" for _, b in blocks if b.like is not None and not b.like.trusted
        )
        if ambiguous:
            # Reported ahead of unverified because it is a different kind of
            # problem with a different fix: signing more numbers will not
            # resolve it, someone has to say which exception governs.
            verdict = Verdict.ambiguous
        elif untrusted or missing or unread:
            verdict = Verdict.unverified
        else:
            verdict = Verdict.trusted

        return ZoneResolution(
            jurisdiction=layer_id,
            zone=zone,
            verdict=verdict,
            values=resolved,
            untrusted=tuple(sorted(untrusted + unread)),
            missing_required=missing,
            exempted=tuple(sorted(exempted)),
            chain=chain_ids,
            conditions=held,
            ambiguous=ambiguous,
            borrowed_from=borrowed_from,
        )
