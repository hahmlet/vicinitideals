"""Resolve a (jurisdiction, zone) pair into effective standards.

Resolution order, least specific to most::

    OAR 660-046 (state)  →  county  →  city base zone  →  overlay  →  bonus

A more specific layer overrides a less specific one, **except** where the less
specific value is marked ``preempts: true`` — that is how state law that caps a
local standard survives a city trying to exceed it.

Every resolved value remembers the layer and code section it came from, so the
UI can show *"front setback 10 ft — Portland 33.110 Table 110-4"* beside
*"parking 1/unit — OAR 660-046-0220 (state, preempts city 2/unit)"*.

Nothing here decides GREEN/REVIEW/RED. It reports what the code says and how
much that answer can be trusted; the scoring stage acts on it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field as _dc_field
from typing import Any

from flats.rules.fields import REQUIRED_FIELDS
from flats.rules.model import Layer, Provenance, Status, Value


class Verdict(str, enum.Enum):
    """How much the resolved rule set can be trusted for this pair."""

    #: Every value present and verified. The only state that may produce GREEN or RED.
    trusted = "trusted"
    #: Encoded, but at least one value is draft/encoded/stale. Routes to REVIEW.
    unverified = "unverified"
    #: Jurisdiction is encoded, this zone is not. Routes to REVIEW, lands on the backlog.
    zone_not_encoded = "zone_not_encoded"
    #: No layer for this jurisdiction at all. Routes to REVIEW.
    jurisdiction_not_encoded = "jurisdiction_not_encoded"


#: Reason codes emitted alongside a non-trusted verdict.
REASON_FOR_VERDICT: dict[Verdict, str] = {
    Verdict.unverified: "RULE_UNVERIFIED",
    Verdict.zone_not_encoded: "ZONE_NOT_ENCODED",
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

    @property
    def trusted(self) -> bool:
        return self.status is Status.verified


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

    @property
    def trusted(self) -> bool:
        return self.verdict is Verdict.trusted

    @property
    def reason(self) -> str | None:
        return REASON_FOR_VERDICT.get(self.verdict)

    def get(self, name: str, default: Any = None) -> Any:
        r = self.values.get(name)
        return default if r is None else r.value


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

    def eligible(self, layer_id: str) -> bool:
        """Jurisdiction toggle. Report-time policy — never a structural drop."""
        layer = self.layers.get(layer_id)
        return bool(layer and layer.eligible)

    # -- resolution ---------------------------------------------------

    def resolve(self, layer_id: str, zone: str) -> ZoneResolution:
        chain = self.chain_for(layer_id)
        chain_ids = tuple(reversed([layer.layer for layer in chain]))

        target = self.layers.get(layer_id)
        if target is None:
            return ZoneResolution(
                layer_id, zone, Verdict.jurisdiction_not_encoded, chain=chain_ids
            )

        zone_block = target.zones.get(zone)
        if zone_block is None:
            return ZoneResolution(layer_id, zone, Verdict.zone_not_encoded, chain=chain_ids)

        resolved: dict[str, Resolved] = {}
        locked: set[str] = set()

        def apply(values: dict[str, Value], layer: str, origin: str) -> None:
            for name, val in values.items():
                if name in locked:
                    # A preempting ancestor already fixed this field. Record what
                    # was displaced so the UI can say why the local number lost.
                    prev = resolved[name]
                    resolved[name] = Resolved(
                        prev.name, prev.value, prev.status, prev.prov, prev.layer,
                        prev.origin, preempted=True, shadowed=val.value,
                    )
                    continue
                resolved[name] = Resolved(name, val.value, val.status, val.prov, layer, origin)
                if val.preempts:
                    locked.add(name)

        # Least specific first so later layers override — except where locked.
        for layer in chain:
            apply(layer.defaults, layer.layer, "defaults")
        apply(zone_block.values, target.layer, "zone")

        untrusted = tuple(sorted(n for n, r in resolved.items() if not r.trusted))
        missing = tuple(sorted(REQUIRED_FIELDS - set(resolved)))
        verdict = Verdict.trusted if not untrusted and not missing else Verdict.unverified

        return ZoneResolution(
            jurisdiction=layer_id,
            zone=zone,
            verdict=verdict,
            values=resolved,
            untrusted=untrusted,
            missing_required=missing,
            chain=chain_ids,
        )
