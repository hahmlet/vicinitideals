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
from flats.encode.find import code_of, names_zone
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


#: A use-table row: the housing type opens the line and its cells follow.
#: "Quadplex   P   P   NP" is the whole answer in one line, and it is better
#: evidence than any sentence — which is why it wins over one.
_ROW = re.compile(
    r"^(?:quad[- ]?plex|quadraplex|four[- ]?plex|four[- ]unit|middle housing)\b", re.I
)


#: A cell in a layout-extracted table. Codifiers separate columns with runs of
#: spaces and words within a cell with one, so two spaces is the boundary.
_CELL = re.compile(r"[^ ](?:[^ ]| (?! ))*")

#: What a use-table cell says. "Yes", "P" and "A" grant; "No", "N" and "NP"
#: refuse. Anything else — "CU", "III", a footnote marker — is neither, and a
#: cell this cannot read is left for a person rather than guessed at.
_CELL_YES = re.compile(r"^(?:yes|y|p|a|permitted|allowed)\b", re.I)
_CELL_NO = re.compile(r"^(?:no|n|np|not permitted|prohibited)\b", re.I)

#: How far a data cell may sit from its header cell and still be that column.
#: Extraction shifts a cell by a character or two where the printed text is
#: centred; a column over is a different zone's answer.
_DRIFT = 12


def _cells(line: str) -> list[tuple[int, int, str]]:
    """One line of a table as ``(start, end, text)`` per cell."""
    return [(m.start(), m.end(), m.group(0)) for m in _CELL.finditer(line)]


def _columns(line: str, siblings: Sequence[str]) -> dict[str, tuple[int, int]]:
    """The zone each column of a table header belongs to, by character span.

    A cell naming two zones names neither column: "R20 through R2.5" is a range
    printed in one cell, and the cells beneath it answer for a set this cannot
    split.
    """
    out: dict[str, tuple[int, int]] = {}
    for start, end, text in _cells(line):
        named = [z for z in siblings if _names_zone(text, z)]
        if len(named) == 1:
            out[named[0]] = (start, end)
    return out


def _cell_at(line: str, span: tuple[int, int]) -> str:
    """The cell of this row printed under that column, or "".

    Position is the only thing that says which zone a "Yes" answers for once a
    grid has been flattened to text, so a cell that does not line up is not
    read at all.
    """
    want = (span[0] + span[1]) / 2
    best_text, best_gap = "", None
    for start, end, text in _cells(line):
        gap = 0.0 if start < span[1] and end > span[0] else min(
            abs(start - span[1]), abs(span[0] - end)
        )
        if best_gap is None or gap < best_gap or (gap == best_gap and abs((start + end) / 2 - want) < 1):
            best_text, best_gap = text, gap
    return best_text if best_gap is not None and best_gap <= _DRIFT else ""


#: A cell of a linearised grid: a line that is nothing but the answer. Code
#: Publishing renders a use table as HTML and the extractor emits one cell per
#: line, so the row and its answers arrive as four lines rather than one.
_STACK_YES = re.compile(r"^(?:p|yes|a|permitted|allowed)[0-9*]{0,3}[.]?$", re.I)
_STACK_NO = re.compile(r"^(?:x|n|np|no|not permitted|prohibited)[0-9*]{0,3}[.]?$", re.I)
#: Neither: a conditional use, a special review, a limited permission. Each is
#: a yes with a process attached, which is a different standard from a yes and
#: not one this reader is entitled to decide.
_STACK_MAYBE = re.compile(r"^(?:c|cu|l|s|sur|pc)[0-9*]{0,3}[.]?$", re.I)
#: A zone code standing alone on a line, as a stacked header prints one —
#: with its footnote markers, which travel with the code and are not part of
#: it. "R-3 [3]" rejected as a column is not one column lost: it is the seven
#: after it read one place to the left, under the wrong districts.
_CODE_LINE = re.compile(
    r"^[A-Z][A-Z0-9]{0,3}(?:[-./][A-Z0-9.]{1,4})*(?:\s*(?:\[[0-9]+\]|\*+|[0-9]{1,2}))*$"
)


def _stack_cell(line: str) -> str:
    """Which of the three a stacked cell is: "yes", "no", or "" for neither."""
    if _STACK_MAYBE.match(line):
        return ""
    if _STACK_YES.match(line):
        return "yes"
    if _STACK_NO.match(line):
        return "no"
    return ""


