"""Of the standards nobody read, which state a number we hold nowhere.

:mod:`flats.encode.uncited` produces the reading debt: every line in a document
we hold that states a measure and that no encoded value quotes. Its ``unread``
bucket is the sharp end -- a line naming a standard this system *has a field
for*, unquoted. There are about a thousand of them, and read end to end they
are unworkable, because almost all of them are the second column of a table
whose first column we took, or the same standard for a use we do not build.

The lever is arithmetic, and it is the one thing a machine can do here that a
person should not have to: **compare the number on the line against every
number this jurisdiction holds for that field.** A line stating 35 ft for a
height in a city that holds a 35 somewhere is bookkeeping -- our reader took it
off a different row of the same table. A line stating 24 ft for a height in a
city that holds no 24 for height in any zone is a number this corpus has never
seen, and that is either a zone we skipped, an exception nobody encoded, or a
use that is not ours. Two of those three are findings.

So this is **a sort, not a verdict**, and the distinction is load-bearing. An
``unheld`` row is not an error and most of them will close in seconds:

- it is the industrial column of a table we read the residential column of;
- it is a standard for a detached house, a duplex, a school;
- it is an accessory-structure limit, a fence, a sign;
- it is the same standard in a district this layer does not encode.

What it is *not* is invisible, which is what those lines are today. The
opposite error -- a standard we simply never took, sitting in a document we
have held for months -- looks exactly like the nine hundred lines around it,
and that is the failure this ledger is built to make findable. Milwaukie's side
yard height plane was found by hand; nothing was going to find the next one.

Three answers:

``unheld``      the line states a number, and this layer holds none like it for
                that field, in any zone. Read these.
``held``        some number on the line is one we already carry for that field
                somewhere. Bookkeeping -- the standard is in the corpus, on
                another row.
``unnumbered``  the line names a field and states no figure this can compare:
                a cross-reference, a prose condition, a bare exemption.

**What counts as a number is deliberately narrow.** Section numbers, ordinance
numbers, dashed OAR citations and the years in an amendment trail are masked
out before anything is read, and each field's *kind* supplies a plausibility
window -- a height of 40,000 is a floor area that wandered into the sentence,
not a height. Masking too much costs a row to ``unnumbered``, which is a queue
nobody has to work; masking too little costs a false alarm in the one queue
that is supposed to be worth reading.

**What counts as held is the figure a reader will find**, not the figure the
model uses: :func:`flats.encode.readiness._printed` already answers that
question for every derived form this project carries -- per-dwelling areas,
acreages, one-space-per-two-units rates -- and it is reused here rather than
re-derived, so a new form has one place to be taught, exactly as the citation
check does.

The sort is half the job. The other half is a blind reading of what it puts at
the top -- :func:`work_list` builds cards carrying the sentence and the page
around it and *not* the figure this corpus holds, and :func:`score` joins the
readings back. ``missed`` is the only answer that is a finding.

**The reading queue drops the cities the screen does not cover, and the ledger
does not.** That split is settled practice here, and the first run of this
queue is why it is worth stating twice: 26 of its 185 readings, and 8 of its 29
findings, were Lake Oswego and Rivergrove -- land nobody screens. A finding
there is a true statement about a code that decides nothing, and unlike a
marked row in a ranked feed it cannot be skipped past, because reading the card
*is* the work. So :func:`render` marks them and keeps counting them, and only
:func:`work_list` narrows; ``include_off`` puts them back for the day a city is
switched on.

Run it::

    uv run python -m flats.encode.missed
    uv run python -m flats.encode.missed or/clackamas/milwaukie
    uv run python -m flats.encode.missed --csv data/flats/missed.csv
    uv run python -m flats.encode.missed --out work/ --batch 25
    uv run python -m flats.encode.missed --out work/ --sections --context 2
    uv run python -m flats.encode.missed --score work/ --csv data/flats/read.csv
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Collection, Iterable, Sequence

from flats.encode.crossrefs import _cited_lines, _doc_ids
from flats.encode.reread import CONTEXT, _above, _passage
from flats.encode.readiness import _printed, _printed_variant
from flats.encode.triage import unscreened
from flats.encode.uncited import Uncited, _sections, survey
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.model import Layer

#: Spans that carry numbers which are never standards. Masked before any digit
#: is read, because one section number in a sentence is enough to make a line
#: look like it states a figure this layer has never held.
_MASKS: tuple[re.Pattern[str], ...] = (
    # "Section 19.301.4", "Table 4.0131", "§ 33.110", "Ord. 1234"
    re.compile(
        r"(?:§+\s*|\b(?:sections?|tables?|chapters?|figures?|subsections?|titles?"
        r"|exhibits?|appendix|ordinances?|ord|nos?|paragraphs?|items?|notes?"
        r"|maps?|policies|policy|charts?|columns?|rows?)\.?\s*)"
        r"[A-Za-z]?\d+(?:[.\-–—][\dA-Za-z]+)*",
        re.IGNORECASE,
    ),
    # A dotted citation on its own -- "19.301.4". Two dots, because "19.5" is
    # a measurement and this ledger exists to read measurements.
    re.compile(r"\b\d+(?:\.\d+){2,}\b"),
    # An OAR or hyphenated code number -- "660-046-0220", "33-110". Two digits
    # a side, so "3-5 feet" survives: a masked range costs a row to the
    # unnumbered pile, and that pile is where a real standard goes to hide.
    re.compile(r"\b\d{2,}(?:-\d{2,})+\b"),
    # The amendment trail every scanned ordinance ends with.
    re.compile(
        r"\b(?:amend\w*|adopt\w*|repeal\w*|effective|eff|enacted|passed)\b[^.;]{0,40}",
        re.IGNORECASE,
    ),
)

#: A bare number, after masking. Commas are part of it -- "5,000" is one
#: figure -- and a trailing ordinal or letter is not.
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w.])")

#: The unit a figure of each kind has to be wearing. This is the whole
#: difference between a ledger worth reading and a ledger of every digit in a
#: paragraph: Milwaukie 19.303.4 says a building "can utilize up to 2 of the
#: development incentive bonuses", and 2 is a perfectly plausible number of
#: feet. It is not a height, and the sentence says so by not putting "ft"
#: after it.
#:
#: A standard states its unit. Prose about a standard often does not, and the
#: cost of insisting is a row filed as ``unnumbered`` -- a queue nobody has to
#: work -- rather than a false alarm in the one queue that is meant to be read.
#: Each kind maps to the units it can be printed in, and each unit names its
#: own window above. Order matters only in that the first unit a figure wears
#: is the one it is judged by.
_UNIT: dict[str, tuple[tuple[str, str], ...]] = {
    "length_ft": ((r"(?:ft\b|feet\b|foot\b|')", "ft"),),
    "area_sqft": (
        (r"(?:sq\.?\s*ft|square\s+f(?:ee|oo)t|\bsf\b)", "sqft"),
        (r"acres?\b", "acres"),
    ),
    "percent": ((r"(?:%|percent|percentage)", "percent"),),
    "ratio": ((r"(?:spaces?\b|stalls?\b|per\b|:\s*\d|to\s+1\b)", "ratio"),),
    "count": (
        (r"(?:units?\b|dwellings?\b|stor(?:y|ies)\b|spaces?\b|stalls?\b|bedrooms?\b)", "count"),
    ),
}

#: How far past the figure its unit may sit. Three characters covers the
#: bracketed restatement Oregon ordinances are fond of -- "forty-five (45)
#: feet" -- and stops well short of the next clause.
_GAP = r"[\s\)\.\-–—]{0,3}"

#: What magnitude a figure can plausibly have, **given the unit it is wearing**.
#: A number outside its window is something else in the same sentence -- a floor
#: area beside a height, a lot size beside a coverage percentage -- and
#: comparing it against the wrong field's values manufactures a disagreement.
#:
#: The window belongs to the unit rather than to the kind because one kind can
#: be printed in two units. An area is 5,000 square feet or 80 acres, and 80 is
#: below any floor that would exclude a square footage. Nothing is converted:
#: this ledger compares the figure a reader will find against the figure the
#: file records having found, and both are printed in whatever unit the
#: ordinance chose -- the same bargain :func:`_printed` makes.
#:
#: The windows are wide on purpose. They throw out an obvious category error;
#: they do not judge whether a standard is reasonable.
_WINDOW: dict[str, tuple[Decimal, Decimal]] = {
    "ft": (Decimal("1"), Decimal("400")),
    "sqft": (Decimal("100"), Decimal("10000000")),
    "acres": (Decimal("0.05"), Decimal("2000")),
    "percent": (Decimal("0"), Decimal("100")),
    "ratio": (Decimal("0.01"), Decimal("100")),
    "count": (Decimal("1"), Decimal("500")),
}

#: Kinds this cannot compare at all. A bool has no figure; an enum has no
#: order; a curve is a table and its rows are checked by the column ledger.
_UNCOMPARABLE = frozenset({"bool", "enum", "curve"})

#: How near two figures may be and still count as the same standard. Codes
#: print "twenty-two feet" as 22 and a table prints 22.0; nothing in this
#: corpus distinguishes standards a hundredth of a foot apart.
_TOL = Decimal("0.005")


@dataclass(frozen=True, slots=True)
class Missed:
    """One unread line naming a field, against what its layer holds."""

    layer: str
    field: str
    path: str
    line: int
    section: str
    text: str
    #: Figures on the line that could be a standard of this field.
    stated: tuple[Decimal, ...]
    #: Figures this layer holds for this field, in any zone, as printed.
    held: tuple[Decimal, ...]
    #: The intersection.
    matched: tuple[Decimal, ...]
    repeats: int = 1
    #: Fields an encoded value was read from *in this line's own section*.
    read_here: tuple[str, ...] = ()

    @property
    def verdict(self) -> str:
        if not self.stated:
            return "unnumbered"
        return "held" if self.matched else "unheld"

    @property
    def nearness(self) -> str:
        """How close this line sits to reading somebody already did.

        The single most useful thing known about an unread line, and it costs
        nothing: it is a property of where the line sits, not of what it says.

        ``same_field``      a value of *this very standard* was read from this
                            section. Somebody had the table open, took a row,
                            and left this one. That is the shape of every
                            missed standard this project has found by hand.
        ``read_section``    the section was read, for some other standard.
        ``unread_section``  nothing in this section has ever been quoted. Not a
                            miss so much as a door nobody opened -- real work,
                            different work, and much more of it.

        **A section is only as fine as the document's own headings.** Milwaukie
        prints ``19.301.4`` and the tiers mean what they say; Portland's
        extracted text carries ``33.110`` for a whole chapter and Wilsonville's
        carries ``4``, so there ``same_field`` means "somewhere in this
        chapter", which is a much weaker claim. It is still the right claim to
        make -- it is what the document supports -- but a Portland row at the
        top of the queue has earned less than a Milwaukie one.
        """
        if self.field in self.read_here:
            return "same_field"
        return "read_section" if self.read_here else "unread_section"

    @property
    def novel(self) -> tuple[Decimal, ...]:
        """The figures on this line that appear nowhere in the layer."""
        return tuple(s for s in self.stated if not _near(s, self.held))


def _near(figure: Decimal, among: Sequence[Decimal]) -> bool:
    return any(abs(figure - other) <= _TOL for other in among)


def _figures(text: str, kind: str) -> tuple[Decimal, ...]:
    """Every number in a line that could be a standard of this kind.

    Two gates, and both are needed. The unit gate says the sentence meant this
    number as a measure of this kind; the window says the measure is of a size
    this kind can have. Neither alone is enough -- "25% of the gross floor
    area" wears a unit and is not a height, and a bare 12 in a sentence about
    heights is inside every window there is.
    """
    if kind in _UNCOMPARABLE or kind not in _UNIT:
        return ()
    masked = text
    for mask in _MASKS:
        masked = mask.sub(" ", masked)
    out: list[Decimal] = []
    for pattern, unit in _UNIT[kind]:
        wearing = re.compile(
            rf"(?<![\w.])(\d{{1,3}}(?:,\d{{3}})+|\d+(?:\.\d+)?)(?![\w.]){_GAP}{pattern}",
            re.IGNORECASE,
        )
        low, high = _WINDOW[unit]
        for token in wearing.findall(masked):
            try:
                figure = Decimal(token.replace(",", ""))
            except InvalidOperation:  # pragma: no cover - findall cannot produce this
                continue
            if low <= figure <= high and not _near(figure, out):
                out.append(figure)
    return tuple(out)


def _held(layer: Layer) -> dict[str, tuple[Decimal, ...]]:
    """Every printed figure this layer carries, by field.

    Zones are pooled deliberately. An uncited line rarely says which district
    it belongs to -- it is a table row, or a sentence under a heading -- so
    asking "does this jurisdiction hold this number for this standard at all"
    is the only question the text actually supports. It under-reports, which
    is the direction a queue meant to be read should err in.
    """
    out: dict[str, list[Decimal]] = defaultdict(list)
    for zone in layer.zones.values():
        for name, value in zone.values.items():
            for figure in (_printed(value), *(_printed_variant(v) for v in value.variants)):
                number = _decimal(figure)
                if number is not None and not _near(number, out[name]):
                    out[name].append(number)
    return {name: tuple(sorted(figures)) for name, figures in out.items()}


def _decimal(figure: object) -> Decimal | None:
    if isinstance(figure, bool) or figure is None:
        return None
    if isinstance(figure, (int, float, Decimal)):
        return Decimal(str(figure))
    return None


def _read_sections(
    layer: Layer, store: ProvenanceStore | None = None
) -> dict[str, dict[str, set[str]]]:
    """``path -> section -> the fields an encoded value was read from there``.

    Built from the same two pieces the reading ledger itself is built from --
    the cited lines of a layer and the document's own section headings -- so a
    section is "read" by exactly the evidence that stops a line being uncited,
    and the two can never disagree about what has been quoted.
    """
    store = store or ProvenanceStore()
    cited = _cited_lines(layer)
    out: dict[str, dict[str, set[str]]] = {}
    for path, lines_read in cited.items():
        if path.rsplit("/", 1)[0] != layer.layer:
            continue
        try:
            lines = store.text_path(path).read_text(encoding="utf-8").splitlines()
        except OSError:  # pragma: no cover - a document in the ledger but not on disk
            continue
        sections = _sections(lines, {i.partition(".")[0] for i in _doc_ids([path])})
        here: dict[str, set[str]] = defaultdict(set)
        for line, fields in lines_read.items():
            if 0 < line <= len(sections):
                here[sections[line - 1]].update(fields)
        out[path] = dict(here)
    return out


def audit(
    rows: Sequence[Uncited] | None = None,
    layers: dict[str, Layer] | None = None,
    store: ProvenanceStore | None = None,
    read: dict[str, dict[str, set[str]]] | None = None,
) -> list[Missed]:
    """Every ``unread`` statement, scored against its own layer's figures."""
    layers = load_rules(strict=False) if layers is None else layers
    if rows is None:
        rows = survey(list(layers.values()), store)
    if read is None:
        read = {}
        for layer in layers.values():
            read.update(_read_sections(layer, store))

    held_by_layer = {lid: _held(layer) for lid, layer in layers.items()}
    out: list[Missed] = []
    for row in rows:
        if row.bucket != "unread":
            continue
        definition = FIELDS.get(row.field)
        if definition is None:
            continue
        held = held_by_layer.get(row.layer, {}).get(row.field, ())
        stated = _figures(row.text, definition.kind)
        out.append(
            Missed(
                layer=row.layer,
                field=row.field,
                path=row.path,
                line=row.line,
                section=row.section,
                text=" ".join(row.text.split()),
                stated=stated,
                held=held,
                matched=tuple(s for s in stated if _near(s, held)),
                repeats=row.repeats,
                read_here=tuple(sorted(read.get(row.path, {}).get(row.section, ()))),
            )
        )
    return out


