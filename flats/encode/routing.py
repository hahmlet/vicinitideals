"""A sentence that sends you somewhere else, in a chapter we already hold.

:mod:`flats.encode.crossrefs` asks which sections our documents point at that
we *cannot* open. This asks the complement, which is the question nobody was
asking: which sections do our documents point at that we **can** open,
standing beside a number this screen uses, where nobody followed the pointer?

Portland's parking aisle is why. 33.266.120 is titled for this building,
states a 9 x 18 stall, and names no aisle anywhere in the section -- so
"Portland states no aisle width" was encoded and shipped. Four lines above the
sentence that was quoted, 33.266.120.B.1 says parking in a parking tract "is
subject to the standards of Section 33.266.130 instead of the standards of
this section", and 33.266.130's Table 266-4 states an aisle. The reference was
in the same file, already fetched, already in the store. Every ledger reported
the corpus clean, because every ledger was built to notice a document we are
missing.

Three conditions make a row, and each one is doing work:

*routing language*
    Not every reference redirects. "See 33.910 for definitions" adds a term;
    "is subject to the standards of Section X instead" replaces a standard.
    Only the second shape can move a number without appearing near it, and
    matching only that shape is what keeps this ledger a page rather than a
    corpus.

*inside a section we read from*
    Not "within N lines". An applicability paragraph governs its whole
    section, and Portland's sits forty lines above the row that was quoted --
    a line-window ledger would have reported the corpus clean on the day the
    aisle was refused, which is the one day it needed to speak. So the scope
    is the section: a redirect counts when some encoded value was read from
    inside the same section the redirect is in.

*into a document we hold*
    A reference we cannot open is already counted, once, in the other ledger.
    Counting it twice would bury this one.

A row closes on evidence rather than on a note. It is **followed** when some
encoded value in the same layer was read from a line inside the section the
sentence points at -- the corpus itself demonstrating that somebody went
there. Portland's row reads followed today and would have read open the day
the aisle was refused, which is the whole test. That mechanism is deliberate:
a ruling channel would let a row be closed by asserting it had been read, and
this is the one class of mistake where the assertion is exactly what failed.

Run it::

    uv run python -m flats.encode.routing
    uv run python -m flats.encode.routing or/multnomah/portland
    uv run python -m flats.encode.routing --all
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from flats.encode.crossrefs import (
    _HEADING,
    _REF,
    _WRAPPED,
    _cited_lines,
    _doc_ids,
    _headings,
    _resolves,
)
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

#: Where the ledger is written.
LEDGER = Path(__file__).resolve().parents[2] / "data" / "flats" / "routing.csv"

#: The verbs that replace a standard rather than add to one.
#:
#: "Supersede", "instead of" and "in lieu" are the plain cases. "Subject to"
#: is here because it is how several codes in this corpus write a redirect --
#: Portland's parking tract sentence is "is subject to the standards of
#: Section 33.266.130 instead", and Fairview's village chapters are "subject
#: to the provisions of this chapter". "Does not apply" earns its place from
#: the other side: it removes a standard, and the sentence that removes one
#: usually names the section that supplies the replacement.
#:
#: Not here: "see", "pursuant to", "as defined in", "in accordance with".
#: Those point at a definition or a procedure, and a ledger that admitted them
#: would report every chapter in the store.
_ROUTE = re.compile(
    r"\b(?:instead of|in place of|in lieu|rather than"
    r"|(?:is|are|shall be) subject to"
    r"|except as (?:provided|otherwise)"
    r"|do(?:es)? not apply"
    r"|supersede|take[s]? precedence)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class Routing:
    """One redirect standing beside a number this screen uses."""

    layer: str
    #: The document and line the sentence is on.
    path: str
    line: int
    #: The section the sentence is in -- the one whose standards it hands off.
    section: str
    #: The section it sends you to.
    ref: str
    #: The sentence, trimmed to something a reader can judge.
    text: str
    #: Whether an encoded value in this layer was read from inside ``ref``.
    followed: bool

    @property
    def label(self) -> str:
        return f"{self.layer} {self.section} -> {self.ref}"


#: A section number followed by a lowercase word is a sentence, not a heading.
#:
#: :mod:`flats.encode.crossrefs` rejects a wrapped reference by looking at the
#: line before it, which works when the wrap is clean. It is not always clean:
#: a page break lands between the two halves, so the line above is a running
#: header and the guard sees nothing to catch. Portland's Table 266-4 is on
#: the wrong side of one of those -- "Section 33.266.140 below. Mechanical
#: parking systems are exempt..." opens a line six lines after a page number,
#: and read as a heading it moves the aisle table out of 33.266.130 and into
#: a section that starts twenty lines later.
#:
#: A title is capitalised in every document in this store. "below", "means",
#: "through", "pertained" and "concurrently" are not titles; 153 of 7,382
#: matches are this shape and every one of them is a wrapped sentence.
_SENTENCE = re.compile(
    r"^\s*(?:§\s*)?(?:(?:Section|Chapter)\s+|[A-Z]{2,5}\s+)?"
    r"\d[\d.\-]*\d[A-Z]?\.?\s+[a-z]"
)


def _heading_lines(text: str, owns: set[str], mine: set[str]) -> dict[int, str]:
    """Line number -> the section number that opens there.

    The same heading test :mod:`flats.encode.crossrefs` uses, kept per-line
    instead of collapsed to a set, because this ledger needs to know not just
    that a document prints a section but *where* -- a cited line is inside a
    section or it is not. Which also means a false heading costs more here: it
    does not merely add a number to a set, it moves every line after it into
    the wrong section.
    """
    out: dict[int, str] = {}
    prev = ""
    for n, line in enumerate(text.splitlines(), start=1):
        m = _HEADING.match(line)
        if m and not _SENTENCE.match(line):
            num = m.group("num").rstrip(".")
            # A document devoted to a chapter does not restart it halfway
            # down. Every extracted code in this store prints its chapter
            # number as a running header on each page -- "Chapter 33.266" on
            # one line, "266-14" on another -- and taken as headings they cut
            # every section into page-sized pieces. Portland's Table 266-4
            # sits four page breaks below the 33.266.130 heading, so the last
            # heading above it was a page header and the table belonged, as
            # far as this ledger could tell, to no section at all.
            if num in mine or any(own.startswith(f"{num}.") for own in mine):
                continue
            if num.partition(".")[0] in owns and (
                any(num == own or num.startswith(f"{own}.") for own in mine)
                or not (prev and _WRAPPED.search(prev.rstrip()))
            ):
                out[n] = num
        if line.strip():
            prev = line
    return out


def _section_at(line: int, starts: Sequence[int], heads: dict[int, str]) -> str | None:
    """The section a line sits in: the nearest heading at or above it."""
    prior = [s for s in starts if s <= line]
    return heads[prior[-1]] if prior else None


def _sections_read(
    cited: dict[str, set[int]], heads: dict[str, dict[int, str]]
) -> set[str]:
    """Every section some encoded value in this layer was read from.

    A cited line that is *itself* a heading does not count, and that exclusion
    is the difference between this working and not. Every code chapter in this
    store opens with a table of contents -- one line per section, each of them
    a section number at the start of a line, each of them indistinguishable
    from the heading it lists. Portland's parking maxima are quoted against
    that contents block, and read naively it says the layer has read all eight
    sections of 33.266, including the one nobody opened. A citation into a
    list of section titles is evidence of nothing.

    Otherwise a cited line belongs to the nearest heading above it, which is
    coarse in the safe direction: it can call a section read when the value
    came from the paragraph after its last subheading, closing a row that
    could have stayed open. It cannot call a section unread when a value
    really came from inside it, which would be the ledger crying wolf until
    nobody reads it.
    """
    found: set[str] = set()
    for path, lines in cited.items():
        here = heads.get(path, {})
        starts = sorted(here)
        for line in lines:
            if line in here:
                continue
            section = _section_at(line, starts, here)
            if section:
                found.add(section)
    return found


#: "Sections 9.0822 to 9.0840", "19.65.030 through 19.65.090".
_SPAN = re.compile(
    r"(?<![\d.])(\d[\d.]*\d)\s*(?:to|through|--|-|–)\s*(\d[\d.]*\d)(?![\d.])"
)


def _parts(section: str) -> tuple[int, ...]:
    """A section number as something comparable. ``9.0825`` -> ``(9, 825)``."""
    out: list[int] = []
    for piece in section.split("."):
        digits = "".join(c for c in piece if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def _spans(line: str) -> list[tuple[str, str]]:
    """The section ranges a sentence names.

    A code that hands off a block of standards names the block, not each
    section in it -- "parking lot design standards (Sections 9.0822 to
    9.0840)". Reading 9.0825 answers that sentence, and a ledger matching only
    the number the reference *starts* with would hold the row open forever
    while the standard it points at sits encoded three sections in.
    """
    return [(m.group(1), m.group(2)) for m in _SPAN.finditer(line)]


def _within(section: str, lo: str, hi: str) -> bool:
    """Whether a section falls inside a named range, compared numerically."""
    return _parts(lo) <= _parts(section) <= _parts(hi)


def _is_followed(ref: str, read: set[str]) -> bool:
    """Whether the corpus shows somebody went where this sentence points.

    One direction only: a section read has to *be* the target or sit inside
    it. Reading a chapter's other sections is not evidence anybody opened this
    one -- 33.266 is where both the aisle and the refusal to state an aisle
    live, and a rule that let any 33.266.x citation answer for 33.266.130
    would close the row this ledger exists to hold open.

    A sentence naming a whole chapter still closes on any section within it,
    which is the same rule seen from the other end: what was read is inside
    what was pointed at.
    """
    return any(
        section == ref or section.startswith(f"{ref}.") for section in read
    )


def redirects(layer: Layer, store: ProvenanceStore | None = None) -> list[Routing]:
    """Every redirect this layer's own documents make beside a number it uses."""
    store = store or ProvenanceStore()
    paths = [p for p in store.documents() if p.startswith(f"{layer.layer}/")]
    if not paths:
        return []

    texts = {p: store.text_path(p).read_text(encoding="utf-8") for p in paths}
    ids = _doc_ids(paths)
    headings: set[str] = set()
    heads: dict[str, dict[int, str]] = {}
    for path, text in texts.items():
        own = _doc_ids([path])
        owns = {i.partition(".")[0] for i in own}
        headings |= _headings(text, owns, own)
        heads[path] = _heading_lines(text, owns, own)

    cited = _cited_lines(layer)
    read = _sections_read(cited, heads)

    rows: list[Routing] = []
    for path, text in texts.items():
        if path not in cited:
            continue
        here = heads[path]
        starts = sorted(here)
        for n, line in enumerate(text.splitlines(), start=1):
            if not _ROUTE.search(line):
                continue
            section = _section_at(n, starts, here)
            # A redirect in a section no value was read from cannot have
            # moved a number: nothing here was taken from around it.
            if section is None or section not in read:
                continue
            seen: set[str] = set()
            for m in _REF.finditer(line):
                ref = (
                    m.group("named") or m.group("abbrev") or m.group("dotted") or ""
                ).rstrip(".")
                if not ref or (ref.isdigit() and len(ref) < 2) or ref in seen:
                    continue
                seen.add(ref)
                # Already counted, once, as a chapter we cannot open.
                if not _resolves(ref, ids, headings):
                    continue
                # "The standards of this section" -- a sentence naming its own
                # home sends nobody anywhere.
                if _is_followed(ref, {section}) or section.startswith(f"{ref}."):
                    continue
                followed = _is_followed(ref, read) or any(
                    _within(s, lo, hi)
                    for lo, hi in _spans(line)
                    if lo == ref
                    for s in read
                )
                rows.append(
                    Routing(
                        layer=layer.layer,
                        path=path,
                        line=n,
                        section=section,
                        ref=ref,
                        text=" ".join(line.split())[:200],
                        followed=followed,
                    )
                )
    rows.sort(key=lambda r: (r.followed, r.path, r.line, r.ref))
    return rows


