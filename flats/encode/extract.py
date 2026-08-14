"""Reading a stored ordinance into clauses and candidate values.

Extraction proposes; a human disposes. Nothing here can produce a trusted
number — every candidate lands as ``draft`` with a quote pointing at the line
it came from, and a reviewer either signs it or does not. That division is the
whole reason this file is allowed to use heuristics at all.

Two outputs, because they answer different questions.

*Clauses* answer "have we read all of it?" Every line of the section is tagged
RASE — applicability, selection, requirement, exception, non-normative — and a
section is complete when nothing is untagged and every requirement resolved to
a value. An exception nobody noticed is the failure mode that produces a
confident wrong answer, so an untagged sentence is a gap, not a shrug.

*Candidates* answer "what number does it say?" A phrase like "the minimum front
building setback is 10 feet" becomes ``setback_front_ft: 10`` with its line
quoted. When a section states two different numbers for the same field —
common, because codes qualify by lot size or corner status — both are emitted
and marked in conflict. Picking one silently is how a screen ends up confidently
wrong across a whole zone, so the tool refuses to pick.

Run::

    python -m flats.encode.extract or/multnomah/portland/33.110.txt --zone R5
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence

from flats.provenance.store import ProvenanceStore
from flats.rules.fields import FIELDS, field
from flats.rules.ledger import Clause, Rase

#: Bumped when the patterns change — extraction output is reproducible, and a
#: candidate set that moved because the harness changed is not new evidence.
EXTRACTOR = "flats-rase/1"

_NUM = r"(?P<n>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"

#: Phrase → field. Ordered: the first match on a line wins, so the more
#: specific phrasings are listed before the ones that would swallow them.
_SUBJECTS: tuple[tuple[str, str], ...] = (
    (r"street[ -]side (?:building )?setback", "setback_street_side_ft"),
    # The corner-lot phrasings of the same standard — "Side Setback on a
    # Corner Lot", "Side Setback (corner lot)", "corner side setback",
    # "exterior side setback". Listed before the plain side pattern because
    # both match at the same offset and the tie goes to the earlier entry.
    (
        r"side (?:building |yard )?setback (?:on|of|for) a corner lot"
        r"|side (?:building |yard )?setback \(corner lot\)"
        r"|(?:corner|exterior)[ -]side (?:building |yard )?setback",
        "setback_street_side_ft",
    ),
    (r"(?:maximum|max\.?) front (?:building )?setback", "setback_front_max_ft"),
    (r"garage (?:entrance|door)", "setback_garage_entrance_ft"),
    (r"front (?:building |yard )?setback", "setback_front_ft"),
    (r"(?:interior )?side (?:building |yard )?setback", "setback_side_ft"),
    (r"rear (?:building |yard )?setback", "setback_rear_ft"),
    # "average lot size" is a purpose statement — Springwater's VLDR preamble
    # describes character at "an average lot size of 12,000 square feet" —
    # not a minimum anybody may hold a permit to.
    (r"(?<!average )lot (?:area|size)", "min_lot_sqft"),
    # "Width at building line" is Gresham's name for lot width — the heading
    # "E. Minimum Lot Width" is real but its sub-headings replace it as the
    # group, and they say "1. Width at building line: Interior lot" instead.
    (r"lot width|width at building line", "min_lot_width_ft"),
    # Qualified on purpose: bare "frontage" is a unit of counting in driveway
    # rules — "approaches must not exceed 32 feet per frontage" — and the
    # driveway width lands as a frontage standard on every zone in the
    # chapter.
    (r"(?:lot|street|minimum) frontage|frontage of at least", "min_frontage_ft"),
    (r"(?:building )?height", "max_height_ft"),
    (r"floor area ratio|\bFAR\b", "max_far"),
    (r"(?:building|lot|site) coverage", "max_coverage_pct"),
    (r"outdoor area|open space", "open_space_min_pct"),
    (r"parking spaces?|off-street parking", "parking_min_per_unit"),
    (r"dwelling units?|units", "max_units"),
)

#: Unit → the field kinds a number in those units can legitimately fill.
_UNITS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"square feet|sq\.? ?ft\.?", ("area_sqft",)),
    (r"percent|%", ("percent",)),
    (r"feet|foot|ft\.?", ("length_ft",)),
    (r"spaces? per (?:dwelling )?unit|per unit", ("ratio",)),
    (r"units", ("count",)),
)

_EXCEPTION = re.compile(
    r"\b(except|unless|notwithstanding|does not apply|shall not apply|exempt"
    # Relief provisions are exceptions in everything but the word. Portland's
    # "the front building setback may be reduced to 10 feet" states a number
    # that is not the standard, and reading it as one understates the setback
    # on every lot in the zone.
    # "shall not be employed where ..." — Gresham's zero-lot-line side yard
    # provision. The clause prohibits a special setback and then states the
    # 5-foot fallback for when it cannot be used; neither number is the base
    # standard, and reading the fallback as one contradicts every zone whose
    # real side setback is larger.
    # "may be permitted" is the same family — Springwater's "the maximum
    # front or street side setback of up to 20 feet may be permitted when
    # enhanced pedestrian spaces are provided" grants relief, not a standard.
    r"|may be reduced|is reduced|may extend|is lowered|is allowed if|may be increased"
    r"|may be permitted|shall not be employed)\b",
    re.I,
)
#: An outline heading that puts everything under it in exception scope.
_EXCEPTION_HEADING = re.compile(r"\b(exceptions?|adjustments?|reductions?|special situations)\b", re.I)
#: A top-level outline marker: "A.", "B." — where a heading's scope begins and ends.
_TOP_LEVEL = re.compile(r"^[A-Z]\.\s")
_REQUIREMENT = re.compile(
    r"\b(shall|must|may not|no .{0,40} shall|required|minimum|maximum|at least|no more than)\b",
    re.I,
)
_SELECTION = re.compile(
    # "in zones with ..." selects by a property of the zone — Troutdale keys
    # its parking minimums to lot-size classes that way, and the thresholds
    # are not lot-size standards.
    r"\b(corner lot|through lot|flag lot|abut(?:s|ting)|adjacent to|where the"
    r"|in (?:zones|districts) with)\b",
    re.I,
)
_APPLICABILITY = re.compile(
    r"\b(this (?:section|chapter) applies|applies to|in the .{1,30} zones?|are the standards)\b",
    re.I,
)
_DEFINITION = re.compile(r"\b(means|is defined as|for the purposes of|see (?:section|chapter))\b", re.I)
#: A section heading. The optional prefix is not cosmetic: Portland prints
#: "33.110.220 Development Standards", Wilsonville prints "Section  4.122.
#: Residential Zone", and Tualatin prints "TDC 40.100. Purpose" — the code's
#: own initials in front of every heading. Without the prefix every heading in
#: the second and third kinds of code goes unrecognised, which leaves every
#: paragraph attributed to whatever section was last seen — and section is
#: what binds a prose standard to a zone. The initials form is confined to
#: 2–4 capitals — case-sensitively, inside a pattern that is otherwise
#: case-insensitive — so a sentence starting "The 10.25 acre site" or
#: "and 40.100" never reads as a heading.
_SECTION = re.compile(
    # The second component runs to four digits for Gresham, which numbers
    # sections "4.0101" — three was the corpus maximum until it was not.
    r"^(?:(?:Sec(?:tion|\.)?|(?-i:[A-Z]{2,4}))\s+)?(?P<sec>\d{1,3}\.\d{2,4}(?:\.\d{1,4})?)\b", re.I
)
#: Cross-references, table and figure names. Their digits are addresses, not
#: sizes — "See Figures 110-2 and 110-3" contains no standard whatsoever.
_CITATION = re.compile(
    r"\b\d{1,3}\.\d{2,4}(?:\.\d{1,4})?\b"  # 33.110.265, 4.0130
    r"|\b(?:Table|Figure|Map)s?\s+\d+-\d+\b"  # Table 110-4
    r"|\b\d{1,3}-\d{1,3}\b",  # a bare hyphenated pair is an identifier
    re.I,
)
#: "stated in Table 110-4" — the standard is real, and its number lives
#: somewhere this harness cannot read.
_DEFERS = re.compile(r"\b(?:stated|listed|shown|set out|found) in Table\s+(?P<table>\d+-\d+)", re.I)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One proposed value, and exactly where it was read."""

    field: str
    value: float | int
    line: int
    text: str
    #: ``path#L12`` — what a reviewer will be shown beside the number.
    quote: str
    #: Another candidate proposes a different value for the same field.
    conflict: bool = False
    #: Where it was read: ``"prose"``, ``"table"``, or ``"pair"`` — a stacked
    #: label/value line pair, a table row that lost its geometry to HTML
    #: linearisation. Load-bearing, not a label: a table cell is written for
    #: one zone; a pair or a sentence is not, and counts only where a document
    #: or declared section binds it to one.
    source: str = "prose"
    #: Footnotes qualifying this number. A candidate with notes states a base
    #: case with an exit attached, not a standard, and must not be encoded as
    #: an unconditional value.
    notes: tuple[str, ...] = ()
    #: The code section this was read under — "4.122". Load-bearing for codes
    #: that state standards in prose per zone: the heading is the only thing
    #: saying whose setback this is.
    section: str = ""
    #: The housing type the row was written for — "townhouse", "duplex",
    #: "default" ("All other uses") — when the table stratifies a standard by
    #: type rather than stating one number per zone. Empty for ordinary rows.
    #: A typed value is not the zone's standard; it is one housing type's, and
    #: which type speaks for the pod is decided at selection, not here.
    housing_type: str = ""

    @property
    def conditional(self) -> bool:
        return bool(self.notes)

    @property
    def kind(self) -> str:
        return field(self.field).kind


