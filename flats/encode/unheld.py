"""Find claims that a DOCUMENT is not in the store, and re-ask them.

:mod:`flats.encode.stale` watches one axis of this problem and only one. It
asks whether a dismissal's reason still says something true about *which zones
this layer encodes*, because that is the claim somebody else can falsify by
doing their job. There is a second axis with the same property and nothing was
watching it:

    "ZDO 1005 is not held" · "a chapter not in this corpus" ·
    "Chapter 12.16 ... was not in the store" · "never fetched"

A claim about the STORE decays exactly the way a claim about the zones does,
and faster, because fetching a document is a smaller act than encoding a
district. Four claims that ZDO 1005 was not held went false on 2026-09-08, the
day the document was fetched, and were found on 2026-09-09 by hand while
reading for something else. ``stale.py`` could not have caught them: it looks
for zone codes, and none of the four names one.

**What it reads.** The same three places
:mod:`flats.encode.refusals` reads, because a claim about the store is prose
like any other -- layer and zone ``notes`` off the loaded model, and ``#``
comments off the file. With one exclusion that is not an optimisation but a
correctness fix: **comments inside the ``code:`` block are skipped.** That
block is the fetch manifest -- not ``ingest:``, which is the parcel-join
config -- and the comment above an entry is the argument for fetching it:
"cited eleven times across the district chapters and never fetched". Every one
of those sentences is a true statement about the past standing directly above
the document it caused to be fetched, and reading them as live claims would
bury the report in its own success stories.

It also reads the two **ruling blocks**, ``crossrefs`` and ``readings``, which
the prose harvest cannot see because a ruling is a structured field rather
than a note. That is where this claim takes its sharpest form: a
cross-reference closed *because* we do not hold the chapter is a decision
resting on the absence, not a remark about it, and it is the row that should
reopen the moment the chapter arrives.

**How a claim is resolved.** By :func:`flats.encode.crossrefs.opens`, and
deliberately by nothing else. That predicate is what the cross-reference ledger
uses to decide whether the store answers for a reference, and two ledgers
giving two answers to "do we hold that chapter" would be worse than either
ledger alone. It also gets this right where a filename cannot: Gresham's
Section 9.0851 lives inside ``9.0800.parking.txt``, so matching a reference
against document names would have missed the four notes that motivated the
module.

**Where in the sentence it looks, and why that is the whole trick.** Only at
the text *before* the marker, back to the last sentence boundary. A claim names
its document first and draws its consequence second -- "in Chapter 12.16 ...
which was not in the store", "'As provided in Section 9.0851', a cross-
reference to a chapter not in this corpus". What comes *after* a not-held
marker is usually a list of the documents that DO mention the thing, and
reading those as the subject of the claim inverts it. The sentence this module
was written beside is the case: "the Floodplain Management District ... whose
own chapter is NOT in this store: the only three documents here that name it
are this one, ZDO 1012 ... and Gladstone 17.25". Both of those are held. Both
are named to say the district is real, not to say the store has its chapter.

Three answers, and only the first is work:

``contradicted``   the store answers for a document the claim says is missing
``outstanding``    it names a document the store still cannot open -- true today
``settled``        written in the past tense, as the record of somebody fixing it

A span that names no document at all is dropped rather than reported. Those are
the sibling claims -- a map, an overlay, a street classification, an engineering
manual, the neighbour's zoning -- and they are just as decay-prone and not
answerable here, because the store is not what would falsify them.

``self_contradicted`` is the column to read first. It is true when the layer
making the claim **quotes a value out of the very document it says is
missing**, which is not a stale sentence but two answers inside one file.

Usage::

    uv run python -m flats.encode.unheld
    uv run python -m flats.encode.unheld --csv out.csv
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from flats.encode.crossrefs import _cited_lines, opens
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import CONFIG_ROOT, load_rules

#: The phrasings this corpus uses to say a document is not held. Written out
#: rather than generalised: "does not hold" alone is the commonest sentence in
#: the corpus and most of the time its object is a map or an overlay, which
#: this cannot answer for. The reference test downstream is what separates
#: those, so the marker is allowed to be generous.
MARKER = re.compile(
    r"(?:"
    r"not\s+in\s+(?:the|this|our)\s+(?:store|corpus|files)"
    r"|(?:is|are|was|were)\s+not\s+held"
    r"|(?:do|does|did)\s+not\s+hold"
    r"|(?:could|can)\s+not\s+(?:open|cite)"
    r"|unheld"
    r"|(?:not|never)\s+(?:been\s+)?fetched"
    r"|(?:no|never)\s+fetch"
    r")",
    re.IGNORECASE,
)

#: A claim written as history rather than as a live statement. Small and
#: closed, for the same reason ``stale.py``'s repaired vocabulary is: this is
#: the one place the check believes what a sentence says about itself.
SETTLED = re.compile(
    r"(?:"
    r"\bwas\s+not\s+in\s+the\s+store"
    r"|\bused\s+to\b"
    r"|\bSUPERSEDED\b"
    r"|\bstopped\s+being\s+true"
    r"|\bno\s+longer\b"
    r"|\bhas\s+since\s+been\s+fetched"
    r"|\bfetched\s+(?:it|the\s+chapter)\s+"
    r")",
    re.IGNORECASE,
)

#: A reference to a document, as prose spells one. Either an abbreviation
#: (ZDO 1005, MCC 39.4801, GMC Chapter 17.48) or one of the words a code uses
#: for its own divisions, and then a number. One of the two is REQUIRED: a
#: bare number in prose is a measurement far more often than it is a chapter,
#: and this check may not invent a claim.
REFERENCE = re.compile(
    r"(?:\b(?P<book>[A-Z]{2,6})\s+)?"
    r"(?:\b(?P<word>Chapters?|Ch\.|Titles?|Sections?|Articles?|§)\s+)?"
    r"(?P<num>\d+(?:\.\d+)*)",
)

#: How far back from a marker the claim's subject is looked for. A window, not
#: a parse, cut at the previous sentence end.
HEAD = 260

#: What the corpus says it does not hold, when the thing is not a document.
#: These are the sibling claims -- and they are the majority of "does not
#: hold" in this corpus, because a screen that cannot see the neighbour's
#: zoning says so far more often than it says a chapter is missing.
NOT_A_DOCUMENT = re.compile(
    r"\b(?:overlay|map|maps|boundary|boundaries|inventory|classification|"
    r"manual|drawing|drawings|pattern\s+book|book|list|deed|easement)\b",
    re.IGNORECASE,
)

#: What it says it does not hold when the thing IS one. Checked in the same
#: window and given precedence, so "a cross-reference to a chapter not in this
#: corpus" survives a sentence that also mentions a map.
A_DOCUMENT = re.compile(
    r"\b(?:chapter|chapters|section|sections|title|code|ordinance|document|"
    r"documents|volume|article)\b",
    re.IGNORECASE,
)

#: How much of the run-up to the marker decides which of the two it is. Short
#: on purpose: the subject of "does not hold" is next to it, and widening this
#: window is how a sentence that mentions a chapter in passing starts being
#: read as a claim about one.
SUBJECT = 70

#: How far PAST the marker the claim's object is looked for, when the sentence
#: puts it there -- "we do not hold Chapter 12.16". Cut at the first comma,
#: colon, dash or quotation mark, which is what keeps the inversion out:
#: after a marker this corpus habitually writes a colon or a dash and then the
#: documents that DO name the thing -- or quotes the line that cites it -- and
#: reading either as the subject stands the claim on its head.
OBJECT = 60

#: The top-level key holding the fetch manifest, whose comments argue for
#: fetching the entry below them and are therefore never live claims.
MANIFEST = "code"

_OBJECT_END = re.compile(r"""[;:,"'‘’“”]|--|—|(?<=[.!?])\s""")


