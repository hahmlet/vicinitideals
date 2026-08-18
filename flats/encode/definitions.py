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
    "corner_lot": r"\bcorner\s+lot\b|\blots?\s*,\s*corner\b",
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
        r"(?:\s*[.:,]|\s+(?:means|shall mean|is|refers to|is defined as))\s*",
        re.I,
    )
    for term, pattern in PHRASE.items()
}

#: An entry that only points somewhere else. Both Gresham and Portland index
#: "Corner Lot. See Lot." at the top of their definitions chapters and define
#: it eight hundred lines later, so the first hit is reliably the wrong one.
CROSS_REFERENCE = re.compile(r"^see\b", re.I)

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

    @property
    def blocking(self) -> bool:
        """Whether a screen in this jurisdiction has to answer unknown."""
        return self.status not in ("own", "adopted")


def _stored(layer_id: str) -> list[Path]:
    """Documents on disk for a layer. Not what it declared -- what we have."""
    directory = DOCS / layer_id
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.txt") if p.is_file())


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
                # The term with nothing after it is a table of contents line,
                # and the entries under it are the next terms rather than this
                # one's body. Oregon City's chapter opens with a page of them.
                continue
            body = " ".join([head, *lines[i + 1 : i + 1 + LOOKAHEAD]]).strip()
            if CROSS_REFERENCE.match(body) or len(body) < MIN_BODY:
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

    out: list[Coverage] = []
    for term in TERMS:
        defn = resolved.get(term)
        if defn is not None:
            own = term in layer.definitions
            out.append(
                Coverage(
                    layer=layer_id,
                    term=term,
                    status="own" if own else "adopted",
                    where=defn.cite or defn.quote,
                    source="" if own else _owner(rules, layer_id, term),
                )
            )
            continue

        # Search what we hold first: several codes define their terms inside
        # the zoning chapter rather than a chapter of their own, and a hit
        # there is worth more than any statement about what was declared.
        found = _find(layer_id, term) if has_docs else ""
        if found:
            out.append(
                Coverage(layer=layer_id, term=term, status="findable", where=found)
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
        out.append(Coverage(layer=layer_id, term=term, status=status, where=where))
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
    rank = {status: i for i, status in enumerate(reversed(STATUSES))}
    out = [row for layer_id in sorted(rules.layers) for row in coverage_for(rules, layer_id)]
    out.sort(key=lambda r: (rank[r.status], r.layer, r.term))
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
        f"{r.layer:<{width}}  {r.term:<14}  {r.status:<10}  {r.source or r.where}"
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
