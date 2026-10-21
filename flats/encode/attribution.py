"""Whether a value's citation names the section its quote actually sits in.

The store already proves a quote *resolves* and the readiness ladder already
proves the quoted text *states the number*. Neither can see the failure that
sits between them: a citation whose words name one section while its line
numbers point into another.

That is not a cosmetic mismatch. Wilsonville's RN zone cited "4.127 Residential
Neighborhood, Table 2 (Frog Pond West)" against lines that are section 4.113 —
the citywide setback provisions, which apply "unless otherwise provided for by
the Code or a legislative master plan". The number happened to be right. The
authority was not: anyone checking it would open 4.127 and find nothing, and a
master plan that provided otherwise would silently defeat the encoding.

So the section is read back off the document — from the heading above the
quoted lines, or from the running header a codifier prints on every page — and
compared with the section the citation claims. Disagreement is reported, never
repaired: which of the two is wrong is a judgement about the code, and the
whole point of provenance is that a machine does not get to make it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.model import Layer

#: A section number as codifiers write it: 4.113, 19.302.4, 33.110.220.
_SECTION = re.compile(r"(?<![\d.])(?P<n>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)(?![\d])")

#: A heading or running header that announces which section text belongs to.
#: Municode prints "§ 4.113 WILSONVILLE CODE" on every page, which makes the
#: page furniture the most reliable section marker in the document — it is
#: repeated, machine-placed, and immune to a heading that got flattened into a
#: table cell.
#:
#: What follows the number is what tells a heading from a table row, and the
#: rule is narrow on purpose: a heading is followed by its title, so the next
#: thing printed is a capital letter, a dash, or the end of the line. A row of
#: a table is followed by more of the table. The earlier version of this
#: pattern allowed a bare space there, which matched anything at all — Gresham
#: alone lost 57 values to it, its density rows reading as section "14.52
#: units per acre" and a row of "9.0100" cross-references reading as a heading
#: for everything below it.
#: The other form is the heading itself, spelled out: "Section 4.124. Standards
#: Applying to all Planned Development Residential Zones." Wilsonville writes
#: every one of its headings that way, so the running header was the only
#: marker the pattern could see and a quote landed on whichever section's page
#: furniture it happened to sit under — 4.124's own permitted-use list read as
#: 4.123. The trailing guard is the same in both branches: a heading is
#: followed by its title, so a capital letter, a dash, or the end of the line.
#: A cross-reference reads "Section 4.127(.09)(B)" and is followed by a
#: parenthesis, which is how the two stay apart.
#: The indent is the third guard, and it is what a heading cannot fake: a
#: heading starts at the margin, a cross-reference printed inside a table cell
#: starts wherever the column does. Gresham's RTC parking row prints "Section
#: 9.0851" fifty-six columns in, followed by a capital S, and every table note
#: below it read as section 9.0851 without this.
#: The period is the fourth guard, and it cuts both ways. A spelled-out
#: heading ends its number with one -- "Section 4.136. PF—Public Facility
#: Zone." -- and a spelled-out cross-reference printed in a table cell does
#: not: Milwaukie's use tables carry a Standards column whose cells read
#: "Section 19.905 Conditional Uses" and start at the margin, and four use
#: gates read as sections 19.508, 19.700, 19.905 and 19.507 through them.
#: So the "Section" form requires its period. The section-sign form allows
#: one, because Milwaukie and Gresham write their real headings as
#: "§ 19.307.1. Uses Permitted Outright." and "§ 4.1220. Uses", and without
#: it the marker above those chapters was whichever cross-reference sat
#: nearest. Measured 2026-09-20 over the whole corpus: 30 more values
#: resolve to a section, six disagreements gone, none added.
#: The last form is a heading the PDF reader split after the title number:
#: Portland's 33.418 prints "33. 418.030 Applying the Constrained Sites
#: Overlay Zone", and every value quoted from it read as 33.418.010, the
#: purpose statement two headings up. Only a three-part number followed by
#: its title counts -- Oregon City's split table-of-contents lines ("17.
#: 32.010" alone on a line) stay what they were.
#: A bare number has one more guard: it cannot be a fraction. West Linn's
#: dimensional tables print each cell on its own line, so the FAR cell "0.45"
#: sat at the margin with nothing after it and read as a heading for every
#: row below it -- nine FAR and parking values reported as sitting in section
#: "0.45" or "0.30". No codifier numbers a section zero-point-anything.
_HEADING = re.compile(
    r"^[ 	]{0,8}(?:"
    r"Section\s+(?P<s>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)\.\s*(?:[A-Z—-])"
    r"|(?:§|�)\s*(?P<m>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)\.?\s*(?:[A-Z§—-]|$)"
    r"|(?!0\.)(?P<n>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)\s*(?:[A-Z§—-]|$)"
    r"|(?P<t>\d{1,3})\. (?P<u>\d{2,4}\.\d{1,4})\s+[A-Z]"
    r")"
)

#: How far above a quote to look for the section it belongs to. A codifier
#: prints its running header once a page, so this only has to clear one page.
_LOOK_BACK = 90

#: How a disagreement is classified. Report-only: nothing reads these but the
#: gaps ledger and this module's own report, and no class changes whether a
#: disagreement is counted.
#: (a) the claimed section is printed inside the cited lines -- a running
#: header or a cross-reference, so the section reader likely took the wrong
#: marker. Probably harmless, but not provably so.
HEADER_OR_XREF = "header_or_xref"
#: (b) the claimed section has a heading elsewhere in the same document.
HEADING_SAME_FILE = "heading_same_file"
#: (c) the claimed section has a heading only in another stored document.
HEADING_OTHER_FILE = "heading_other_file"
#: Nowhere in the corpus does a heading carry the claimed section.
UNLOCATED = "unlocated"
KINDS = (HEADER_OR_XREF, HEADING_SAME_FILE, HEADING_OTHER_FILE, UNLOCATED)

_NOISE = re.compile(r"[\s\-–—§'\"“”‘’]+")


def _same_section(a: str, b: str) -> bool:
    """Equal, or one is a dotted extension of the other (19.302 / 19.302.4)."""
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def _heading_number(line: str) -> str:
    found = _HEADING.match(line)
    if not found:
        return ""
    return (
        found.group("s")
        or found.group("m")
        or found.group("n")
        or (f"{found.group('t')}.{found.group('u')}" if found.group("t") else "")
    )


def _headings(lines: Iterable[str]) -> set[str]:
    return {n for line in lines if (n := _heading_number(line))}


def _span_ranges(quote: str) -> tuple[tuple[int, int], ...]:
    out: list[tuple[int, int]] = []
    for piece in quote.partition("#")[2].split(","):
        first, _, last = piece.strip().replace("L", "").partition("-")
        if first.isdigit():
            out.append((int(first), int(last) if last.isdigit() else int(first)))
    return tuple(out)


def _printed_in(text: str, claimed: str) -> bool:
    """Whether a section number is printed in text, tolerating spaces, hyphens,
    quotes and section marks inside it, and not as part of a longer number."""
    needle = _NOISE.sub("", claimed)
    pattern = r"(?<![\d.])" + _NOISE.pattern.replace("+", "*").join(map(re.escape, needle))
    return re.search(pattern + r"(?!\d)", text) is not None


class CorpusHeadings:
    """Every heading number of every stored document, read once and lazily."""

    def __init__(self, store: ProvenanceStore) -> None:
        self._store = store
        self._by_document: dict[str, set[str]] | None = None

    def other_than(self, document: str) -> Iterable[set[str]]:
        if self._by_document is None:
            self._by_document = {}
            for path in self._store.documents():
                try:
                    text = self._store.load(path).text
                except (ProvenanceError, OSError):
                    continue
                self._by_document[path] = _headings(text.splitlines())
        return (found for path, found in self._by_document.items() if path != document)


def classify(
    item: Attribution,
    lines: Sequence[str],
    corpus: CorpusHeadings,
) -> str:
    """Which kind of disagreement this is. "" where the item agrees."""
    if item.agrees:
        return ""
    claims = item.claimed.split()
    cited = "\n".join(
        "\n".join(lines[first - 1 : last])
        for first, last in _span_ranges(item.quote)
    )
    if any(_printed_in(cited, one) for one in claims):
        return HEADER_OR_XREF
    outside = set()
    covered: set[int] = set()
    for first, last in _span_ranges(item.quote):
        covered.update(range(first - 1, last))
    for n, line in enumerate(lines):
        if n not in covered and (number := _heading_number(line)):
            outside.add(number)
    if any(_same_section(one, h) for one in claims for h in outside):
        return HEADING_SAME_FILE
    document = item.quote.partition("#L")[0]
    if any(
        _same_section(one, h)
        for found in corpus.other_than(document)
        for one in claims
        for h in found
    ):
        return HEADING_OTHER_FILE
    return UNLOCATED


@dataclass(frozen=True, slots=True)
class Attribution:
    """One value's claimed section against the one its text sits in."""

    layer: str
    zone: str
    field: str
    quote: str
    claimed: str
    found: str
    kind: str = ""

    @property
    def probably_harmless(self) -> bool:
        """Whether the claimed section is printed in the cited lines themselves."""
        return self.kind == HEADER_OR_XREF

    @property
    def agrees(self) -> bool:
        """Whether the claim and the document can be read as the same place.

        Prefix-compatible counts as agreement: a citation to "19.302" against
        text headed "19.302.4" is a citation to the table inside the section it
        names. Only a different section number is a disagreement.

        A quote with several spans sits in several sections, and every one of
        them is an authority the value rests on -- Wilsonville reads the zone
        table and the definition of "Middle Housing" together, and a citation
        naming only the table sends a reviewer to a page that never says a
        quadplex is one. So every section found has to be claimed, not just
        one of them.
        """
        if not self.claimed or not self.found:
            return True
        claims = self.claimed.split()
        return all(
            any(one.startswith(here) or here.startswith(one) for one in claims)
            for here in self.found.split()
        )

    def line(self) -> str:
        return (
            f"{self.layer:34} {self.zone:>8} {self.field:26} "
            f"cites {self.claimed:<10} text is {self.found:<10} {self.quote}"
        )


