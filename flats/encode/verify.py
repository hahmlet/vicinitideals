"""Verification as a signature over a value, not a flag inside it.

Somebody has to read the code text and confirm that the number beside it is
right. The obvious place to record that is in the rule file — ``status:
verified``, a reviewer, a date. The obvious place is wrong for two reasons.

*The files are hand-authored.* A verification tool that edits them churns
someone's YAML under them and loses comments to a round-trip.

*A flag does not know what it approved.* Edit the number a week later and the
``verified`` stays put, now certifying a value nobody ever read. That is the
worst failure this system can have: an untrue claim of review, indistinguishable
from a true one.

So a verification is a signed statement about a specific value: a hash over the
jurisdiction, zone, field, the value itself, its citation and its quote. Change
any of those and the signature stops matching, the promotion silently stops
applying, and the field is back to draft where it belongs. Nothing has to
remember to invalidate anything.

The log is append-only JSONL. Later entries for the same field supersede
earlier ones, and ``revoked`` withdraws a verification without erasing the fact
that it once existed — an audit trail of who believed what, when.

Order of operations at load: parse YAML (everything draft), apply verifications
(promote what still matches), apply staleness (demote what the source outran).
Promotion and demotion are separate passes because they answer different
questions — was this read, and is what was read still true.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from flats.rules.model import LIKE, Incorporation, Layer, Status, Value, Variant

LOG_PATH = Path(__file__).resolve().parents[1] / "config" / "verifications.jsonl"

#: (layer, zone, field, when). ``when`` is empty for a base value and names
#: the sorted conditions of a variant — one signature per number, not per field.
VerKey = tuple[str, str, str, tuple[str, ...]]


class VerificationError(Exception):
    """The verification log is malformed."""


def fingerprint(
    layer: str,
    zone: str,
    field: str,
    value: Any,
    *,
    cite: str = "",
    quote: str | None = None,
    when: Sequence[str] = (),
) -> str:
    """Hash of everything a reviewer was looking at when they signed off.

    The value and its evidence are both in the hash. Correcting a setback from
    10 to 15 invalidates its verification, and so does re-pointing the quote at
    a different section — because in both cases what was reviewed is no longer
    what is there.

    ``when`` names the variant. The base value and each exception hash apart, so
    signing "5 ft." cannot silently certify "10 ft. where affordable" — a
    reviewer reads one sentence at a time and signs for the one they read. The
    conditions are sorted, because the order somebody typed them in is not part
    of what was reviewed.
    """
    payload = json.dumps(
        {
            "layer": layer,
            "zone": zone,
            "field": field,
            "value": value,
            "cite": cite,
            "quote": quote or "",
            "when": sorted(when),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Verification:
    """One signed statement that a value was read against its source."""

    layer: str
    zone: str
    field: str
    fingerprint: str
    reviewer: str
    reviewed: date
    #: Which variant was read. Empty is the base value.
    when: tuple[str, ...] = ()
    note: str = ""
    #: A withdrawal. The entry stays in the log so the history survives.
    revoked: bool = False

    @property
    def key(self) -> VerKey:
        return (self.layer, self.zone, self.field, tuple(sorted(self.when)))

    @property
    def label(self) -> str:
        """How this reads in a queue: the field, or the field under conditions."""
        return f"{self.field} [{'+'.join(sorted(self.when))}]" if self.when else self.field

    def to_json(self) -> str:
        return json.dumps(
            {
                "layer": self.layer,
                "zone": self.zone,
                "field": self.field,
                "fingerprint": self.fingerprint,
                "reviewer": self.reviewer,
                "reviewed": self.reviewed.isoformat(),
                "when": sorted(self.when),
                "note": self.note,
                "revoked": self.revoked,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Verification:
        try:
            return cls(
                layer=str(raw["layer"]),
                zone=str(raw["zone"]),
                field=str(raw["field"]),
                fingerprint=str(raw["fingerprint"]),
                reviewer=str(raw["reviewer"]),
                reviewed=date.fromisoformat(str(raw["reviewed"])),
                when=tuple(sorted(str(c) for c in raw.get("when", ()))),
                note=str(raw.get("note", "")),
                revoked=bool(raw.get("revoked", False)),
            )
        except (KeyError, ValueError) as exc:
            raise VerificationError(f"malformed verification entry: {exc}") from exc


class VerificationLog:
    """Append-only record of who verified what.

    Reading collapses the log to the latest entry per field; the earlier ones
    stay on disk. Nothing here rewrites history — a mistaken verification is
    withdrawn by appending, not by editing.
    """

    def __init__(self, entries: Iterable[Verification] = ()) -> None:
        self.entries: list[Verification] = list(entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[Verification]:
        return iter(self.entries)

    def current(self) -> dict[VerKey, Verification]:
        """Latest entry per field, withdrawals included so they can be seen."""
        out: dict[VerKey, Verification] = {}
        for e in self.entries:
            out[e.key] = e
        return out

    def active(self) -> dict[VerKey, Verification]:
        """Latest entry per field, withdrawals removed."""
        return {k: v for k, v in self.current().items() if not v.revoked}

    def append(self, entry: Verification, path: Path | None = None) -> None:
        self.entries.append(entry)
        target = path or LOG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="") as fh:
            fh.write(entry.to_json() + "\n")

    @classmethod
    def load(cls, path: Path | None = None) -> VerificationLog:
        target = path or LOG_PATH
        if not target.is_file():
            # No verifications yet is a legitimate state, and the correct one
            # for a jurisdiction nobody has reviewed. It is not an error.
            return cls()
        entries = []
        for n, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise VerificationError(f"{target}:{n}: {exc}") from exc
            try:
                entries.append(Verification.from_dict(raw))
            except VerificationError as exc:
                # A wrong-shaped entry is the same problem to whoever has
                # to fix it as a truncated one, so it gets the same context.
                raise VerificationError(f"{target}:{n}: {exc}") from exc
        return cls(entries)


def like_payload(like: Incorporation) -> str:
    """What a reviewer is agreeing to when they sign an incorporation.

    Both halves matter. Pointing at a different zone obviously changes what the
    numbers are; flipping which text governs on conflict changes it just as much
    and is far easier to edit without anyone noticing.
    """
    return f"{like.zone}|{like.wins}"


def sign_like(
    layer: str,
    zone: str,
    like: Incorporation,
    *,
    reviewer: str,
    reviewed: date,
    note: str = "",
) -> Verification:
    """Build a verification for a zone's claim to adopt another zone."""
    return Verification(
        layer=layer,
        zone=zone,
        field=LIKE,
        fingerprint=fingerprint(
            layer, zone, LIKE, like_payload(like), cite=like.prov.cite, quote=like.prov.quote
        ),
        reviewer=reviewer,
        reviewed=reviewed,
        note=note,
    )


