"""Find the line of code that says a fourplex is allowed here.

``quadplex_allowed`` is the most load-bearing value in the corpus and the
least evidenced. Eighty zones assert it as a bare ``true`` — no quote, nothing
to read — and a wrong one is not a wrong number: it turns every lot in the
zone green on a permission that does not exist, or red on one that does.

The numbers got quoted first because the extractor reads numbers. A permission
has none. What it has is a sentence, or a P in a use table, naming a housing
type this system cares about; so this module looks for the sentence rather
than for a value, and never writes, changes or checks the permission itself.
All it adds is the citation, which is what lets a reviewer do the checking.

Two strengths, and the difference is scope:

**anchored** — the line names a fourplex-family housing type and a permission,
and sits in a section this zone claims. Written by ``--apply``.

**loose** — the same sentence with no section to tie it to this zone. Reported
and never written. A use table lists a dozen zones in columns that flatten
into one line of text, so a permission found outside the zone's own sections
is as likely to be some other zone's as this one's, and a citation pointing at
the wrong zone's row is worse than no citation: it reads as evidence.

Usage::

    python -m flats.encode.permit                      # every layer, report
    python -m flats.encode.permit --layer or/x --apply # write the anchored ones
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from flats.encode.despace import repair_text
from flats.encode.extract import _SECTION, _heading_like
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.loader import CONFIG_ROOT, load_rules
from flats.rules.model import Layer

#: The housing types a four-unit attached building is permitted as. "Middle
#: housing" is included because Oregon's cities mostly adopted the statutory
#: phrase rather than listing the four types, and the statute's definition
#: contains the quadplex.
_TYPE = re.compile(
    r"\b(quad[- ]?plex(?:es)?|quadraplex(?:es)?|four[- ]?plex(?:es)?"
    r"|four[- ]unit|4[- ]unit|middle housing)\b",
    re.I,
)

#: A weaker naming: a zone that allows apartments allows a fourplex, but the
#: sentence is about a category this building only belongs to incidentally, so
#: it is reported and never written.
_BROADER = re.compile(r"\b(multi[- ]?(?:unit|family)\s+(?:housing|dwellings?))\b", re.I)

#: What makes the sentence a permission rather than a mention. The bare "P" is
#: how a use table says yes, and it is anchored to a cell boundary — two or
#: more spaces, or the start of the line — because a lone P inside prose is a
#: middle initial.
_ALLOWS = re.compile(
    r"\b(?:permitted|allowed|allowable|permissible"
    r"|may be (?:established|permitted|allowed)"
    r"|are allowed (?:by right|outright))\b"
    r"|(?:^|\s{2,})P(?:\s{2,}|\s*$)",
    re.I,
)

#: What looks like a permission and is not. A sentence about what is
#: prohibited, or one that sends the reader somewhere else, cites nothing.
#: A table caption. It opens a set of columns and so ends the previous one,
#: whether or not the codifier styled it as a heading.
_TABLE = re.compile(r"^Table\s+[0-9]", re.I)

_NEGATED = re.compile(
    r"\b(?:not (?:permitted|allowed)|prohibited|no (?:quad|four)"
    r"|shall not be (?:permitted|allowed)|except)\b",
    re.I,
)

#: A sentence that mentions the housing type while being about something
#: else. Wilsonville's "Accessory Uses Permitted to Single-Family Dwelling
#: Units and Middle Housing" names both a type and a permission and grants
#: neither — it is about sheds. Gresham's "new quadplexes created by adding
#: units to an existing dwelling" is a conversion rule that presumes the
#: permission rather than stating it. Cited as evidence, both read as the
#: base permission, which is the one thing this must never fabricate.
_ABOUT_SOMETHING_ELSE = re.compile(
    r"\b(?:accessory|conversion|converted|created by adding"
    r"|added to an existing|design standards?|definitions?|purpose of this)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class Found:
    """A line proposed as the evidence for one zone's permission."""

    layer: str
    zone: str
    quote: str
    text: str
    #: "anchored" — inside a section this zone claims. "loose" — not.
    strength: str
    #: What matched: the housing type named, or the broader category.
    named: str

    @property
    def writable(self) -> bool:
        return self.strength == "anchored"


def _in_section(section: str, claimed: Sequence[str]) -> bool:
    """Whether a clause's section falls under one this zone claims.

    Prefix rather than equality: a zone says it lives in 4.01 and the standard
    is printed under 4.0130, and a zone that claims nothing claims nothing —
    the empty tuple is not a wildcard, it is a gap in the encoding.
    """
    return bool(section) and any(section.startswith(prefix) for prefix in claimed)