def _stacked_header(
    lines: Sequence[tuple[int, str]], at: int, siblings: Sequence[str]
) -> list[str] | None:
    """The zones a run of solo code lines heads, in the order they are printed.

    A column that names no zone this layer knows is kept as an empty string
    rather than dropped. Position is the whole attribution: Clackamas heads
    Table 315-2 with R-2.5 before R-5, and a reader that skipped the district
    it has not encoded would read every remaining column one place to the left
    and file eight zones' standards under their neighbours'.
    """
    run: list[str] = []
    while at + len(run) < len(lines):
        _, text = lines[at + len(run)]
        if not _CODE_LINE.match(text) or len(text) > 20:
            break
        named = [z for z in siblings if _names_zone(text, z)]
        run.append(named[0] if len(named) == 1 else "")
    if len(run) < 2 or not any(run):
        return None
    return run


def stacked_permissions(
    lines: Sequence[tuple[int, str]], *, path: str, zone: str, siblings: Sequence[str]
) -> list[tuple[str, str, str, str]]:
    """Permissions from a use table that lost its geometry to HTML.

    The columnar reader needs the printed gaps to say which zone a "P" answers
    for. Half this corpus arrives without them: the codifier published HTML,
    the extractor walked the table cell by cell, and

        Land Use / R-40 / R-20 / R-15 / ... /
        One single-family dwelling, townhome, duplex, triplex, quadplex ... / P / P / P

    is a grid with every column intact and not one space between them. What
    replaces the geometry is arithmetic: a header of *k* codes, then a label
    and exactly *k* cells, and the zone at position *i* is answered by cell
    *i*. A row that does not produce exactly *k* readable cells is skipped
    rather than guessed at, because a row read one cell short files every
    answer after the gap under the wrong district.

    The line cited is the row's label, not its cell. "P" alone evidences
    nothing a reviewer can check; the sentence naming the housing type, with
    the printed page beside it, is the thing they can.
    """
    out: list[tuple[str, str, str, str]] = []
    i = 0
    columns: list[str] = []
    while i < len(lines):
        header = _stacked_header(lines, i, siblings)
        if header is not None:
            columns = header
            i += len(header)
            continue
        if not columns or zone not in columns:
            i += 1
            continue
        width = len(columns)
        cells = [_stack_cell(text) for _, text in lines[i + 1 : i + 1 + width]]
        over = lines[i + 1 + width : i + 2 + width]
        if len(cells) < width or not all(cells):
            i += 1
            continue
        if over and _stack_cell(over[0][1]):
            # More answers than the header has columns, which means the header
            # is the part this reader got wrong — a zone whose footnote marker
            # or spelling it failed to recognise as a column. Every cell after
            # that point answers for a district one place along, so the row is
            # left alone rather than filed against the wrong one.
            i += 1
            continue
        number, label = lines[i]
        verdict = cells[columns.index(zone)]
        if _TYPE.search(label) and not _NEGATED.search(label):
            out.append(
                (
                    f"{path}#L{number}",
                    label[:200],
                    "anchored" if verdict == "yes" else "contradicted",
                    lines[i + 1 + columns.index(zone)][1],
                )
            )
        i += 1 + width
    return out


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


#: Matched character by character with the separators optional, so TLDR, MUR-S
#: and R8.5 are all findable in whatever shape the codifier chose to print
#: them. Shared with the loose search, which ranks by the same question.
_code = code_of
_names_zone = names_zone


