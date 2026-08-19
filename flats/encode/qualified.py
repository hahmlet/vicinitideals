"""Which encoded values sit under a footnote, and whether anybody ruled on it.

The census finds footnotes. The disposition register records what was decided
about each. This is the join that makes either of them bite: for every value
in the corpus, the footnotes that govern the lines it was read from, and their
states.

Scope is the block's *region* -- the run of lines between the previous notes
block and this one's heading. That is deliberately wider than the cell the
marker sits on. A marker binds one cell, a marker on a row binds a zone, one
on a column head binds every zone in the column, and telling those apart from
extracted text is exactly the judgement that gets made wrong silently. An
over-scoped footnote costs a review. An under-scoped one costs a false GREEN,
which is the failure the whole subsystem exists to prevent, so the wider
reading is the one taken and the narrowing is a decision somebody records.

What this produces is a queue: values whose evidence is qualified by text
nobody has read yet. It is not a claim that the value is wrong. It is a claim
that we do not yet know, which is a different thing and the only honest one
available until the footnote is ruled on.

Run it::

    uv run python -m flats.encode.qualified
    uv run python -m flats.encode.qualified --layer or/multnomah/gresham
    uv run python -m flats.encode.qualified --blocking
    uv run python -m flats.encode.qualified --write-caps
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from flats.encode.dispositions import Note, notes
from flats.encode.footnotes import Census, survey
from flats.rules.caps import LEDGER as CAPS
from flats.rules.loader import load_rules
from flats.rules.model import LIKE, Layer


@dataclass(frozen=True, slots=True)
class Qualified:
    """One encoded value and the footnotes governing the lines it cites."""

    layer: str
    zone: str
    field: str
    quote: str
    governing: tuple[Note, ...]

    @property
    def blocking(self) -> tuple[Note, ...]:
        return tuple(note for note in self.governing if note.blocking)

    @property
    def clear(self) -> bool:
        return not self.blocking

    @property
    def capping(self) -> tuple[Note, ...]:
        """Notes somebody read and could not answer -- see `caps`."""
        return tuple(note for note in self.governing if note.state == "unmeasured")

    @property
    def standard(self) -> str:
        """The field name without the variant's condition key."""
        return self.field.split(" [", 1)[0]


def _quoted(layer: Layer) -> Iterable[tuple[str, str, str]]:
    """Every (zone, field, quote) in a layer that points at a document.

    Variants and incorporation clauses count: both are values somebody has to
    read, and a footnote qualifying one of them qualifies the screen.
    """
    for name, value in layer.defaults.items():
        if value.prov.quote:
            yield "(defaults)", name, value.prov.quote
    for zone_code, zone in sorted(layer.zones.items()):
        for name, value in sorted(zone.values.items()):
            if value.prov.quote:
                yield zone_code, name, value.prov.quote
            for variant in value.variants:
                if variant.prov.quote:
                    key = "+".join(sorted(variant.when))
                    yield zone_code, f"{name} [{key}]", variant.prov.quote
        if zone.like is not None and zone.like.prov.quote:
            yield zone_code, LIKE, zone.like.prov.quote


def _first_line(quote: str) -> tuple[str, int]:
    """The document and first line a quote points at, or ("", 0)."""
    doc, _, ref = quote.partition("#")
    if not ref.startswith("L"):
        return doc, 0
    first = ref[1:].split("-", 1)[0]
    return (doc, int(first)) if first.isdigit() else (doc, 0)


def _governing(census: Census, line: int, per_doc: dict[str, list[Note]]) -> tuple[Note, ...]:
    """The notes of whichever block's region contains this line."""
    for block in census.blocks:
        low, high = block.region
        if not low <= line - 1 < high:
            continue
        lines = {body.line for body in block.bodies}
        return tuple(note for note in per_doc.get(census.doc, []) if note.line in lines)
    return ()


def qualified(layer_id: str | None = None) -> list[Qualified]:
    """Every quoted value in the corpus, with the footnotes over it."""
    censuses = {c.doc: c for c in survey(layer_id)}
    per_doc: dict[str, list[Note]] = {}
    for note in notes(layer_id):
        per_doc.setdefault(note.doc, []).append(note)

    out: list[Qualified] = []
    for identifier, layer in sorted(load_rules().items()):
        if layer_id and identifier != layer_id:
            continue
        for zone, field, quote in _quoted(layer):
            doc, line = _first_line(quote)
            census = censuses.get(doc)
            if census is None or not line:
                continue
            governing = _governing(census, line, per_doc)
            if governing:
                out.append(
                    Qualified(
                        layer=identifier,
                        zone=zone,
                        field=field,
                        quote=quote,
                        governing=governing,
                    )
                )
    return out


def caps(rows: Sequence[Qualified]) -> dict[str, dict[str, dict[str, list[str]]]]:
    """Layer -> zone -> field -> the unmeasured facts its footnotes turn on.

    What :mod:`flats.rules.caps` reads. A value under a footnote nobody could
    answer is not a value the screen may certify, and this is how the rule
    layer finds out: the fact becomes a lever on that standard, and a lever
    nothing measured is what turns a would-be GREEN into an UNKNOWN naming the
    data it needs.

    Variants collapse onto their standard on purpose. A footnote qualifying
    the corner-lot column qualifies the setback, and the screen asks about a
    standard, not about a column.
    """
    out: dict[str, dict[str, dict[str, list[str]]]] = {}
    for row in rows:
        facts = sorted({note.fact for note in row.capping if note.fact})
        if not facts:
            continue
        field = out.setdefault(row.layer, {}).setdefault(row.zone, {}).setdefault(
            row.standard, []
        )
        for fact in facts:
            if fact not in field:
                field.append(fact)
    for zones in out.values():
        for fields in zones.values():
            for names in fields.values():
                names.sort()
    return out


def write_caps(rows: Sequence[Qualified], path: Path | None = None) -> Path:
    """Write the ledger the rule layer reads. Sorted, so the diff is the news."""
    file = path or CAPS
    file.parent.mkdir(parents=True, exist_ok=True)
    payload = caps(rows)
    ordered = {
        layer: {zone: dict(sorted(fields.items())) for zone, fields in sorted(zones.items())}
        for layer, zones in sorted(payload.items())
    }
    file.write_text(json.dumps(ordered, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return file


def render(rows: Sequence[Qualified], *, blocking_only: bool = False) -> str:
    """The join as text, for a terminal or a commit message."""
    shown = [r for r in rows if not blocking_only or r.blocking]
    lines = [
        f"{r.layer:<28} {r.zone:<10} {r.field:<26} {len(r.blocking):>2} unread"
        f" of {len(r.governing):>2}  {r.quote}"
        for r in sorted(shown, key=lambda r: (-len(r.blocking), r.layer, r.zone))
    ]
    blocked = [r for r in rows if r.blocking]
    layers = sorted({r.layer for r in blocked})
    lines.append("")
    lines.append(
        f"qualified_values={len(rows)}  blocked={len(blocked)}  "
        f"jurisdictions={len(layers)}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    layer = args[args.index("--layer") + 1] if "--layer" in args else None
    rows = qualified(layer)
    if "--write-caps" in args:
        # Always over the whole corpus: a per-layer write would silently drop
        # every other jurisdiction's caps from the file it overwrites.
        written = write_caps(qualified())
        capped = sum(len(f) for z in caps(qualified()).values() for f in z.values())
        print(f"{written}  {capped} value(s) capped by an unmeasured footnote")
        return 0
    print(render(rows, blocking_only="--blocking" in args))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["Qualified", "caps", "qualified", "render", "write_caps"]