@dataclass(frozen=True, slots=True)
class Unheld:
    """One written claim that the store does not hold a document."""

    layer: str
    #: Which of the four places the sentence was written: "notes", "comments",
    #: "crossrefs" or "readings".
    kind: str
    zone: str | None
    #: The sentence up to the marker -- what the claim is actually about.
    claim: str
    #: References the claim names that the store DOES answer for.
    held: tuple[str, ...]
    #: References it names that the store still cannot open.
    missing: tuple[str, ...]
    #: The layer quotes an encoded value out of one of the held documents.
    self_contradicted: bool = False
    settled: bool = False
    #: The key the sentence hangs off, when it hangs off one: the section of a
    #: crossref ruling, or the ``<document>#<section>`` of a reading. Empty for
    #: prose, which hangs off the layer or the zone and nothing finer.
    at: str = ""

    @property
    def verdict(self) -> str:
        if self.settled:
            return "settled"
        return "contradicted" if self.held else "outstanding"

    @property
    def label(self) -> str:
        head = f"{self.layer}:{self.zone}" if self.zone else self.layer
        return f"{head} {self.at}" if self.at else head


def _heads(text: str):
    """Each not-held marker in `text`, with the sentence that precedes it.

    Whitespace is collapsed first so a folded YAML scalar and a block scalar
    read the same, which is the same reason :mod:`flats.encode.refusals` reads
    the model rather than the file.
    """
    flat = " ".join((text or "").split())
    for match in MARKER.finditer(flat):
        near = flat[max(0, match.start() - SUBJECT) : match.start()]
        if NOT_A_DOCUMENT.search(near) and not A_DOCUMENT.search(near):
            continue
        head = flat[max(0, match.start() - HEAD) : match.end()]
        cut = list(re.finditer(r"(?<=[.!?])\s+(?=[A-Z(\"'])", head[:-1]))
        if cut:
            head = head[cut[-1].end() :]
        head += _OBJECT_END.split(flat[match.end() : match.end() + OBJECT])[0]
        yield head.strip(), flat[match.start() : match.start() + 200]


