"""A number somebody read and does not believe, recorded so it stops counting.

Verification and dispute are the same mechanism pointed in opposite
directions. A verification is a signature saying *I read this against its
source and it is right*; a dispute says *I read this against its source and
something is wrong*. Both are hashed over the value, its citation and its
quote, and both stop applying the moment any of those change.

That symmetry is the whole design. A dispute nobody has to remember to
withdraw is a dispute that cannot go stale: fix the number in response to it
and the fingerprint stops matching, the demotion silently stops applying, and
the value goes back to whatever the verification log says about it. Nothing
sweeps up.

Why it exists at all: review is batched. Somebody works a page, notices two
numbers that look wrong, and writes them down to encode later that week. In
between, the screen goes on showing those numbers with nothing to say they are
under question -- and a reviewer who has already flagged a value has no way to
stop somebody else acting on it. The gap between noticing and encoding is a
window where the system is confidently wrong and silent about it.

``disputed`` is not ``draft``. Draft means nobody has looked. Disputed means
somebody looked and said no, which is strictly more information and belongs in
a different bucket -- a queue of answered questions waiting to be encoded, not
a queue of unread ones.

Order of operations at load: parse YAML (everything draft), apply
verifications (promote what still matches), apply disputes (demote what
somebody rejected), apply staleness (demote what the source outran). Disputes
run after verifications because a rejection recorded after a signature is
somebody disagreeing with the signature, and the disagreement wins until it is
settled.

The log is append-only JSONL, same as verifications. A dispute is withdrawn by
appending a withdrawal, never by editing -- an argument that was had and
settled is part of the record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from flats.encode.verify import LIKE, fingerprint, like_payload
from flats.rules.model import Layer, Status, Value, Variant

#: Beside the verification log, because they are two halves of one record and
#: reading either without the other tells you less than half the story.
LOG_PATH = Path(__file__).resolve().parents[1] / "config" / "disputes.jsonl"

#: Identity of the thing under dispute: layer, zone, field, variant key.
DisKey = tuple[str, str, str, tuple[str, ...]]

#: What the reviewer said, in the vocabulary the browser already records.
#:
#: ``unclear`` is not indecision. It is the reviewer saying the quoted page
#: does not answer the question -- a finding about the encoding rather than
#: about the number -- and it disqualifies the value just as firmly, because a
#: number whose source does not state it is not a number we may screen on.
VERDICTS = ("rejected", "unclear")

VALUE_CHANGED = "value_changed"
FIELD_GONE = "field_gone"


class DisputeError(Exception):
    """A malformed entry in the dispute log."""


@dataclass(frozen=True, slots=True)
class Dispute:
    """One signed statement that a value was read and is not right."""

    layer: str
    zone: str
    field: str
    fingerprint: str
    reviewer: str
    raised: date
    #: ``rejected`` or ``unclear``.
    verdict: str = "rejected"
    #: Which variant was read. Empty is the base value.
    when: tuple[str, ...] = ()
    #: Why. The route that writes these requires it -- a bare rejection tells
    #: an encoder nothing and cannot be acted on.
    note: str = ""
    #: A withdrawal. The entry stays in the log so the argument survives.
    withdrawn: bool = False

    @property
    def key(self) -> DisKey:
        return (self.layer, self.zone, self.field, tuple(sorted(self.when)))

    @property
    def label(self) -> str:
        """How this reads in a queue: the field, or the field under conditions."""
        if not self.when:
            return self.field
        return self.field + " [" + "+".join(sorted(self.when)) + "]"

    def to_json(self) -> str:
        return json.dumps(
            {
                "layer": self.layer,
                "zone": self.zone,
                "field": self.field,
                "fingerprint": self.fingerprint,
                "reviewer": self.reviewer,
                "raised": self.raised.isoformat(),
                "verdict": self.verdict,
                "when": sorted(self.when),
                "note": self.note,
                "withdrawn": self.withdrawn,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Dispute:
        try:
            verdict = str(raw.get("verdict", "rejected"))
            if verdict not in VERDICTS:
                raise ValueError(
                    "verdict " + repr(verdict) + " is not one of " + ", ".join(VERDICTS)
                )
            return cls(
                layer=str(raw["layer"]),
                zone=str(raw["zone"]),
                field=str(raw["field"]),
                fingerprint=str(raw["fingerprint"]),
                reviewer=str(raw["reviewer"]),
                raised=date.fromisoformat(str(raw["raised"])),
                verdict=verdict,
                when=tuple(sorted(str(c) for c in raw.get("when", ()))),
                note=str(raw.get("note", "")),
                withdrawn=bool(raw.get("withdrawn", False)),
            )
        except (KeyError, ValueError) as exc:
            raise DisputeError(f"malformed dispute entry: {exc}") from exc


class DisputeLog:
    """Append-only record of who rejected what.

    Collapses to the latest entry per value; the earlier ones stay on disk. A
    reviewer who changes their mind appends a withdrawal rather than deleting,
    for the same reason the verification log works that way: that a number was
    once doubted is worth as much to the next reader as the doubt being lifted.
    """

    def __init__(self, entries: Iterable[Dispute] = ()) -> None:
        self.entries: list[Dispute] = list(entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[Dispute]:
        return iter(self.entries)

    def current(self) -> dict[DisKey, Dispute]:
        """Latest entry per value, withdrawals included so they can be seen."""
        out: dict[DisKey, Dispute] = {}
        for e in self.entries:
            out[e.key] = e
        return out

    def active(self) -> dict[DisKey, Dispute]:
        """Latest entry per value, withdrawals removed."""
        return {k: d for k, d in self.current().items() if not d.withdrawn}

    def append(self, entry: Dispute, path: Path | None = None) -> None:
        self.entries.append(entry)
        target = path or LOG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="") as fh:
            fh.write(entry.to_json() + "\n")

    @classmethod
    def load(cls, path: Path | None = None) -> DisputeLog:
        target = path or LOG_PATH
        if not target.is_file():
            # Nothing disputed is a legitimate state, and the common one.
            return cls()
        entries = []
        for n, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DisputeError(f"{target}:{n}: {exc}") from exc
            try:
                entries.append(Dispute.from_dict(raw))
            except DisputeError as exc:
                raise DisputeError(f"{target}:{n}: {exc}") from exc
        return cls(entries)


@dataclass(frozen=True, slots=True)
class Answered:
    """A dispute whose value has since changed.

    Not an error and not a leak. Somebody rejected a number, somebody else
    edited it, and the rejection no longer describes what is written -- so it
    stops demoting and lands here instead, where it reads as *this was acted
    on* rather than vanishing. Whether the edit addressed the complaint is a
    question for a person, so the note comes along to let them ask it.
    """

    layer: str
    zone: str
    field: str
    reviewer: str
    raised: date
    verdict: str
    note: str
    #: ``value_changed`` when the field is still there but different,
    #: ``field_gone`` when nothing by that name remains.
    reason: str
    when: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        if not self.when:
            return self.field
        return self.field + " [" + "+".join(self.when) + "]"


def _matches(layer_id: str, zone_name: str, name: str, part: Value | Variant, d: Dispute) -> bool:
    """Is this dispute still about what is written here?"""
    when = getattr(part, "when", ())
    expected = fingerprint(
        layer_id,
        zone_name,
        name,
        part.value,
        cite=part.prov.cite,
        quote=part.prov.quote,
        when=when,
    )
    return expected == d.fingerprint


def _answered(d: Dispute, reason: str) -> Answered:
    return Answered(
        layer=d.layer,
        zone=d.zone,
        field=d.field,
        reviewer=d.reviewer,
        raised=d.raised,
        verdict=d.verdict,
        note=d.note,
        reason=reason,
        when=tuple(sorted(d.when)),
    )


def apply_disputes(
    layers: Mapping[str, Layer], log: DisputeLog
) -> tuple[dict[str, Layer], list[Answered]]:
    """Demote values a reviewer rejected, and report the ones that moved on.

    A demotion here outranks a promotion from the verification log: a
    rejection recorded after a signature is somebody disagreeing with the
    signature, and until that argument is settled the number is not one this
    screen may call trusted.
    """
    active = log.active()
    used: set[DisKey] = set()
    out: dict[str, Layer] = {}

    for layer_id, layer in layers.items():
        changed = False

        def demote_block(zone_name: str, values: dict[str, Value]) -> dict[str, Value]:
            nonlocal changed
            updated: dict[str, Value] = {}
            for name, value in values.items():
                edits: dict[str, object] = {}

                # Variants first, for the same reason verification takes them
                # first: each is its own reading of its own sentence, and a
                # value with a sound base and one bad exception is the common
                # case rather than the odd one.
                variants = []
                for variant in value.variants:
                    d = active.get((layer_id, zone_name, name, variant.key))
                    if d is None or not _matches(layer_id, zone_name, name, variant, d):
                        variants.append(variant)
                        continue
                    used.add(d.key)
                    variants.append(
                        variant
                        if variant.status is Status.disputed
                        else variant.model_copy(update={"status": Status.disputed})
                    )
                if tuple(variants) != value.variants:
                    edits["variants"] = tuple(variants)

                d = active.get((layer_id, zone_name, name, ()))
                if d is not None and _matches(layer_id, zone_name, name, value, d):
                    used.add(d.key)
                    if value.status is not Status.disputed:
                        # ``reviewer`` and ``reviewed`` are left alone. They
                        # say who confirmed a value, and writing the name of
                        # somebody who rejected it into those fields would put
                        # a doubter where a reader looks for a confirmer.
                        edits["status"] = Status.disputed

                if edits:
                    updated[name] = value.model_copy(update=edits)
                    changed = True
                else:
                    updated[name] = value
            return updated

        def demote_like(zone_code: str, zone: Any) -> Any:
            """The borrowed-zone reference, doubted on its own account."""
            nonlocal changed
            if zone.like is None:
                return None
            d = active.get((layer_id, zone_code, LIKE, ()))
            if d is None:
                return None
            expected = fingerprint(
                layer_id,
                zone_code,
                LIKE,
                like_payload(zone.like),
                cite=zone.like.prov.cite,
                quote=zone.like.prov.quote,
            )
            if expected != d.fingerprint:
                return None
            used.add(d.key)
            if zone.like.status is Status.disputed:
                return None
            changed = True
            return zone.like.model_copy(update={"status": Status.disputed})

        defaults = demote_block("defaults", dict(layer.defaults))
        zones = {}
        for zone_code, zone in layer.zones.items():
            values = demote_block(zone_code, dict(zone.values))
            edits = {}
            if values != zone.values:
                edits["values"] = values
            demoted_like = demote_like(zone_code, zone)
            if demoted_like is not None:
                edits["like"] = demoted_like
            zones[zone_code] = zone.model_copy(update=edits) if edits else zone
        out[layer_id] = (
            layer.model_copy(update={"defaults": defaults, "zones": zones}) if changed else layer
        )

    answered = []
    for key, d in active.items():
        if key in used:
            continue
        layer = layers.get(d.layer)
        present = False
        if layer is not None:
            if d.zone == "defaults":
                present = d.field in layer.defaults
            elif d.zone in layer.zones:
                zone = layer.zones[d.zone]
                present = d.field in zone.values or (d.field == LIKE and zone.like is not None)
        answered.append(_answered(d, VALUE_CHANGED if present else FIELD_GONE))
    answered.sort(key=lambda a: (a.layer, a.zone, a.field, a.when))
    return out, answered
