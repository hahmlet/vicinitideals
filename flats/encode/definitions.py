"""Who defines what, per jurisdiction, and who is borrowing from nobody.

FLATS hangs real consequences on words. A corner lot gets a second front
setback in most of these codes; a flag lot gets its own width rule; an alley is
frontage in none of them. So before a screen can say GREEN it has to know
whether *this* lot is a corner **here** — and the four codes read so far define
corner lot four incompatible ways. Portland wants intersecting frontages,
Gresham counts streets and stops, Oregon City wants them to meet, Rivergrove
wants adjacent sides at 135 degrees or less. One test cannot serve four codes.

The obvious rescue is inheritance: let a city with no definition fall back to
its county, and the county to the state. That rescue is wrong, and this module
exists to say so with evidence rather than assertion.

**An incorporated Oregon city writes its own development code.** The county
code governs unincorporated land. Milwaukie having no stored definition of
"corner lot" is not Clackamas County speaking for Milwaukie — it is us not
having read Milwaukie. The state defines a handful of terms and *preempts*
where it does, which is a different mechanism entirely: preemption overrides a
local number, it does not supply a local meaning. Adoption exists, but only
where a code says it adopts, and then it is a citable clause like any other
(``definitions_from`` on the layer, with the adopting clause quoted).

Everything else is a gap, and the gap has three shapes worth telling apart:

================  =========================================================
status            what it means, and what to do about it
================  =========================================================
``own``           defined here, quoted. Nothing to do.
``adopted``       taken from another layer under a quoted adopting clause.
``findable``      the definition is sitting in a document we already store,
                  unencoded. The work queue: each row names the document and
                  line to encode from.
``silent``        this jurisdiction's definitions chapter is on disk and does
                  not define the term. A finding about the code. The screen
                  answers UNKNOWN and never borrows.
``unfetched``     a definitions chapter is declared and not in the store.
                  One fetch away.
``unsourced``     no definitions chapter has been declared for this
                  jurisdiction. Somebody has to go find one.
``unsearched``    no documents stored at all. We have not started here.
================  =========================================================

The bottom four look alike in a summary and mean opposite things. ``silent``
is a finding about the code; the rest are findings about us. Collapsing them
is how a screen starts inventing corners — a city whose chapter we never
fetched reads as a city whose code says nothing, and "says nothing" is exactly
the licence a fallback needs to fire.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from flats.rules.definitions import TERMS
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

#: Where stored code text lives, one directory per layer id.
DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"

#: How each term is spelled where it is defined. Codes index definitions both
#: ways -- "Corner Lot" and "Lot, Corner" -- so both are matched.
PHRASE = {
    # Plural matters. Codes headline the standard "Corner Lots" and define the
    # term "Corner Lot", and counting only the singular hid Tualatin and Wood
    # Village entirely -- both apply corner rules and neither showed a use.
    #
    # The parenthesised form is Multnomah County's: it indexes "Corner Lot" and
    # defines "Lot (Corner)", so a matcher that knows only the comma inversion
    # finds the cross-reference and stops.
    "corner_lot": r"\bcorner\s+lots?\b|\blots?\s*[,(]\s*corner\b\)?",
}

#: The typographic tell. A code sets a definition as the term *opening its own
#: entry* -- optionally behind a bullet or a list number -- then a period or
#: colon, then the sentence: "Corner Lot. A lot that has frontage on two or
#: more streets." Anchoring on the entry rather than the phrase is what keeps
#: "shall take access from the side of the corner lot. See Figure 13" from
#: reading as a definition, which it does if you only look for the punctuation.
#: Four codes, four typographies, and none of them is optional to support:
#: Gresham and Portland bullet the entry and end the term with a period,
#: Wilsonville numbers it and ends with a colon, Rivergrove quotes the term
#: and joins it to the body with "means". The shared shape is: entry opens the
#: line, term, separator, body.
DEFINED = {
    term: re.compile(
        r"^[^\w\"“]*"  # indent, bullet, an opening paren
        r"(?:\(?[0-9ivxIVX]+[.)]\s*)?"  # a list marker, if the code numbers them
        r"[\"“]?"  # some codes quote the term being defined
        rf"(?:{pattern})"
        r"[\"”]?"
        # A period, a colon or a dash -- never a comma. "For\ncorner lots, this
        # standard shall apply to at least one side" is a wrapped sentence in
        # Troutdale's window standards and reads as a definition if a comma is
        # allowed to separate the term from its body. No code in the corpus
        # uses one. Multnomah County uses an en dash and nothing else.
        r"(?:\s*[.:]|\s*[–—-]\s|\s+(?:means|shall mean|is|refers to|is defined as))\s*",
        re.I,
    )
    for term, pattern in PHRASE.items()
}

#: A body that is not a definition. Two shapes:
#:
#: *A cross-reference.* Gresham, Portland and Multnomah County all index
#: "Corner Lot. See Lot." near the top of their definitions and state the thing
#: itself hundreds of lines later, so the first hit is reliably the wrong one.
#:
#: *A standard wearing a heading.* Allowing a dash to separate a term from its
#: body -- which Multnomah County's definitions require -- also lets Tualatin's
#: "Corner Lots — On corner lots, the setback is..." through. A definition
#: opens with a noun phrase; a standard opens with a preposition or a
#: quantifier, and that is the difference between the two.
NOT_A_DEFINITION = re.compile(
    r"^(?:see|on|for|in|where|when|if|no|all|each|every|except|the following)\b", re.I
)

#: How a body opens when the codifier has set the term on a line of its own.
#: Requiring the verb is what keeps a contents listing -- term, then the next
#: term -- from reading as a definition whose body is the following entry.
DEFINING_VERB = re.compile(r"^(?:means|shall mean|is\s|refers to|is defined as)", re.I)

#: How much text an entry has to carry before it is a definition rather than a
#: line in a table of contents. "Lot, corner." followed by "Lot coverage" is a
#: contents listing in Oregon City's chapter and matches everything else.
MIN_BODY = 40

#: Lines of following text a definition is allowed to run into before the
#: frame verb has to have appeared. Three covers the wrapped ones.
LOOKAHEAD = 3

#: What a declared document has to look like to be the place definitions live.
#: Matched against the document id and title as declared, not against its text,
#: because the question this answers is "did anybody go looking for one".
CHAPTER = re.compile(r"defin|glossar|\bterms\b|interpret", re.I)

STATUSES = (
    "own",
    "adopted",
    "findable",
    "silent",
    "unfetched",
    "unsourced",
    "unsearched",
)


@dataclass(frozen=True, slots=True)
class Coverage:
    """One jurisdiction's standing on one term."""

    layer: str
    term: str
    status: str
    #: For ``own``/``adopted``, the code section cited. For ``findable``, the
    #: stored document and line to encode from. Empty otherwise.
    where: str = ""
    #: For ``adopted``, the layer the definition came from.
    source: str = ""
    #: How many lines of this jurisdiction's stored code use the term. A word
    #: this code hangs standards on is a word we have to be able to answer,
    #: and the count is the whole priority argument: thirteen jurisdictions
    #: apply corner lot rules in text already on disk while none of them has
    #: a definition encoded, which is a queue rather than a curiosity.
    uses: int = 0
    #: Whether this jurisdiction is screened at all. An exempt city's missing
    #: definition costs nothing, and chasing it is wasted work.
    eligible: bool = True

    @property
    def blocking(self) -> bool:
        """Whether a screen in this jurisdiction has to answer unknown."""
        return self.status not in ("own", "adopted")

    @property
    def priority(self) -> int:
        """Rough ordering for the queue: uses we cannot answer."""
        return 0 if not self.blocking or not self.eligible else self.uses