#: Closest first. A queue is worked from the top, so the order here is the
#: only editorial judgement this module makes, and it is made once.
NEARNESS = ("same_field", "read_section", "unread_section")


def by_figure(rows: Iterable[Missed]) -> list[tuple[str, str, Decimal, int, str]]:
    """``(layer, field, figure, lines, nearness)`` for unheld figures.

    The ranking that makes this workable, and it has two keys in this order:

    First, how near the line sits to reading already done. A figure printed in
    a section somebody took *this same standard* out of is a skipped row; the
    same figure in a chapter nobody has opened is a different job, and mixing
    the two is what makes a thousand-line ledger unreadable.

    Second, how many lines print it. One line printing an unheld number is
    usually another use's column; eleven lines printing the *same* unheld
    number for the same standard is a table nobody took.
    """
    counts: Counter[tuple[str, str, Decimal]] = Counter()
    nearest: dict[tuple[str, str, Decimal], int] = {}
    for row in rows:
        if row.verdict != "unheld":
            continue
        rank = NEARNESS.index(row.nearness)
        for figure in row.novel:
            key = (row.layer, row.field, figure)
            counts[key] += row.repeats
            nearest[key] = min(nearest.get(key, len(NEARNESS)), rank)
    return [
        (layer, field, figure, n, NEARNESS[nearest[(layer, field, figure)]])
        for (layer, field, figure), n in sorted(
            counts.items(),
            key=lambda kv: (nearest[kv[0]], -kv[1], kv[0][0], kv[0][1], kv[0][2]),
        )
    ]