def claimed_sections(cite: str) -> tuple[str, ...]:
    """Every section a citation names, in the order it names them.

    A citation often names several: Gresham's use standards are read off
    "Tables 4.0120/4.0130/4.0131", printed in three different sections. Taking
    only the first would report the other two as somewhere else entirely.
    """
    return tuple(found.group("n") for found in _SECTION.finditer(cite or ""))


def claimed_section(cite: str) -> str:
    """The first section a citation names, or "" if it names none."""
    found = claimed_sections(cite)
    return found[0] if found else ""


def _spans(quote: str) -> tuple[int, ...]:
    """The first line of each span in a quote, skipping anything unreadable.

    Only the first line of a span is needed: a span short enough to quote does
    not cross a section boundary, and one that does is a citation problem this
    check has no way to repair.
    """
    out: list[int] = []
    for piece in quote.partition("#")[2].split(","):
        first = piece.strip().lstrip("L").partition("-")[0]
        if first.isdigit():
            out.append(int(first))
    return tuple(out)


def _order(section: str) -> tuple[int, ...]:
    return tuple(int(part) for part in section.split("."))


def section_at(lines: Sequence[str], line: int) -> str:
    """The section the text at this line sits in, read off the document.

    Nearest marker above wins. A running header printed at the foot of the
    previous page is closer than the heading that opened the section twelve
    pages back, and it says the same thing -- almost always. Municode's page
    furniture lags: the header on the page after "Section 4.136. PF—Public
    Facility Zone." still reads "§ 4.135.5 WILSONVILLE CODE", so the last item
    of 4.136's conditional-use list, printed just below that header, read as
    4.135.5. A heading cannot lag, so when the nearest marker is furniture the
    scan goes on to the nearest spelled-out heading within reach, and a
    heading that opens a LATER section than the furniture names is the one
    the text sits under. An earlier heading is what the furniture already
    said, and the furniture wins as before.
    """
    furniture = ""
    for n in range(min(line, len(lines)) - 1, max(line - _LOOK_BACK, 0) - 1, -1):
        found = _HEADING.match(lines[n])
        if not found:
            continue
        if spelled := found.group("s"):
            if furniture and _order(spelled) <= _order(furniture):
                return furniture
            return spelled
        if not furniture:
            furniture = (
                found.group("m")
                or found.group("n")
                or f"{found.group('t')}.{found.group('u')}"
            )
    return furniture


