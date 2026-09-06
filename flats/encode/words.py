"""What the words in our numbers mean *in this city* — the review under signing.

Signing asks "does this number match the sentence it was taken from". It is
the right question and it is not the first one. A number is only as meaningful
as the words the sentence measures it in, and these codes define ordinary words
their own way: :mod:`flats.rules.definitions` found four cities giving four
incompatible tests for *corner lot*, and :mod:`flats.encode.glossary` found
seven giving seven different subtraction lists for *net acre*. Sign three
hundred numbers first and then learn that a city measured lot width across the
building line rather than the frontage, and some of that signing has to be done
again. So this queue sits **underneath** the signing queue, and is worked first.

**A card is one word in one jurisdiction, not one word.** The whole finding is
that the same word means different things in different books, so a ruling that
spanned jurisdictions would erase exactly what is being reviewed. Answer
"lot width" once for Gresham and it settles every Gresham number measured in
lot widths; Portland still has to be asked.

**Only words that carry weight get asked about.** A city's glossary runs to
several hundred entries -- 4,349 across the corpus -- and almost none of them
touch a dimension we screen on. :data:`GOVERNS` names the words that set the
meaning of a field we actually encode, and a card exists only where this
jurisdiction holds at least one value on one of those fields. A word nothing
we hold is measured in is somebody else's problem.

**Three standings, and they are not the same instruction.** ``defined`` is the
ordinary case: the city says what it means and a reviewer can compare it to how
we measure. ``silent`` is a finding *about the code* -- the definitions chapter
is on disk and this word is not in it, so nothing here can be assumed and the
reviewer is being asked whether that costs us anything. ``unread`` is a finding
about *us*: no glossary has been read for this jurisdiction, so the word may
well be defined and nobody has looked. Collapsing the last two would hide the
difference between "the code is quiet" and "we did not open the book", which
are opposite pieces of news.

**A silence is not the end of the answer.** A card that reports only that the
glossary has no entry hands the reviewer a hunt through every document we
hold, and the corpus usually already knows where to look, because the code
says so out loud: Portland defines neither *lot width* nor *building height*
and its own text sends the reader to "Chapter 33.930, Measurements" for both.
So every card carries a few of the lines that write the word, with the ones
that hand it to another chapter on top -- and the reviewer answers with a
chapter number in one click instead of twenty minutes. Those lines are context
and are deliberately outside the fingerprint: they are how the word gets
*used*, not what the city says it *means*.
"""

from __future__ import annotations

import hashlib
import re
from bisect import insort
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from flats.encode import glossary
from flats.encode.crossrefs import _HEADING, _REF
from flats.rules.fields import FIELDS
from flats.rules.loader import load_rules
from flats.rules.model import WORD_CLOSED, Layer, Reading

#: Which of our fields a word sets the meaning of.
#:
#: Derived from the 32 fields actually encoded in the corpus, not from the
#: field registry in full: a word governing a standard nobody has encoded
#: anywhere cannot change a number, and asking about it would be inventing
#: work. Each entry answers one question -- *if this city defines this word
#: unusually, which of our numbers are measured wrong?* -- and a field appears
#: under every word that can move it, because a front setback depends both on
#: what a yard is and on which line it is measured from.
GOVERNS: dict[str, tuple[str, ...]] = {
    # The denominator words. These do not change a standard's number, they
    # change what the number is divided by, which is the same thing in effect
    # and much easier to miss. Seven codes subtract seven different lists from
    # a "net acre" -- see the measured_on invariant in flats.rules.model.
    "lot area": (
        "min_lot_sqft",
        "max_coverage_pct",
        "coverage_curve",
        "max_far",
        "min_landscaped_pct",
        "open_space_min_pct",
        "open_space_min_sqft",
        "min_density_du_per_acre",
        "max_density_du_per_acre",
        "min_density_trigger_lot_sqft",
    ),
    "net acre": (
        "max_density_du_per_acre",
        "min_density_du_per_acre",
    ),
    "density": (
        "max_density_du_per_acre",
        "min_density_du_per_acre",
        "min_units_at_trigger",
    ),
    # The shape words. A lot's width is not one measurement: some codes take it
    # at the front line, some at the building line, some as a mean of the two
    # side lines. The pod has a fixed footprint, so this is load-bearing.
    "lot width": ("min_lot_width_ft", "max_building_width_ft"),
    "lot depth": ("min_lot_depth_ft", "max_lot_depth_ratio"),
    "lot line": (
        "setback_front_ft",
        "setback_front_max_ft",
        "setback_rear_ft",
        "setback_side_ft",
        "setback_side_total_ft",
        "setback_street_side_ft",
        "setback_garage_entrance_ft",
        "parking_street_setback_ft",
    ),
    "frontage": ("min_frontage_ft", "setback_front_ft", "setback_street_side_ft"),
    # The setback words. Front, rear and side are three separate entries
    # because a code can define one carefully and leave the others to custom,
    # and a single "yard" card would let a reviewer close all three on the
    # strength of the one they read.
    "yard": (
        "setback_front_ft",
        "setback_front_max_ft",
        "setback_rear_ft",
        "setback_side_ft",
        "setback_side_total_ft",
        "setback_street_side_ft",
    ),
    "front yard": ("setback_front_ft", "setback_front_max_ft", "setback_garage_entrance_ft"),
    "rear yard": ("setback_rear_ft",),
    "side yard": ("setback_side_ft", "setback_side_total_ft"),
    "street side yard": ("setback_street_side_ft",),
    "setback": (
        "setback_front_ft",
        "setback_front_max_ft",
        "setback_rear_ft",
        "setback_side_ft",
        "setback_side_total_ft",
        "setback_street_side_ft",
        "setback_garage_entrance_ft",
        "parking_street_setback_ft",
    ),
    # The height words. Where height is measured *from* is the whole question
    # on a sloped lot, and Happy Valley's slope mask exists because of it.
    "building height": ("max_height_ft", "max_height_stories"),
    "story": ("max_height_stories", "max_height_ft"),
    "grade": ("max_height_ft",),
    # The bulk words.
    "lot coverage": ("max_coverage_pct", "coverage_curve"),
    "floor area": ("max_far",),
    "building": (
        "min_building_separation_ft",
        "max_building_width_ft",
        "setback_garage_entrance_ft",
    ),
    # The count words. What counts as a dwelling unit decides whether our pod
    # is four of them, and every per-unit standard rests on it.
    "dwelling unit": (
        "max_units",
        "min_units_at_trigger",
        "parking_min_per_unit",
        "parking_max_per_unit",
        "max_density_du_per_acre",
        "min_density_du_per_acre",
        "quadplex_allowed",
    ),
    "middle housing": ("quadplex_allowed",),
    "townhouse": ("quadplex_allowed",),
    # The access words. A stall's size and an aisle's width are the assumed-24ft
    # argument; a street that is not a street changes what fronts on what.
    "parking space": ("parking_min_per_unit", "parking_max_per_unit"),
    "street": (
        "min_frontage_ft",
        "setback_front_ft",
        "setback_street_side_ft",
        "parking_street_setback_ft",
    ),
    "alley": ("min_frontage_ft", "setback_rear_ft"),
    "landscaping": ("min_landscaped_pct",),
    "open space": ("open_space_min_pct", "open_space_min_sqft"),
}