def render(
    rows: Sequence[Missed],
    *,
    top: int = 40,
    off: Collection[str] = (),
    orphaned: Sequence[Orphan] = (),
) -> str:
    counts = Counter(r.verdict for r in rows)
    near = Counter(r.nearness for r in rows if r.verdict == "unheld")
    ranked = by_figure(rows)
    dark = sum(1 for r in rows if r.layer in off)
    out = [
        f"unread statements naming a field we screen on: {len(rows)}",
        f"  states a figure this layer holds nowhere: {counts['unheld']}",
        f"  states a figure the layer already carries: {counts['held']}",
        f"  states no comparable figure:               {counts['unnumbered']}",
        *(
            [f"  of all of them, in cities the screen does not cover: {dark}"]
            if dark
            else []
        ),
        "",
        "of the unheld, where the line sits:",
        f"  in a section we took THIS standard from: {near['same_field']}",
        f"  in a section we read, for something else: {near['read_section']}",
        f"  in a section nothing has ever been quoted from: {near['unread_section']}",
        "",
        f"FIGURES THIS CORPUS HAS NEVER HELD: {len(ranked)}",
        "(a sort, not a finding -- most are another use's column; read from the top)",
        "",
    ]
    shown_tier = ""
    for layer, field, figure, lines, nearness in ranked[:top]:
        if nearness != shown_tier:
            shown_tier = nearness
            out.append(f"--- {nearness} ---")
        shown = format(figure.normalize(), "f")
        mark = "   [SWITCHED OFF -- not screened]" if layer in off else ""
        out.append(f"  {lines:>3} lines  [{layer}] {field} = {shown}{mark}")
        example = next(
            r
            for r in rows
            if r.layer == layer
            and r.field == field
            and figure in r.novel
            and r.nearness == nearness
        )
        out.append(f"           {example.path}#L{example.line}  ({example.section})")
        out.append(f"           {example.text[:150]}")
    if len(ranked) > top:
        out.append(f"  ... and {len(ranked) - top} more")
    if orphaned:
        out += [
            "",
            f"A STANDARD MOST NEIGHBOURS REGULATE AND THIS CITY DOES NOT: {len(orphaned)}",
            "(held in no zone here, held by most screened layers, and named by an"
            " unread line in this city's own code)",
            "",
        ]
        for o in orphaned:
            first = o.rows[0]
            out.append(
                f"  {o.peers:>3}/{o.total} cities  [{o.layer}] {o.field}"
                f"  ({o.lines} unread line{'s' if o.lines != 1 else ''})"
            )
            out.append(f"           {first.path}#L{first.line}  ({first.section})")
            out.append(f"           {first.text[:150]}")
    return "\n".join(out)


