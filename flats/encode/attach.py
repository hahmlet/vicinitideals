"""Giving an already-encoded number the sentence it came from.

The readiness ladder reports two jurisdictions stuck at ``unquoted``: 93 values
that state a standard and point at no text. They came in through the quadfit
port, which carried numbers and not citations, and in that state they are
unreviewable — a reviewer asked to sign one has nothing to read.

Re-reading a chapter to re-find a number somebody already read is the wrong
shape of work when the document is in the store and
:mod:`flats.encode.corroborate` is already matching encoded values against it.
This closes that loop: where corroboration says the document states this number
for this zone, the quote it matched on is written into the file.

Four refusals, and they are the module:

*It never overwrites a quote.* A value already pointing somewhere is a reading
somebody made. Repointing it at a different sentence would move a citation
without anybody deciding to.

*It attaches only zone-keyed evidence.* Corroboration counts table columns and
single-zone documents only, because a sentence in a fifty-page chapter does not
say which zone it belongs to. A quote taken from the wrong zone's paragraph is
worse than no quote: it reads as confirmation.

*It refuses where the document states more than one number.* Two numbers for
one field is a base case and an exception (§16), and quoting the base as though
it were the whole rule hides the exit. That pair needs encoding as variants,
not a citation stapled to one half of it.

*It refuses footnoted numbers* for the same reason, even when the number agrees.

What it emphatically does not do is verify anything. A quote is where to look,
not proof that somebody looked; the value stays a draft and stays on the review
queue. Attaching is the difference between an unreviewable value and a
reviewable one, and nothing more.

Run::

    python -m flats.encode.attach or/multnomah/portland \\
        --doc or/multnomah/portland/33.110.txt --apply
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

from flats.encode.corroborate import Verdict, check_layer
from flats.encode.draft import layer_path
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import CONFIG_ROOT, load_rules
from flats.rules.model import Layer


@dataclass(frozen=True, slots=True)
class Attachment:
    """One value, and the line the document states it on."""

    zone: str
    field: str
    value: float | int
    quote: str

    def __str__(self) -> str:
        return f"{self.zone:8} {self.field:28} {self.value:>8}  {self.quote}"


@dataclass(frozen=True, slots=True)
class Skipped:
    """One value left alone, and why."""

    zone: str
    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.zone:8} {self.field:28} {self.reason}"


def unquoted(layer: Layer) -> set[tuple[str, str]]:
    """Every (zone, field) carrying a value and no quote.

    Variants are deliberately absent. An exception cites the clause that grants
    it, which is rarely the line stating the base number, and assuming it is
    would attach the wrong sentence to the value most likely to be misread.
    """
    return {
        (code, name)
        for code, zone in layer.zones.items()
        for name, value in zone.values.items()
        if not value.prov.quote
    }


def plan(findings, layer: Layer) -> tuple[list[Attachment], list[Skipped]]:
    """Sort corroboration findings into what may be attached and what may not."""
    wanted = unquoted(layer)
    attachments: list[Attachment] = []
    skipped: list[Skipped] = []
    for finding in findings:
        if (finding.zone, finding.field) not in wanted or finding.encoded is None:
            continue
        if finding.verdict is not Verdict.agrees:
            if finding.verdict is Verdict.differs:
                # Loud on purpose. The file says one thing and the zone's own
                # table column says another; one of them is wrong, and that is
                # a reading question rather than a citation to staple on.
                skipped.append(
                    Skipped(
                        finding.zone,
                        finding.field,
                        f"document states {finding.found} — resolve first",
                    )
                )
            continue
        if len(finding.found) > 1:
            skipped.append(
                Skipped(
                    finding.zone,
                    finding.field,
                    f"document states more than one value {finding.found}",
                )
            )
            continue
        if finding.conditional:
            skipped.append(
                Skipped(finding.zone, finding.field, f"conditional — {finding.notes[0][:60]}")
            )
            continue
        if not finding.quote:
            continue
        attachments.append(Attachment(finding.zone, finding.field, finding.encoded, finding.quote))
    return attachments, skipped


def apply(
    raw: dict[str, Any], attachments: Sequence[Attachment]
) -> tuple[dict[str, Any], list[Skipped]]:
    """Write each quote into the parsed YAML. Returns the document and refusals."""
    out = dict(raw)
    zones = dict(out.get("zones") or {})
    refused: list[Skipped] = []
    for at in attachments:
        zone = dict(zones.get(at.zone) or {})
        node = zone.get(at.field)
        if node is None:
            refused.append(Skipped(at.zone, at.field, "not in the file"))
            continue
        if isinstance(node, dict):
            if node.get("quote"):
                refused.append(Skipped(at.zone, at.field, "already quoted"))
                continue
            updated = dict(node)
        else:
            # The shorthand form — `setback_front_ft: 10` — has nowhere to put
            # a quote, so it expands to the mapping form carrying the same
            # number.
            updated = {"value": node}
        updated["quote"] = at.quote
        zone[at.field] = updated
        zones[at.zone] = zone
    out["zones"] = zones
    return out, refused


def insert_quotes(text: str, attachments: Sequence[Attachment]) -> tuple[str, list[Skipped]]:
    """Write the quotes into the file's own text, leaving everything else alone.

    Re-dumping parsed YAML would be shorter and would silently delete every
    comment in the file — including the ones recording *why* a URL is the one
    that serves the ordinance, which is knowledge nothing else holds. So the
    edit is textual: a scalar grows into the mapping form carrying the same
    number, and a mapping gains one line.

    The result is checked against the parsed transform before anybody writes it
    (see :func:`main`), so a mis-indented edit fails loudly instead of quietly
    rewriting a rule file.
    """
    lines = text.splitlines()
    wanted = {(a.zone, a.field): a for a in attachments}
    done: set[tuple[str, str]] = set()
    out: list[str] = []

    in_zones = False
    zone: str | None = None
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if stripped and not line.startswith(" "):
            in_zones = stripped.rstrip() == "zones:"
            zone = None
        elif in_zones and stripped and not stripped.startswith("#") and indent == 2:
            zone = stripped.split(":", 1)[0].strip().strip("'\"") if stripped.endswith(":") else None

        out.append(line)
        if zone is None or not stripped or stripped.startswith("#") or indent != 4:
            continue
        name, _, rest = stripped.partition(":")
        at = wanted.get((zone, name.strip()))
        if at is None or (zone, name.strip()) in done:
            continue
        pad = " " * (indent + 2)
        if rest.strip():
            # Shorthand. The scalar moves down a level unchanged; nothing here
            # reinterprets it, because re-writing a number is not this tool's
            # job.
            out[-1] = f"{' ' * indent}{name.strip()}:"
            out.append(f"{pad}value: {rest.strip()}")
        out.append(f'{pad}quote: "{at.quote}"')
        done.add((zone, name.strip()))

    missed = [
        Skipped(a.zone, a.field, "not in the file")
        for key, a in wanted.items()
        if key not in done
    ]
    joined = "\n".join(out)
    return (joined + "\n" if text.endswith("\n") else joined), missed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-attach",
        description="Point already-encoded values at the lines the document states them on.",
    )
    parser.add_argument("layer", help="layer id, e.g. or/multnomah/portland")
    parser.add_argument("--doc", required=True, help="store path of the document to read")
    parser.add_argument("--zone", action="append", default=[], help="limit to these zones")
    parser.add_argument("--rules", type=Path, default=CONFIG_ROOT)
    parser.add_argument("--docs", type=Path, default=None, help="provenance store root")
    parser.add_argument(
        "--zoned-doc",
        action="store_true",
        help="the document covers exactly one zone, so its sentences count as evidence",
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the file; without this it only reports"
    )
    args = parser.parse_args(argv)

    layers = load_rules(args.rules, strict=False)
    layer = layers.get(args.layer)
    if layer is None:
        print(f"no such layer: {args.layer}", file=sys.stderr)
        return 2
    try:
        doc = ProvenanceStore(args.docs).load(args.doc)
    except (ProvenanceError, FileNotFoundError) as exc:
        print(f"{args.doc}: {exc}", file=sys.stderr)
        return 2

    findings = check_layer(doc.text, layer, path=args.doc, zones=args.zone, zoned=args.zoned_doc)
    attachments, skipped = plan(findings, layer)

    for at in attachments:
        print(f"  + {at}")
    for skip in skipped:
        print(f"  ~ {skip}")

    still = len(unquoted(layer)) - len(attachments)
    print(f"{args.layer}: {len(attachments)} quotable, {still} value(s) still unquoted after this")
    if not attachments:
        return 0
    if not args.apply:
        print("re-run with --apply to write")
        return 0

    path = layer_path(args.rules, args.layer)
    before = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(before) or {}
    expected, refused = apply(raw, attachments)
    for skip in refused:
        print(f"  ~ {skip}")

    written, missed = insert_quotes(before, [a for a in attachments if not _refused(a, refused)])
    for skip in missed:
        print(f"  ~ {skip}")
    if yaml.safe_load(written) != expected:
        # The textual edit and the parsed transform disagree, which means the
        # edit landed somewhere unintended. A rule file is not worth guessing
        # at: leave it exactly as it was.
        print(f"{path}: edit did not match the parsed result — nothing written", file=sys.stderr)
        return 1
    path.write_text(written, encoding="utf-8")
    print(f"wrote {path}")
    return 0


def _refused(at: Attachment, refused: Sequence[Skipped]) -> bool:
    return any(s.zone == at.zone and s.field == at.field for s in refused)


__all__ = ["Attachment", "Skipped", "apply", "insert_quotes", "main", "plan", "unquoted"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