def survey(
    layers: Sequence[Layer] | None = None, store: ProvenanceStore | None = None
) -> list[Routing]:
    store = store or ProvenanceStore()
    chosen = layers if layers is not None else list(load_rules().values())
    rows: list[Routing] = []
    for layer in chosen:
        rows.extend(redirects(layer, store))
    rows.sort(key=lambda r: (r.followed, r.layer, r.path, r.line))
    return rows


def write(rows: Sequence[Routing], path: Path | None = None) -> Path:
    file = path or LEDGER
    file.parent.mkdir(parents=True, exist_ok=True)
    # lineterminator is not cosmetic. csv writes CRLF by default, so this
    # ledger regenerated on Windows rewrote every row it had and buried the
    # real change -- 264 new rows inside a 19,082-line diff, 2026-09-03. A
    # ledger nobody can read the diff of is a ledger nobody checks.
    with file.open("w", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh, lineterminator="
")
        out.writerow(
            ["layer", "path", "line", "section", "ref", "followed", "text"]
        )
        for row in rows:
            out.writerow(
                [
                    row.layer,
                    row.path,
                    row.line,
                    row.section,
                    row.ref,
                    "yes" if row.followed else "",
                    row.text,
                ]
            )
    return file


def render(rows: Sequence[Routing], *, show_all: bool = False) -> Iterator[str]:
    open_rows = [r for r in rows if not r.followed]
    followed = [r for r in rows if r.followed]

    if not open_rows:
        yield (
            "no unfollowed redirects -- every sentence that sends a number "
            "somewhere else points at a section this corpus reads from"
        )
    else:
        by_layer: dict[str, list[Routing]] = defaultdict(list)
        for row in open_rows:
            by_layer[row.layer].append(row)
        yield (
            f"{len(open_rows)} redirect(s) beside an encoded number, pointing at "
            f"a section nothing was read from, across {len(by_layer)} jurisdiction(s)"
        )
        yield ""
        for name in sorted(by_layer):
            yield f"  {name}"
            for row in by_layer[name]:
                yield (
                    f"    {row.section:<14} -> {row.ref:<14} "
                    f"{Path(row.path).name}:{row.line}"
                )
                yield f"       {row.text}"
            yield ""

    # Printed, not hidden. A followed row is the ledger's evidence that the
    # mechanism bites -- Portland's parking tract sentence sits in this half
    # only because the aisle was finally encoded from where it points.
    if followed and show_all:
        yield f"  followed -- a value was read from inside it ({len(followed)})"
        for row in followed:
            yield (
                    f"    {row.layer} {row.section} -> {row.ref:<14} "
                    f"{Path(row.path).name}:{row.line}"
                )
        yield ""
    elif followed:
        yield f"  ({len(followed)} followed; --all to list them)"


def main(argv: Sequence[str] | None = None) -> int:
    # Code documents carry characters a Windows console cannot encode, and a
    # ledger that crashes on a sample line is a ledger nobody runs.
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    show_all = "--all" in args
    args = [a for a in args if not a.startswith("--")]

    layers = load_rules()
    chosen = [layers[a.strip("/")] for a in args] if args else list(layers.values())
    rows = survey(chosen)
    for line in render(rows, show_all=show_all):
        print(line)

    if not args:
        print(f"\nwritten -> {write(rows)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
