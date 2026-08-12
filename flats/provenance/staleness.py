"""Demote values whose evidence no longer holds.

Staleness is computed at load time from hashes on disk, never written back into
the rule YAML. Two reasons a `verified` value stops being trustworthy:

``source_changed``
    A re-fetch of the cited URL produced different text. The number may still be
    right, but nobody has checked it against the new words.

``evidence_missing``
    The value claims verification but its quote does not resolve to stored text.
    A verification nobody can re-check is an assertion, and an assertion from
    six months ago is exactly what this whole apparatus exists to avoid.

Both demote to `stale`, which routes the zone to REVIEW rather than deleting it.
That is the recall bias again: losing confidence in a rule is a reason to look
again, never a reason to quietly drop the lots it governs.

Only `verified` values are demoted. A draft is already untrusted, and marking it
stale would only blur why it is untrusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from flats.provenance.store import ProvenanceError, ProvenanceStore, parse_quote
from flats.rules.model import Layer, Status, Value

#: Reason codes, surfaced to the review queue so a reviewer knows what to do.
SOURCE_CHANGED = "source_changed"
EVIDENCE_MISSING = "evidence_missing"


@dataclass(frozen=True, slots=True)
class Staleness:
    """One demoted value and why."""

    layer: str
    #: Zone code, or ``"defaults"`` for a layer-level value.
    zone: str
    field: str
    reason: str
    detail: str = ""


def _demote(value: Value) -> Value:
    return value.model_copy(update={"status": Status.stale})


def _reason_for(
    value: Value, invalidated: frozenset[str], store: ProvenanceStore | None, require_quote: bool
) -> tuple[str, str] | None:
    """Why this value should be demoted, or None to leave it alone."""
    if value.status is not Status.verified:
        return None

    quote = value.prov.quote
    if not quote:
        if require_quote:
            return EVIDENCE_MISSING, "verified with no quote into the provenance store"
        return None

    try:
        path = parse_quote(quote).path
    except ProvenanceError as exc:
        return EVIDENCE_MISSING, str(exc)

    if path in invalidated:
        return SOURCE_CHANGED, f"{path} changed since it was verified"

    if store is not None:
        try:
            store.quote(quote)
        except ProvenanceError as exc:
            return EVIDENCE_MISSING, str(exc)

    return None


def apply_staleness(
    layers: Mapping[str, Layer],
    invalidated: Iterable[str] = (),
    *,
    store: ProvenanceStore | None = None,
    require_quote: bool = True,
) -> tuple[dict[str, Layer], list[Staleness]]:
    """Return layers with untrustworthy values demoted, plus the report.

    ``invalidated`` is the set of document paths a drift check found changed or
    missing. ``store``, when given, additionally checks that every verified
    value's quote actually resolves — catching a citation that points at text
    which was never fetched.
    """
    bad = frozenset(invalidated)
    out: dict[str, Layer] = {}
    report: list[Staleness] = []

    for layer_id, layer in layers.items():
        changed = False

        defaults: dict[str, Value] = {}
        for name, value in layer.defaults.items():
            found = _reason_for(value, bad, store, require_quote)
            if found:
                reason, detail = found
                report.append(Staleness(layer_id, "defaults", name, reason, detail))
                defaults[name] = _demote(value)
                changed = True
            else:
                defaults[name] = value

        zones = {}
        for zone_code, zone in layer.zones.items():
            values: dict[str, Value] = {}
            zone_changed = False
            for name, value in zone.values.items():
                found = _reason_for(value, bad, store, require_quote)
                if found:
                    reason, detail = found
                    report.append(Staleness(layer_id, zone_code, name, reason, detail))
                    values[name] = _demote(value)
                    zone_changed = True
                else:
                    values[name] = value
            zones[zone_code] = zone.model_copy(update={"values": values}) if zone_changed else zone
            changed = changed or zone_changed

        out[layer_id] = (
            layer.model_copy(update={"defaults": defaults, "zones": zones}) if changed else layer
        )

    report.sort(key=lambda s: (s.layer, s.zone, s.field))
    return out, report
