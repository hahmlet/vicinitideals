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
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable, Sequence

from flats.encode.dispositions import Note, notes
from flats.encode.footnotes import Census, survey
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
    print(render(qualified(layer), blocking_only="--blocking" in args))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["Qualified", "qualified", "render"]