def _stored(layer_id: str) -> list[Path]:
    """Documents on disk for a layer. Not what it declared -- what we have."""
    directory = DOCS / layer_id
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.txt") if p.is_file())


def _uses(layer_id: str, term: str) -> int:
    """Lines of this jurisdiction's stored code that use the term.

    Usage, not definition. A code that writes a corner lot setback fifteen
    times and defines the word nowhere we hold is the most expensive kind of
    gap: every one of those fifteen standards resolves against a word the
    screen cannot answer.
    """
    pattern = PHRASE.get(term)
    if pattern is None:
        return 0
    phrase = re.compile(pattern, re.I)
    return sum(
        1
        for path in _stored(layer_id)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if phrase.search(line)
    )


def _find(layer_id: str, term: str) -> str:
    """Where this layer's code defines the term, if a stored document does.

    Returns a ``document#Lnnn`` reference in the same shape a quote takes, so
    the row can be encoded from without going looking again.
    """
    defined = DEFINED.get(term)
    if defined is None:
        return ""
    for path in _stored(layer_id):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            opening = defined.match(line)
            if opening is None:
                continue
            head = line[opening.end() :].strip()
            if not head:
                # The term with nothing after it is usually a table of contents
                # line, where the entries below are the next terms rather than
                # this one's body -- Oregon City's chapter opens with a page of
                # them. But Milwaukie's codifier sets the term on its own line
                # and opens the body with "means" on the next, which is a
                # definition list rather than a contents listing. The defining
                # verb is what tells them apart.
                nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if not DEFINING_VERB.match(nxt):
                    continue
                head = nxt
            body = " ".join([head, *lines[i + 1 : i + 1 + LOOKAHEAD]]).strip()
            if NOT_A_DEFINITION.match(body) or len(body) < MIN_BODY:
                continue
            return f"{layer_id}/{path.stem}.txt#L{i + 1}"
    return ""


