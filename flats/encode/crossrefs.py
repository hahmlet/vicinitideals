"""Code we know exists and have never fetched.

Every other check in this system reasons about documents in the store. This one
reasons about the documents they *point at*. A code chapter is not a self-
contained statement of anything: it says "subject to the standards of Section
7.0420", "except as provided in Chapter 52", "see TDC 36.410", and each of
those is a sentence that can change a number without appearing anywhere near
it.

Gresham is why this exists. Its rear setbacks were read from Table 4.0130 in
the residential chapter, and the sentence that makes a 26 ft building stand
five feet further back lives in 7.0420, a *design standards* chapter nothing in
the encoding cited. It was found by reading, a year late, across roughly 21,000
lots. Nothing reported it, because every check in the system started from a
document we held, and that document was not held.

So the question here is the one nobody was asking: **which sections do our own
documents reference that we cannot open?**

Resolution is deliberately generous. A reference resolves if any document held
for that jurisdiction prints a heading for it -- codes are extracted with
section numbers at the start of a line, and a whole-title fetch (Oregon City's
Title 17 is one file, Wilsonville's Chapter 4 is another) answers for every
section inside it. What survives is a reference to text that is genuinely not
in the store.

Three rankings, and the last is the one to work from:

``mentions``
    How many times the corpus points at it. A chapter referenced twenty times
    is load-bearing somewhere.
``binding``
    The reference stands within a few lines of text an encoded value was read
    from. That is the Gresham shape exactly -- a standard and, beside it, a
    pointer to the rule that qualifies it. These are not "chapters we might
    want"; they are chapters that qualify numbers this screen is using now.
``fields``
    *Which* numbers, named. Proximity alone cannot tell a design chapter that
    moves a setback from a use table's "Signs -- see Chapter 19.170", and
    those two are the same row under ``binding``: both stand a line from an
    encoded value. Fairview's queue opened on five references to home
    occupations, wireless towers, signs and day care providers, every one of
    them flagged binding, and the ledger had no way to say why they were not
    worth a fetch.

    A reference standing beside a standard that carries a *distance* -- a
    setback, a height, a lot area, anything the fit has slack against -- ranks
    above one standing beside a use permission, because that is what a missed
    chapter eats into. ``FieldDef.has_slack`` already draws that line for the
    scoring code and it is the same line here.

State law (ORS, OAR) is counted separately. It is a different fetch problem
with a different source, and mixing it in would bury a city's own missing
chapter under a hundred boilerplate statutory references.

A reference can also leave this queue without being fetched, and that outcome
needs recording or the queue lies. Gladstone's 17.62.070 was the loudest
reference in the corpus — ten mentions, every one of them beside a number this
screen uses — and all ten are one sentence spanned by ``rowspan`` over ten
table cells: setbacks for manufactured homes in a mobile home park. Reading it
settles it, and nothing in a ledger built on "is the chapter in the store"
could ever see that. So a jurisdiction file may record a ruling::

    crossrefs:
      "17.62.070": >-
        Setbacks for manufactured homes in a mobile home park — neither the
        building nor the tenure this screen places.

A ruling may also carry the *shape* of the decision -- ``other_building``,
``narrows_only``, ``procedure``, ``preempted``, and two that do not close the
row: ``fetch`` is work ordered and ``later`` is work deferred. Closed rows sort
to the bottom and are printed under their own heading rather than hidden; an
ordered one stays in the queue with its note attached, because a decision to
go and read something is not a disposal of it.

Rulings are checked the other way too: a ruling on a reference the corpus no
longer makes is reported as stale, because the chapter was fetched or the
sentence was amended away and either way the note has moved.

Run it::

    uv run python -m flats.encode.crossrefs
    uv run python -m flats.encode.crossrefs or/clackamas/tualatin
    uv run python -m flats.encode.crossrefs --binding
    uv run python -m flats.encode.crossrefs --slack
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from flats.provenance.store import ProvenanceStore, parse_quote
from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.model import Layer

#: Where the ledger is written, beside the coverage ledger it complements.
LEDGER = Path(__file__).resolve().parents[2] / "data" / "flats" / "crossrefs.csv"

#: How near an encoded citation a reference must stand to count as binding.
#: Wider than a line because a table's "Additional Standards" column and the
#: row it qualifies are printed several lines apart, and narrower than a page
#: because a reference in the next section is about the next section.
BINDING_WINDOW = 12

#: A section number, with the suffix letter some codes append (Tualatin's
#: Chapter 73A). The letter must end the token — "40.220LOW DENSITY" is table
#: text that lost its space in extraction, not section 40.220L.
_NUM = r"\d[\d.\-]*\d(?:[A-Z](?![A-Za-z]))?|\d(?:[A-Z](?![A-Za-z]))?"
_REF = re.compile(
    #: Three ways a document points somewhere else, and they need different
    #: strictness.
    #:
    #: A spelled-out word may take a bare number: "Chapter 35" is a reference
    #: and there is nothing else it could be.
    rf"(?:(?:Chapters?|Sections?|Subsections?|Titles?|Articles?|Divisions?)"
    rf"\s+(?P<named>{_NUM})"
    #: A city's own abbreviation may not. Every city invents one (TDC, CDC,
    #: FMC, MCC, PCC, GDC) so they are matched generically — and generically
    #: also matches a zone code, which in an extracted table sits directly in
    #: front of a number: "MDR-12, OFR   10 ft." is not a reference to Section
    #: 10. Requiring a dot in the number is what separates the two, because a
    #: section number has one and a table cell does not. ORS and OAR are
    #: excluded here and counted by :func:`state_law`.
    #: The chapter may carry a letter — "TDC 73A.170" — and without it the
    #: whole reference went unread rather than being read loosely: the abbrev
    #: branch failed at the "A", and the other two branches want a keyword or
    #: three dotted groups. Tualatin's accessory-dwelling standards were cited
    #: twice in a held document and appeared in no ledger at all. The letter
    #: must end the chapter token, which is the same rule the named branch
    #: uses and the reason "40.220LOW DENSITY" is still not section 40.220L.
    r"|(?<![A-Za-z])(?!ORS\b|OAR\b)[A-Z]{2,4}\b\s+"
    r"(?P<abbrev>\d+(?:[A-Z](?![A-Za-z]))?\.[\d.\-]*\d)"
    #: And a number with three dotted groups needs no introduction at all — a
    #: decimal never has two dots, and a section number often does.
    r"|(?<![\d.])(?P<dotted>\d+\.\d+\.\d+[\d.]*))"
)
#: State law, counted apart from a city's own chapters.
_STATE = re.compile(r"\b(?:ORS|OAR)\s+(?P<num>[\d][\d.\-]*)")
#: A section heading: the number that opens a line. Extraction puts them there
#: in every document in this store, whether the code prints "17.02.010" or
#: "Section 4.137." or a bare "7.0420" in a contents block.
#: A leading abbreviation is part of the heading in several codes -- Tualatin
#: prints "TDC 40.300. Development Standards." as the section's own title, and
#: reading only line-initial digits would report a city's own chapters as
#: unfetched.
#:
#: So is a section symbol, and missing it is worse than missing an
#: abbreviation. Four jurisdictions print every heading in the form
#: "SECTION-SIGN 19.302.4. Development Standards." — 837 lines across
#: Wilsonville, unincorporated Multnomah, Lake Oswego and Milwaukie — and
#: without it a city reports its own fetched chapters as missing. Milwaukie led
#: the first ledger with 123 binding hits on sections printed in the document
#: the references were read from.
_HEADING = re.compile(
    r"^\s*(?:§\s*)?(?:(?:Section|Chapter)\s+|[A-Z]{2,5}\s+)?"
    r"(?P<num>\d[\d.\-]*\d(?:[A-Z](?![A-Za-z]))?|\d(?:[A-Z](?![A-Za-z]))?)\b"
)

#: A line that begins with a number is not a heading when the line before
#: it ended in the middle of a reference. Extraction wraps a citation across
#: the column edge -- "...standards of Chapter" / "33.248, Landscaping and
#: Screening" -- and the second line looks exactly like a heading: a section
#: number, a comma, a title. Read as one it says the store holds 33.248, and
#: the chapter drops out of this queue without anybody ruling on it.
#:
#: Portland is why. Its whole code is Title 33, so the ownership test below
#: (first dotted component) admits every 33.x number in every one of its
#: files, and twenty references -- Conditional Uses, Measurements,
#: Landscaping and Screening among them -- answered for themselves off a
#: wrapped line. Ownership separates chapters from each other; it cannot
#: separate a chapter from its own siblings, and this is what does.
_WRAPPED = re.compile(
    r"\b(?:Chapters?|Sections?|Subsections?|Titles?|Articles?|Divisions?"
    r"|of|in|by|to|under|with|see|per|and|through)\s*[,;]?$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class Dangling:
    """One reference this corpus makes and cannot follow."""

    layer: str
    ref: str
    mentions: int
    binding: int
    #: Where it is written, most-referenced document first.
    sources: tuple[str, ...]
    #: One line of context, so the row can be judged without opening anything.
    sample: str
    #: Why this reference was read and does not reach this building, where the
    #: jurisdiction file records a ruling on it. Empty means nobody has looked.
    ruling: str = ""
    #: The encoded standards this reference stands beside, most-often first.
    #: ``like`` where the nearby citation is a zone borrowing another's rules
    #: rather than a field of its own.
    fields: tuple[str, ...] = ()

    @property
    def outcome(self) -> str:
        """The shape of the decision, where one was recorded."""
        return getattr(self.ruling, "outcome", "read") if self.ruling else ""

    @property
    def ruled(self) -> bool:
        """Whether the row is closed, which is not the same as ruled on.

        ``fetch`` is work ordered and ``later`` is work deferred, and the
        vocabulary has said so since it was written -- ``CROSSREF_CLOSED``
        excludes both, and the review queue honours it. This ledger did not,
        so the first ordered fetch anybody recorded sorted to the bottom under
        a heading reading "read, and about somebody else's building". A
        decision is not a disposal.
        """
        return bool(self.ruling) and getattr(self.ruling, "closed", True)

    @property
    def slack_fields(self) -> tuple[str, ...]:
        """Of those standards, the ones a missed chapter could move.

        A boolean is settled or it is not -- reading a chapter cannot make a
        prohibited use slightly more prohibited -- so a reference sitting in a
        use table is a different kind of finding from one sitting beside a
        setback, however adjacent both are.
        """
        return tuple(f for f in self.fields if f in FIELDS and FIELDS[f].has_slack)

    @property
    def rank(self) -> tuple[int, int, int]:
        """How far up the queue this sits.

        A ruled reference ranks at the bottom whatever its counts, which is
        the whole point of recording the ruling: Gladstone's 17.62.070 is ten
        mentions and ten binding hits of one settled sentence, and left at the
        top it is the first thing anybody working this queue sees.
        """
        if self.ruled:
            return (0, 0, 0)
        return (len(self.slack_fields), self.binding, self.mentions)


#: A code's own abbreviation, where the filename opens with one. Clackamas
#: County's zoning ordinance is ``zdo.1012.txt`` and Rivergrove's is
#: ``rldo.composite.txt``; lowercase and short, which is what separates them
#: from ``residential`` or ``definitions`` further along the stem.
_ABBREV = re.compile(r"[a-z]{2,5}")


def _doc_ids(paths: Iterable[str]) -> set[str]:
    """The section numbers a filename claims to hold.

    ``40-41.residential`` holds two chapters, ``7.0400.middle-housing-design``
    holds one, and ``4.planning`` holds all of Chapter 4. Read off the leading
    numeric part of the stem, because that is the convention every document in
    the store was named under.

    The abbreviation may come first, and stopping at it is expensive. Four
    Clackamas County documents are named for their ordinance rather than their
    chapter, and reading only line-initial digits gave them no sections at all
    — so the county's own Section 1012, fifteen mentions and the loudest
    reference in that layer, led this queue while sitting in the store. A
    document that claims nothing also proves nothing, which is why
    :func:`dangling` has to treat that case separately rather than trusting it.
    """
    ids: set[str] = set()
    for path in paths:
        stem = Path(path).stem
        parts = stem.split(".")
        if parts and _ABBREV.fullmatch(parts[0]):
            parts = parts[1:]
        lead = []
        for part in parts:
            # A trailing letter belongs to the chapter: Tualatin's design
            # standards are Chapter 73A and its condominium rules are 73C, and
            # a reader that stopped at the first non-digit gave that document
            # no sections at all — it claimed nothing and the chapter it held
            # went on reporting as unfetched.
            if not re.fullmatch(r"\d[\d\-]*[A-Z]?", part):
                break
            lead.append(part)
        if not lead:
            continue
        ids |= _spanned(".".join(lead))
    return ids


def _spanned(head: str) -> set[str]:
    """The sections a hyphenated name covers, in whichever group it is in.

    ``40-41`` is two chapters and ``73A.020-060`` is a span within one, and a
    document that names a span answers for everything inside it. The range
    read only in the first group before, so ``36.400-420`` claimed a section
    number that does not exist and answered for none of the three it held.
    """
    groups = head.split(".")
    for i, group in enumerate(groups):
        lo, sep, hi = group.partition("-")
        if not sep or not (lo.isdigit() and hi.isdigit()) or int(lo) > int(hi):
            continue
        # Width preserved: this code prints 73A.030, and 73A.30 is a section
        # of some other city's code.
        wide = len(lo) if lo.startswith("0") else 0
        return {
            ".".join(groups[:i] + [f"{n:0{wide}d}" if wide else str(n)] + groups[i + 1 :])
            for n in range(int(lo), int(hi) + 1)
        }
    return {head}


def _headings(
    text: str, owns: set[str] | None, own_ids: Iterable[str] = ()
) -> set[str]:
    """Section numbers this document prints at the start of a line and owns.

    The ownership test is what keeps a cross-reference from being read as a
    heading. Extracted table text wraps, and Tualatin's residential chapter
    prints a bare ``TDC 36.410.`` at the start of eight lines — every one of
    them a pointer to a chapter this store does not hold. Taken as headings
    they answer for themselves, and the single reference most worth chasing in
    that city reports as fetched.

    So a heading has to belong here: its first dotted component must match the
    document's own. A chapter file answers for every section inside it, which
    is what makes a whole-title fetch work, and answers for nothing outside it,
    which is what makes this check work at all.

    ``owns=None`` is the one document that cannot be asked: a whole code in a
    single file, named for the ordinance and not for any chapter of it.
    Rivergrove's is 3.x, 5.x and 6.x together and there is no chapter it does
    not hold, so refusing it ownership reported its own sections as unfetched.
    It keeps the wrapped-line guard, which is the part that was actually doing
    the work — ownership only ever short-circuited that guard for a document's
    own children.
    """
    mine = tuple(own_ids)
    found: set[str] = set()
    prev = ""
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            num = m.group("num").rstrip(".")
            if (owns is None or num.partition(".")[0] in owns) and (
                # A number under this document's own id is a heading whatever
                # precedes it: 33.110.250 in 33.110.txt is not a wrap, and the
                # sections of a held chapter resolve on nothing else.
                any(num == own or num.startswith(f"{own}.") for own in mine)
                or not (prev and _WRAPPED.search(prev.rstrip()))
            ):
                found.add(num)
        if line.strip():
            prev = line
    return found


def _resolves(ref: str, ids: set[str], headings: set[str]) -> bool:
    """Whether some held document answers for this reference.

    Generous on purpose. A whole-title fetch answers for every section inside
    it, so a reference resolves when a document *claims* the chapter and the
    number is printed in it, or when any document prints the number at all --
    and a bare chapter reference resolves when we hold anything under it.
    """
    if ref in headings or ref in ids:
        return True
    # "Chapter 52" against a store holding 52.010, 52.020, ...
    return any(h.startswith(f"{ref}.") for h in headings) or any(
        i == ref or i.startswith(f"{ref}.") for i in ids
    )


#: Stands in for a field name where the nearby citation is a zone that borrows
#: another zone's rules. It is a real citation and it belongs in the window,
#: but it names no standard, so it can never make a reference rank as though a
#: dimension were at stake.
LIKE = "like"


def _cited_lines(layer: Layer) -> dict[str, dict[int, set[str]]]:
    """Per document, every line an encoded value was read from, and which one.

    The field name is the whole point. A reference twelve lines from *some*
    citation is a coincidence waiting to be judged; a reference twelve lines
    from ``setback_rear_ft`` is the Gresham sentence.
    """
    lines: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))

    def take(quote: str | None, name: str) -> None:
        if not quote:
            return
        try:
            ref = parse_quote(quote)
        except Exception:
            return
        for n in ref.numbers:
            lines[ref.path][n].add(name)

    for name, value in layer.defaults.items():
        take(value.prov.quote, name)
    for zone in layer.zones.values():
        if zone.like is not None:
            take(zone.like.prov.quote, LIKE)
        for name, value in zone.values.items():
            take(value.prov.quote, name)
            take(value.step_back_quote, name)
            take(value.measured_on_quote, name)
            take(value.qualified_quote, name)
            for variant in value.variants:
                take(variant.prov.quote, name)
    return lines


def _near(line: int, cited: dict[int, set[str]]) -> set[str]:
    """The encoded standards whose citations this line stands within reach of."""
    found: set[str] = set()
    for cite, names in cited.items():
        if abs(line - cite) <= BINDING_WINDOW:
            found |= names
    return found


def dangling(layer: Layer, store: ProvenanceStore | None = None) -> list[Dangling]:
    """Every reference this layer's documents make that the store cannot open."""
    store = store or ProvenanceStore()
    prefix = f"{layer.layer}/"
    paths = [p for p in store.documents() if p.startswith(prefix)]
    if not paths:
        return []

    texts = {p: store.text_path(p).read_text(encoding="utf-8") for p in paths}
    ids = _doc_ids(paths)
    headings: set[str] = set()
    for path, text in texts.items():
        own = _doc_ids([path])
        owns = {i.partition(".")[0] for i in own} if own else None
        headings |= _headings(text, owns, own)
    cited = _cited_lines(layer)

    mentions: dict[str, int] = defaultdict(int)
    binding: dict[str, int] = defaultdict(int)
    beside: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sources: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sample: dict[str, str] = {}

    for path, text in texts.items():
        here = cited.get(path, {})
        for n, line in enumerate(text.splitlines(), start=1):
            for m in _REF.finditer(line):
                ref = (
                    m.group("named") or m.group("abbrev") or m.group("dotted")
                ).rstrip(".")
                if not ref or ref.isdigit() and len(ref) < 2:
                    continue
                if _resolves(ref, ids, headings):
                    continue
                mentions[ref] += 1
                sources[ref][Path(path).name] += 1
                near = _near(n, here)
                if near:
                    binding[ref] += 1
                    for name in near:
                        beside[ref][name] += 1
                sample.setdefault(ref, line.strip()[:160])

    out = [
        Dangling(
            layer=layer.layer,
            ref=ref,
            mentions=count,
            binding=binding[ref],
            sources=tuple(
                name
                for name, _ in sorted(
                    sources[ref].items(), key=lambda kv: (-kv[1], kv[0])
                )
            ),
            sample=sample[ref],
            ruling=layer.crossrefs.get(ref, ""),
            fields=tuple(
                name
                for name, _ in sorted(
                    beside[ref].items(), key=lambda kv: (-kv[1], kv[0])
                )
            ),
        )
        for ref, count in mentions.items()
    ]
    out.sort(key=lambda d: (tuple(-n for n in d.rank), d.ref))
    return out