def variant_for(value: Value, when: Sequence[str]) -> Variant:
    """The exception this reviewer means, found by its exact condition set.

    Exact, not most-specific: :meth:`Value.under` answers "what applies to this
    lot", which is a different question from "which sentence am I signing". A
    near-miss here would put a signature on a number nobody looked at.
    """
    want = frozenset(when)
    for variant in value.variants:
        if frozenset(variant.when) == want:
            return variant
    known = [" + ".join(sorted(v.when)) for v in value.variants] or ["(none encoded)"]
    raise VerificationError(
        f"{value.name}: no variant under {sorted(want)} — encoded variants are {known}"
    )


def sign(
    layer: str,
    zone: str,
    field: str,
    value: Value,
    *,
    reviewer: str,
    reviewed: date,
    note: str = "",
    when: Sequence[str] = (),
) -> Verification:
    """Build a verification for a value as it currently stands.

    ``when`` signs one of the value's variants rather than its base. They are
    separate signatures over separate text, so a value whose variants are
    unsigned is only partly reviewed — which is what the queue should say about
    it, instead of showing it green.
    """
    signed: Value | Variant = variant_for(value, when) if when else value
    return Verification(
        layer=layer,
        zone=zone,
        field=field,
        fingerprint=fingerprint(
            layer,
            zone,
            field,
            signed.value,
            cite=signed.prov.cite,
            quote=signed.prov.quote,
            when=when,
        ),
        reviewer=reviewer,
        reviewed=reviewed,
        when=tuple(sorted(when)),
        note=note,
    )


@dataclass(frozen=True, slots=True)
class Orphan:
    """A verification that no longer matches the value it was signed against."""

    layer: str
    zone: str
    field: str
    reviewer: str
    reviewed: date
    #: "value_changed" when the field is still there but different,
    #: "field_gone" when nothing by that name remains.
    reason: str
    #: The variant this signature was over. Empty is the base value. A base
    #: that still stands while its exception was rewritten produces exactly one
    #: orphan, and this is what says which.
    when: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.field} [{'+'.join(self.when)}]" if self.when else self.field


VALUE_CHANGED = "value_changed"
FIELD_GONE = "field_gone"


def _promote(value: Value, v: Verification) -> Value:
    return value.model_copy(
        update={"status": Status.verified, "reviewer": v.reviewer, "reviewed": v.reviewed}
    )


def _promote_variant(variant: Variant, v: Verification) -> Variant:
    return variant.model_copy(
        update={"status": Status.verified, "reviewer": v.reviewer, "reviewed": v.reviewed}
    )


