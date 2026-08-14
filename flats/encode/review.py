"""The reviewer's tool: read the code text, then sign the number beside it.

Everything else in the encoding system is machinery for making review
trustworthy. This is the part a person actually uses, and it is deliberately
small: show a value next to the exact source text it claims to come from, and
let the reviewer put their name on it or not::

    python -m flats.encode.review plan
    python -m flats.encode.review show or/multnomah/portland R5 setback_front_ft
    python -m flats.encode.review sign or/multnomah/portland R5 setback_front_ft --reviewer sjk

``plan`` is where a session starts: one line per jurisdiction naming what blocks
it and the command that unblocks it, worst first.

Four rules the tool enforces, because they are the ones that fail quietly.

*No signing what you cannot read.* A value whose quote does not resolve to
stored text cannot be verified here at all. The point of the signature is that
a human compared two things; if one of them is missing there is nothing to
compare, and a signature over it would be a lie with a name on it.

*No signing a restatement.* A citation pointing at a zoning aggregator rather
than the jurisdiction's own publisher fails in the opposite direction: the
reviewer can read it, and what they read is a third party's transcription of
the ordinance. It is the one failure mode that survives careful review, so the
tool refuses it rather than trusting anyone to notice the hostname.

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

from flats.encode.gaps import CAUSES, NEXT, Gap, by_cause, gaps, read_layer, summarise
from flats.encode.load import load_trusted
from flats.encode.readiness import by_stage, readiness
from flats.encode.verify import (
    LOG_PATH,
    Verification,
    VerificationError,
    VerificationLog,
    sign,
    sign_like,
    variant_for,
)
from flats.provenance.sources import authority_for, host_of
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import CONFIG_ROOT, load_rules
from flats.rules.model import LIKE, Incorporation, Layer, Status, Value, Variant

#: Values in these states are what the queue is for.
PENDING = (Status.draft, Status.encoded, Status.stale)


def _block(layer: Layer, zone: str) -> dict[str, Value]:
    if zone == "defaults":
        return dict(layer.defaults)
    z = layer.zones.get(zone)
    return dict(z.values) if z else {}


def _find(layers: dict[str, Layer], layer_id: str, zone: str, field: str) -> Value | Incorporation:
    layer = layers.get(layer_id)
    if layer is None:
        raise SystemExit(f"no such jurisdiction: {layer_id}")
    if field == LIKE:
        block = layer.zones.get(zone)
        if block is None or block.like is None:
            raise SystemExit(f"{layer_id} {zone}: adopts no other zone's standards")
        return block.like
    block = layer.zones.get(zone)
    values = _block(layer, zone)
    if not values and block is None:
        raise SystemExit(f"{layer_id}: no zone {zone!r}")
    if field not in values:
        if block is not None and block.like is not None:
            # Not missing — borrowed. Sending the reviewer to the zone the
            # sentence actually lives in is the whole point of not copying it.
            raise SystemExit(
                f"{layer_id} {zone}: {field!r} comes from {block.like.zone} — "
                f"review it there, or run 'show {layer_id} {zone} {LIKE}'"
            )
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


def _zones(layers: dict[str, Layer]):
    """Every (layer, zone code, zone) in the hierarchy, in reading order."""
    for layer_id in sorted(layers):
        for zone_code in sorted(layers[layer_id].zones):
            yield layer_id, zone_code, layers[layer_id].zones[zone_code]


def _evidence(store: ProvenanceStore, part) -> tuple[str, str]:
    """The stored text a value cites, or the reason there is none.

    Takes a variant as readily as a base value, because an exception usually
    cites a different sentence — often a different chapter — and it is that
    sentence the reviewer has to be shown.
    """
    if not part.prov.quote:
        return "", "no quote — nothing to compare the number against"
    try:
        return store.quote(part.prov.quote), ""
    except ProvenanceError as exc:
        return "", str(exc)


def _part(value, when: Sequence[str]):
    """The base value, or the one exception named on the command line."""
    if isinstance(value, Incorporation):
        if when:
            raise SystemExit("an incorporation clause has no exceptions to sign")
        return value
    if not when:
        return value
    try:
        return variant_for(value, when)
    except VerificationError as exc:
        raise SystemExit(str(exc)) from exc


def _label(field: str, when: Sequence[str]) -> str:
    return f"{field} [{'+'.join(sorted(when))}]" if when else field


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
            f"  ORPHAN {orphan.layer} {orphan.zone} {orphan.label}: {orphan.reason}"
            f" (signed {orphan.reviewed} by {orphan.reviewer})"
        )
    for stale in trusted.stale:
        print(f"  STALE  {stale.layer} {stale.zone} {stale.field}: {stale.reason} — {stale.detail}")
    for problem in trusted.problems:
        print(f"  PROBLEM {problem}")
    return 0 if trusted.clean else 1


def cmd_plan(args: argparse.Namespace) -> int:
    """One line per jurisdiction: where it is stuck and what unsticks it."""
    store = ProvenanceStore(args.docs)
    trusted = load_trusted(args.root, log=VerificationLog.load(args.log), store=store, strict=False)
    reports = [
        r for r in readiness(trusted, store)
        if not args.layer or r.layer.startswith(args.layer)
    ]
    if not reports:
        print(f"no jurisdiction matching {args.layer!r}", file=sys.stderr)
        return 1

    counts = by_stage(reports)
    print(f"{len(reports)} jurisdiction(s): " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print()
    for r in reports:
        if args.ready or not r.ready:
            print(r.line())
    if not args.verbose:
        return 0

    # The detail is what an agent or a reviewer acts on; the summary above is
    # what a person scans. Both from one pass so they cannot disagree.
    for r in reports:
        detail = (
            [f"    unfetched  {p}" for p in r.unfetched]
            + [f"    unquoted   {z} {f}" for z, f in r.unquoted]
            + [f"    no text    {z} {f}" for z, f in r.no_evidence]
            + [f"    misquoted  {z} {f}" for z, f in r.misquoted]
        )
        if detail:
            print(f"\n  {r.layer}")
            for line in detail[: args.limit or None]:
                print(line)
            if args.limit and len(detail) > args.limit:
                print(f"    ... {len(detail) - args.limit} more")
    return 0


def cmd_gaps(args: argparse.Namespace) -> int:
    """Why the unquoted values are unquoted, which is five answers, not one."""
    store = ProvenanceStore(args.docs)
    layers = load_rules(args.root, strict=False)
    wanted = {
        name: layer
        for name, layer in sorted(layers.items())
        if layer.zones and (not args.layer or name.startswith(args.layer))
    }
    if not wanted:
        print(f"no jurisdiction matching {args.layer!r}", file=sys.stderr)
        return 1

    found: dict[str, list[Gap]] = {}
    for name, layer in wanted.items():
        items = gaps(layer, read_layer(layer, store))
        if args.cause:
            items = [g for g in items if g.cause == args.cause]
        if items:
            found[name] = items

    totals = summarise(found)
    print(
        f"{sum(totals.values())} unquoted value(s) in {len(found)} jurisdiction(s): "
        + ", ".join(f"{k}={v}" for k, v in totals.items())
    )
    for cause, n in totals.items():
        print(f"  {cause:12} {n:>4}  -> {NEXT[cause].format(layer='<layer>', doc='<document>')}")

    for name, items in found.items():
        print(f"\n{name}: " + ", ".join(f"{k}={v}" for k, v in by_cause(items).items()))
        if not args.verbose:
            continue
        for gap in items[: args.limit or None]:
            print(gap.line())
        if args.limit and len(items) > args.limit:
            print(f"  ... {len(items) - args.limit} more")
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    trusted = load_trusted(
        args.root,
        log=VerificationLog.load(args.log),
        store=ProvenanceStore(args.docs),
        strict=False,
    )
    shown = 0
    for layer_id, zone_code, zone in _zones(trusted.layers):
        if args.layer and not layer_id.startswith(args.layer):
            continue
        if args.zone and zone_code != args.zone:
            continue
        # A zone that borrows its standards has one line of work before any of
        # them can be trusted: has anybody read the sentence that says it does?
        if zone.like is not None and zone.like.status in PENDING:
            print(
                f"{zone.like.status.value:8} {layer_id} {zone_code} {LIKE}"
                f" = {zone.like.zone}  [{zone.like.prov.cite}]"
            )
            shown += 1
            if args.limit and shown >= args.limit:
                return 0

    for layer_id, zone, field, value in _walk(trusted.layers):
        if args.layer and not layer_id.startswith(args.layer):
            continue
        if args.zone and zone != args.zone:
            continue
        # Base and exceptions queue separately. A standard whose base is signed
        # and whose "10 ft. where affordable" is not has one line of work left,
        # and hiding that behind a verified base is how a half-read rule starts
        # looking finished.
        for part in (value, *value.variants):
            if part.status not in PENDING:
                continue
            print(
                f"{part.status.value:8} {layer_id} {zone} "
                f"{_label(field, getattr(part, 'when', ()))} = {part.value}"
                f"  [{part.prov.cite}]"
            )
            shown += 1
            if args.limit and shown >= args.limit:
                return 0
    if not shown:
        print("nothing pending")
    return 0


def _print_evidence(store: ProvenanceStore, part) -> int:
    print()
    text, err = _evidence(store, part)
    if err:
        print(f"  NO EVIDENCE: {err}")
        print("  Nothing to review against. Fetch the source before signing.")
        return 1
    for line in text.splitlines():
        print(f"  | {line}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    layers = load_rules(args.root)
    value = _find(layers, args.layer, args.zone, args.field)
    part = _part(value, args.when)
    store = ProvenanceStore(args.docs)

    print(f"{args.layer} {args.zone} {_label(args.field, args.when)}")
    if isinstance(value, Incorporation):
        governs = "this zone's own text" if value.wins == "local" else f"the {value.zone} chapter"
        print(f"  adopts    {value.zone}")
        print(f"  conflict  {governs} governs where the two disagree")
    else:
        print(f"  value     {part.value}")
    print(f"  status    {part.status.value}")
    print(f"  cite      {part.prov.cite}")
    print(f"  url       {part.prov.url}")
    print(f"  retrieved {part.prov.retrieved}")
    print(f"  quote     {part.prov.quote or '(none)'}")
    if isinstance(value, Value):
        if value.preempts:
            print("  preempts  yes — a more specific layer cannot override this")
        if not args.when and value.variants:
            # Reviewing the base without being told the exceptions exist is how
            # a signature ends up standing for more than the reviewer read.
            print("  exceptions:")
            for other in value.variants:
                print(
                    f"    {other.value} when {'+'.join(sorted(other.when))}"
                    f"  ({other.status.value}) — sign with --when {' '.join(sorted(other.when))}"
                )
    return _print_evidence(store, part)


def cmd_sign(args: argparse.Namespace) -> int:
    layers = load_rules(args.root)
    store = ProvenanceStore(args.docs)
    log = VerificationLog.load(args.log)
    reviewed = date.fromisoformat(args.reviewed) if args.reviewed else date.today()

    active = log.active()
    entries = []
    when = tuple(sorted(args.when))
    for field in args.fields:
        value = _find(layers, args.layer, args.zone, field)
        part = _part(value, when)
        _, err = _evidence(store, part)
        if err:
            # Nothing is written. A partial batch would leave the reviewer
            # unsure which of the fields they named actually got signed.
            print(f"refusing {_label(field, when)}: {err}", file=sys.stderr)
            return 1
        authority = authority_for(part.prov.url)
        if not authority.may_verify:
            # A third party restating the code is how a summary becomes a
            # citation. The reviewer would be reading real text and signing it
            # in good faith; what they could not see is that the text is
            # somebody's transcription of the ordinance rather than the
            # ordinance. 81 values in the corpus cite one aggregator.
            print(
                f"refusing {_label(field, when)}: {host_of(part.prov.url)} is "
                f"{authority.value}, not the jurisdiction's own publisher — "
                f"re-cite this against the adopted text",
                file=sys.stderr,
            )
            return 1
        # Whether this is already verified is a question for the log, not for
        # the file — the file always loads draft, by design.
        entry = (
            sign_like(args.layer, args.zone, part, reviewer=args.reviewer, reviewed=reviewed,
                      note=args.note)
            if isinstance(part, Incorporation)
            else sign(args.layer, args.zone, field, value, reviewer=args.reviewer,
                      reviewed=reviewed, note=args.note, when=when)
        )
        prior = active.get((args.layer, args.zone, field, when))
        if prior is not None and prior.fingerprint == entry.fingerprint:
            print(f"{_label(field, when)}: already verified by {prior.reviewer}, nothing to sign")
            continue
        entries.append(entry)

    for entry in entries:
        log.append(entry, args.log)
        print(
            f"signed {entry.layer} {entry.zone} {entry.label}"
            f" ({entry.reviewer}, {entry.reviewed})"
        )
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    log = VerificationLog.load(args.log)
    when = tuple(sorted(args.when))
    label = _label(args.field, when)
    existing = log.active().get((args.layer, args.zone, args.field, when))
    if existing is None:
        print(f"no active verification for {args.layer} {args.zone} {label}", file=sys.stderr)
        return 1

    log.append(
        Verification(
            layer=args.layer,
            zone=args.zone,
            field=args.field,
            fingerprint=existing.fingerprint,
            reviewer=args.reviewer,
            reviewed=date.fromisoformat(args.reviewed) if args.reviewed else date.today(),
            when=when,
            note=args.note,
            revoked=True,
        ),
        args.log,
    )
    print(
        f"withdrew {args.layer} {args.zone} {label}"
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

    plan = sub.add_parser("plan", help="per jurisdiction: what blocks it, and the next command")
    plan.add_argument("--layer", default="", help="jurisdiction prefix filter")
    plan.add_argument("--ready", action="store_true", help="include jurisdictions with nothing left")
    plan.add_argument("--verbose", action="store_true", help="list what is blocking, item by item")
    plan.add_argument("--limit", type=int, default=10, help="detail lines per jurisdiction")
    plan.set_defaults(func=cmd_plan)

    gap = sub.add_parser("gaps", help="why the unquoted values are unquoted")
    gap.add_argument("--layer", default="", help="jurisdiction prefix filter")
    gap.add_argument("--cause", default="", choices=("", *CAUSES), help="one cause only")
    gap.add_argument("--verbose", action="store_true", help="list the values, item by item")
    gap.add_argument("--limit", type=int, default=20, help="detail lines per jurisdiction")
    gap.set_defaults(func=cmd_gaps)

    queue = sub.add_parser("queue", help="values awaiting review")
    queue.add_argument("--layer", default="", help="jurisdiction prefix filter")
    queue.add_argument("--zone", default="", help="zone code filter")
    queue.add_argument("--limit", type=int, default=50)
    queue.set_defaults(func=cmd_queue)

    show = sub.add_parser("show", help="a value beside the source text it claims")
    show.add_argument("layer")
    show.add_argument("zone")
    show.add_argument("field")
    show.add_argument("--when", nargs="*", default=[], help='condition(s) naming the exception to act on, e.g. --when affordable. Omit for the base value.')
    show.set_defaults(func=cmd_show)

    signer = sub.add_parser("sign", help="record that you read these values against the text")
    signer.add_argument("layer")
    signer.add_argument("zone")
    signer.add_argument("fields", nargs="+", help="field names, typed out — never globbed")
    signer.add_argument("--reviewer", required=True, help="who read it; no default on purpose")
    signer.add_argument("--reviewed", default="", help="ISO date, defaults to today")
    signer.add_argument("--note", default="", help="e.g. the table the number came from")
    signer.add_argument("--when", nargs="*", default=[], help='condition(s) naming the exception to act on, e.g. --when affordable. Omit for the base value.')
    signer.set_defaults(func=cmd_sign)

    revoke = sub.add_parser("revoke", help="withdraw a verification without erasing it")
    revoke.add_argument("layer")
    revoke.add_argument("zone")
    revoke.add_argument("field")
    revoke.add_argument("--reviewer", required=True)
    revoke.add_argument("--reviewed", default="")
    revoke.add_argument("--note", default="", help="why it is being withdrawn")
    revoke.add_argument("--when", nargs="*", default=[], help='condition(s) naming the exception to act on, e.g. --when affordable. Omit for the base value.')
    revoke.set_defaults(func=cmd_revoke)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