def stale_rulings(layer: Layer, store: ProvenanceStore | None = None) -> list[str]:
    """Rulings on references this layer's documents no longer make.

    Two ways that happens and both want reporting. The chapter was fetched, so
    the ruling is a settled question about a document we now hold and the note
    belongs beside the values instead; or the document that made the reference
    was re-fetched and the sentence is gone, in which case the ruling is
    describing a code that has been amended.

    A ruling nobody can see is the same fault as a citation nobody can follow.
    """
    live = {d.ref for d in dangling(layer, store)}
    return sorted(ref for ref in layer.crossrefs if ref not in live)


def state_law(layer: Layer, store: ProvenanceStore | None = None) -> dict[str, int]:
    """ORS and OAR references, counted apart from a city's own chapters."""
    store = store or ProvenanceStore()
    prefix = f"{layer.layer}/"
    counts: dict[str, int] = defaultdict(int)
    held = {Path(p).stem for p in store.documents() if p.startswith("or/")}
    for path in store.documents():
        if not path.startswith(prefix):
            continue
        text = store.text_path(path).read_text(encoding="utf-8")
        for m in _STATE.finditer(text):
            num = m.group("num").rstrip(".")
            if not any(stem.endswith(num) for stem in held):
                counts[num] += 1
    return dict(counts)


