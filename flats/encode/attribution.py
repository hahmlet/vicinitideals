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
_HEADING = re.compile(
    r"^\s*(?:§|�)?\s*(?P<n>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)\s*(?:[A-Z§—-]|$)"
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
        """
        if not self.claimed or not self.found:
            return True
        return any(
            one.startswith(self.found) or self.found.startswith(one)
            for one in self.claimed.split()
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


def section_at(lines: Sequence[str], line: int) -> str:
    """The section the text at this line sits in, read off the document.

    Nearest marker above wins. A running header printed at the foot of the
    previous page is closer than the heading that opened the section twelve
    pages back, and it says the same thing.
    """
    for n in range(min(line, len(lines)) - 1, max(line - _LOOK_BACK, 0) - 1, -1):
        if found := _HEADING.match(lines[n]):
            return found.group("n")
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
        try:
            first = int(quote.partition("#L")[2].split("-")[0].lstrip("L"))
        except ValueError:
            continue
        out.append(
            Attribution(
                layer=layer.layer,
                zone=zone,
                field=field,
                quote=quote,
                claimed=" ".join(claimed_sections(value.prov.cite or "")),
                found=section_at(lines, first),
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
