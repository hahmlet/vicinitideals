"""The city's own text, with the city's own vocabulary marked in it.

A reviewer -- human or agent -- reading a standard needs the sentence exactly
as the jurisdiction wrote it. What they cannot get from the sentence alone is
which of its ordinary-looking words this city gave a meaning to, and where.
"Setback", "lot line", "street" and "story" are the words a code redefines,
and a reader carrying the general meaning through a local standard is how a
number gets applied to lots it was never written for.

So: the passage verbatim, unedited, line-numbered so every line stays a
citation, with defined terms marked -- and beneath it the definitions
themselves, in full, in the city's words, each with the line it came from.
The human can skim the legend. The agent cannot: the meanings are in the same
buffer as the standard, so a reading that ignores them is a choice somebody
made rather than a lookup nobody did.

Nothing here rewrites the code. Marks live in the rendering, the store keeps
the original bytes, and every citation in the corpus still points at the
city's text rather than at ours.

Run it::

    uv run python -m flats.encode.reading --layer or/multnomah/gresham \\
        --quote or/multnomah/gresham/3.0100.definitions.txt#L1755-L1760
    uv run python -m flats.encode.reading --layer or/multnomah/gresham \\
        --zone DRL-1 --field min_lot_width_ft
"""

from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass
from typing import Sequence

from flats.encode.glossary import Entry
from flats.encode.qualified import _quoted
from flats.encode.tagging import Index, index, normal
from flats.provenance.store import ProvenanceError, ProvenanceStore, parse_quote
from flats.rules.loader import load_rules

#: How a marked term is set off. Doubled brackets: codes use single brackets
#: for table references and asterisks for footnote markers, and a mark that
#: collides with the city's own punctuation changes the text it claims to
#: leave alone. ASCII on purpose -- this gets read in terminals whose code
#: page turns anything else into a question mark.
OPEN, CLOSE = "[[", "]]"


class ReadingError(Exception):
    """A passage that cannot be shown: no such value, or nothing stored."""


@dataclass(frozen=True, slots=True)
class Passage:
    """One quoted stretch of code, marked, with the meanings under it."""

    layer: str
    quote: str
    #: (line number, text) as stored, marks inserted.
    lines: tuple[tuple[int, str], ...]
    #: The definitions the marks point at, in the city's own words.
    legend: tuple[Entry, ...]

    def render(self, *, width: int = 96) -> str:
        out = [f"{self.layer}  {self.quote}", ""]
        out.extend(f"  {number:>5} | {text}" for number, text in self.lines)
        if not self.legend:
            out.extend(["", "  (this city defines none of the words in these lines)"])
            return "\n".join(out)
        out.extend(["", f"  Defined by this jurisdiction -- {len(self.legend)} terms:"])
        for entry in self.legend:
            out.append("")
            out.append(f"  {OPEN}{entry.term}{CLOSE}  {entry.quote}")
            out.extend(
                textwrap.wrap(
                    entry.text,
                    width=width,
                    initial_indent="      ",
                    subsequent_indent="      ",
                )
            )
        return "\n".join(out)


def _mark(text: str, vocabulary: Index) -> tuple[str, list[Entry]]:
    """One line, marked, and the entries its marks point at."""
    if vocabulary._pattern is None:
        return text, []
    found: list[Entry] = []

    def replace(match) -> str:
        entry = vocabulary.by_spelling.get(normal(match.group(0)))
        if entry is None:
            return match.group(0)
        found.append(entry)
        return f"{OPEN}{match.group(0)}{CLOSE}"

    return vocabulary._pattern.sub(replace, text), found


def passage(quote: str, *, layer_id: str, store: ProvenanceStore | None = None) -> Passage:
    """A citation, as the city wrote it, with its vocabulary marked."""
    store = store or ProvenanceStore()
    try:
        text = store.quote(quote)
    except (ProvenanceError, KeyError, ValueError) as exc:
        raise ReadingError(f"{quote}: nothing stored to read -- {exc}") from exc

    reference = parse_quote(quote)
    first = getattr(reference, "start", None) or 1
    vocabulary = index(layer_id)

    lines: list[tuple[int, str]] = []
    legend: dict[str, Entry] = {}
    for offset, raw in enumerate(text.splitlines()):
        marked, found = _mark(raw, vocabulary)
        lines.append((first + offset, marked))
        for entry in found:
            legend.setdefault(normal(entry.term), entry)
    return Passage(
        layer=layer_id,
        quote=quote,
        lines=tuple(lines),
        legend=tuple(legend.values()),
    )


def for_value(layer_id: str, zone: str, field: str, *, store: ProvenanceStore | None = None) -> Passage:
    """The passage an encoded value was read from, marked.

    The reviewer's entry point: they are looking at a number, not at a
    citation, and the citation is what has to be produced for them.
    """
    layer = load_rules().get(layer_id)
    if layer is None:
        raise ReadingError(f"{layer_id}: no such jurisdiction")
    for candidate_zone, candidate_field, quote in _quoted(layer):
        if (candidate_zone, candidate_field) == (zone, field):
            return passage(quote, layer_id=layer_id, store=store)
    raise ReadingError(f"{layer_id} {zone} {field}: no value carrying a quote")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    def option(name: str) -> str | None:
        return args[args.index(name) + 1] if name in args else None

    layer_id = option("--layer")
    if not layer_id:
        print("usage: --layer <id> (--quote <doc#Lx-Ly> | --zone <code> --field <name>)")
        return 2
    try:
        quote = option("--quote")
        if quote:
            found = passage(quote, layer_id=layer_id)
        else:
            zone, field = option("--zone"), option("--field")
            if not zone or not field:
                print("usage: --zone <code> --field <name>, or --quote <doc#Lx-Ly>")
                return 2
            found = for_value(layer_id, zone, field)
    except ReadingError as exc:
        print(str(exc))
        return 1
    print(found.render())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["OPEN", "CLOSE", "Passage", "ReadingError", "for_value", "passage"]