def _values(layer: Layer) -> Iterable[tuple[str, str, object]]:
    for name, value in layer.defaults.items():
        yield "(defaults)", name, value
    for code, zone in sorted(layer.zones.items()):
        for name in sorted(zone.values):
            value = zone.values[name]
            yield code, name, value
            for variant in value.variants:
                yield code, f"{name} [{'+'.join(variant.key)}]", variant


def check(
    layer: Layer,
    store: ProvenanceStore,
    corpus: CorpusHeadings | None = None,
) -> list[Attribution]:
    """Every value in a layer, with the section it claims and the one it is in.

    Each disagreement carries a ``kind``; pass one ``corpus`` across layers to
    read the stored documents only once.
    """
    corpus = corpus or CorpusHeadings(store)
    out: list[Attribution] = []
    cache: dict[str, list[str]] = {}
    for zone, field, value in _values(layer):
        quote = value.prov.quote or ""
        if "#L" not in quote:
            continue
        document = quote.partition("#L")[0]
        if document not in cache:
            try:
                cache[document] = store.load(document).text.splitlines()
            except (ProvenanceError, OSError):
                cache[document] = []
        lines = cache[document]
        if not lines:
            continue
        starts = _spans(quote)
        if not starts:
            continue
        # Every span, de-duplicated but kept in the order the quote reads --
        # two spans on the same page are one authority, not two.
        here: list[str] = []
        for first in starts:
            section = section_at(lines, first)
            if section and section not in here:
                here.append(section)
        item = Attribution(
            layer=layer.layer,
            zone=zone,
            field=field,
            quote=quote,
            claimed=" ".join(claimed_sections(value.prov.cite or "")),
            found=" ".join(here),
        )
        out.append(replace(item, kind=classify(item, lines, corpus)))
    return out