@dataclass(frozen=True, slots=True)
class Extraction:
    """Everything read out of one document."""

    path: str
    clauses: tuple[Clause, ...] = ()
    candidates: tuple[Candidate, ...] = ()

    @property
    def untagged(self) -> tuple[Clause, ...]:
        return tuple(c for c in self.clauses if c.tag is None)

    @property
    def conflicted(self) -> tuple[str, ...]:
        return tuple(sorted({c.field for c in self.candidates if c.conflict}))

    @property
    def tables(self) -> tuple[str, ...]:
        """Tables the prose defers its numbers to.

        Portland states almost nothing in sentences: 33.110.220 says the
        setbacks "are stated in Table 110-4", and the table is a grid with one
        column per zone that flattens into unreadable text. Naming the table is
        the honest output — the alternative is reading a column belonging to
        some other zone and encoding it with confidence.
        """
        found = {m.group("table") for c in self.clauses if (m := _DEFERS.search(c.text))}
        return tuple(sorted(found))

    def unresolved(self) -> tuple[Clause, ...]:
        """Requirement clauses that produced no candidate value.

        Each is a rule the code states and the screen would otherwise ignore —
        the quiet failure that makes a lot look buildable when it is not.
        """
        lines = {c.line for c in self.candidates}
        return tuple(
            c
            for c in self.clauses
            if c.tag in (Rase.requirement, Rase.exception) and _line_of(c.quote) not in lines
        )

    def for_field(self, name: str) -> tuple[Candidate, ...]:
        return tuple(c for c in self.candidates if c.field == name)