#: Other spellings of the same word, where a code's own wording differs from
#: ours. Matching is on words rather than characters -- a glossary files its
#: entries the way an index does, "Lot, Width" for what the code then writes as
#: "lot width" -- so only genuinely different *words* belong here, not
#: inversions or plurals, which are handled.
SPELLINGS: dict[str, tuple[str, ...]] = {
    "lot area": ("lot size", "site area", "area of lot"),
    "net acre": ("net developable area", "net area", "net acreage", "net site area"),
    "lot coverage": ("building coverage", "site coverage", "coverage"),
    "floor area": ("gross floor area", "floor area ratio"),
    "building height": ("height", "height of building"),
    "dwelling unit": ("dwelling",),
    "parking space": ("parking stall", "off street parking space", "vehicle space"),
    "street side yard": ("exterior side yard", "corner side yard", "street yard"),
    "lot line": ("property line", "front lot line", "rear lot line", "side lot line"),
    "grade": ("finished grade", "natural grade", "average grade", "base point"),
    "story": ("storey", "half story"),
    "middle housing": ("middle housing dwelling unit",),
    "landscaping": ("landscape area", "landscaped area"),
}

_NOT_WORD = re.compile(r"[^a-z0-9 ]+")
_SPACE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _SPACE.sub(" ", _NOT_WORD.sub(" ", (text or "").lower())).strip()


def _stem(word: str) -> str:
    """Crude singular. Codes headline "Corner Lots" and define "Corner Lot"."""
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _bag(text: str) -> frozenset[str]:
    """A phrase as the set of its stems, which is how a glossary is indexed.

    "Lot, Corner" and "Corner Lot" are the same entry filed two ways, and the
    order carries no meaning -- the comma inversion IS the index form. Comparing
    word sets rather than strings is what reads both without a rule per code.
    """
    return frozenset(_stem(w) for w in _norm(text).split() if w)


def spellings(term: str) -> list[str]:
    """Every way this word is written, ours first."""
    return [term, *SPELLINGS.get(term, ())]


def forms(term: str) -> list[frozenset[str]]:
    """Every word-set that counts as this term being defined."""
    return [_bag(s) for s in spellings(term)]


def _seqs(term: str) -> list[tuple[str, ...]]:
    """The same, as ordered stems, for finding a word inside a longer entry."""
    return [tuple(_stem(w) for w in _norm(s).split() if w) for s in spellings(term)]