def _code(zone: str) -> str:
    """A zone code in the one shape a rule file and a code document share.

    The files write R40 and the ordinance prints R-40; the same zone, and a
    comparison that respected the hyphen would find neither in the other.
    The decimal stays — R8.5 and R85 are two zones.
    """
    return re.sub(r"[^A-Z0-9.]", "", zone.upper())


def _names_zone(line: str, zone: str) -> bool:
    """Whether a line names this zone, and not a longer code containing it.

    R-5 sits inside R-50, and a table heading for the large-lot zones read
    as naming the small-lot one scopes every row under it to the wrong
    zone. Matched character by character with the separators optional, so
    TLDR, MUR-S and R8.5 are all findable in whatever shape the codifier
    chose to print them.
    """
    want = _code(zone)
    if not want:
        return False
    body = ("[- ]?").join(re.escape(c) for c in want)
    return re.search(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", line) is not None


def permissions_in(
    text: str, *, path: str, zone: str, claimed: Sequence[str], spaced: bool = False
) -> list[tuple[str, str, str, str]]:
    """Lines in one document that state this zone's permission.

    Read line by line rather than by clause, because in a use table the
    evidence *is* one line — "Quadplex  P  P  P" — and a paragraph reader
    swallows the whole grid into a blob that cites forty lines and states
    nothing a reviewer can check against.

    Two things scope a line to a zone, and either will do. A section the zone
    claims is one. The other is the nearest heading above it that names the
    zone: a use table headed "Table 16.22.020-1 Very Low Density Residential
    (R-40, R-20, R-15) Permitted Uses" says which columns follow, and every
    row under it belongs to those three zones and to no others.

    Returns ``(quote, text, strength, named)``.
    """
    out: list[tuple[str, str, str, str]] = []
    section = ""
    scoped = False
    for n, raw in enumerate((repair_text(text) if spaced else text).splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        found = _SECTION.match(line)
        if found and _heading_like(line):
            section = found.group("sec")
        if _heading_like(line) or _TABLE.match(line):
            # A heading resets the zone scope even when it names no zone:
            # the table it opens is a new set of columns, and inheriting the
            # last table's would attribute its rows to whatever came before.
            scoped = _names_zone(line, zone)
        if _NEGATED.search(line) or _ABOUT_SOMETHING_ELSE.search(line):
            continue
        if not _ALLOWS.search(line):
            continue
        named = _TYPE.search(line) or _BROADER.search(line)
        if named is None:
            continue
        anchored = (
            _in_section(section, claimed) or scoped or _names_zone(line, zone)
        ) and bool(_TYPE.search(line))
        out.append(
            (
                f"{path}#L{n}",
                line[:200],
                "anchored" if anchored else "loose",
                named.group(0),
            )
        )
    return out


def unquoted_zones(layer: Layer) -> list[str]:
    """Zones whose permission is asserted with nothing to read."""
    return sorted(
        w.zone for w in layer.wanted if w.field == "quadplex_allowed" and w.value.value is True
    )


def search(layer: Layer, store: ProvenanceStore) -> list[Found]:
    """Every proposal for every unevidenced permission in one layer."""
    zones = unquoted_zones(layer)
    if not zones:
        return []
    documents = []
    for doc in layer.code:
        path = f"{layer.layer}/{doc.id}.txt"
        try:
            documents.append((path, store.load(path).text, doc.spaced))
        except (ProvenanceError, OSError):
            continue

    out: list[Found] = []
    for code in zones:
        claimed = layer.zones[code].section
        for path, text, spaced in documents:
            for quote, line, strength, named in permissions_in(
                text, path=path, zone=code, claimed=claimed, spaced=spaced
            ):
                out.append(Found(layer.layer, code, quote, line, strength, named))
    return out


#: A use-table row: the housing type opens the line and its cells follow.
#: "Quadplex   P   P   NP" is the whole answer in one line, and it is better
#: evidence than any sentence — which is why it wins over one.
_ROW = re.compile(
    r"^(?:quad[- ]?plex|quadraplex|four[- ]?plex|four[- ]unit|middle housing)\b", re.I
)


def best(found: Iterable[Found]) -> dict[tuple[str, str], Found]:
    """One proposal per zone: its strongest anchored line, or nothing.

    A use-table row beats a sentence, and among equals the earlier line wins
    — where a code states the permission twice the first is the general
    statement and the second is usually its exception. This writes a citation
    for a person to read, not a verdict, so the ranking only decides what
    they are shown first.
    """
    out: dict[tuple[str, str], Found] = {}
    for item in found:
        if not item.writable:
            continue
        key = (item.layer, item.zone)
        held = out.get(key)
        if held is None or (_ROW.match(item.text) and not _ROW.match(held.text)):
            out[key] = item
    return out


#: ``  quadplex_allowed: true`` and nothing else. A value already written as a
#: block, or carrying a comment, or set to false, is left alone: this rewrites
#: a line it can reconstruct exactly, and anything else is someone's editing.
_BARE = re.compile(r"^(?P<indent> +)quadplex_allowed:\s*(?P<value>true|True)\s*$")


def apply(text: str, quotes: dict[str, str]) -> tuple[str, list[str]]:
    """Give each zone's bare ``true`` the line it was read from.

    ``quotes`` maps zone code to citation. Textual, like the drafter, because
    re-dumping the parsed file deletes every comment in it — and the comments
    are where the encoders wrote down what did not port.
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    zone_at = _zone_of(lines)

    written: list[str] = []
    for i, line in enumerate(lines):
        match = _BARE.match(line)
        zone = zone_at.get(i)
        if match is None or zone is None or zone not in quotes:
            continue
        pad = match.group("indent")
        lines[i] = (
            f"{pad}quadplex_allowed:{newline}"
            f'{pad}  value: true{newline}'
            f'{pad}  quote: "{quotes[zone]}"'
        )
        written.append(zone)
    return newline.join(lines) + newline, written


def _zone_of(lines: Sequence[str]) -> dict[int, str]:
    """Which zone block each line sits in.

    Built from indentation rather than from the parsed document, because the
    rewrite happens on lines and a value has to land in the zone it was found
    under — the failure this guards against is silent, and it is the standard
    becoming some other zone's.
    """
    out: dict[int, str] = {}
    start = next((i for i, ln in enumerate(lines) if ln.rstrip() == "zones:"), None)
    if start is None:
        return out
    depth = None
    current = ""
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line.startswith((" ", "\t")):
            break
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        if depth is None:
            depth = indent
        if indent == depth and stripped.endswith(":"):
            current = stripped[:-1].strip().strip("'\"")
        out[i] = current
    return out


def layer_path(root: Path, layer_id: str) -> Path:
    parts = layer_id.split("/")
    return root.joinpath(*parts[:-1], f"{parts[-1]}.yaml") if len(parts) > 1 else root / "_state.yaml"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-permit", description="Find the line that permits a fourplex."
    )
    parser.add_argument("--layer", default="", help="one layer id; default every layer")
    parser.add_argument("--root", type=Path, default=CONFIG_ROOT, help="jurisdiction rule files")
    parser.add_argument("--docs", type=Path, default=None, help="provenance store root")
    parser.add_argument("--apply", action="store_true", help="write the anchored citations")
    parser.add_argument("--verbose", action="store_true", help="show the loose lines too")
    args = parser.parse_args(argv)

    root = args.root
    store = ProvenanceStore(args.docs)
    layers = load_rules(root)
    if args.layer:
        if args.layer not in layers:
            print(f"no such layer: {args.layer}")
            return 2
        layers = {args.layer: layers[args.layer]}

    unevidenced = written = 0
    for layer_id, layer in sorted(layers.items()):
        zones = unquoted_zones(layer)
        if not zones:
            continue
        unevidenced += len(zones)
        found = search(layer, store)
        chosen = best(found)
        print(f"\n{layer_id}  {len(zones)} zone(s) with no line to read")
        for code in zones:
            pick = chosen.get((layer_id, code))
            if pick:
                print(f"  {code:14} {pick.quote}")
                print(f"  {'':14} {pick.text[:110]}")
            else:
                loose = [f for f in found if f.zone == code]
                why = (
                    f"{len(loose)} line(s) found, none inside this zone's sections"
                    if loose
                    else "no line in this layer's documents names a permitted fourplex"
                )
                print(f"  {code:14} -- {why}")
                if args.verbose:
                    for item in loose[:3]:
                        print(f"  {'':14}    loose: {item.quote}  {item.text[:90]}")

        if args.apply and chosen:
            path = layer_path(root, layer_id)
            updated, wrote = apply(
                path.read_text(encoding="utf-8"),
                {code: pick.quote for (_, code), pick in chosen.items()},
            )
            path.write_text(updated, encoding="utf-8")
            written += len(wrote)
            print(f"  wrote {len(wrote)} citation(s) into {path.name}")

    print(f"\n{unevidenced} permission(s) with nothing to read.")
    if args.apply:
        print(f"{written} now carry a citation. Read them before signing anything.")
    else:
        print("Re-run with --apply to write the anchored ones.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