def tally(items: Iterable[Attribution]) -> dict[str, int]:
    """Disagreements per kind; every kind present, zero included."""
    counts = dict.fromkeys(KINDS, 0)
    for one in items:
        if not one.agrees:
            counts[one.kind] += 1
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    """Report every value whose citation names a section its text is not in.

    Exit 1 when any disagree, so this can gate a corpus the way the firewall
    check gates a commit.
    """
    import argparse

    from flats.rules.loader import load_rules

    parser = argparse.ArgumentParser(prog="python -m flats.encode.attribution")
    parser.add_argument("--layer", default="", help="layer id prefix")
    parser.add_argument("--verbose", action="store_true", help="list agreeing values too")
    args = parser.parse_args(argv)

    store = ProvenanceStore()
    corpus = CorpusHeadings(store)
    checked = 0
    disagreeing: list[Attribution] = []
    for layer_id, layer in sorted(load_rules(strict=False).items()):
        if args.layer and not layer_id.startswith(args.layer):
            continue
        for item in check(layer, store, corpus):
            checked += 1
            if item.agrees:
                if args.verbose:
                    print(f"  ok  {item.line()}")
                continue
            disagreeing.append(item)
            print(f"[{item.kind}] {item.line()}")
    counts = tally(disagreeing)
    real = len(disagreeing) - counts[HEADER_OR_XREF]
    print(f"\n{len(disagreeing)} of {checked} value(s) cite a section their text is not in")
    print(f"  {real} to review (heading elsewhere or unlocated)")
    print(f"  {counts[HEADER_OR_XREF]} probably harmless (section printed in the cited lines)")
    return 1 if disagreeing else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