def _contains(entry: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    """Whether an entry's term carries this word as a run of whole words.

    Portland files "Site Frontage" and "Front Lot Line", not "frontage" and
    "lot line", and a code that only defines the specific flavour has still
    defined the word. Matching on whole stems in order is what separates that
    from "Streetcar Line", which shares four letters with *street* and nothing
    else.
    """
    n = len(phrase)
    return n > 0 and any(entry[i : i + n] == phrase for i in range(len(entry) - n + 1))


#: Where stored code text lives, one directory per layer id. Same root as
#: :mod:`flats.encode.definitions`; the question here is different (does this
#: code lean on the word) but the corpus is the one on disk, not the one
#: declared.
DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"


def _flex(phrase: str) -> str:
    """A phrase as it appears in running code text: plural, any spacing.

    Bounded at both ends, and the boundaries are not decoration. Without them
    *alley* matched inside "Pleasant Valley" and "Happy Valley" -- so Gresham
    and Happy Valley were credited with hundreds of uses of a word about
    vehicle access on the strength of their own place names, the usage gate
    passed on that, and the lines the card offered as evidence were about
    solar energy systems and tree removal plans.

    A vowel before the final *y* takes a plain -s: the plural of *alley* is
    alleys, and only *story* becomes stories. Spelling both the same way cost
    the word about vehicle access every plural sentence in the corpus.
    """
    out = []
    for word in _norm(phrase).split():
        if word.endswith("y") and len(word) > 3 and word[-2] not in "aeiou":
            out.append(re.escape(word[:-1]) + "(?:y|ies)")
        elif word.endswith("s"):
            out.append(re.escape(word))
        else:
            out.append(re.escape(word) + "s?")
    return r"\b" + r"\s+".join(out) + r"\b"


#: The verbs that hand a word's meaning to another chapter.
#:
#: Deliberately the list :mod:`flats.encode.routing` refuses. That ledger is
#: hunting sentences that *replace a standard* -- "instead of", "supersedes" --
#: and it excludes "see" and "as defined in" because admitting them would
#: report every chapter in the store. Here they are the whole point: the
#: question a word card asks is where this code settles what a word means, and
#: "See 33.930.100" is the code answering it in as many words.
_DEFERS = re.compile(
    r"\b(?:see|refer to|in accordance with|pursuant to|according to"
    r"|as (?:defined|described|measured|provided|specified|set forth|listed|used)"
    r"|(?:standards?|requirements?|provisions?|purposes?|definitions?) of"
    r"|(?:defined|described|specified|measured|listed|stated|regulated) in"
    r"|is governed by|are governed by|subject to)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class Mention:
    """One line of this jurisdiction's own code that writes the word."""

    doc: str
    line: int
    text: str
    #: Chapters or sections this line hands the reader to. Non-empty is the
    #: interesting case and the reason mentions are shown at all.
    sends: tuple[str, ...] = ()


#: How many mentions of each kind a card keeps. Two handfuls: enough to show
#: how a code uses a word, few enough that the card stays a card. Deferrals
#: are kept apart from plain uses because they answer a different question --
#: not "what does this look like in use" but "where has this code put the
#: answer".
KEEP = 4


#: The chapter a stored document *is*, read off its own filename. Every
#: document in this store is filed under the chapter it holds -- "33.130.txt",
#: "33.910.definitions.txt" -- which is what makes an intra-chapter pointer
#: tellable from a hand-off to another book.
_CHAPTER = re.compile(r"^(\d+(?:\.\d+)*)")


def _home(doc: str) -> str:
    """The chapter this document holds, or "" if its name does not say."""
    found = _CHAPTER.match(doc)
    return found.group(1) if found else ""


def _away(home: str, sends: Sequence[tuple[str, int]]) -> bool:
    """Whether this line sends the reader out of the chapter they are in.

    The distinction that matters on a word card. Portland's height table
    prints "Base Height (see 33.130.210.B.1)" -- a pointer to a subsection of
    the chapter already open, which tells a reviewer nothing they did not have.
    Four lines away the same chapter says height is "stated in Chapter 33.930,
    Measurements", and that is the sentence the card exists to surface. Both
    are references sitting next to the word; only one leaves the book.
    """
    if not home:
        return True
    return any(
        not (ref == home or ref.startswith(f"{home}.")) for ref, _ in sends
    )


def _sends(line: str) -> tuple[tuple[str, int], ...]:
    """Where this line hands the reader, if it hands them anywhere.

    A reference alone is not a hand-off: a section prints its own number at
    the head of its own heading, and "33.130.200 Lot Size" sends nobody
    anywhere. So the line's own heading number is dropped, and what is left
    counts only beside a verb that defers -- which is the difference between
    a chapter mentioned in passing and the chapter this code says the answer
    is in.

    Each chapter comes back with where on the line it was raised, so a card
    can lead with the hand-off that is about *this word* rather than the one
    that happens to sit earliest in the document. Portland's tree chapter
    opens by citing four sections at once, and without that a card about
    density would put a tree plan above "See 33.930.100, Measurements".
    """
    if not _DEFERS.search(line):
        return ()
    head = _HEADING.match(line)
    mine = head.group("num").rstrip(".") if head else ""
    out: list[tuple[str, int]] = []
    seen: set[str] = set()
    for m in _REF.finditer(line):
        ref = (
            m.group("named") or m.group("abbrev") or m.group("dotted") or ""
        ).rstrip(".")
        if not ref or ref == mine or ref in seen or (ref.isdigit() and len(ref) < 2):
            continue
        seen.add(ref)
        out.append((ref, m.start()))
    return tuple(out)


def _scan(
    layer_id: str, terms: Sequence[str], *, keep: int = KEEP
) -> tuple[dict[str, int], dict[str, tuple[Mention, ...]]]:
    """Count and sample the lines of stored code that write each word.

    One pass. Counting and sampling separately would read every document
    twice for an answer the first pass already had, and ``keep=0`` is the
    counting-only case -- the usage gate does not want the samples and should
    not pay for finding them.
    """
    counts = dict.fromkeys(terms, 0)
    #: Deferrals ranked, ordinary uses in the order the code prints them. The
    #: first four uses of a word are the code being read from the top, which
    #: is the right way to meet it; the first four *deferrals* would be an
    #: accident of which document sorts first.
    ranked: dict[str, list[tuple[tuple[int, int], str, int, Mention]]] = {
        t: [] for t in terms
    }
    plain: dict[str, list[Mention]] = {t: [] for t in terms}

    directory = DOCS / layer_id
    if not directory.is_dir():
        return counts, {t: () for t in terms}

    patterns = {
        term: re.compile("|".join(_flex(s) for s in spellings(term)), re.I)
        for term in terms
    }
    for path in sorted(directory.glob("*.txt")):
        doc = path.name
        home = _home(doc)
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if len(line) < 4:
                continue
            hit = [(t, m) for t, p in patterns.items() if (m := p.search(line))]
            if not hit:
                continue
            sends: tuple[tuple[str, int], ...] | None = None
            for term, word in hit:
                counts[term] += 1
                if not keep:
                    continue
                if sends is None:
                    sends = _sends(line)
                if not sends:
                    if len(plain[term]) < keep:
                        plain[term].append(
                            Mention(doc=doc, line=number, text=" ".join(line.split()))
                        )
                    continue
                # Out of the chapter first, then by how far the nearest
                # chapter sits from the word itself. A sentence that names the
                # word and the chapter in the same breath is the hand-off; one
                # that cites four sections at the other end of the line is a
                # list that happens to contain it.
                gap = min(abs(at - word.start()) for _, at in sends)
                row = (
                    (0 if _away(home, sends) else 1, gap),
                    doc,
                    number,
                    Mention(
                        doc=doc,
                        line=number,
                        text=" ".join(line.split()),
                        sends=tuple(ref for ref, _ in sends),
                    ),
                )
                bucket = ranked[term]
                if len(bucket) < keep or row[:3] < bucket[-1][:3]:
                    insort(bucket, row, key=lambda r: r[:3])
                    del bucket[keep:]
    # Deferrals first. "See Chapter 33.930, Measurements" is the answer to the
    # question the card is asking; an ordinary use is only context for it.
    return counts, {
        t: tuple([r[3] for r in ranked[t]] + plain[t]) for t in terms
    }


def uses(layer_id: str, terms: Sequence[str]) -> dict[str, int]:
    """Lines of this jurisdiction's stored code that use each word.

    Usage is the gate, not the sort. Portland writes *setback* and never
    *yard*; asking a reviewer what Portland means by a yard is asking about a
    word its code does not contain, and a queue that does that teaches people
    to skip rows. A word this code never uses cannot be measuring one of our
    numbers, whatever our field names call it.
    """
    return _scan(layer_id, terms, keep=0)[0]


@dataclass(frozen=True, slots=True)
class Definition:
    """One entry from this jurisdiction's own glossary."""

    term: str
    text: str
    cite: str
    doc: str
    line: int


@dataclass(frozen=True, slots=True)
class Card:
    """One word, in one jurisdiction, with what the city says about it."""

    layer: str
    label: str
    term: str
    #: ``defined`` | ``silent`` | ``unread`` -- see the module docstring.
    standing: str
    #: The city's own entries for this word. More than one where a code files
    #: it under several headings ("Yard", "Yard, Front"), and all of them are
    #: shown, because picking one would be us deciding which the code meant.
    says: tuple[Definition, ...] = ()
    #: Whether any of them is an entry for this word itself rather than for a
    #: flavour of it. False means the code defines "Design Street" and "Street
    #: Tree" and never "street" -- which the reviewer has to be told, rather
    #: than left to infer from a list that looks like an answer.
    exact: bool = False
    #: Our fields this word sets the meaning of, that this layer actually holds.
    fields: tuple[str, ...] = ()
    #: Encoded values resting on those fields here. The cost of getting the
    #: word wrong, in numbers that would have to be read again.
    values: int = 0
    #: Lines of this jurisdiction's stored code that write the word. Evidence
    #: that the question is real: a card exists only where this is non-zero.
    uses: int = 0
    #: A few of those lines as the code writes them, the ones that hand the
    #: reader somewhere else first. A ``silent`` card otherwise says only that
    #: the glossary has no entry, which leaves the reviewer to go and find out
    #: where else the word might be settled -- and this corpus usually already
    #: knows, because the code says so out loud: Portland's own text points at
    #: "Chapter 33.930, Measurements" twelve times for how its setbacks and
    #: heights are measured. Showing that turns a hunt into an ``elsewhere``
    #: ruling that names the chapter.
    #:
    #: Context, never part of the fingerprint. This is how the word gets used,
    #: not what the city says it means; hashing it would reopen every card
    #: every time a document was re-extracted.
    shown: tuple[Mention, ...] = ()
    #: Lots in this jurisdiction. The sort, never a filter.
    lots: int = 0
    ruling: Reading | None = None

    @property
    def key(self) -> str:
        """How a ruling addresses this card: our word, not the city's."""
        return self.term

    @property
    def sends(self) -> tuple[str, ...]:
        """Chapters this jurisdiction's own text hands the word off to.

        Deduplicated across the shown lines and left in the order the code
        raises them. Where a word is silent this is the shortlist of places
        the answer is, written by the city rather than guessed by us.
        """
        return tuple(dict.fromkeys(c for m in self.shown for c in m.sends))

    @property
    def outcome(self) -> str:
        return self.ruling.outcome if self.ruling is not None else ""

    @property
    def fingerprint(self) -> str:
        """What this city said about the word when it was read.

        A glossary is re-extracted every time its document is re-fetched, and
        this corpus has already watched entries appear, split and triple on a
        re-read. So the ruling remembers the wording it was made against, and
        stops matching when that wording changes -- the same bargain the
        reading queues and ``FlatsRuleSignature`` both strike.

        The standing is part of it. A word going from silent to defined is the
        most important change that can happen to one of these cards, and a
        fingerprint over the entries alone would be blind to it, because there
        were no entries to hash.
        """
        body = "\n".join(
            [self.standing, *(f"{d.cite}\t{d.term}\t{d.text}" for d in self.says)]
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    @property
    def moved(self) -> bool:
        """Whether the wording changed under a decision already made.

        Does not keep the card closed: it comes back to be re-ruled in seconds
        or confirmed in one click. A ruling carrying no fingerprint is not
        drift -- it was written by hand and there is nothing to compare.
        """
        return bool(
            self.ruling
            and self.ruling.fingerprint
            and self.ruling.fingerprint != self.fingerprint
        )

    @property
    def closed(self) -> bool:
        return self.outcome in WORD_CLOSED

    @property
    def open(self) -> bool:
        """Three ways to be open, and they are different states.

        Nobody has ruled; somebody ruled and the ruling orders work rather than
        closing; or somebody ruled and the city's wording has changed since.
        """
        return self.ruling is None or not self.closed or self.moved


def _held(layer: Layer) -> set[str]:
    """Fields this jurisdiction has encoded a value for, anywhere."""
    out: set[str] = set(layer.defaults)
    for zone in layer.zones.values():
        out |= set(zone.values)
    return out


def _weight(layer: Layer, fields: Sequence[str]) -> int:
    """How many encoded values rest on these fields here."""
    wanted = set(fields)
    n = sum(1 for f in layer.defaults if f in wanted)
    for zone in layer.zones.values():
        n += sum(1 for f in zone.values if f in wanted)
    return n


def _glossary(
    layer: Layer,
) -> tuple[list[tuple[frozenset[str], tuple[str, ...], Definition]], bool]:
    """This jurisdiction's definitions, ready to match, and whether we read any."""
    out: list[tuple[frozenset[str], tuple[str, ...], Definition]] = []
    chapters = glossary.read_all(layer)
    for chapter in chapters:
        for entry in chapter.entries:
            stems = tuple(_stem(w) for w in _norm(entry.term).split() if w)
            out.append(
                (
                    frozenset(stems),
                    stems,
                    Definition(
                        term=entry.term,
                        text=entry.text,
                        cite=entry.quote,
                        doc=entry.doc,
                        line=entry.line,
                    ),
                )
            )
    return out, bool(chapters)


#: A sentence that says where a word is *settled*, not merely where to read
#: on. Narrower than :data:`_DEFERS` on purpose, and the narrowing was
#: measured: "shown as open space. See Chapter 33.810, Comprehensive Plan
#: Amendments" defers, names a chapter, and is about how a map designation is
#: amended -- and on the broad pattern it put a plan-procedure chapter second
#: in Portland's whole fetch queue, on 185,397 lots. What separates it from
#: "See Chapter 33.930, Measurements" is that the second sentence is about
#: measuring. So this wants a verb or a noun of determination, and a chapter
#: cited for its standards rather than for its meanings does not qualify --
#: that is a missed standard, which is a different queue's question.
_SETTLES = re.compile(
    r"\b(?:is|are|shall be|must be|to be)\s+"
    r"(?:measured|determined|calculated|computed|defined|established)"
    r"|\bas\s+(?:defined|measured|determined|calculated|described)\s+in"
    r"|\bfor (?:the )?purposes? of"
    r"|\b(?:measurement|definition|meaning)s?\b",
    re.I,
)


def _governed(layer: Layer) -> dict[str, tuple[str, ...]]:
    """Words that set the meaning of a number this jurisdiction actually holds."""
    held = _held(layer)
    if not held:
        return {}
    governed = {t: tuple(f for f in g if f in held) for t, g in GOVERNS.items()}
    return {t: f for t, f in governed.items() if f}


def _says(
    term: str, entries: Sequence[tuple[frozenset[str], tuple[str, ...], Definition]]
) -> tuple[list[Definition], list[Definition]]:
    """This code's entries for a word: the exact ones, then the near ones.

    One function because two callers must mean the same thing by *defined*.
    The queue asks a reviewer about a word its glossary is silent on; the fetch
    ranking below lifts the chapter that silence points at. If they disagreed,
    a chapter would climb to the top of one queue for a word the other shows
    as answered.
    """
    bags = forms(term)
    seqs = _seqs(term)
    exact: list[Definition] = []
    near: list[Definition] = []
    seen: set[str] = set()
    for bag, stems, found in entries:
        if found.cite in seen:
            continue
        if bag in bags:
            seen.add(found.cite)
            exact.append(found)
        elif any(_contains(stems, s) for s in seqs):
            seen.add(found.cite)
            near.append(found)
    return exact, near


def _lots_on(
    layer: Layer, fields: Sequence[str], lots: Mapping[tuple[str, str], int]
) -> int:
    """Lots in zones holding a number on one of these fields.

    A layer default applies to every zone, so a field held only in ``defaults``
    reaches the whole jurisdiction. Counted per zone and never per value: a
    zone holding four of these numbers is one zone.
    """
    wanted = set(fields)
    here = {z: n for (layer_id, z), n in lots.items() if layer_id == layer.layer}
    if wanted & set(layer.defaults):
        return sum(here.values())
    return sum(
        n
        for zone, n in here.items()
        if zone in layer.zones and wanted & set(layer.zones[zone].values)
    )


def undefined_here(
    layer: Layer, lots: Mapping[tuple[str, str], int] | None = None
) -> dict[str, tuple[tuple[str, ...], int]]:
    """Chapters this code says a word is settled in, that its glossary is not.

    Written for the fetch queue rather than for this one, and this is the
    measurement behind it: a chapter reaches our numbers two ways, and only one
    of them leaves a trace where :mod:`flats.encode.triage` looks. It can stand
    beside a standard we read -- a reference in the margin of a table, which is
    what that ledger ranks on. Or the code can hand it a *word* every one of
    those standards is measured in, which is said once, in prose, nowhere near
    a value. Portland's Chapter 33.930, Measurements, is the second kind: it
    settles how every setback in the city is measured, it is not in the store,
    and it ranked (0, 0, 0, 0) at the bottom of a 75-card queue.

    Deliberately only the words this code's own definitions chapter leaves
    alone. Measured over the corpus, every governed word deferring anywhere
    would lift 123 of the cards -- most of them "as defined in Chapter 17",
    which tells a reviewer nothing. The silent ones are 18, and each is a
    chapter we cannot open standing where a definition we do not have should
    be.

    Returns chapter -> (the words, the lots behind the numbers measured in
    them). Counted over every deferring line, not the handful a card shows.
    """
    from flats.encode.triage import _lots_by_zone

    governed = _governed(layer)
    if not governed:
        return {}
    entries, _ = _glossary(layer)
    silent = {t: f for t, f in governed.items() if not any(_says(t, entries))}
    if not silent:
        return {}

    directory = DOCS / layer.layer
    if not directory.is_dir():
        return {}
    patterns = {
        term: re.compile("|".join(_flex(s) for s in spellings(term)), re.I)
        for term in silent
    }
    fields: dict[str, set[str]] = {}
    words: dict[str, list[str]] = {}
    for path in sorted(directory.glob("*.txt")):
        home = _home(path.name)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if len(line) < 4:
                continue
            sends = _sends(line)
            if not sends or not _away(home, sends):
                continue
            if not _SETTLES.search(line):
                continue
            for term, pattern in patterns.items():
                if not pattern.search(line):
                    continue
                for chapter, _ in sends:
                    # Only standards with room in them, the same filter
                    # ``triage.Card.live_lots`` applies and for the same
                    # reason: a chapter that can only make a prohibited use
                    # more prohibited is not eating anybody's building.
                    # Without it the two halves of the rank would be measured
                    # on different scales and the deferral half would win
                    # every comparison.
                    fields.setdefault(chapter, set()).update(
                        f
                        for f in silent[term]
                        if f not in FIELDS or FIELDS[f].has_slack
                    )
                    if term not in words.setdefault(chapter, []):
                        words[chapter].append(term)

    known = _lots_by_zone() if lots is None else lots
    return {
        chapter: (
            tuple(sorted(words[chapter])),
            _lots_on(layer, sorted(held), known),
        )
        for chapter, held in fields.items()
    }


def cards(
    layer: Layer,
    *,
    lots: int = 0,
    overrides: Mapping[str, Reading] | None = None,
) -> list[Card]:
    """Every word worth asking about in one jurisdiction."""
    governed = _governed(layer)
    if not governed:
        return []

    spoken, sampled = _scan(layer.layer, list(governed))
    entries, read_any = _glossary(layer)
    rulings = dict(layer.words or {})
    rulings.update(overrides or {})

    out: list[Card] = []
    for term, mine in governed.items():
        # A word this code never writes is not measuring one of its numbers,
        # whatever our field is called. Portland's setbacks are not yards.
        if not spoken[term]:
            continue

        # Exact entries first. A code that files both "Street" and "Design
        # Street" has defined the word in the first one; leading with the
        # qualified flavour makes a reviewer read the special case as the rule.
        exact, near = _says(term, entries)
        # Exact entries first, then the rest in the order the code lists them.
        # No cleverer ranking: "Street Tree" and "Street, Road or Highway" both
        # open with the word and only one of them defines it, and every rule
        # that tells them apart is a rule about English rather than about this
        # code. Where nothing is exact the card says so and shows the lot, and
        # the reviewer's eye does the choosing -- which is the same bargain the
        # signing screen strikes.
        says = exact + near

        if says:
            standing = "defined"
        elif read_any:
            standing = "silent"
        else:
            standing = "unread"

        out.append(
            Card(
                layer=layer.layer,
                label=layer.label,
                term=term,
                standing=standing,
                says=tuple(says),
                exact=bool(exact),
                fields=mine,
                values=_weight(layer, mine),
                uses=spoken[term],
                shown=sampled[term],
                lots=lots,
                ruling=rulings.get(term),
            )
        )
    return out


#: Standings in the order a reviewer should meet them. ``unread`` first is
#: deliberate: it is the only one that can be answered without reading a word
#: of code -- somebody has to go and get the glossary -- and leaving it mixed
#: in among real reading makes a fetch look like a judgement.
STANDINGS: tuple[str, ...] = ("unread", "silent", "defined")

#: What each standing is called in front of a person, and the question it asks.
#: Three different jobs, and the split is the whole reason this is a queue and
#: not a report: fetching a book nobody has opened, deciding what a silent code
#: lets us assume, and comparing a definition to how we measure are not the
#: same hour of work.
QUEUES: dict[str, tuple[str, str]] = {
    "unread": (
        "No glossary read",
        "Nobody has read this city's definitions, so this word may well be "
        "defined and we would not know. Is there a definitions chapter to go "
        "and get?",
    ),
    "silent": (
        "The code is quiet",
        "The definitions chapter is on disk and this word is not in it. Can "
        "the screen safely assume the ordinary meaning, or is that a gap?",
    ),
    "defined": (
        "Defined here",
        "The city says what it means. Does it mean what our numbers assume, "
        "or does this city measure it differently?",
    ),
}


def feed(
    standing: str = "",
    layers: Mapping[str, Layer] | None = None,
    *,
    layer: str | None = None,
    field: str | None = None,
    ruled: bool = False,
    overrides: Mapping[str, Mapping[str, Reading]] | None = None,
    eligible_only: bool = True,
) -> list[Card]:
    """The queue, heaviest first.

    Ordered by how much a wrong reading costs: the values resting on the word
    here, then the lots behind the jurisdiction. Consequence is the sort and
    never a filter -- a small city's word is still wrong if it is wrong.
    """
    from flats.encode.worklist import _lots_by_layer

    chosen = layers if layers is not None else load_rules()
    lots = _lots_by_layer()

    out: list[Card] = []
    for layer_id, this in chosen.items():
        if eligible_only and not this.eligible:
            continue
        if layer and layer_id != layer:
            continue
        out += cards(
            this,
            lots=lots.get(layer_id, 0),
            overrides=(overrides or {}).get(layer_id),
        )
    if standing:
        out = [c for c in out if c.standing == standing]
    if field:
        out = [c for c in out if field in c.fields]
    if not ruled:
        out = [c for c in out if c.open]
    out.sort(key=lambda c: (STANDINGS.index(c.standing), -c.values, -c.lots, c.layer, c.term))
    return out


def counts(rows: Sequence[Card]) -> dict[str, int]:
    out = {s: 0 for s in STANDINGS}
    for card in rows:
        out[card.standing] += 1
    return out


def tally(
    layers: Mapping[str, Layer] | None = None,
    *,
    overrides: Mapping[str, Mapping[str, Reading]] | None = None,
) -> dict[str, tuple[int, int]]:
    """Cards and the values resting behind them, per standing.

    What the landing page shows. Two numbers rather than one because they say
    different things: how many questions are waiting, and how many numbers
    already in production would have to be read again if the answers are not
    what we assumed.
    """
    rows = feed(layers=layers, overrides=overrides)
    out: dict[str, list[int]] = {s: [0, 0] for s in STANDINGS}
    for card in rows:
        out[card.standing][0] += 1
        out[card.standing][1] += card.values
    return {k: (v[0], v[1]) for k, v in out.items()}


def orders(
    layers: Mapping[str, Layer] | None = None,
    *,
    overrides: Mapping[str, Mapping[str, Reading]] | None = None,
) -> list[Card]:
    """Every word ruling that asked for something and has not got it yet.

    The same bargain the reading queues strike: a ruling is not a disposal.
    "This city measures it differently", "go and fetch the glossary", "the code
    never defines this" are jobs, and a job recorded inside the queue that
    asked the question is a job nobody doing a day of encoding can see.

    Filtered on :data:`WORD_WORK` rather than on ``card.open`` because the two
    are not the same set: ``differs`` closes nothing and orders a re-read, and
    a card whose city has since published a glossary stops existing on its own.
    """
    from flats.rules.model import WORD_WORK

    rows = feed(layers=layers, overrides=overrides, ruled=True)
    jobs = list(WORD_WORK)
    out = [c for c in rows if c.outcome in WORD_WORK]
    out.sort(key=lambda c: (jobs.index(c.outcome), -c.values, -c.lots, c.layer, c.term))
    return out


@dataclass(frozen=True, slots=True)
class Audit:
    """What the queue would no longer ask, and what it should ask again."""

    #: Rulings with no card behind them any more. The word is still a word;
    #: what has gone is the *reason to ask* -- this jurisdiction stopped
    #: holding a number the word governs, or its code stopped writing it.
    settled: tuple[str, ...]
    #: Ruled, and the city's wording has changed since. These are back in the
    #: queue already; the audit is how you find out how many before opening it.
    moved: tuple[str, ...]
    #: Still open, by standing. Not a fault -- the size of the day's work.
    open_by_standing: tuple[tuple[str, int], ...]

    @property
    def clean(self) -> bool:
        return not self.settled and not self.moved


def audit(layers: Mapping[str, Layer] | None = None) -> Audit:
    """Ask the queue whether it would still ask what it is asking.

    Run before working it, not after. A queue that outlives its reasons is
    worse than no queue: it spends the one scarce thing here, a reviewer's
    attention, on questions that answered themselves. This project has watched
    that happen twice -- a ledger reporting lines unread that the corpus proved
    were quoted, and a test pinning a corpus condition that went red when the
    corpus was fixed -- so the check is cheap and unconditional.

    Cards are derived, so nothing has to be retired by hand: encode a number
    and the card it justified disappears on its own. What this catches is the
    other half -- a *ruling* left standing over a question nobody would ask
    now, and a ruling made against wording that has since moved.
    """
    chosen = layers if layers is not None else load_rules()

    settled: list[str] = []
    moved: list[str] = []
    open_counts = dict.fromkeys(STANDINGS, 0)

    for layer_id, this in chosen.items():
        # The same set the queue asks about. A jurisdiction the screen is
        # switched off for is not work anybody has, and counting its cards as
        # open would report a morning that does not exist.
        if not this.eligible:
            continue
        made = cards(this)
        here = {c.term: c for c in made}
        for term in this.words or {}:
            if term not in here:
                settled.append(f"{layer_id}  {term}")
        for card in made:
            if card.moved:
                moved.append(f"{layer_id}  {card.term}")
            if card.open:
                open_counts[card.standing] += 1

    return Audit(
        settled=tuple(sorted(settled)),
        moved=tuple(sorted(moved)),
        open_by_standing=tuple((s, open_counts[s]) for s in STANDINGS),
    )


def report(found: Audit) -> str:
    """The audit, for a terminal."""
    out: list[str] = []
    if found.clean:
        out.append("every open card still asks something this corpus has not answered")
    for name in found.settled:
        out.append(f"settled   {name}  (ruled, and nothing rests on the word here now)")
    for name in found.moved:
        out.append(f"moved     {name}  (ruled against wording that has changed since)")
    out.append("")
    out.append(
        "  ".join(f"{s}={n}" for s, n in found.open_by_standing)
        + f"  open={sum(n for _, n in found.open_by_standing)}"
    )
    return "\n".join(out)


def render(rows: Sequence[Card]) -> str:
    lines = []
    for card in rows:
        says = card.says[0].text[:90] if card.says else ""
        lines.append(
            f"{card.layer:30} {card.term:18} {card.standing:8} "
            f"{card.values:>4} values {card.uses:>5} uses {card.lots:>7,} lots  {says}"
        )
    tally = counts(rows)
    lines.append("")
    lines.append("  ".join(f"{k}={v}" for k, v in tally.items()) + f"  total={len(rows)}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if "--audit" in args:
        print(report(audit()))
        return 0
    rows = feed(ruled="--ruled" in args)
    if "--counts" in args:
        tally = counts(rows)
        print("  ".join(f"{k}={v}" for k, v in tally.items()) + f"  total={len(rows)}")
        return 0
    print(render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# --- writing a decision back into the rule files -----------------------------


def rule(
    layer_id: str,
    term: str,
    standing: str,
    outcome: str,
    note: str,
    fingerprint: str = "",
) -> Path:
    """Record one word decision in the jurisdiction file, or raise.

    Raises rather than writing a file the loader will reject: the loader
    accumulates problems across the whole corpus and refuses the set, so one
    bad splice takes every jurisdiction down with it. The file is written,
    re-read, and rolled back if the ruling did not take.

    The splice itself is :func:`flats.encode.worklist._splice`, told to write a
    ``words:`` block. A second copy of that would be a second place for the
    YAML to be got subtly wrong.
    """
    from flats.encode.triage import layer_path
    from flats.encode.worklist import NEWLINE, _splice
    from flats.rules.loader import MIN_RULING
    from flats.rules.model import WORD_OUTCOMES

    if standing not in WORD_OUTCOMES:
        raise ValueError(
            f"unknown standing {standing!r}; one of {', '.join(sorted(WORD_OUTCOMES))}"
        )
    if outcome not in WORD_OUTCOMES[standing]:
        raise ValueError(
            f"{outcome!r} is not an answer the {standing} queue asks for; one of "
            f"{', '.join(sorted(WORD_OUTCOMES[standing]))}"
        )
    if term not in GOVERNS:
        raise ValueError(f"{term!r} is not a word this queue asks about")
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
    spliced = _splice(
        before.splitlines(), term, standing, outcome, note, fingerprint, block="words"
    )
    path.write_text(NEWLINE.join(spliced) + NEWLINE, encoding="utf-8")
    try:
        load_rules.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    try:
        got = load_rules()[layer_id].words.get(term)
        if got is None or got.outcome != outcome:
            raise ValueError(f"ruling did not take on {layer_id} {term}")
    except Exception:
        path.write_text(before, encoding="utf-8")
        try:
            load_rules.cache_clear()  # type: ignore[attr-defined]
        except AttributeError:
            pass
        raise
    return path
