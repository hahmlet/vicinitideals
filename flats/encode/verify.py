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
from typing import Any, Iterable, Iterator, Mapping

from flats.rules.model import Layer, Status, Value

LOG_PATH = Path(__file__).resolve().parents[1] / "config" / "verifications.jsonl"


class VerificationError(Exception):
    """The verification log is malformed."""


def fingerprint(
    layer: str, zone: str, field: str, value: Any, *, cite: str = "", quote: str | None = None
) -> str:
    """Hash of everything a reviewer was looking at when they signed off.

    The value and its evidence are both in the hash. Correcting a setback from
    10 to 15 invalidates its verification, and so does re-pointing the quote at
    a different section — because in both cases what was reviewed is no longer
    what is there.
    """
    payload = json.dumps(
        {
            "layer": layer,
            "zone": zone,
            "field": field,
            "value": value,
            "cite": cite,
            "quote": quote or "",
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
    note: str = ""
    #: A withdrawal. The entry stays in the log so the history survives.
    revoked: bool = False

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.layer, self.zone, self.field)

    def to_json(self) -> str:
        return json.dumps(
            {
                "layer": self.layer,
                "zone": self.zone,
                "field": self.field,
                "fingerprint": self.fingerprint,
                "reviewer": self.reviewer,
                "reviewed": self.reviewed.isoformat(),
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

    def current(self) -> dict[tuple[str, str, str], Verification]:
        """Latest entry per field, withdrawals included so they can be seen."""
        out: dict[tuple[str, str, str], Verification] = {}
        for e in self.entries:
            out[e.key] = e
        return out

    def active(self) -> dict[tuple[str, str, str], Verification]:
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


def sign(
    layer: str,
    zone: str,
    field: str,
    value: Value,
    *,
    reviewer: str,
    reviewed: date,
    note: str = "",
) -> Verification:
    """Build a verification for a value as it currently stands."""
    return Verification(
        layer=layer,
        zone=zone,
        field=field,
        fingerprint=fingerprint(
            layer, zone, field, value.value, cite=value.prov.cite, quote=value.prov.quote
        ),
        reviewer=reviewer,
        reviewed=reviewed,
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


VALUE_CHANGED = "value_changed"
FIELD_GONE = "field_gone"


def _promote(value: Value, v: Verification) -> Value:
    return value.model_copy(
        update={"status": Status.verified, "reviewer": v.reviewer, "reviewed": v.reviewed}
    )


def apply_verifications(
    layers: Mapping[str, Layer], log: VerificationLog
) -> tuple[dict[str, Layer], list[Orphan]]:
    """Promote values whose signature still matches, and report the ones that do not.

    An orphaned verification is not a failure to fix quietly. It means somebody
    reviewed a number and the number has since changed — the field drops back
    to draft on its own, and the orphan is the queue entry that says why.
    """
    active = log.active()
    used: set[tuple[str, str, str]] = set()
    out: dict[str, Layer] = {}

    for layer_id, layer in layers.items():
        changed = False

        def promote_block(zone_name: str, values: dict[str, Value]) -> dict[str, Value]:
            nonlocal changed
            updated: dict[str, Value] = {}
            for name, value in values.items():
                v = active.get((layer_id, zone_name, name))
                if v is None:
                    updated[name] = value
                    continue
                expected = fingerprint(
                    layer_id,
                    zone_name,
                    name,
                    value.value,
                    cite=value.prov.cite,
                    quote=value.prov.quote,
                )
                if expected != v.fingerprint:
                    # The signature is over a value that is no longer there.
                    updated[name] = value
                    continue
                # Matched, so the verification is accounted for either way —
                # a file that already declares `verified` keeps its own
                # reviewer rather than having the log overwrite it.
                used.add(v.key)
                if value.status is Status.verified:
                    updated[name] = value
                else:
                    updated[name] = _promote(value, v)
                    changed = True
            return updated

        defaults = promote_block("defaults", dict(layer.defaults))
        zones = {}
        for zone_code, zone in layer.zones.items():
            values = promote_block(zone_code, dict(zone.values))
            zones[zone_code] = (
                zone.model_copy(update={"values": values}) if values != zone.values else zone
            )
        out[layer_id] = (
            layer.model_copy(update={"defaults": defaults, "zones": zones}) if changed else layer
        )

    orphans = []
    for key, v in active.items():
        if key in used:
            continue
        layer_id, zone_name, field = key
        layer = layers.get(layer_id)
        present = False
        if layer is not None:
            block = layer.defaults if zone_name == "defaults" else (
                layer.zones[zone_name].values if zone_name in layer.zones else {}
            )
            present = field in block
        orphans.append(
            Orphan(
                layer=layer_id,
                zone=zone_name,
                field=field,
                reviewer=v.reviewer,
                reviewed=v.reviewed,
                reason=VALUE_CHANGED if present else FIELD_GONE,
            )
        )
    orphans.sort(key=lambda o: (o.layer, o.zone, o.field))
    return out, orphans
