"""What stands between a jurisdiction and screenable lots.

The encoding effort is a queue of jurisdictions, not a pile of 603 undifferentiated
values, and the two consumers that matter — a person working a review UI and an
agent picking up work — both need the same thing from it: *for this jurisdiction,
what is the next blocking action?*

``review status`` answers "0.0% verified", which is true and useless. It cannot
distinguish a city nobody has found a code URL for from one where every number is
written, quoted and waiting on a signature. Those are hours apart in effort and
they belong in different places in a queue.

So readiness is a **ladder**, and a jurisdiction sits on the first rung it fails:

===============  =========================================================
stage            what it means
===============  =========================================================
``no_zones``     nothing encoded here at all
``no_source``    zones written, no document declared to read them from
``unfetched``    documents declared, not in the store
``unquoted``     values that point at no text — unreviewable as written
``no_evidence``  quotes that do not resolve to stored text
``unsigned``     everything present; waiting on somebody to read it
``stale``        read, but the source has moved since
``ready``        every value verified against text that still says it
===============  =========================================================

The ladder is ordered by what blocks what, not by severity. Signing values whose
evidence was never fetched is not possible, so ``unfetched`` outranks ``unsigned``
however few documents are missing. That ordering is the whole product: it turns
"603 drafts" into one sentence per jurisdiction that names the next command.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from flats.encode.load import Trusted
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.model import LIKE, Layer, Status

#: Rungs, blocking-order first. A jurisdiction reports the first one it fails.
STAGES = (
    "no_zones",
    "no_source",
    "unfetched",
    "unquoted",
    "no_evidence",
    "unsigned",
    "stale",
    "ready",
)

#: What to do about each, phrased as the thing somebody would actually run or
#: read. `{layer}` is filled in; anything else is prose on purpose, because the
#: first two rungs are human work with no command behind them.
ACTION = {
    "no_zones": "encode this jurisdiction's zones: nothing is written yet",
    "no_source": "find the URL that serves the ordinance text, and declare it under `code:`",
    "unfetched": "python -m flats.provenance.fetch --layer {layer}",
    "unquoted": "add quotes: a value pointing at no text cannot be reviewed",
    "no_evidence": "python -m flats.provenance.fetch --layer {layer} (quotes point at text that is not stored)",
    "unsigned": "python -m flats.encode.review queue --layer {layer}, then read and sign",
    "stale": "re-read the values whose source moved, then re-sign",
    "ready": "nothing: every value is verified against text that still says it",
}


@dataclass(frozen=True, slots=True)
class Readiness:
    """One jurisdiction's position on the ladder, and the counts behind it."""

    layer: str
    label: str
    stage: str
    zones: int = 0
    values: int = 0
    verified: int = 0
    #: Declared documents that are not in the store.
    unfetched: tuple[str, ...] = ()
    #: (zone, field) pairs carrying no quote.
    unquoted: tuple[tuple[str, str], ...] = ()
    #: (zone, field) pairs whose quote does not resolve.
    no_evidence: tuple[tuple[str, str], ...] = ()
    #: Values demoted because their evidence moved.
    stale: int = 0

    @property
    def rung(self) -> int:
        return STAGES.index(self.stage)

    @property
    def ready(self) -> bool:
        return self.stage == "ready"

    @property
    def pct_verified(self) -> float:
        return 100.0 * self.verified / self.values if self.values else 0.0

    @property
    def action(self) -> str:
        return ACTION[self.stage].format(layer=self.layer)

    def line(self) -> str:
        return (
            f"{self.stage:12} {self.layer:34} {self.verified:>4}/{self.values:<4} verified"
            f"  -> {self.action}"
        )


def _quoted_parts(layer: Layer) -> Iterable[tuple[str, str, str | None]]:
    """Every (zone, field, quote) in a layer, exceptions and references included.

    A variant citing a different chapter and an incorporation clause are both
    values somebody has to read, so both are counted here. Leaving either out
    would report a jurisdiction as finished with unread rules in it.
    """
    yield from ((("defaults"), name, v.prov.quote) for name, v in layer.defaults.items())
    for zone_code, zone in layer.zones.items():
        for name, value in zone.values.items():
            yield zone_code, name, value.prov.quote
            for variant in value.variants:
                yield zone_code, f"{name} [{'+'.join(sorted(variant.when))}]", variant.prov.quote
        if zone.like is not None:
            yield zone_code, LIKE, zone.like.prov.quote


def _statuses(layer: Layer) -> list[Status]:
    out = [v.status for v in layer.defaults.values()]
    for zone in layer.zones.values():
        for value in zone.values.values():
            out.append(value.status)
            out.extend(v.status for v in value.variants)
        if zone.like is not None:
            out.append(zone.like.status)
    return out


def readiness_for(
    layer: Layer, *, store: ProvenanceStore, stale: int = 0
) -> Readiness:
    """Place one jurisdiction on the ladder."""
    statuses = _statuses(layer)
    verified = sum(1 for s in statuses if s is Status.verified)

    unfetched = tuple(sorted(p for p in layer.documents() if not store.exists(p)))
    unquoted: list[tuple[str, str]] = []
    no_evidence: list[tuple[str, str]] = []
    for zone_code, name, quote in _quoted_parts(layer):
        if not quote:
            unquoted.append((zone_code, name))
            continue
        try:
            store.quote(quote)
        except (ProvenanceError, KeyError, ValueError):
            # Whatever went wrong — document absent, line range past the end,
            # malformed reference — the reviewer's problem is the same: there
            # is nothing on screen to compare the number against.
            no_evidence.append((zone_code, name))

    if not layer.zones and not layer.defaults:
        stage = "no_zones"
    elif not layer.code:
        stage = "no_source"
    elif unfetched:
        stage = "unfetched"
    elif unquoted:
        stage = "unquoted"
    elif no_evidence:
        stage = "no_evidence"
    elif verified < len(statuses):
        stage = "unsigned"
    elif stale:
        stage = "stale"
    else:
        stage = "ready"

    return Readiness(
        layer=layer.layer,
        label=layer.label,
        stage=stage,
        zones=len(layer.zones),
        values=len(statuses),
        verified=verified,
        unfetched=unfetched,
        unquoted=tuple(unquoted),
        no_evidence=tuple(no_evidence),
        stale=stale,
    )


def readiness(trusted: Trusted, store: ProvenanceStore) -> list[Readiness]:
    """Every jurisdiction, worst rung first.

    Ties break on how much is already verified, descending — among cities at the
    same rung, the one closest to done is the cheapest to finish, and finishing
    one jurisdiction is worth more than advancing three, because a half-encoded
    city screens no lots at all.
    """
    stale_by_layer: dict[str, int] = {}
    for s in trusted.stale:
        stale_by_layer[s.layer] = stale_by_layer.get(s.layer, 0) + 1

    out = [
        readiness_for(layer, store=store, stale=stale_by_layer.get(layer_id, 0))
        for layer_id, layer in trusted.layers.items()
    ]
    out.sort(key=lambda r: (r.rung, -r.pct_verified, r.layer))
    return out


def by_stage(reports: Iterable[Readiness]) -> dict[str, int]:
    """How many jurisdictions sit on each rung, in ladder order."""
    counts = {stage: 0 for stage in STAGES}
    for r in reports:
        counts[r.stage] += 1
    return {k: v for k, v in counts.items() if v}


__all__ = [
    "ACTION",
    "STAGES",
    "Readiness",
    "by_stage",
    "readiness",
    "readiness_for",
]
