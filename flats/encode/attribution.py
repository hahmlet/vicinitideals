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
import sys
from dataclasses import dataclass
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
_HEADING = re.compile(
    r"^[ 	]{0,8}(?:"
    r"Section\s+(?P<s>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)\.?\s*(?:[A-Z—-])"
    r"|(?:§|�)?\s*(?P<n>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)\s*(?:[A-Z§—-]|$)"
    r")"
)

#: How far above a quote to look for the section it belongs to. A codifier
#: prints its running header once a page, so this only has to clear one page.
_LOOK_BACK = 90


@dataclass(frozen=True, slots=True)
class Attribution:
    """One value's claimed section against the one its text sits in."""

    layer: str
    zone: str
    field: str
    quote: str
    claimed: str
    found: str

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


def section_at(lines: Sequence[str], line: int) -> str:
    """The section the text at this line sits in, read off the document.

    Nearest marker above wins. A running header printed at the foot of the
    previous page is closer than the heading that opened the section twelve
    pages back, and it says the same thing.
    """
    for n in range(min(line, len(lines)) - 1, max(line - _LOOK_BACK, 0) - 1, -1):
        if found := _HEADING.match(lines[n]):
            return found.group("s") or found.group("n")
    return ""


def _values(layer: Layer) -> Iterable[tuple[str, str, object]]:
    for name, value in layer.defaults.items():
        yield "(defaults)", name, value
    for code, zone in sorted(layer.zones.items()):
        for name in sorted(zone.values):
            value = zone.values[name]
            yield code, name, value
            for variant in value.variants:
                yield code, f"{name} [{'+'.join(variant.key)}]", variant


def check(layer: Layer, store: ProvenanceStore) -> list[Attribution]:
    """Every value in a layer, with the section it claims and the one it is in."""
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
        out.append(
            Attribution(
                layer=layer.layer,
                zone=zone,
                field=field,
                quote=quote,
                claimed=" ".join(claimed_sections(value.prov.cite or "")),
                found=" ".join(here),
            )
        )
    return out


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
    checked = disagreeing = 0
    for layer_id, layer in sorted(load_rules(strict=False).items()):
        if args.layer and not layer_id.startswith(args.layer):
            continue
        for item in check(layer, store):
            checked += 1
            if item.agrees:
                if args.verbose:
                    print(f"  ok  {item.line()}")
                continue
            disagreeing += 1
            print(item.line())
    print(f"\n{disagreeing} of {checked} value(s) cite a section their text is not in")
    return 1 if disagreeing else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