# --- reading it out ---------------------------------------------------------
#
# The ledger says which lines are worth a second opinion. Getting the opinion
# is a reading job, and it is blind in the one way that decides whether the
# answer is worth having: the card carries the sentence and the page around it
# and **not the figure this corpus holds**. A reader shown "we hold 35" agrees
# with 35, every time, and the agreement means nothing.
#
# It is blind in a second way too, and this one is particular to this ledger.
# The card does not say which standard we think the line is about. That guess
# is `uncited._subject`'s, made from the line's own wording, and it is wrong
# often enough to be worth checking -- a sentence about trimming plants beside
# a trail is filed under building height. Asking an open question costs
# nothing here and buys the guess back as an answer.


def work_list(
    rows: Sequence[Missed] | None = None,
    store: ProvenanceStore | None = None,
    context: int = CONTEXT,
    tiers: Sequence[str] = ("same_field", "read_section"),
    off: Collection[str] = (),
    include_off: bool = False,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    """``(cards, answer key, what was skipped)`` for the unheld statements.

    Only ``unheld`` lines, and by default only the two near tiers. The third
    is 357 lines in chapters nobody has opened, which is a different question
    -- "is there anything in here for us" -- and a card built for this one
    answers it badly.

    ``off`` names the jurisdictions the screen does not cover, and this list
    drops them, which is the opposite of what :func:`flats.encode.triage.feed`
    does with the same set. The two are not inconsistent: triage ranks cards
    by lots at stake and can afford to show excluded land marked, because the
    reader is choosing what to open. Here a card *is* the work -- somebody
    reads a page of code and answers a question -- and the first run of this
    queue spent 26 of its 185 readings, and 8 of its 29 findings, on Lake
    Oswego and Rivergrove, which nobody screens. That is not a marked row a
    reader can skip past. It is an hour of reading with no lot behind it.

    The ledger still counts them; :func:`render` marks them. Only the reading
    queue drops them, and ``include_off`` puts them back for the day somebody
    switches a city on.
    """
    rows = audit() if rows is None else rows
    store = ProvenanceStore() if store is None else store
    off = frozenset(() if include_off else off)

    cards: list[dict[str, object]] = []
    key: list[dict[str, object]] = []
    skipped = {
        "held_or_unnumbered": 0,
        "far_tier": 0,
        "switched_off": 0,
        "no_text": 0,
    }
    docs: dict[str, list[str]] = {}

    order = {n: i for i, n in enumerate(NEARNESS)}
    for row in sorted(rows, key=lambda r: (order[r.nearness], r.layer, r.path, r.line)):
        if row.verdict != "unheld":
            skipped["held_or_unnumbered"] += 1
            continue
        if row.nearness not in tiers:
            skipped["far_tier"] += 1
            continue
        if row.layer in off:
            skipped["switched_off"] += 1
            continue
        if row.path not in docs:
            try:
                docs[row.path] = store.text_path(row.path).read_text(
                    encoding="utf-8"
                ).splitlines()
            except OSError:
                docs[row.path] = []
        whole = docs[row.path]
        if not whole:
            skipped["no_text"] += 1
            continue

        headings, caption_at = _above(whole, row.line)
        ident = f"{len(cards):05d}"
        cards.append(
            {
                "id": ident,
                "jurisdiction": row.layer,
                "document": row.path,
                "cited_lines": f"L{row.line}",
                "section": row.section,
                "headings": headings,
                "passage": _passage(whole, [(row.line, row.line)], context, caption_at),
            }
        )
        key.append(
            {
                "id": ident,
                "layer": row.layer,
                "field": row.field,
                "path": row.path,
                "line": row.line,
                "section": row.section,
                "nearness": row.nearness,
                "repeats": row.repeats,
                "text": row.text,
                # The answers. Never on the card.
                "stated": [format(f.normalize(), "f") for f in row.stated],
                "held": [format(f.normalize(), "f") for f in row.held],
            }
        )
    return cards, key, skipped


# --- the standard every neighbour regulates and this city does not -----------


@dataclass(frozen=True, slots=True)
class Orphan:
    """A field this layer holds in no zone at all, that most of its peers do."""

    layer: str
    field: str
    peers: int
    total: int
    rows: tuple[Missed, ...]

    @property
    def lines(self) -> int:
        return len(self.rows)


def orphans(
    rows: Sequence[Missed],
    layers: dict[str, Layer],
    off: Collection[str] = (),
    share: float = 0.5,
) -> list[Orphan]:
    """Fields a city records nothing for while most of its neighbours do.

    A different question from the rest of this module, and it came from an
    accident. West Linn holds no garage-entrance setback in any of its nine
    zones; Gresham holds one in sixteen and Wilsonville in nine; and West
    Linn's own access chapter says a driveway "shall include a minimum of 20
    feet in length between the garage door and the back of sidewalk". No
    coverage ledger sees that, because the field is not required and the zones
    are complete without it -- the gap is only visible against what everybody
    else wrote down.

    So: a field held *nowhere* in this layer, held by at least ``share`` of the
    screened layers, and named by at least one unread line in this layer's own
    documents. All three conditions matter. The first two alone are ordinary
    variation between cities -- Gresham genuinely has no residential lot
    coverage standard, and a whole-corpus read confirms it. The third is what
    makes it a question: the city's own code has a sentence about the thing.

    Precision is about what the rest of this module gets, and for the same
    reason -- two of the seven rows on the first run were real (West Linn's
    driveway, Fairview's garage setback in VSF), two were the field guess
    misfiring on a cottage-cluster garage *door width*, one was an option in a
    menu nobody has to pick, and two were in a field no screen reads.
    """
    off = frozenset(off)
    live = {
        lid: layer for lid, layer in layers.items() if lid not in off and "/" in lid
    }
    holds: dict[str, set[str]] = defaultdict(set)
    for lid, layer in live.items():
        for zone in layer.zones.values():
            for name in zone.values:
                holds[name].add(lid)
        for name in layer.defaults:
            holds[name].add(lid)

    grouped: dict[tuple[str, str], list[Missed]] = defaultdict(list)
    for row in rows:
        if row.verdict == "unheld" and row.layer in live:
            grouped[(row.layer, row.field)].append(row)

    floor = len(live) * share
    out = [
        Orphan(
            layer=layer,
            field=field,
            peers=len(holds.get(field, ())),
            total=len(live),
            rows=tuple(sorted(members, key=lambda r: r.line)),
        )
        for (layer, field), members in grouped.items()
        if layer not in holds.get(field, ()) and len(holds.get(field, ())) >= floor
    ]
    return sorted(out, key=lambda o: (-o.peers, -o.lines, o.layer, o.field))


# --- the chapter nobody opened -----------------------------------------------
#
# The third nearness tier is a different question and a per-line card answers
# it badly. 347 of its lines sit in 144 sections of screened cities, and 89 of
# those sections hold exactly one measuring line -- so asking line by line
# would buy 347 readings of a question that has 144 answers, and would ask the
# largest of them (Gresham 4.1252, 34 lines) thirty-four times over.
#
# So one card is one section, every unquoted measuring line in it marked at
# once, and the question changes with the shape: not "does this line bind us"
# but "is there anything in this section our building has to satisfy, and
# where". A section of land-division procedure closes in one answer. That is
# the whole economy of it.


def chapter_list(
    rows: Sequence[Missed] | None = None,
    store: ProvenanceStore | None = None,
    context: int = 2,
    off: Collection[str] = (),
    include_off: bool = False,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    """``(cards, answer key, what was skipped)``, one card per unopened section.

    Biggest section first, because a card's cost is one reading either way and
    the 34-line ones carry more of the queue than the 89 single-line ones put
    together.
    """
    rows = audit() if rows is None else rows
    store = ProvenanceStore() if store is None else store
    off = frozenset(() if include_off else off)

    groups: dict[tuple[str, str, str], list[Missed]] = defaultdict(list)
    skipped = {"not_the_far_tier": 0, "switched_off": 0, "no_text": 0}
    for row in rows:
        if row.verdict != "unheld" or row.nearness != "unread_section":
            skipped["not_the_far_tier"] += 1
        elif row.layer in off:
            skipped["switched_off"] += 1
        else:
            groups[(row.layer, row.path, row.section)].append(row)

    cards: list[dict[str, object]] = []
    key: list[dict[str, object]] = []
    docs: dict[str, list[str]] = {}
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for (layer, path, section), members in ordered:
        if path not in docs:
            try:
                docs[path] = store.text_path(path).read_text(
                    encoding="utf-8"
                ).splitlines()
            except OSError:
                docs[path] = []
        whole = docs[path]
        if not whole:
            skipped["no_text"] += len(members)
            continue
        members = sorted(members, key=lambda r: r.line)
        lines = [r.line for r in members]
        headings, caption_at = _above(whole, lines[0])
        ident = f"{len(cards):05d}"
        cards.append(
            {
                "id": ident,
                "jurisdiction": layer,
                "document": path,
                "section": section,
                "headings": headings,
                "marked_lines": ", ".join(f"L{n}" for n in lines),
                "passage": _passage(
                    whole, [(n, n) for n in lines], context, caption_at
                ),
            }
        )
        key.append(
            {
                "id": ident,
                "layer": layer,
                "path": path,
                "section": section,
                "lines": lines,
                # Our guesses, and they are only guesses -- never on the card.
                "fields": sorted({r.field for r in members}),
                "texts": [r.text for r in members],
            }
        )
    return cards, key, skipped


def score_chapters(
    key: Sequence[dict],
    answers: dict[str, dict],
    layers: dict[str, Layer] | None = None,
) -> list[dict[str, object]]:
    """Join the section readings back.

    There is no held figure to compare against here -- that is what makes it
    the unopened tier -- so the only machine check available is the weak one:
    is the number the reader read printed *anywhere* in that jurisdiction's
    file, for any standard at all. ``worth_reading`` means it is not, which is
    the same claim the per-line ledger makes and a much weaker version of it.
    """
    layers = load_rules(strict=False) if layers is None else layers
    pooled: dict[str, list[Decimal]] = {}
    out: list[dict[str, object]] = []
    for k in key:
        a = answers.get(str(k["id"])) or {}
        binds = str(a.get("binds") or "").strip().lower()
        read = _reader_number(a.get("number"))
        layer = str(k["layer"])
        if layer not in pooled:
            found = layers.get(layer)
            pooled[layer] = (
                sorted({f for figs in _held(found).values() for f in figs})
                if found is not None
                else []
            )
        if not binds:
            verdict = "missing"
        elif binds == "no":
            verdict = "agree"
        elif binds != "yes":
            verdict = "unclear"
        elif read is not None and _near(read, pooled[layer]):
            verdict = "seen_elsewhere"
        else:
            verdict = "worth_reading"
        out.append(
            {
                **{n: v for n, v in k.items() if n not in ("lines", "fields", "texts")},
                "lines": ",".join(f"L{n}" for n in k["lines"]),
                "fields": ",".join(k["fields"]),
                "verdict": verdict,
                "binds": binds,
                "reader_lines": str(a.get("lines") or ""),
                "reader_number": str(a.get("number") or ""),
                "reader_standard": str(a.get("standard") or ""),
                "reader_about": str(a.get("about") or ""),
                "reader_note": str(a.get("note") or ""),
            }
        )
    return out


def report_chapters(rows: Sequence[dict]) -> str:
    counts = Counter(str(r["verdict"]) for r in rows)
    out = [
        f"sections read: {len(rows)}  "
        + "  ".join(f"{n}={counts[n]}" for n in sorted(counts)),
        "",
        f"SOMETHING IN HERE BINDS US: {counts['worth_reading'] + counts['seen_elsewhere']}",
        f"  and the figure is printed nowhere in that city's file: {counts['worth_reading']}",
        "",
    ]
    for r in rows:
        if r["verdict"] in ("worth_reading", "seen_elsewhere"):
            out.append(
                f"  [{r['layer']}] {r['section']} {r['reader_lines']}"
                f"  {r['reader_standard']} = {r['reader_number']}"
            )
            out.append(f"      {str(r['reader_note'])[:150]}")
    return "\n".join(out)


def _reader_number(said: object) -> Decimal | None:
    """The first figure in whatever the reader typed."""
    match = re.search(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", str(said or ""))
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:  # pragma: no cover - the pattern cannot produce this
        return None


#: What the reading can conclude. ``missed`` is the only one that is a finding.
READINGS = ("missed", "already_held", "agree", "unclear", "missing")


def score(key: Sequence[dict], answers: dict[str, dict]) -> list[dict[str, object]]:
    """Join the readings back to the ledger.

    ``agree``         the reader says the sentence does not bind this building,
                      so leaving it unencoded was right
    ``already_held``  it binds, and the figure they read is one we carry for
                      that standard -- our reader took it off another row
    ``missed``        it binds, and the figure is one this corpus holds nowhere
    ``unclear``       the reader could not tell from the page
    ``missing``       nobody answered this card
    """
    out: list[dict[str, object]] = []
    for k in key:
        a = answers.get(str(k["id"])) or {}
        binds = str(a.get("binds") or "").strip().lower()
        read = _reader_number(a.get("number"))
        held = [Decimal(h) for h in k["held"]]
        if not binds:
            verdict = "missing"
        elif binds == "no":
            verdict = "agree"
        elif binds != "yes":
            verdict = "unclear"
        elif read is not None and _near(read, held):
            verdict = "already_held"
        else:
            verdict = "missed"
        out.append(
            {
                **{n: v for n, v in k.items() if n != "held"},
                "held": ",".join(k["held"]),
                "stated": ",".join(k["stated"]),
                "verdict": verdict,
                "binds": binds,
                "reader_number": "" if read is None else format(read.normalize(), "f"),
                "reader_standard": str(a.get("standard") or "")[:120],
                "reader_about": str(a.get("about") or "")[:120],
                "reader_note": str(a.get("note") or "")[:400],
            }
        )
    return out


def report(rows: Sequence[dict]) -> str:
    counts = Counter(str(r["verdict"]) for r in rows)
    missed = [r for r in rows if r["verdict"] == "missed"]
    out = [
        f"cards={len(rows)} " + " ".join(f"{n}={counts[n]}" for n in READINGS if counts[n]),
        "",
        f"A STANDARD THIS CORPUS HOLDS NOWHERE: {len(missed)}",
    ]
    same = [r for r in missed if r["nearness"] == "same_field"]
    out.append(f"  of those, in a section we took that very standard from: {len(same)}")
    out.append("")
    for r in sorted(missed, key=lambda r: (r["nearness"] != "same_field", str(r["layer"]))):
        out.append(f"  [{r['layer']}] {r['path']}#L{r['line']}  ({r['section']}) {r['nearness']}")
        out.append(f"      reader: {r['reader_standard']} = {r['reader_number']}"
                   f"  about: {r['reader_about']}")
        out.append(f"      we hold for {r['field']}: {r['held'] or '(nothing)'}")
        out.append(f"      line  : {str(r['text'])[:150]}")
        if r["reader_note"]:
            out.append(f"      note  : {str(r['reader_note'])[:200]}")
    return "\n".join(out)


def _write_work(
    out_dir: Path,
    batch: int,
    context: int,
    tiers: Sequence[str],
    off: Collection[str] = (),
    include_off: bool = False,
    sections: bool = False,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    if sections:
        cards, key, skipped = chapter_list(
            context=context, off=off, include_off=include_off
        )
    else:
        cards, key, skipped = work_list(
            context=context, tiers=tiers, off=off, include_off=include_off
        )
    (out_dir / "answer_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    for n in range(0, len(cards), batch):
        (out_dir / f"batch_{n // batch:03d}.json").write_text(
            json.dumps(cards[n : n + batch], indent=1), encoding="utf-8"
        )
    print(
        f"cards={len(cards)} batches={(len(cards) + batch - 1) // batch} skipped={skipped}"
    )
    return 0


def _score_dir(work: Path, csv_out: Path | None) -> int:
    key = json.loads((work / "answer_key.json").read_text(encoding="utf-8"))
    answers: dict[str, dict] = {}
    for path in sorted(work.glob("answers_*.json")):
        try:
            for a in json.loads(path.read_text(encoding="utf-8")):
                answers[str(a.get("id"))] = a
        except json.JSONDecodeError as exc:
            print(f"BAD JSON {path.name}: {exc}")
    # The two card shapes score differently and the key says which it is: a
    # section card carries a list of lines, a line card carries one.
    if key and isinstance(key[0].get("lines"), list):
        rows = score_chapters(key, answers)
        print(report_chapters(rows))
    else:
        rows = score(key, answers)
        print(report(rows))
    if csv_out:
        import csv

        csv_out.parent.mkdir(parents=True, exist_ok=True)
        with csv_out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print("wrote", csv_out)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layer", nargs="*", help="restrict to these layer ids")
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--out", type=Path, help="write a blind reading list here")
    ap.add_argument("--score", type=Path, help="score a finished reading directory")
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--context", type=int, default=CONTEXT)
    ap.add_argument(
        "--tier",
        action="append",
        choices=NEARNESS,
        help="which nearness tiers to read (default: the two near ones)",
    )
    ap.add_argument(
        "--include-off",
        action="store_true",
        help="build reading cards for jurisdictions the screen does not cover",
    )
    ap.add_argument(
        "--sections",
        action="store_true",
        help="one card per unopened section instead of one per line",
    )
    args = ap.parse_args(argv)
    if args.score:
        return _score_dir(args.score, args.csv)
    if hasattr(sys.stdout, "reconfigure"):
        # Extracted PDF text carries ligatures -- 'fl' as one glyph -- that a
        # Windows console cannot encode, and a ledger that dies printing the
        # evidence it found is worse than one that prints a question mark.
        sys.stdout.reconfigure(errors="replace")

    layers = load_rules(strict=False)
    if args.layer:
        layers = {lid: layer for lid, layer in layers.items() if lid in set(args.layer)}
    rows = audit(layers=layers)
    off = unscreened(layers)
    if args.out:
        return _write_work(
            args.out,
            args.batch,
            args.context,
            tuple(args.tier) if args.tier else ("same_field", "read_section"),
            off,
            args.include_off,
            args.sections,
        )
    print(render(rows, top=args.top, off=off, orphaned=orphans(rows, layers, off)))
    if args.csv:
        import csv

        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(
                ["layer", "field", "verdict", "nearness", "path", "line", "section",
                 "stated", "novel", "held", "repeats", "text"]
            )
            order = {n: i for i, n in enumerate(NEARNESS)}
            for r in sorted(
                rows,
                key=lambda r: (r.verdict != "unheld", order[r.nearness], r.layer, r.path, r.line),
            ):
                w.writerow(
                    [
                        r.layer,
                        r.field,
                        r.verdict,
                        r.nearness,
                        r.path,
                        r.line,
                        r.section,
                        ",".join(format(f.normalize(), "f") for f in r.stated),
                        ",".join(format(f.normalize(), "f") for f in r.novel),
                        ",".join(format(f.normalize(), "f") for f in r.held),
                        r.repeats,
                        r.text,
                    ]
                )
        print("wrote", args.csv)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