def _matches(
    layer_id: str, zone_name: str, name: str, part: Value | Variant, v: Verification
) -> bool:
    """Is this signature still over what is written here?"""
    when = getattr(part, "when", ())
    expected = fingerprint(
        layer_id, zone_name, name, part.value, cite=part.prov.cite, quote=part.prov.quote, when=when
    )
    return expected == v.fingerprint


def apply_verifications(
    layers: Mapping[str, Layer], log: VerificationLog
) -> tuple[dict[str, Layer], list[Orphan]]:
    """Promote values whose signature still matches, and report the ones that do not.

    An orphaned verification is not a failure to fix quietly. It means somebody
    reviewed a number and the number has since changed — the field drops back
    to draft on its own, and the orphan is the queue entry that says why.
    """
    active = log.active()
    used: set[VerKey] = set()
    out: dict[str, Layer] = {}

    for layer_id, layer in layers.items():
        changed = False

        def promote_block(zone_name: str, values: dict[str, Value]) -> dict[str, Value]:
            nonlocal changed
            updated: dict[str, Value] = {}
            for name, value in values.items():
                edits: dict[str, object] = {}

                # The exceptions first: each is its own signature over its own
                # sentence, and a value can perfectly well have a verified base
                # and a draft variant. That mix is the honest state of most
                # half-reviewed standards, and it has to survive this pass.
                variants = []
                for variant in value.variants:
                    key = (layer_id, zone_name, name, tuple(sorted(variant.when)))
                    v = active.get(key)
                    if v is None or not _matches(layer_id, zone_name, name, variant, v):
                        variants.append(variant)
                        continue
                    used.add(v.key)
                    variants.append(
                        variant
                        if variant.status is Status.verified
                        else _promote_variant(variant, v)
                    )
                if tuple(variants) != value.variants:
                    edits["variants"] = tuple(variants)

                v = active.get((layer_id, zone_name, name, ()))
                if v is not None and _matches(layer_id, zone_name, name, value, v):
                    # Matched, so the verification is accounted for either way —
                    # a file that already declares `verified` keeps its own
                    # reviewer rather than having the log overwrite it.
                    used.add(v.key)
                    if value.status is not Status.verified:
                        edits.update(
                            status=Status.verified, reviewer=v.reviewer, reviewed=v.reviewed
                        )

                if edits:
                    updated[name] = value.model_copy(update=edits)
                    changed = True
                else:
                    updated[name] = value
            return updated

        def promote_like(zone_code: str, zone):
            """The reference itself, promoted on its own signature."""
            nonlocal changed
            if zone.like is None:
                return None
            v = active.get((layer_id, zone_code, LIKE, ()))
            if v is None:
                return None
            expected = fingerprint(
                layer_id,
                zone_code,
                LIKE,
                like_payload(zone.like),
                cite=zone.like.prov.cite,
                quote=zone.like.prov.quote,
            )
            if expected != v.fingerprint:
                # Repointed at a different zone, or the conflict rule flipped.
                return None
            used.add(v.key)
            if zone.like.status is Status.verified:
                return None
            changed = True
            return zone.like.model_copy(
                update={"status": Status.verified, "reviewer": v.reviewer, "reviewed": v.reviewed}
            )

        defaults = promote_block("defaults", dict(layer.defaults))
        zones = {}
        for zone_code, zone in layer.zones.items():
            values = promote_block(zone_code, dict(zone.values))
            edits = {}
            if values != zone.values:
                edits["values"] = values
            promoted_like = promote_like(zone_code, zone)
            if promoted_like is not None:
                edits["like"] = promoted_like
            zones[zone_code] = zone.model_copy(update=edits) if edits else zone
        out[layer_id] = (
            layer.model_copy(update={"defaults": defaults, "zones": zones}) if changed else layer
        )

    orphans = []
    for key, v in active.items():
        if key in used:
            continue
        layer_id, zone_name, field, when = key
        layer = layers.get(layer_id)
        present = False
        if layer is not None:
            block = layer.defaults if zone_name == "defaults" else (
                layer.zones[zone_name].values if zone_name in layer.zones else {}
            )
            if field == LIKE:
                zone_block = layer.zones.get(zone_name) if zone_name != "defaults" else None
                present = zone_block is not None and zone_block.like is not None
            else:
                value = block.get(field)
                # A variant whose conditions were rewritten is gone in the sense
                # that matters: there is no longer any sentence this signature
                # could stand over, so it reads the same as a deleted field.
                present = value is not None and (
                    not when or any(frozenset(x.when) == frozenset(when) for x in value.variants)
                )
        orphans.append(
            Orphan(
                layer=layer_id,
                zone=zone_name,
                field=field,
                reviewer=v.reviewer,
                reviewed=v.reviewed,
                reason=VALUE_CHANGED if present else FIELD_GONE,
                when=when,
            )
        )
    orphans.sort(key=lambda o: (o.layer, o.zone, o.field, o.when))
    return out, orphans
