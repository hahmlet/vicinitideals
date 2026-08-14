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
``misquoted``    quotes that resolve, to text that does not state the number
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
    "misquoted",
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
    "unquoted": "python -m flats.encode.attach {layer} --doc {doc} (what it refuses, quote by hand)",
    "no_evidence": "python -m flats.provenance.fetch --layer {layer} (quotes point at text that is not stored)",
    "misquoted": (
        "python -m flats.encode.attach {layer} --doc {doc} — quotes resolve to text that "
        "does not state the number, which is what a re-fetch does to line numbers"
    ),
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
    #: (zone, field) pairs whose quote resolves to text without the number in
    #: it. The silent one: re-extracting a document moves every line, so a
    #: citation keeps pointing at line 136 while line 136 becomes a nav bar.
    #: Nothing else in the ladder can see that, because the value still has a
    #: quote and the quote still resolves.
    misquoted: tuple[tuple[str, str], ...] = ()
    #: Values demoted because their evidence moved.
    stale: int = 0
    #: A declared document, for actions that name one. The first is as good as
    #: any: a jurisdiction with several is one where somebody has to choose,
    #: and printing all of them would bury the sentence.
    doc: str = ""

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
        return ACTION[self.stage].format(layer=self.layer, doc=self.doc or "<document>")

    def line(self) -> str:
        return (
            f"{self.stage:12} {self.layer:34} {self.verified:>4}/{self.values:<4} verified"
            f"  -> {self.action}"
        )


def _quoted_parts(layer: Layer) -> Iterable[tuple[str, str, str | None, object]]:
    """Every (zone, field, quote, number) in a layer, exceptions included.

    A variant citing a different chapter and an incorporation clause are both
    values somebody has to read, so both are counted here. Leaving either out
    would report a jurisdiction as finished with unread rules in it.
    """
    yield from (
        ("defaults", name, v.prov.quote, getattr(v, "value", None))
        for name, v in layer.defaults.items()
    )
    for zone_code, zone in layer.zones.items():
        for name, value in zone.values.items():
            yield zone_code, name, value.prov.quote, getattr(value, "value", None)
            for variant in value.variants:
                yield (
                    zone_code,
                    f"{name} [{'+'.join(sorted(variant.when))}]",
                    variant.prov.quote,
                    getattr(variant, "value", None),
                )
        if zone.like is not None:
            yield zone_code, LIKE, zone.like.prov.quote, None


#: How a number can be printed in an ordinance: 7500, 7,500, 7500.0, 7.5.
def _renderings(number: float | int) -> tuple[str, ...]:
    whole = int(number)
    exact = whole if float(number) == whole else number
    out = {str(exact), f"{exact:,}" if isinstance(exact, int) else str(exact)}
    if isinstance(exact, float):
        out.add(f"{exact:g}")
    return tuple(out)


def quotes_the_number(text: str, value) -> bool:
    """Whether the cited text actually states the value's number.

    Deliberately generous: a code writes "7,500 sq ft" and "0.60" and "7.5
    ft", and a check that demanded one spelling would flag half the corpus.
    Non-numeric values — permission flags, enums, curves — are nothing this
    can check, so they pass. What it does catch is the citation that no
    longer points at its own sentence.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    return any(shape in text for shape in _renderings(value))


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
    misquoted: list[tuple[str, str]] = []
    for zone_code, name, quote, number in _quoted_parts(layer):
        if not quote:
            unquoted.append((zone_code, name))
            continue
        try:
            cited = store.quote(quote)
        except (ProvenanceError, KeyError, ValueError):
            # Whatever went wrong — document absent, line range past the end,
            # malformed reference — the reviewer's problem is the same: there
            # is nothing on screen to compare the number against.
            no_evidence.append((zone_code, name))
            continue
        if not quotes_the_number(cited, number):
            misquoted.append((zone_code, name))

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
    elif misquoted:
        stage = "misquoted"
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
        misquoted=tuple(misquoted),
        stale=stale,
        doc=next(iter(layer.documents()), ""),
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