def _line_of(quote: str) -> int:
    _, _, frag = quote.partition("#L")
    return int(frag.split("-")[0]) if frag else 0


def tag_of(text: str) -> Rase | None:
    """Best-effort RASE tag, or None when the sentence is unclear.

    None is a legitimate and frequent answer. A wrong tag hides a clause inside
    a category nobody re-reads; an absent one puts it on the queue.
    """
    if _EXCEPTION.search(text):
        return Rase.exception
    if _DEFINITION.search(text):
        return Rase.non_normative
    if _REQUIREMENT.search(text):
        return Rase.requirement
    if _APPLICABILITY.search(text):
        return Rase.applicability
    if _SELECTION.search(text):
        return Rase.selection
    return None


def states_a_rule(text: str) -> bool:
    """Whether a sentence states a base standard, rather than qualifying one.

    The asymmetry corroboration needs: a number in conditional text — "when a
    side or rear yard abuts a more restrictive zone, setbacks shall be 15 ft"
    — is real evidence that the number appears in the code, but it is not the
    zone's base standard, so it may corroborate an encoded value and must
    never contradict one. Only a clause that tags as a requirement with no
    selection keyword in it speaks with enough authority to disagree.
    """
    return tag_of(text) is Rase.requirement and not _SELECTION.search(text)


def _match_subject(text: str) -> tuple[int, int, str] | None:
    lowered = text.lower()
    best: tuple[int, int, str] | None = None
    for pattern, name in _SUBJECTS:
        m = re.search(pattern, lowered)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), m.end(), name)
    return best


def _subject(text: str) -> str | None:
    found = _match_subject(text)
    return found[2] if found else None


def _subject_span(text: str) -> tuple[int, int] | None:
    found = _match_subject(text)
    return (found[0], found[1]) if found else None


def _units_allow(text: str, kind: str) -> bool:
    lowered = text.lower()
    for pattern, kinds in _UNITS:
        if re.search(pattern, lowered):
            return kind in kinds
    return False


