"""Fetch triage — one question, asked well, about a chapter we cannot open.

:mod:`flats.encode.crossrefs` finds the references: every section our own
documents point at and the store cannot open. It is a good ledger and a bad
worklist. It prints ``mentions`` and ``binding`` as counts, one truncated line
of context, and 1,468 rows sorted by a number that means "how loud", and the
person working it has to open a document to learn what any row is about.

This module builds the worklist. The question a reviewer answers here is
exactly one sentence long -- *does this chapter change a number we screen on?*
-- and everything on a card exists to answer it:

**What it stands beside.** The ledger already knows a reference is *binding*,
meaning it sits within a few lines of text an encoded value was read from. It
throws away which value. That is the whole decision. A reference standing
beside Gresham R-5's rear setback across 21,000 lots and a reference standing
beside a definition of "story" are the same row in the ledger and are not
remotely the same job. Cards carry the neighbours by name, with the lots behind
them.

**Every mention, not a sample.** Ruling a reference means reading the sentences
that make it. Nine of the seventeen rulings written by hand turn on a clause in
the second half of a sentence the ledger's 160-character sample cut off.

**Lots, as the sort.** ``binding`` counts how many times a reference is written
near a number. Lots count what changes if it turns out to matter. Gladstone's
loudest reference was ten mentions of one settled sentence about mobile home
parks; the quiet ones are worth more.

State law is deliberately absent. ORS and OAR references are a different fetch
problem with a different publisher, and one fetch answers for all seventeen
layers rather than one -- mixing them in would bury a city's own missing
chapter under a hundred boilerplate statutory pointers, which is the complaint
that produced this module.

Run it::

    uv run python -m flats.encode.triage
    uv run python -m flats.encode.triage --layer or/multnomah/gresham
    uv run python -m flats.encode.triage --field setback_rear_ft
    uv run python -m flats.encode.triage --ruled
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from flats.encode.crossrefs import (
    BINDING_WINDOW,
    _REF,
    _doc_ids,
    _headings,
    _resolves,
)
from flats.encode.legible import is_grid, legible
from flats.provenance.store import ProvenanceStore, parse_quote
from flats.rules.fields import FIELDS
from flats.rules.ledger import read_coverage
from flats.rules.loader import load_rules
from flats.rules.loader import MIN_RULING
from flats.rules.model import CROSSREF_OUTCOMES, Layer, Ruling

#: How much of a mention line to keep, centred on the reference itself. The
#: ledger kept the first 160 characters of the line, which on an extracted
#: table is the row's cells and not the sentence -- Portland 33.236 came back
#: as "(See Chapter 33.236)" followed by six columns of the word "Yes". A
#: window around the reference is both shorter and more likely to hold the
#: clause that settles it.
SNIPPET = 260

#: What a chapter calls itself, taken from the sentence that cites it. Codes
#: name a chapter when they first point at it -- "Chapter 33.236, Floating
#: Structures", "Section 7.0420. Residential Design Standards" -- and that
#: title answers the card's question more often than the rest of the card
#: does. Three mentions of Portland 33.236 and only the third carries it.
_TITLE = re.compile(
    r"(?P<kind>Chapter|Section|Title|Article)\s+%s\s*[,.:]?\s+"
    r"(?P<title>[A-Z][A-Za-z&'/-]*"
    r"(?:\s+(?:of|the|and|for|in|to|a|an|with|from|on)"
    r"|\s+[A-Z][A-Za-z&'/-]*){0,7})"
)

#: Where a title stops: a sentence continues past it, a title does not.
_TITLE_STOP = re.compile(
    r"\b(?:shall|is|are|may|must|does|do|which|that|when|except"
    r"|of\s+the\s+(?:Community|City|Code))\b",
    re.I,
)

#: Words a title may contain and may not end on.
_DANGLING = ("of", "the", "and", "for", "in", "to", "a", "an", "with", "from", "on")


@dataclass(frozen=True, slots=True)
class Neighbour:
    """A standard this reference stands beside, across every zone that shares it.

    Grouped by field *and* figure rather than listed per zone, because a
    reference beside Portland's coverage curve is beside the same eleven-cell
    curve in R5, R7, R2.5 and R10, and printing it four times is four times the
    reading for none of the information. What differs between those rows is the
    zone name and the lot count, and both are carried here.

    ``distance`` is in lines, and small is not the same as important -- a
    reference in the "Additional Standards" column of a table is printed
    several lines from the row it qualifies, which is why the binding window is
    twelve rather than one.
    """

    field: str
    shown: str
    zones: tuple[str, ...]
    distance: int
    lots: int

    @property
    def title(self) -> str:
        """What to call this standard in front of a person."""
        spec = FIELDS.get(self.field)
        return spec.shown if spec else self.field.replace("_", " ")

    @property
    def has_slack(self) -> bool:
        """Whether being wrong here could change whether a building fits."""
        spec = FIELDS.get(self.field)
        return spec.has_slack if spec else True

    @property
    def label(self) -> str:
        where = ", ".join(self.zones[:4])
        if len(self.zones) > 4:
            where += f" +{len(self.zones) - 4}"
        return f"{self.title} = {self.shown}   [{where}]"


@dataclass(frozen=True, slots=True)
class Mention:
    """One place the reference is written."""

    doc: str
    line: int
    text: str
    binding: bool


@dataclass(frozen=True, slots=True)
class Card:
    """One reference, and everything needed to rule on it without opening a file."""

    layer: str
    ref: str
    mentions: tuple[Mention, ...]
    neighbours: tuple[Neighbour, ...]
    #: Every zone this reference stands beside, with the lots behind it. Held
    #: flat rather than derived from ``neighbours`` because neighbours group by
    #: figure and one zone appears in several of them -- summing those would
    #: count R5's 73,690 lots once per standard it happens to share.
    zone_lots: tuple[tuple[str, int], ...] = ()
    #: What the code calls this chapter, where a citing sentence names it.
    #: Empty when nothing does -- never guessed.
    title: str = ""
    #: The noun the code uses for it: Title, Chapter, Section or Article.
    #: Defaults to the commonest rather than the truest, because most of these
    #: are sections and every card that finds a citing sentence overrides it.
    kind: str = "Section"
    #: The reference this one sits inside, where that is also in the queue.
    #: Portland's Title 11 and its Chapter 11.50 are one fetch and were two
    #: cards in a row, showing the same lots and the same sentences.
    inside: str = ""
    #: References inside this one that are also in the queue.
    contains: tuple[str, ...] = ()
    ruling: Ruling | None = None

    @property
    def _zone_lots(self) -> dict[str, int]:
        return dict(self.zone_lots)

    @property
    def key(self) -> str:
        return f"{self.layer}|{self.ref}"

    @property
    def outcome(self) -> str:
        return self.ruling.outcome if self.ruling is not None else ""

    @property
    def open(self) -> bool:
        """Whether this row still wants a decision.

        A ``fetch`` ruling stays open on purpose: it is work ordered, not work
        finished, and the row closes when the document lands in the store and
        the reference resolves. ``later`` stays open for the same reason from
        the other direction.
        """
        return self.ruling is None or not self.ruling.closed

    @property
    def binding(self) -> int:
        return sum(1 for m in self.mentions if m.binding)

    @property
    def lots(self) -> int:
        """Lots behind the values this reference stands beside.

        Counted per zone rather than per neighbour: a reference beside four of
        R-5's numbers is one R-5, not four.
        """
        return sum(self._zone_lots.values())

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(sorted({n.field for n in self.neighbours}))

    @property
    def zones(self) -> tuple[str, ...]:
        return tuple(sorted(self._zone_lots))

    @property
    def docs(self) -> tuple[str, ...]:
        return tuple(sorted({m.doc for m in self.mentions}))

    @property
    def distinct(self) -> tuple[tuple[Mention, int], ...]:
        """The mentions worth reading, each with how many places repeat it.

        A code says the same sentence in every zone's chapter. Portland's tree
        reference is written fourteen times and says eight different things,
        and the four the card showed were the four that repeat -- the two that
        carry anything ("a Title 11 tree permit must be obtained", "Large
        canopy trees are defined in") were behind "and 10 more mentions".

        Binding first, because the mention standing next to a number we use is
        the one the question is about. Repeats are counted rather than dropped:
        a sentence written in every chapter of the code is a different kind of
        fact from one written once.
        """
        order: list[str] = []
        seen: dict[str, tuple[Mention, int]] = {}
        for m in self.mentions:
            key = _same(m.text)
            if key in seen:
                first, count = seen[key]
                # A binding instance outranks a non-binding one written first:
                # it is the same sentence, but only one of them is next to the
                # number, and that is the copy worth citing.
                keep = m if (m.binding and not first.binding) else first
                seen[key] = (keep, count + 1)
                continue
            order.append(key)
            seen[key] = (m, 1)
        # One quote that is the opening of another is the same statement read
        # off a narrower column. "...are specified in Title 11." and "...are
        # specified in Title 11, Trees." are one sentence and the longer one
        # contains the shorter whole, so folding them loses nothing.
        #
        # Only prefixes. Merging on a similarity score was measured against
        # the corpus and collapses "P P P Accessory dwelling units complying
        # with Section 16.44.050" into "X X X Accessory dwelling units..." at
        # 0.945 -- permitted and prohibited, told apart by one letter -- and
        # "the minimum lot size standards apply" into "the minimum and maximum
        # lot size standards apply". A queue that shows one sentence twice
        # wastes a reader's time; one that silently merges two rules is wrong.
        merged: list[tuple[str, Mention, int]] = []
        for key in order:
            mention, count = seen[key]
            for i, (other, kept, tally) in enumerate(merged):
                if not (key.startswith(other) or other.startswith(key)):
                    continue
                keep = mention if (mention.binding and not kept.binding) else kept
                if keep is kept and mention.binding == kept.binding:
                    # Neither is more binding than the other, so show whichever
                    # says more. Never a text from one document under another
                    # document's line number.
                    keep = max((kept, mention), key=lambda m: len(m.text))
                merged[i] = (max(other, key, key=len), keep, tally + count)
                break
            else:
                merged.append((key, mention, count))
        rows = [(m, n) for _, m, n in merged]
        rows.sort(key=lambda r: (not r[0].binding, -r[1]))
        return tuple(rows)

    @property
    def live_lots(self) -> int:
        """Lots behind the standards that have slack in them.

        Sorting on total lots put a houseboat chapter at the top of the whole
        corpus. Portland 33.236 is cross-referenced from the citywide use
        table, so it stands beside every zone's use gate and inherits all
        178,237 lots -- and the only standard it touches is a settled yes/no.
        Reading the chapter cannot make a prohibited use more prohibited.

        What a missed cross-reference actually eats is the distance between a
        standard and the building: a rear setback with four feet of room, a
        height limit with one. Those are the kinds with slack, and this counts
        the lots behind those alone. A reference beside nothing but use gates
        scores zero here and sinks below every reference that touches a number
        with room in it, whatever its headline lot count.
        """
        live = {z for n in self.neighbours if n.has_slack for z in n.zones}
        return sum(lots for zone, lots in self.zone_lots if zone in live)

    @property
    def rank(self) -> tuple[int, int, int, int]:
        """Worst first.

        Lots behind standards with slack, then how many distinct standards it
        touches -- a chapter cited beside four different numbers is a standards
        chapter, one cited beside the same number everywhere is usually a
        pointer -- then total lots, then how often it binds.
        """
        return (
            self.live_lots,
            len(self.fields),
            self.lots,
            self.binding,
        )


def _window(line: str, start: int, end: int) -> str:
    """The reference and the words around it, with the table wreckage gone.

    An extracted table row is one line holding a dozen cells separated by runs
    of spaces, so the first 160 characters of it are whatever cells happened to
    come first. Centring on the reference gets the sentence when there is one;
    collapsing the runs to a marker keeps what is left honest about being cells
    rather than pretending the words ran together.
    """
    half = SNIPPET // 2
    left = line[max(0, start - half) : start]
    right = line[end : end + half]
    body = f"{left}{line[start:end]}{right}"
    body = re.sub(r"\s{3,}", "  ·  ", body).strip()
    # A marker at either end has nothing on one side of it to separate, and
    # reads as a bullet rather than as the cut it is.
    body = body.strip("· ").strip()
    if start - half > 0:
        body = "…" + body
    if end + half < len(line):
        body = body + "…"
    # A line the extractor wrapped ends mid-clause even when nothing was cut
    # here: "...standards in Section 7.0112 shall apply to new" is the whole
    # line, and the rest of the sentence is on the next one. Unmarked it reads
    # as a sentence the code left unfinished.
    if not body.endswith(("…", ".", ";", ":", "!", "?", "·")):
        body += "…"
    return body


def _named_in(ref: str, line: str, nxt: str = "") -> tuple[str, str]:
    """What the code calls this reference, from a sentence that cites it.

    Both halves of the name. Portland's tree rules are Title 11, not Section
    11, and a card that prints the wrong noun is telling a reviewer the
    document is something other than what it is -- a title is a whole body of
    code and a section is a paragraph of one.

    Returns empty rather than guessing. A wrong title is worse than none: it is
    the first thing on the card, and a reviewer who trusts it stops reading.
    """
    pattern = _TITLE.pattern % re.escape(ref)
    found = re.search(pattern, line)
    if not found:
        return "", ""
    # A title that runs to the end of its line is a title the extraction broke
    # in half. Gresham 10.1520 ends its line on "Reduction in" and finishes on
    # the next -- taken from one line it reads "Reduction", which is a wrong
    # title rather than a short one.
    if nxt and found.end() >= len(line.rstrip()) - 1:
        joined = re.search(pattern, f"{line.rstrip()} {nxt.strip()}")
        found = joined or found
    title = " ".join(found.group("title").split())
    cut = _TITLE_STOP.search(title)
    if cut:
        title = title[: cut.start()].strip()
    title = title.rstrip(",.;:").strip()
    words = title.split()
    while words and words[-1].lower() in _DANGLING:
        words.pop()
    title = " ".join(words)
    kind = found.group("kind").title()
    return (kind, title) if len(title) > 3 else (kind, "")


#: Where one sentence ends and the next begins. A full stop, then space, then
#: something that starts a sentence. Written to miss "33.236" and "Section
#: 7.0420." followed by a lower-case word, because splitting inside a citation
#: is how a quote comes to end on the number it was shown for.
_SENTENCE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(]|\d+\.\d)")

#: A section heading on a line of its own: the number, then a short title, no
#: full stop. Portland prints "33.110.227 Trees" above the paragraph it names,
#: and joining that to the sentence under it produces "Trees Requirements for
#: street trees" -- a heading read as the first two words of a sentence, and
#: three chapters saying the same thing under three different numbers reading
#: as three different things.
_HEADING = re.compile(r"^\d+\.\d[\d.]*\s+[A-Z][^.]{0,70}$")

#: How far either side of a mention to look for the rest of its sentence. An
#: extractor wraps at the page width, so a sentence is rarely more than two or
#: three lines, and reaching further starts joining unrelated paragraphs.
_REACH = 3


def _passage(body: Sequence[str], n: int, start: int, end: int, ref: str) -> str:
    """A mention as a sentence, not as the slice of a line it landed on.

    An extractor breaks lines at the page width, not at the full stop, so the
    line a reference sits on routinely begins and ends mid-clause: "dangerous
    by an arborist, and a Title 11 tree permit must be obtained.  If a". Shown
    like that a card reads as broken English and a reviewer cannot tell
    whether the sentence was cut by us or by the code.

    So prose is rejoined across the wrap and cut back to the sentence holding
    the reference. Grid rows are left alone -- a table row's horizontal spacing
    is the only record of which column a number belonged to, and joining one to
    its neighbours makes three rows look like one.
    """
    line = body[n - 1]
    if is_grid(line):
        return _window(line, start, end)

    def stop(text: str) -> bool:
        """Whether a neighbouring line belongs to a different passage."""
        return (
            not text.strip()
            or is_grid(text)
            or bool(_HEADING.match(text.strip()))
        )

    lo = n - 1
    while lo > 0 and n - lo <= _REACH:
        if stop(body[lo - 1]):
            break
        lo -= 1
    hi = n
    while hi < len(body) and hi - n < _REACH:
        if stop(body[hi]):
            break
        hi += 1

    # Where the mention lands once the window is one string.
    head = " ".join(legible(x) for x in body[lo : n - 1] if x.strip())
    joined = " ".join(legible(x) for x in body[lo:hi] if x.strip())
    at = joined.find(ref, max(0, len(head) - 1))
    if at < 0:
        at = joined.find(ref)
    if at < 0:
        return _window(line, start, end)

    cuts = [0] + [m.end() for m in _SENTENCE.finditer(joined)] + [len(joined)]
    left = max((c for c in cuts if c <= at), default=0)
    right = min((c for c in cuts if c >= at + len(ref)), default=len(joined))
    body_text = joined[left:right].strip()
    if len(body_text) > SNIPPET:
        return _window(joined, at, at + len(ref))
    # The ellipsis means "this is a fragment", not "there was other text
    # nearby". Marking on position put one in front of a sentence that began
    # exactly where it should, and left one off a fragment that began mid-word
    # because the line above it was a table.
    lead = "…" if body_text[:1].islower() else ""
    tail = "" if body_text.endswith((".", ";", ":", "!", "?")) else "…"
    return f"{lead}{body_text}{tail}"


def _same(text: str) -> str:
    """A key on which two renderings of one sentence are one sentence.

    Portland states its tree requirement identically in three chapters and the
    card called it three different things: the extractor had written "on -site"
    in one of them, and each carried its own section number. Neither is a
    difference in what the code says, and a card that reports nine different
    statements where there are five is inflating its own evidence.

    Punctuation and case go too. What is left is the words.
    """
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _title_in(ref: str, line: str, nxt: str = "") -> str:
    """Just the title. The noun is :func:`_named_in`."""
    return _named_in(ref, line, nxt)[1]


def _below_a_section(ref: str) -> bool:
    """Whether this "reference" is a number smaller than any section.

    No code in this corpus numbers a section below 1, and every extracted
    dimensional table is full of ratios that look like one: Portland's floor
    area ratio column reads "0.7 to 1", and "0.7" led the entire queue at
    147,192 lots because it sits in the middle of the residential standards
    table.

    Narrow on purpose. It rejects a shape no section number has rather than
    guessing at which numbers look untrustworthy -- ``11`` is Portland's Title
    11, Trees, and is real.
    """
    head, _, _ = ref.partition(".")
    return head.isdigit() and int(head) == 0


def _zone_key(zone: str) -> tuple[object, ...]:
    """Sort a zone name the way a planner reads it.

    Zone names are a letter and a number and the number is a density, so plain
    string order prints Portland's residential zones "R10, R2.5, R20, R5, R7"
    -- which looks like a list nobody checked, and buries the fact that they
    run smallest lot to largest.
    """
    out: list[object] = []
    for part in re.split(r"(\d+(?:\.\d+)?)", zone):
        if not part:
            continue
        try:
            out.append((1, float(part), ""))
        except ValueError:
            out.append((0, 0.0, part.upper()))
    return tuple(out)


def _lots_by_zone() -> dict[tuple[str, str], int]:
    rows = read_coverage() or []
    out: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        out[(r.jurisdiction, r.zone)] += r.lots
    return dict(out)


def _num(x: object) -> str:
    """A figure with thousands separators and no trailing ``.0``."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return str(x)
    return f"{int(x):,}" if float(x).is_integer() else f"{x:,}"


def _curve(rows: Sequence[Sequence[float]]) -> str:
    """A tiered coverage table, said out loud.

    Stored as ``[floor, base, pct]`` triples and read by
    ``flats.score.screen._coverage_allowed_sqft`` as: on a lot at or above
    ``floor``, the footprint may be ``base`` square feet plus ``pct`` of
    everything above ``floor``. Printed as the raw list it is four nested
    brackets that a reviewer has to decode before they can answer the card's
    question, and truncated at forty-four characters it is three of them.
    """
    parts = []
    for row in rows:
        if len(row) != 3:
            return str(list(rows))
        floor, base, pct = row
        head = "any lot" if not floor else f"from {_num(floor)} sqft"
        parts.append(f"{head}: {_num(base)} sqft + {_num(pct)}% of the excess")
    return "; ".join(parts)


def _shown(value: object) -> str:
    """A value as a reviewer needs to see it, not as it is stored."""
    v = getattr(value, "value", None)
    if v is None:
        return "no figure" if getattr(value, "exempt", False) else "—"
    if v is True:
        return "yes"
    if v is False:
        return "no"
    if isinstance(v, (int, float)):
        return _num(v)
    if isinstance(v, (list, tuple)) and v:
        if all(isinstance(r, (list, tuple)) for r in v):
            return _curve(v)
        return ", ".join(_num(x) for x in v)
    text = str(v)
    return text if len(text) <= 44 else text[:41] + "..."


def _cited_values(layer: Layer) -> dict[str, dict[int, list[tuple[str, str, str]]]]:
    """Per document, per line, the encoded values read from that line.

    The counterpart of :func:`flats.encode.crossrefs._cited_lines`, which
    answers "was anything read here" and discards what. Everything a reviewer
    needs to judge a reference is in what it discards.
    """
    out: dict[str, dict[int, list[tuple[str, str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    def take(quote: str | None, zone: str, field: str, value: object) -> None:
        if not quote:
            return
        try:
            ref = parse_quote(quote)
        except Exception:
            return
        for n in ref.numbers:
            out[ref.path][n].append((zone, field, _shown(value)))

    for field, value in layer.defaults.items():
        take(value.prov.quote, "(all zones)", field, value)
    for zone in layer.zones.values():
        if zone.like is not None:
            take(zone.like.prov.quote, zone.zone, "(borrowed from)", zone.like)
        for field, value in zone.values.items():
            take(value.prov.quote, zone.zone, field, value)
            take(value.step_back_quote, zone.zone, field, value)
            take(value.measured_on_quote, zone.zone, field, value)
            take(value.qualified_quote, zone.zone, field, value)
            for variant in value.variants:
                take(variant.prov.quote, zone.zone, field, value)
    return out


#: Scanned cards per layer, without rulings attached. The scan reads every
#: stored document and runs the reference regex over every line -- four
#: seconds for the corpus, which is fine once and not fine per page load. What
#: changes while somebody works the queue is the *rulings*, and those are read
#: from the loaded layer on every call rather than cached, so a decision shows
#: up immediately and a re-scan is never needed to see it.
_SCANNED: dict[str, tuple[Card, ...]] = {}


def refresh(layer_id: str | None = None) -> None:
    """Drop the scan cache — call after fetching a document into the store."""
    if layer_id is None:
        _SCANNED.clear()
    else:
        _SCANNED.pop(layer_id, None)


def cards(
    layer: Layer,
    store: ProvenanceStore | None = None,
    overrides: Mapping[tuple[str, str], Ruling] | None = None,
) -> list[Card]:
    """Every unfetchable city-code reference this layer makes, as a worklist.

    ``overrides`` carries rulings that exist outside the rule files — the
    review inbox, where a decision made in a browser lands before the drain
    writes it into the repository. They are applied here rather than filtered
    afterwards, because "hide the rows already ruled" happens downstream and a
    ruling the feed cannot see is a row the reviewer answers twice.
    """
    scanned = _SCANNED.get(layer.layer)
    if scanned is None:
        scanned = tuple(_scan(layer, store))
        _SCANNED[layer.layer] = scanned
    extra = overrides or {}
    family = _nesting(tuple(c.ref for c in scanned))
    return [
        Card(
            layer=c.layer,
            ref=c.ref,
            mentions=c.mentions,
            neighbours=c.neighbours,
            zone_lots=c.zone_lots,
            title=c.title,
            kind=c.kind,
            inside=family[c.ref][0],
            contains=family[c.ref][1],
            ruling=extra.get((c.layer, c.ref)) or layer.crossrefs.get(c.ref),
        )
        for c in scanned
    ]


def _nesting(refs: Sequence[str]) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Which references in this queue sit inside which others.

    Codes number by containment -- Portland's Chapter 11.50 is inside its
    Title 11, and 195 of 1,446 cards have a parent somewhere in the same
    queue. Ruling the parent answers the child, and the two arrived back to
    back showing identical lots and identical sentences, so a reviewer
    answered the same question twice without being told it was the same
    question.

    Not merged. Fetching a title and fetching one chapter of it are different
    fetches, and a code can publish a chapter separately. Named, so the
    decision is made once knowingly rather than twice unknowingly.
    """
    out: dict[str, tuple[str, tuple[str, ...]]] = {}
    for ref in refs:
        parents = [p for p in refs if p != ref and ref.startswith(p + ".")]
        # The nearest one. A section inside a chapter inside a title has two,
        # and the useful one is the smallest thing that already covers it.
        parent = max(parents, key=len) if parents else ""
        kids = tuple(sorted(k for k in refs if k != ref and k.startswith(ref + ".")))
        out[ref] = (parent, kids)
    return out


def _scan(layer: Layer, store: ProvenanceStore | None = None) -> list[Card]:
    """The document read. Expensive, and independent of any ruling."""
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
        headings |= _headings(text, {i.partition(".")[0] for i in own}, own)

    cited = _cited_values(layer)
    lots = _lots_by_zone()

    mentions: dict[str, list[Mention]] = defaultdict(list)
    near: dict[str, dict[tuple[str, str], tuple[int, str]]] = defaultdict(dict)
    #: Titles are read from the whole line. The window shown on the card is
    #: centred on the reference and routinely cuts a title in half -- Gresham
    #: 10.1520 came back as "Reduction" when the code calls it "Reduction in
    #: Minimum Street Frontage". Reading the display text would ship that.
    titles: dict[str, str] = {}
    kinds: dict[str, str] = {}

    for path, text in texts.items():
        here = cited.get(path, {})
        name = Path(path).name
        body = text.splitlines()
        for n, line in enumerate(body, start=1):
            hits = list(_REF.finditer(line))
            if not hits:
                continue
            for m in hits:
                ref = (
                    m.group("named") or m.group("abbrev") or m.group("dotted")
                ).rstrip(".")
                if not ref or (ref.isdigit() and len(ref) < 2):
                    continue
                if _resolves(ref, ids, headings):
                    continue
                if _below_a_section(ref):
                    continue
                if ref not in titles:
                    found_kind, found_title = _named_in(
                        ref, line, body[n] if n < len(body) else ""
                    )
                    if found_kind:
                        kinds.setdefault(ref, found_kind)
                    if found_title:
                        titles[ref] = found_title

                found = [
                    (abs(n - at), zone, field, shown)
                    for at, rows in here.items()
                    if abs(n - at) <= BINDING_WINDOW
                    for zone, field, shown in rows
                ]
                mentions[ref].append(
                    Mention(
                        doc=name,
                        line=n,
                        text=_passage(body, n, m.start(), m.end(), ref),
                        binding=bool(found),
                    )
                )
                for distance, zone, field, shown in found:
                    slot = near[ref].get((zone, field))
                    if slot is None or distance < slot[0]:
                        near[ref][(zone, field)] = (distance, shown)

    out = []
    for ref, seen in mentions.items():
        # Collapse to one row per standard-and-figure, carrying the zones that
        # share it. Nearest mention wins the distance; lots are summed over
        # distinct zones.
        grouped: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
        zone_lots: dict[str, int] = {}
        for (zone, field), (distance, shown) in near[ref].items():
            grouped[(field, shown)].append((zone, distance))
            zone_lots[zone] = lots.get((layer.layer, zone), 0)

        neighbours = tuple(
            sorted(
                (
                    Neighbour(
                        field=field,
                        shown=shown,
                        zones=tuple(
                            z for z, _ in sorted(zones, key=lambda x: _zone_key(x[0]))
                        ),
                        distance=min(d for _, d in zones),
                        lots=sum(zone_lots[z] for z, _ in zones),
                    )
                    for (field, shown), zones in grouped.items()
                ),
                key=lambda n: (-n.lots, n.field, n.shown),
            )
        )
        out.append(
            Card(
                layer=layer.layer,
                ref=ref,
                mentions=tuple(seen),
                neighbours=neighbours,
                zone_lots=tuple(sorted(zone_lots.items())),
                title=titles.get(ref, ""),
                kind=kinds.get(ref, "Section"),
                ruling=layer.crossrefs.get(ref),
            )
        )
    out.sort(key=lambda c: (tuple(-x for x in c.rank), c.ref))
    return out


def feed(
    *,
    layer: str | None = None,
    field: str | None = None,
    doc: str | None = None,
    outcome: str | None = None,
    binding_only: bool = False,
    ruled: bool = False,
    overrides: Mapping[tuple[str, str], Ruling] | None = None,
    store: ProvenanceStore | None = None,
) -> list[Card]:
    """The worklist, filtered the four ways a reviewer picks a session.

    ``layer`` is "Gresham today", ``field`` is "setbacks everywhere", ``doc``
    is "I have this chapter open", ``outcome`` is "show me what I called a
    procedure last month". They compose.

    Ruled rows are hidden by default and are never *deleted* from the feed --
    ``ruled=True`` brings them back, because a decision that cannot be found
    again is a decision nobody can overturn.
    """
    store = store or ProvenanceStore()
    layers = load_rules()
    chosen = (
        [layers[layer]] if layer else [v for k, v in sorted(layers.items())]
    )

    rows: list[Card] = []
    for lay in chosen:
        rows.extend(cards(lay, store, overrides))

    if not ruled:
        rows = [c for c in rows if c.open]
    if outcome:
        rows = [c for c in rows if c.outcome == outcome]
    if binding_only:
        rows = [c for c in rows if c.binding]
    if field:
        rows = [c for c in rows if field in c.fields]
    if doc:
        rows = [c for c in rows if any(doc in d for d in c.docs)]

    rows.sort(key=lambda c: (tuple(-x for x in c.rank), c.layer, c.ref))
    return rows


def fields_in(rows: Iterable[Card]) -> list[tuple[str, int]]:
    """Which fields the feed touches, commonest first — the filter's own menu."""
    counts: dict[str, int] = defaultdict(int)
    for card in rows:
        for f in card.fields:
            counts[f] += 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def render(rows: Sequence[Card], *, limit: int = 20) -> str:
    """The feed as a person reads it at a terminal."""
    out: list[str] = []
    for card in rows[:limit]:
        head = f"{card.layer}  {card.ref}"
        if card.ruling is not None:
            head += f"   [{card.ruling.outcome}]"
        out.append(head)
        out.append(
            f"    {card.lots:,} lots · binds {card.binding}× · "
            f"{len(card.mentions)} mention(s) · {', '.join(card.docs)}"
        )
        for n in card.neighbours[:4]:
            out.append(f"      beside  {n.label}  ({n.lots:,} lots, {n.distance} lines)")
        if len(card.neighbours) > 4:
            out.append(f"      beside  … and {len(card.neighbours) - 4} more")
        for m in card.mentions[:2]:
            out.append(f"      “{m.text[:120]}”  — {m.doc}:{m.line}")
        out.append("")

    shown = min(limit, len(rows))
    out.append(
        f"{len(rows)} reference(s) in the feed, {shown} shown · "
        f"{sum(1 for c in rows if c.binding)} binding · "
        f"{sum(c.lots for c in rows):,} lots behind them"
    )
    return "\n".join(out)


# --------------------------------------------------------------------------
# Recording a decision
# --------------------------------------------------------------------------
#
# Jurisdiction files are hand-written and full of prose: the notes explaining
# why a zone is encoded the way it is are the most valuable text in this
# repository. So a ruling is spliced in as text and never round-tripped
# through a YAML dumper, which would reflow every block scalar and drop every
# comment in the file. The splice is verified by reloading the layer, and the
# file is restored if the reload fails.

CONFIG = Path(__file__).resolve().parents[1] / "config" / "jurisdictions"

#: Where the crossrefs block goes when a file has none: before the first of
#: these top-level keys, so it lands beside the other layer-wide bookkeeping
#: rather than after two thousand lines of zones.
_AFTER = ("zones:", "defaults:", "code:", "definitions:")

NEWLINE = chr(10)


def _key(line: str) -> str:
    """The section number a crossrefs entry line names, or empty.

    Entries sit at one indent under the block and may be quoted or bare;
    anything deeper belongs to the entry above it.
    """
    if not line.startswith("  ") or line.startswith("   "):
        return ""
    head = line.strip()
    if not head.endswith(":"):
        return ""
    return head[:-1].strip().strip(chr(34)).strip(chr(39))


def _wrap(text: str, width: int = 92, indent: str = "      ") -> list[str]:
    words, lines, row = text.split(), [], ""
    for word in words:
        if row and len(row) + 1 + len(word) > width:
            lines.append(indent + row)
            row = word
        else:
            row = f"{row} {word}".strip()
    if row:
        lines.append(indent + row)
    return lines


def layer_path(layer_id: str) -> Path:
    """The jurisdiction file for a layer id, or raise.

    The id arrives from a browser form and everything past this point writes,
    so it is checked twice rather than sanitised once.

    The real constraint is that the id must name a layer the loader actually
    holds -- a set of seventeen strings, not a shape. Pattern-matching a path
    fragment would accept ``or/multnomah/../../../etc/hosts`` on the days the
    pattern is slightly wrong, and there is no reason to guess when the
    authoritative list is already in memory.

    The containment check behind it is not redundant. It is what holds if the
    keyset is ever loosened, or fed from a directory walk instead of a parse,
    and it costs one resolve.
    """
    if layer_id not in load_rules():
        raise ValueError(f"not a layer we hold: {layer_id!r}")
    root = CONFIG.resolve()
    path = (root / f"{layer_id}.yaml").resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"outside the rule tree: {layer_id!r}")
    return path


def _entry(ref: str, outcome: str, note: str) -> list[str]:
    return [
        f'  "{ref}":',
        f"    outcome: {outcome}",
        "    note: >-",
        *_wrap(" ".join(note.split())),
    ]


def _splice(lines: list[str], ref: str, outcome: str, note: str) -> list[str]:
    """Put one ruling into the file's lines, replacing any ruling already there."""
    entry = _entry(ref, outcome, note)

    start = next(
        (i for i, ln in enumerate(lines) if ln.rstrip() == "crossrefs:"), None
    )
    if start is None:
        at = next(
            (
                i
                for i, ln in enumerate(lines)
                if any(ln.startswith(k) for k in _AFTER)
            ),
            len(lines),
        )
        return lines[:at] + ["crossrefs:", *entry, ""] + lines[at:]

    stop = start + 1
    while stop < len(lines) and (
        not lines[stop].strip() or lines[stop].startswith((" ", "	", "#"))
    ):
        stop += 1

    body = lines[start + 1 : stop]
    here = next(
        (
            i
            for i, ln in enumerate(body)
            if _key(ln) == ref
            and not ln.startswith("   ")
        ),
        None,
    )
    if here is None:
        body = body + entry
    else:
        end = here + 1
        while end < len(body) and (
            not body[end].strip() or body[end].startswith("    ")
        ):
            end += 1
        body = body[:here] + entry + body[end:]

    return lines[: start + 1] + body + lines[stop:]


def rule(layer_id: str, ref: str, outcome: str, note: str) -> Path:
    """Record one triage decision in the jurisdiction file, or raise.

    Raises rather than writing a file the loader will reject, because a rule
    file that does not load takes every jurisdiction down with it -- the loader
    accumulates problems across the whole corpus and refuses the set.
    """
    if outcome not in CROSSREF_OUTCOMES:
        raise ValueError(
            f"unknown outcome {outcome!r}; one of {', '.join(sorted(CROSSREF_OUTCOMES))}"
        )
    note = " ".join(note.split())
    if len(note) < MIN_RULING:
        raise ValueError(
            f"a ruling needs at least {MIN_RULING} characters of reasoning; "
            f"got {len(note)}"
        )

    path = layer_path(layer_id)
    if not path.exists():
        raise FileNotFoundError(path)

    before = path.read_text(encoding="utf-8")
    lines = before.splitlines()
    spliced = _splice(lines, ref, outcome, note)
    path.write_text(NEWLINE.join(spliced) + NEWLINE, encoding="utf-8")
    try:
        load_rules.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    try:
        got = load_rules()[layer_id].crossrefs.get(ref)
        if got is None or got.outcome != outcome:
            raise ValueError(f"ruling did not take on {layer_id} {ref}")
    except Exception:
        path.write_text(before, encoding="utf-8")
        try:
            load_rules.cache_clear()  # type: ignore[attr-defined]
        except AttributeError:
            pass
        raise
    return path


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--layer")
    ap.add_argument("--field")
    ap.add_argument("--doc")
    ap.add_argument("--outcome", choices=sorted(CROSSREF_OUTCOMES))
    ap.add_argument("--binding", action="store_true")
    ap.add_argument("--ruled", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--fields", action="store_true", help="the field filter's menu")
    args = ap.parse_args(argv)

    rows = feed(
        layer=args.layer,
        field=args.field,
        doc=args.doc,
        outcome=args.outcome,
        binding_only=args.binding,
        ruled=args.ruled,
    )
    if args.fields:
        for name, count in fields_in(rows):
            print(f"{name:34s} {count:5d}")
        return 0
    print(render(rows, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