def survey(
    layers: Sequence[Layer] | None = None, store: ProvenanceStore | None = None
) -> list[Dangling]:
    store = store or ProvenanceStore()
    chosen = layers if layers is not None else list(load_rules().values())
    rows: list[Dangling] = []
    for layer in chosen:
        rows.extend(dangling(layer, store))
    rows.sort(key=lambda d: (tuple(-n for n in d.rank), d.layer, d.ref))
    return rows


def write(rows: Sequence[Dangling], path: Path | None = None) -> Path:
    file = path or LEDGER
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("w", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh)
        out.writerow(
            [
                "layer",
                "ref",
                "mentions",
                "binding",
                "outcome",
                "fields",
                "slack_fields",
                "sources",
                "sample",
                "ruling",
            ]
        )
        for row in rows:
            out.writerow(
                [
                    row.layer,
                    row.ref,
                    row.mentions,
                    row.binding,
                    row.outcome,
                    " ".join(row.fields),
                    " ".join(row.slack_fields),
                    " ".join(row.sources),
                    row.sample,
                    row.ruling,
                ]
            )
    return file


def _beside(row: Dangling) -> str:
    """The standards a reference stands beside, named for a reader.

    Slack-carrying ones first and marked, because the order of this line is
    the finding: "beside front setback, max. height" is a chapter to fetch,
    and "beside fourplex allowed" is a use table pointing at its own footnote.
    """
    if not row.fields:
        return ""
    slack = set(row.slack_fields)
    ordered = [f for f in row.fields if f in slack] + [
        f for f in row.fields if f not in slack
    ]
    named = [FIELDS[f].shown if f in FIELDS else f for f in ordered[:3]]
    more = f" +{len(ordered) - 3}" if len(ordered) > 3 else ""
    mark = "!" if slack else "-"
    return f"  {mark} beside: {', '.join(named)}{more}"


