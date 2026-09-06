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
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from flats.encode import glossary
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
    """A phrase as it appears in running code text: plural, any spacing."""
    out = []
    for word in _norm(phrase).split():
        if word.endswith("y") and len(word) > 3:
            out.append(re.escape(word[:-1]) + "(?:y|ies)")
        elif word.endswith("s"):
            out.append(re.escape(word))
        else:
            out.append(re.escape(word) + "s?")
    return r"\s+".join(out)


def uses(layer_id: str, terms: Sequence[str]) -> dict[str, int]:
    """Lines of this jurisdiction's stored code that use each word.

    Usage is the gate, not the sort. Portland writes *setback* and never
    *yard*; asking a reviewer what Portland means by a yard is asking about a
    word its code does not contain, and a queue that does that teaches people
    to skip rows. A word this code never uses cannot be measuring one of our
    numbers, whatever our field names call it.
    """
    directory = DOCS / layer_id
    out = dict.fromkeys(terms, 0)
    if not directory.is_dir():
        return out
    patterns = {
        term: re.compile("|".join(_flex(s) for s in spellings(term)), re.I)
        for term in terms
    }
    for path in sorted(directory.glob("*.txt")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if len(line) < 4:
                continue
            for term, pattern in patterns.items():
                if pattern.search(line):
                    out[term] += 1
    return out


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
    #: Lots in this jurisdiction. The sort, never a filter.
    lots: int = 0
    ruling: Reading | None = None

    @property
    def key(self) -> str:
        """How a ruling addresses this card: our word, not the city's."""
        return self.term

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


def cards(
    layer: Layer,
    *,
    lots: int = 0,
    overrides: Mapping[str, Reading] | None = None,
) -> list[Card]:
    """Every word worth asking about in one jurisdiction."""
    held = _held(layer)
    if not held:
        return []

    governed = {t: tuple(f for f in g if f in held) for t, g in GOVERNS.items()}
    governed = {t: f for t, f in governed.items() if f}
    if not governed:
        return []

    spoken = uses(layer.layer, list(governed))
    entries, read_any = _glossary(layer)
    rulings = dict(layer.words or {})
    rulings.update(overrides or {})

    out: list[Card] = []
    for term, mine in governed.items():
        # A word this code never writes is not measuring one of its numbers,
        # whatever our field is called. Portland's setbacks are not yards.
        if not spoken[term]:
            continue

        bags = forms(term)
        seqs = _seqs(term)
        # Exact entries first. A code that files both "Street" and "Design
        # Street" has defined the word in the first one; leading with the
        # qualified flavour makes a reviewer read the special case as the rule.
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