def _chapter(layer: Layer) -> tuple[str, bool]:
    """The declared definitions chapter for a layer, and whether we hold it.

    Both halves are needed to tell "this code does not define the term" from
    "we never fetched the chapter that would", which are the same row in a
    naive report and opposite instructions to whoever reads it.
    """
    stored = {p.stem for p in _stored(layer.layer)}
    for doc in layer.code:
        if CHAPTER.search(f"{doc.id} {doc.title}"):
            return doc.id, doc.id in stored
    return "", False


def coverage_for(rules: RuleSet, layer_id: str) -> list[Coverage]:
    """Every term, this jurisdiction, with the evidence behind each answer."""
    layer = rules.layers[layer_id]
    resolved = rules.definitions_for(layer_id)
    chapter, held = _chapter(layer)
    has_docs = bool(_stored(layer_id))
    common = {"layer": layer_id, "eligible": layer.eligible}

    out: list[Coverage] = []
    for term in TERMS:
        uses = _uses(layer_id, term)
        defn = resolved.get(term)
        if defn is not None:
            own = term in layer.definitions
            out.append(
                Coverage(
                    **common,
                    term=term,
                    status="own" if own else "adopted",
                    where=defn.cite or defn.quote,
                    source="" if own else _owner(rules, layer_id, term),
                    uses=uses,
                )
            )
            continue

        # Search what we hold first: several codes define their terms inside
        # the zoning chapter rather than a chapter of their own, and a hit
        # there is worth more than any statement about what was declared.
        found = _find(layer_id, term) if has_docs else ""
        if found:
            out.append(
                Coverage(
                    **common, term=term, status="findable", where=found, uses=uses
                )
            )
            continue
        if chapter and held:
            status, where = "silent", chapter
        elif chapter:
            status, where = "unfetched", chapter
        elif has_docs:
            status, where = "unsourced", ""
        else:
            status, where = "unsearched", ""
        out.append(
            Coverage(**common, term=term, status=status, where=where, uses=uses)
        )
    return out


def _owner(rules: RuleSet, layer_id: str, term: str) -> str:
    """Which adopted layer actually supplied the definition."""
    for candidate in rules.layers[layer_id].definitions_from:
        if term in rules.layers.get(candidate, Layer(layer=candidate, kind="", label="")).definitions:
            return candidate
    return ""


def coverage(rules: RuleSet | None = None) -> list[Coverage]:
    """The whole register, worst standing first, so the queue reads top-down."""
    rules = rules or RuleSet(load_rules())
    out = [row for layer_id in sorted(rules.layers) for row in coverage_for(rules, layer_id)]
    # Worst standing first, and within it the jurisdictions whose codes lean
    # hardest on the word -- which is the order somebody should work the queue.
    out.sort(key=lambda r: (-r.priority, r.status, r.layer, r.term))
    return out


def by_status(rows: list[Coverage]) -> dict[str, int]:
    """How many jurisdiction-terms sit at each standing."""
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row.status] += 1
    return {k: v for k, v in counts.items() if v}


def render(rows: list[Coverage]) -> str:
    """The register as text, for a terminal or a commit message."""
    width = max((len(r.layer) for r in rows), default=10)
    lines = [
        f"{r.layer:<{width}}  {r.term:<12}  {r.status:<10}  "
        f"{'' if r.eligible else 'exempt '}{r.uses:>3} uses  {r.source or r.where}"
        for r in rows
    ]
    tally = by_status(rows)
    lines.append("")
    lines.append("  ".join(f"{k}={v}" for k, v in tally.items()))
    return "\n".join(lines)


def main() -> None:
    print(render(coverage()))


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = [
    "Coverage",
    "STATUSES",
    "by_status",
    "coverage",
    "coverage_for",
    "render",
]