def _references(claim: str) -> tuple[str, ...]:
    """Every document number the claim names, in order, without repeats."""
    out: list[str] = []
    for m in REFERENCE.finditer(claim):
        if not (m.group("book") or m.group("word")):
            continue
        num = m.group("num").rstrip(".")
        if num and num not in out:
            out.append(num)
    return tuple(out)


def _comment_blocks(path: Path):
    """Runs of ``#`` lines in a jurisdiction file, outside the fetch manifest.

    The ``code:`` block is skipped whole. Its comments are the arguments for
    fetching the documents listed under them, so they say "not fetched" about
    things the store has held ever since -- true when written, permanently
    contradicted, and never work. It is ``code:`` and not ``ingest:``: the
    latter is the parcel-join config and holds no prose at all.
    """
    block: list[str] = []
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        top = re.match(r"^(?P<key>[a-z_]+):", line)
        if top:
            section = top.group("key")
        stripped = line.strip()
        if stripped.startswith("#"):
            if section != MANIFEST:
                block.append(stripped.lstrip("#").strip())
            continue
        if block:
            yield " ".join(block)
            block = []
    if block:
        yield " ".join(block)


def claims(
    text: str,
    *,
    layer: str,
    kind: str,
    zone: str | None = None,
    at: str = "",
    answers: Callable[[str], bool],
    quotes: Callable[[str], bool] = lambda ref: False,
) -> list[Unheld]:
    """Every not-held claim in one piece of prose, resolved by `answers`.

    The resolver is injected rather than reached for so the mechanism can be
    tested on sentences written in a test file. Everything the corpus walk
    does beyond this is finding the prose and building the two predicates.
    """
    out: list[Unheld] = []
    for claim, tail in _heads(text):
        refs = _references(claim)
        if not refs:
            continue
        held = tuple(r for r in refs if answers(r))
        out.append(
            Unheld(
                layer=layer,
                kind=kind,
                zone=zone,
                claim=claim,
                held=held,
                missing=tuple(r for r in refs if r not in held),
                self_contradicted=any(quotes(r) for r in held),
                settled=bool(SETTLED.search(claim) or SETTLED.search(tail)),
                at=at,
            )
        )
    return out


