"""The reviewer's tool: read the code text, then sign the number beside it.

Everything else in the encoding system is machinery for making review
trustworthy. This is the part a person actually uses, and it is deliberately
small: show a value next to the exact source text it claims to come from, and
let the reviewer put their name on it or not::

    python -m flats.encode.review show or/multnomah/portland R5 setback_front_ft
    python -m flats.encode.review sign or/multnomah/portland R5 setback_front_ft --reviewer sjk

Three rules the tool enforces, because they are the ones that fail quietly.

*No signing what you cannot read.* A value whose quote does not resolve to
stored text cannot be verified here at all. The point of the signature is that
a human compared two things; if one of them is missing there is nothing to
compare, and a signature over it would be a lie with a name on it.

*Fields are named, never globbed.* Several may be signed in one command,
because a reviewer reads one table and confirms a row of numbers from it — but
each is typed out. There is no "sign everything": a tool that signs whatever it
is handed reproduces exactly the false certification the log exists to prevent.

*Withdrawal is an append.* ``revoke`` writes a new entry rather than deleting
the old one, so the record of who believed what, when, survives being wrong.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from flats.encode.load import load_trusted
from flats.encode.verify import LOG_PATH, Verification, VerificationLog, sign
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import CONFIG_ROOT, load_rules
from flats.rules.model import Layer, Status, Value

#: Values in these states are what the queue is for.
PENDING = (Status.draft, Status.encoded, Status.stale)


def _block(layer: Layer, zone: str) -> dict[str, Value]:
    if zone == "defaults":
        return dict(layer.defaults)
    z = layer.zones.get(zone)
    return dict(z.values) if z else {}


def _find(layers: dict[str, Layer], layer_id: str, zone: str, field: str) -> Value:
    layer = layers.get(layer_id)
    if layer is None:
        raise SystemExit(f"no such jurisdiction: {layer_id}")
    values = _block(layer, zone)
    if not values:
        raise SystemExit(f"{layer_id}: no zone {zone!r}")
    if field not in values:
        raise SystemExit(f"{layer_id} {zone}: no field {field!r}")
    return values[field]


def _walk(layers: dict[str, Layer]):
    """Every (layer, zone, field, value) in the hierarchy, in reading order."""
    for layer_id in sorted(layers):
        layer = layers[layer_id]
        for name, value in sorted(layer.defaults.items()):
            yield layer_id, "defaults", name, value
        for zone_code in sorted(layer.zones):
            for name, value in sorted(layer.zones[zone_code].values.items()):
                yield layer_id, zone_code, name, value


def _evidence(store: ProvenanceStore, value: Value) -> tuple[str, str]:
    """The stored text a value cites, or the reason there is none."""
    if not value.prov.quote:
        return "", "no quote — nothing to compare the number against"
    try:
        return store.quote(value.prov.quote), ""
    except ProvenanceError as exc:
        return "", str(exc)


def cmd_status(args: argparse.Namespace) -> int:
    trusted = load_trusted(
        args.root,
        log=VerificationLog.load(args.log),
        store=ProvenanceStore(args.docs),
        strict=False,
    )
    for line in trusted.summary():
        print(line)
    for orphan in trusted.orphans:
        print(
            f"  ORPHAN {orphan.layer} {orphan.zone} {orphan.field}: {orphan.reason}"
            f" (signed {orphan.reviewed} by {orphan.reviewer})"
        )
    for stale in trusted.stale:
        print(f"  STALE  {stale.layer} {stale.zone} {stale.field}: {stale.reason} — {stale.detail}")
    for problem in trusted.problems:
        print(f"  PROBLEM {problem}")
    return 0 if trusted.clean else 1


def cmd_queue(args: argparse.Namespace) -> int:
    trusted = load_trusted(
        args.root,
        log=VerificationLog.load(args.log),
        store=ProvenanceStore(args.docs),
        strict=False,
    )
    shown = 0
    for layer_id, zone, field, value in _walk(trusted.layers):
        if value.status not in PENDING:
            continue
        if args.layer and not layer_id.startswith(args.layer):
            continue
        if args.zone and zone != args.zone:
            continue
        print(
            f"{value.status.value:8} {layer_id} {zone} {field} = {value.value}"
            f"  [{value.prov.cite}]"
        )
        shown += 1
        if args.limit and shown >= args.limit:
            break
    if not shown:
        print("nothing pending")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    value = _find(load_rules(args.root), args.layer, args.zone, args.field)
    store = ProvenanceStore(args.docs)

    print(f"{args.layer} {args.zone} {args.field}")
    print(f"  value     {value.value}")
    print(f"  status    {value.status.value}")
    print(f"  cite      {value.prov.cite}")
    print(f"  url       {value.prov.url}")
    print(f"  retrieved {value.prov.retrieved}")
    print(f"  quote     {value.prov.quote or '(none)'}")
    if value.preempts:
        print("  preempts  yes — a more specific layer cannot override this")
    print()

    text, err = _evidence(store, value)
    if err:
        print(f"  NO EVIDENCE: {err}")
        print("  Nothing to review against. Fetch the source before signing.")
        return 1
    for line in text.splitlines():
        print(f"  | {line}")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    layers = load_rules(args.root)
    store = ProvenanceStore(args.docs)
    log = VerificationLog.load(args.log)
    reviewed = date.fromisoformat(args.reviewed) if args.reviewed else date.today()

    active = log.active()
    entries = []
    for field in args.fields:
        value = _find(layers, args.layer, args.zone, field)
        _, err = _evidence(store, value)
        if err:
            # Nothing is written. A partial batch would leave the reviewer
            # unsure which of the fields they named actually got signed.
            print(f"refusing {field}: {err}", file=sys.stderr)
            return 1
        # Whether this is already verified is a question for the log, not for
        # the file — the file always loads draft, by design.
        prior = active.get((args.layer, args.zone, field))
        if prior is not None and prior.fingerprint == sign(
            args.layer, args.zone, field, value, reviewer=args.reviewer, reviewed=reviewed
        ).fingerprint:
            print(f"{field}: already verified by {prior.reviewer}, nothing to sign")
            continue
        entries.append(
            sign(
                args.layer,
                args.zone,
                field,
                value,
                reviewer=args.reviewer,
                reviewed=reviewed,
                note=args.note,
            )
        )

    for entry in entries:
        log.append(entry, args.log)
        print(f"signed {entry.layer} {entry.zone} {entry.field} ({entry.reviewer}, {entry.reviewed})")
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    log = VerificationLog.load(args.log)
    existing = log.active().get((args.layer, args.zone, args.field))
    if existing is None:
        print(f"no active verification for {args.layer} {args.zone} {args.field}", file=sys.stderr)
        return 1

    log.append(
        Verification(
            layer=args.layer,
            zone=args.zone,
            field=args.field,
            fingerprint=existing.fingerprint,
            reviewer=args.reviewer,
            reviewed=date.fromisoformat(args.reviewed) if args.reviewed else date.today(),
            note=args.note,
            revoked=True,
        ),
        args.log,
    )
    print(
        f"withdrew {args.layer} {args.zone} {args.field}"
        f" (was {existing.reviewer}, {existing.reviewed})"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flats-review", description="Read the code text, then sign the number beside it."
    )
    parser.add_argument("--root", type=Path, default=CONFIG_ROOT, help="jurisdiction rule files")
    parser.add_argument("--docs", type=Path, default=None, help="provenance store root")
    parser.add_argument("--log", type=Path, default=LOG_PATH, help="verification log")
    sub = parser.add_subparsers(dest="cmd", required=True)

    status = sub.add_parser("status", help="trust across the hierarchy, and what blocks it")
    status.set_defaults(func=cmd_status)

    queue = sub.add_parser("queue", help="values awaiting review")
    queue.add_argument("--layer", default="", help="jurisdiction prefix filter")
    queue.add_argument("--zone", default="", help="zone code filter")
    queue.add_argument("--limit", type=int, default=50)
    queue.set_defaults(func=cmd_queue)

    show = sub.add_parser("show", help="a value beside the source text it claims")
    show.add_argument("layer")
    show.add_argument("zone")
    show.add_argument("field")
    show.set_defaults(func=cmd_show)

    signer = sub.add_parser("sign", help="record that you read these values against the text")
    signer.add_argument("layer")
    signer.add_argument("zone")
    signer.add_argument("fields", nargs="+", help="field names, typed out — never globbed")
    signer.add_argument("--reviewer", required=True, help="who read it; no default on purpose")
    signer.add_argument("--reviewed", default="", help="ISO date, defaults to today")
    signer.add_argument("--note", default="", help="e.g. the table the number came from")
    signer.set_defaults(func=cmd_sign)

    revoke = sub.add_parser("revoke", help="withdraw a verification without erasing it")
    revoke.add_argument("layer")
    revoke.add_argument("zone")
    revoke.add_argument("field")
    revoke.add_argument("--reviewer", required=True)
    revoke.add_argument("--reviewed", default="")
    revoke.add_argument("--note", default="", help="why it is being withdrawn")
    revoke.set_defaults(func=cmd_revoke)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