def _numbers(text: str, *, subject: tuple[int, int] | None = None) -> list[float]:
    """Numbers in the line, minus the ones that are addresses rather than sizes.

    Every false positive found on real Portland text came from here: a
    cross-reference to 33.110.275 reads as "33.11" and "275", and a chapter is
    dense with them. Citations, table and figure names are struck out first.

    Position then decides ownership. A standard states its number after the
    thing it governs — "the minimum front setback is 10 feet" — or immediately
    before it as a quantity — "2 parking spaces per unit". A number further
    back than that belongs to a different clause of the same sentence, which is
    how "cisterns that are 6 feet or less in height" becomes a 6-foot height
    limit for the entire zone.
    """
    scrubbed = _CITATION.sub(lambda m: " " * len(m.group(0)), text)
    start, end = subject if subject else (0, 0)
    return [
        float(m.group("n").replace(",", ""))
        for m in re.finditer(_NUM, scrubbed)
        if m.start() >= end or m.end() >= start - QUANTITY_LEAD
    ]


def candidates_in(text: str, line: int, path: str, *, quote: str = "") -> list[Candidate]:
    """Proposed values from one line of code text.

    Deliberately conservative, and every restriction here was earned on real
    text. A number is proposed only when the line names a subject this system
    has a field for, carries units that field could be measured in, and states
    the number *after* the subject — because standards read "the minimum front
    setback is 10 feet", while "cisterns that are 6 feet or less in height" is
    a sentence about cisterns that happens to end in the word height.

    Exceptions are never mined. A clause tagged E qualifies a standard rather
    than setting one, so a number inside it is the one case the rule does not
    apply to — precisely the value that must never end up encoded as the rule.
    """
    if tag_of(text) is Rase.exception:
        return []

    name = _subject(text)
    if name is None:
        return []
    if not _units_allow(text, FIELDS[name].kind):
        return []

    # A sentence that names its housing type states that type's standard,
    # not the zone's — "For townhouses the minimum lot size ... is 1,500
    # square feet" — and which type speaks for the pod is decided at
    # selection, exactly as for a typed table row. Imported here because
    # tables imports this module at load.
    from flats.encode.tables import _housing_type

    htype = _housing_type(text) or ""

    out: list[Candidate] = []
    for number in _numbers(text, subject=_subject_span(text)):
        value = int(number) if number.is_integer() else number
        out.append(
            Candidate(
                field=name,
                value=value,
                line=line,
                text=text.strip(),
                quote=quote or f"{path}#L{line}",
                housing_type=htype,
            )
        )
    return out


#: A line that opens a new clause: "A.", "1.", "a.", "(2)", a bullet, or a
#: section number. Codes are outlines, and the outline marker is the boundary.
_OPENER = re.compile(r"^(?:[A-Za-z]\.|\(?\d+\)|\d+\.|[•\-•▪]|\d{1,3}\.\d{2,3})\s")
#: What follows a section number in a real heading: optional punctuation, then
#: a word that starts a title — "Section 5.010.  Land Use", "40.210 Residential
#: Districts". A wrapped citation resumes lowercase or with a comma ("TDC
#: 36.410, or Greenway and"), a subsection address with a paren ("36.410(2)(b)"),
#: and a bare "TDC 36.410." with nothing at all — none of those name a section.
_HEADING_TEXT = re.compile(r"^[.:]?\s+[A-Z0-9]")


def _heading_like(line: str) -> bool:
    """Whether a line is a section heading rather than a citation to one.

    Load-bearing twice over: a heading opens a new paragraph, and it is the
    only thing allowed to move the section cursor. A wrapped citation taken
    for a heading does not just split a sentence — it mis-attributes every
    clause after it until the next real heading.
    """
    m = _SECTION.match(line)
    return bool(m) and bool(_HEADING_TEXT.match(line[m.end() :]))
#: Running page numbers like "110-14".
_PAGE_NUMBER = re.compile(r"^\d{2,3}-\d{1,3}$")
#: A line repeated this often across a document is a header or footer, not text.
FURNITURE_REPEATS = 3
#: A section line no longer than this is a heading, not the first sentence.
HEADING_WORDS = 8
#: How far before its subject a number may sit and still belong to it —
#: enough for "2 parking spaces", not enough for "6 feet or less in height".
QUANTITY_LEAD = 12