def render(
    rows: Sequence[Dangling], *, binding_only: bool = False, slack_only: bool = False
) -> Iterator[str]:
    ruled = [r for r in rows if r.ruled]
    open_rows = [r for r in rows if not r.ruled]
    shown = open_rows
    if slack_only:
        shown = [r for r in shown if r.slack_fields]
    elif binding_only:
        shown = [r for r in shown if r.binding]
    if not shown:
        yield "no unfetched references — every section this corpus points at is in the store"
        return

    by_layer: dict[str, list[Dangling]] = defaultdict(list)
    for row in shown:
        by_layer[row.layer].append(row)

    total_binding = sum(1 for r in shown if r.binding)
    total_slack = sum(1 for r in shown if r.slack_fields)
    yield (
        f"{len(shown)} unfetched reference(s) across {len(by_layer)} jurisdiction(s)"
        f" — {total_binding} standing beside a number this screen uses,"
        f" {total_slack} of them beside one that carries a distance"
    )
    yield ""
    for layer in sorted(by_layer, key=lambda l: (-max(r.rank for r in by_layer[l])[0], l)):
        group = by_layer[layer]
        yield f"  {layer}   ({sum(r.mentions for r in group)} mention(s))"
        for row in group[:12]:
            mark = f"BINDING x{row.binding}" if row.binding else ""
            yield f"    {row.ref:<14} {row.mentions:>3} mention(s)  {mark}{_beside(row)}"
            if row.outcome:
                yield f"       {row.outcome.upper()}: {row.ruling[:120]}"
            yield f"       in {row.sources[0]}: {row.sample}"
        if len(group) > 12:
            yield f"    ... and {len(group) - 12} more"
        yield ""

    if ruled:
        # Kept in the output rather than filtered away. A queue that silently
        # dropped rows would be as untrustworthy as one that never dropped
        # any: the reader has to be able to see what was ruled and disagree.
        yield f"  closed — read, and about somebody else's building ({len(ruled)})"
        for row in sorted(ruled, key=lambda r: (r.layer, r.ref)):
            yield f"    {row.layer} {row.ref:<14} x{row.mentions}  [{row.outcome}] {row.ruling[:88]}"
        yield ""


def main(argv: Sequence[str] | None = None) -> int:
    # Code documents carry ligatures and dashes a Windows console cannot
    # encode, and a ledger that crashes on a sample line is a ledger nobody
    # runs. The CSV keeps the characters; the terminal gets what it can print.
    if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover
        sys.stdout.reconfigure(errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    binding_only = "--binding" in args
    slack_only = "--slack" in args
    args = [a for a in args if not a.startswith("--")]

    layers = load_rules()
    chosen = [layers[a.strip("/")] for a in args] if args else list(layers.values())
    rows = survey(chosen)
    for line in render(rows, binding_only=binding_only, slack_only=slack_only):
        print(line)

    for layer in chosen:
        for ref in stale_rulings(layer):
            print(f"  STALE RULING  {layer.layer} {ref}: nothing points at it any more")

    if not args:
        print(f"\nwritten -> {write(rows)}")
        for layer in chosen:
            state = state_law(layer)
            if state:
                top = sorted(state.items(), key=lambda kv: -kv[1])[:4]
                named = ", ".join(f"{n} x{c}" for n, c in top)
                print(f"  state law unfetched  {layer.layer}: {named}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