def audit(store: ProvenanceStore | None = None) -> list[Unheld]:
    """Every written claim that a document is missing, re-asked of the store."""
    store = store or ProvenanceStore()
    out: list[Unheld] = []

    for name, layer in sorted(load_rules(strict=False).items()):
        answers = opens(layer, store)
        cited = set(_cited_lines(layer))

        def quotes(ref: str, *, cited=cited, root=layer.layer) -> bool:
            return _answers_for(ref, cited, root, store)

        kw = dict(layer=name, answers=answers, quotes=quotes)

        out += claims(layer.notes or "", kind="notes", **kw)
        for code, zone in sorted(layer.zones.items()):
            out += claims(zone.notes or "", kind="notes", zone=code, **kw)

        path = CONFIG_ROOT / f"{name}.yaml"
        if path.is_file():
            for block in _comment_blocks(path):
                out += claims(block, kind="comments", **kw)

        # The two ruling blocks. A crossref ruling closed *because* we do not
        # hold the chapter is the sharpest form this claim takes -- it is a
        # decision resting on the absence, not a remark about it -- and a
        # reading ruling that parks a row on the same ground is its twin.
        for ref, ruling in sorted(layer.crossrefs.items()):
            out += claims(str(ruling), kind="crossrefs", at=ref, **kw)
        for key, reading in sorted(layer.readings.items()):
            out += claims(reading.note, kind="readings", at=key, **kw)

    return out


def _answers_for(ref: str, cited: set[str], root: str, store: ProvenanceStore) -> bool:
    """Does the layer quote a value out of a document that answers for `ref`?

    The strongest row this check can produce is not a stale sentence but a
    file arguing with itself, so it is worth the extra read: a claim that a
    chapter is missing, standing in a layer that took a number out of it.
    """
    from flats.encode.crossrefs import _doc_ids, _headings

    for path in cited:
        if path.rsplit("/", 1)[0] != root:
            continue
        own = _doc_ids([path])
        if ref in own or any(i.startswith(f"{ref}.") for i in own):
            return True
        text = store.text_path(path).read_text(encoding="utf-8")
        owns = {i.partition(".")[0] for i in own} if own else None
        headings = _headings(text, owns, own)
        if ref in headings or any(h.startswith(f"{ref}.") for h in headings):
            return True
    return False


def render(rows: list[Unheld]) -> str:
    from collections import Counter

    counts = Counter(r.verdict for r in rows)
    bad = [r for r in rows if r.verdict == "contradicted"]
    out = [
        f"written claims that a document is not held: {len(rows)}",
        f"  the store answers for it today:        {counts['contradicted']}",
        f"    of those, the layer QUOTES it:       {sum(1 for r in bad if r.self_contradicted)}",
        f"  still true, and able to go stale:      {counts['outstanding']}",
        f"  written as history, not as a claim:    {counts['settled']}",
    ]
    if bad:
        out += ["", f"CONTRADICTED BY THE STORE: {len(bad)}"]
        for r in sorted(bad, key=lambda r: (not r.self_contradicted, r.label)):
            flag = "  <- and quotes it" if r.self_contradicted else ""
            out.append(f"  [{r.kind}] {r.label} -- holds {', '.join(r.held)}{flag}")
            out.append(f"      {r.claim[:240]}")
    live = [r for r in rows if r.verdict == "outstanding"]
    if live:
        out += ["", f"still true today, and the set that goes stale next: {len(live)}"]
        for r in sorted(live, key=lambda r: r.label):
            out.append(f"  [{r.kind}] {r.label} -- wants {', '.join(r.missing)}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Re-ask every written claim that a document is missing.")
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args(argv)
    rows = audit()
    print(render(rows))
    if args.csv:
        import csv

        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "layer",
                    "kind",
                    "zone",
                    "at",
                    "verdict",
                    "self_contradicted",
                    "held",
                    "missing",
                    "claim",
                ]
            )
            for r in rows:
                w.writerow(
                    [
                        r.layer,
                        r.kind,
                        r.zone or "",
                        r.at,
                        r.verdict,
                        r.self_contradicted,
                        ",".join(r.held),
                        ",".join(r.missing),
                        r.claim,
                    ]
                )
        print("wrote", args.csv)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