def _furniture(lines: Sequence[str]) -> set[str]:
    """Lines that are page decoration rather than ordinance.

    A chapter PDF stamps its title and revision date on all fifty pages, which
    lands in the middle of sentences and splits them. Frequency finds them
    without hard-coding any one codifier's layout.
    """
    counts: dict[str, int] = {}
    for line in lines:
        if line and len(line) < 80:
            counts[line] = counts.get(line, 0) + 1
    return {line for line, n in counts.items() if n >= FURNITURE_REPEATS}


def paragraphs(text: str) -> list[tuple[int, int, str]]:
    """Reassemble wrapped lines into clauses, as ``(first_line, last_line, text)``.

    A PDF breaks "the minimum front building setback is / 10 feet" across two
    lines, and reading each half as its own clause loses the standard entirely
    — the subject is on one line and the number on the other. Joining is what
    makes the sentence readable to both a tagger and a person.
    """
    lines = [line.strip() for line in text.splitlines()]
    junk = _furniture(lines)
    out: list[tuple[int, int, str]] = []
    start = 0
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            out.append((start, start + len(buffer) - 1, " ".join(buffer)))

    for n, line in enumerate(lines, start=1):
        if not line or line in junk or _PAGE_NUMBER.match(line):
            # Furniture does not end a sentence; it interrupts one. Skipping it
            # without flushing lets the sentence continue across the page break.
            continue
        # A line that begins "Section 5.010.  Land Use" starts a section,
        # whatever came before it — page furniture without terminal
        # punctuation otherwise glues itself to the heading, and the paragraph
        # then starts before the heading line, which mis-attributes every
        # candidate in it to the previous section.
        opens = bool(_OPENER.match(line)) or _heading_like(line)
        ends = buffer and buffer[-1].endswith((".", ";", ":"))
        if buffer and (opens or ends):
            flush()
            buffer, start = [], n
        if not buffer:
            start = n
        buffer.append(line)
        if _SECTION.match(line) and len(line.split()) <= HEADING_WORDS:
            # "33.110.220 Setbacks" carries no terminal period, so without this
            # the heading swallows the first sentence of its own section.
            flush()
            buffer = []
    flush()
    return out


def extract(
    text: str, *, path: str, jurisdiction: str = "", section: str = "", zone: str = ""
) -> Extraction:
    """Read a stored document into tagged clauses and candidate values.

    ``zone`` also reads the standards tables, which is where a code like
    Portland's states almost everything the prose defers to. It is a zone
    argument because a table row holds one value per zone and only the column
    written for this zone may be read.
    """
    # Imported here because the table reader is built on this module's subject
    # matching: prose and grid ask the same question of a label.
    from flats.encode.tables import (
        blank_tables,
        candidates_for,
        read_pairs,
        read_stacked_grids,
        read_tables,
        stacked_candidates_for,
    )

    clauses: list[Clause] = []
    proposed: list[Candidate] = []
    current = section

    in_exceptions = False

    for first, last, stripped in paragraphs(blank_tables(text)):
        n = first
        quote = f"{path}#L{first}" if first == last else f"{path}#L{first}-L{last}"
        found = _SECTION.match(stripped)
        if found and _heading_like(stripped):
            # Only a heading moves the section cursor. A paragraph that opens
            # on a wrapped citation — "TDC 36.410, or Greenway and ..." —
            # matches the section pattern too, and taking its number would
            # file everything until the next real heading under a
            # cross-reference.
            current = found.group("sec")
        if _TOP_LEVEL.match(stripped):
            # Codes are outlines, and scope is inherited. Everything under
            # "D. Exceptions to the required setbacks" qualifies the standard
            # rather than stating it, however plainly the sub-clause reads.
            in_exceptions = bool(_EXCEPTION_HEADING.search(stripped.split(".", 1)[1][:80]))

        tag = tag_of(stripped)
        if in_exceptions and tag in (Rase.requirement, None):
            tag = Rase.exception
        if tag is None and found and len(stripped.split()) <= 8:
            # A section heading states no rule. Leaving it untagged would put
            # every heading in the document on the review queue, which is the
            # fastest way to teach a reviewer to ignore the queue.
            tag = Rase.non_normative
        clauses.append(
            Clause(
                id=quote,
                jurisdiction=jurisdiction,
                section=current,
                quote=quote,
                text=stripped,
                tag=tag,
            )
        )
        if tag is not Rase.exception:
            proposed.extend(
                replace(candidate, section=current)
                for candidate in candidates_in(stripped, n, path, quote=quote)
            )

    if zone:
        for table in read_tables(text):
            proposed.extend(candidates_for(table, zone, path=path))
        proposed.extend(stacked_candidates_for(read_stacked_grids(text, path=path), zone))

    # Stacked label/value pairs — a table that lost its geometry to HTML
    # linearisation. Zone-blind like prose, so they carry their section and
    # count only where a declared section or a single-zone document binds them.
    proposed.extend(read_pairs(blank_tables(text), path=path))

    return Extraction(path=path, clauses=tuple(clauses), candidates=tuple(_mark(proposed)))