def permissions_in(
    text: str,
    *,
    path: str,
    zone: str,
    claimed: Sequence[str],
    spaced: bool = False,
    siblings: Sequence[str] = (),
) -> list[tuple[str, str, str, str]]:
    """Lines in one document that state this zone's permission.

    Read line by line rather than by clause, because in a use table the
    evidence *is* one line — "Quadplex  P  P  P" — and a paragraph reader
    swallows the whole grid into a blob that cites forty lines and states
    nothing a reviewer can check against.

    Three things scope a line to a zone, and any will do. A section the zone
    claims is one. The nearest heading above it that names the zone is another:
    a use table headed "Table 16.22.020-1 Very Low Density Residential (R-40,
    R-20, R-15) Permitted Uses" says which columns follow, and every row under
    it belongs to those three zones and to no others.

    The third is the column header, which is where most codes put it. A caption
    reading "Table 19.301.2 Moderate Density Residential Uses Allowed" names no
    zone at all; the row beneath it — "Use | R-MD | Standards" — names the zone
    the columns answer for, and Portland's "Housing Type | RF | R20 | R10 | R7 |
    R5 | R2.5" names six.

    Which is why a row is read by position rather than as a sentence. Layout
    extraction keeps the columns where the codifier printed them, so the cell
    under RF in "Fourplex | No | Yes | Yes | Yes | Yes | Yes" is the one that
    answers for RF, and the anchoring claim is "this cell, in this column" — a
    claim a reviewer can check in one glance at the page. A cell that does not
    line up under a header is not read: a column over is a different zone's
    answer, and citing it would evidence a permission that was refused.

    The fourth shape has no columns left to read. A code published as HTML
    linearises one cell to a line, and what pins the zone there is arithmetic
    rather than geometry: *k* codes in the header, then a label and *k* cells.
    See ``stacked_permissions``.

    A refusal is reported and never written. The value it contradicts may be
    right — a code amended after the encoding, a table this reader mis-columned
    — and either way it is a question for a person, not a citation to staple on.

    Returns ``(quote, text, strength, named)``.
    """
    body = repair_text(text) if spaced else text
    numbered = [
        (n, line.strip())
        for n, line in enumerate(body.splitlines(), 1)
        if line.strip()
    ]
    out: list[tuple[str, str, str, str]] = list(
        stacked_permissions(numbered, path=path, zone=zone, siblings=siblings)
    )
    read_as_a_stack = {quote for quote, _, _, _ in out}
    section = ""
    scoped = False
    columns: dict[str, tuple[int, int]] = {}
    header_window = 0
    for n, raw in enumerate(body.splitlines(), 1):
        line = raw.strip()
        if not line or f"{path}#L{n}" in read_as_a_stack:
            # Already read as a row of a linearised grid, by position. Reading
            # it a second time as prose would offer the same line twice, once
            # with the cell that answers for this zone and once without.
            continue
        found = _SECTION.match(line)
        if found and _heading_like(line):
            section = found.group("sec")
        if _heading_like(line) or _TABLE.match(line):
            # A heading resets the zone scope even when it names no zone:
            # the table it opens is a new set of columns, and inheriting the
            # last table's would attribute its rows to whatever came before.
            scoped = _names_zone(line, zone)
            columns = {}
            # A caption is not always the header: Portland prints the table
            # number, then its title, then the columns. Three lines of grace,
            # and the first that names zones in cells wins.
            header_window = 3 if _TABLE.match(line) else 0
        elif header_window and not columns:
            header_window -= 1
            columns = _columns(raw, siblings)

        if columns.get(zone) and _ROW.match(line):
            cell = _cell_at(raw, columns[zone])
            if _CELL_YES.match(cell):
                out.append((f"{path}#L{n}", line[:200], "anchored", cell))
            elif _CELL_NO.match(cell):
                out.append((f"{path}#L{n}", line[:200], "contradicted", cell))
            continue
        if _NEGATED.search(line) or _ABOUT_SOMETHING_ELSE.search(line):
            continue
        if not _ALLOWS.search(line):
            continue
        named = _TYPE.search(line) or _BROADER.search(line)
        if named is None:
            continue
        # Rows under a header were answered above, by column. What is left is
        # prose: a sentence granting the permission in words, which is scoped
        # by the section it sits in or by a heading naming the zone — never by
        # a table header, whose columns say nothing about the paragraph printed
        # beneath the grid.
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
                text,
                path=path,
                zone=code,
                claimed=claimed,
                spaced=spaced,
                siblings=sorted(layer.zones),
            ):
                out.append(Found(layer.layer, code, quote, line, strength, named))
    return out


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
                near = [f for f in found if f.zone == code]
                against = [f for f in near if f.strength == "contradicted"]
                loose = [f for f in near if f.strength == "loose"]
                if against:
                    # Louder than a gap, because it is not one. The file says
                    # the fourplex is allowed and the table it should have been
                    # read from says it is not, and until somebody settles that
                    # the zone is worse than unencoded.
                    print(f"  {code:14} !! table says {against[0].named!r} — {against[0].quote}")
                    continue
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