def _mark(candidates: Iterable[Candidate]) -> list[Candidate]:
    """Flag every field where the section states more than one distinct value."""
    values: dict[str, set[float]] = {}
    listed = list(candidates)
    for c in listed:
        values.setdefault(c.field, set()).add(float(c.value))
    # ``replace`` rather than a positional rebuild: the rebuild silently
    # dropped every field it did not name, which is how housing_type vanished
    # between the reader and the checker the day it was added.
    return [replace(c, conflict=len(values[c.field]) > 1) for c in listed]


def to_yaml(extraction: Extraction, *, zone: str, cite: str, url: str, retrieved: str) -> str:
    """Draft YAML for the zone — every value draft, every value quoted.

    Paste-ready but not paste-and-forget: conflicts are left in as comments
    rather than resolved, because which number applies is a reading question
    and this file has not read anything.
    """
    lines = [
        f"# {extraction.path} — extracted by {EXTRACTOR}, all values draft.",
        "# Each number below still has to be read against its quote and signed.",
        "cite_default:",
        f'  cite: "{cite}"',
        f'  url: "{url}"',
        f"  retrieved: {retrieved}",
        "zones:",
        f"  {zone}:",
    ]

    seen: set[str] = set()
    for c in sorted(extraction.candidates, key=lambda c: (c.field, c.line)):
        if c.conflict:
            lines.append(f"    # CONFLICT {c.field}: {c.value} — {c.text[:70]}")
            continue
        if c.field in seen:
            continue
        seen.add(c.field)
        lines.append(f"    {c.field}:")
        lines.append(f"      value: {c.value}")
        lines.append(f'      quote: "{c.quote}"')

    for clause in extraction.unresolved():
        lines.append(f"    # UNRESOLVED {clause.tag.name}: {clause.text[:70]}")
    for clause in extraction.untagged:
        lines.append(f"    # UNTAGGED: {clause.text[:70]}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flats-extract", description="Read a stored ordinance into draft values."
    )
    parser.add_argument("path", help="store path, e.g. or/multnomah/portland/33.110.txt")
    parser.add_argument("--zone", required=True)
    parser.add_argument("--jurisdiction", default="")
    parser.add_argument("--docs", type=Path, default=None)
    parser.add_argument("--cite", default="")
    parser.add_argument("--yaml", action="store_true", help="emit a draft zone block")
    args = parser.parse_args(argv)

    doc = ProvenanceStore(args.docs).load(args.path)
    extraction = extract(
        doc.text, path=args.path, jurisdiction=args.jurisdiction, zone=args.zone
    )

    if args.yaml:
        print(
            to_yaml(
                extraction,
                zone=args.zone,
                cite=args.cite or args.path,
                url=doc.url,
                retrieved=doc.retrieved.isoformat(),
            )
        )
        return 0

    print(f"{args.path}: {len(extraction.clauses)} clause(s), {len(extraction.candidates)} candidate(s)")
    for c in sorted(extraction.candidates, key=lambda c: (c.field, c.line)):
        mark = " CONFLICT" if c.conflict else ""
        print(f"  {c.field} = {c.value}{mark}  [{c.quote}] {c.text[:60]}")
    for clause in extraction.unresolved():
        print(f"  UNRESOLVED {clause.tag.name} [{clause.quote}] {clause.text[:60]}")
    for clause in extraction.untagged:
        print(f"  UNTAGGED [{clause.quote}] {clause.text[:60]}")
    if extraction.tables:
        # Which grids the prose sent its numbers to. Some were read; a table
        # this reader could not parse leaves the standard unencoded, and the
        # only way that shows up is here.
        print(f"  tables referenced: {', '.join(extraction.tables)}")
    # Untagged and unresolved clauses are work, not failure — but they are the
    # difference between "we read the section" and "we read some of it".
    return 1 if (extraction.untagged or extraction.unresolved() or extraction.conflicted) else 0


if __name__ == "__main__":
    raise SystemExit(main())
