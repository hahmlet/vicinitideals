"""Which of a city's own words a number is written in, and which we never read.

The glossary captures every term a jurisdiction defined. This is what the
capture is *for*: taking the lines an encoded value was read from and marking
the words in them that this city gave its own meaning to. A reviewer sees the
sentence as the city wrote it, with its vocabulary marked and each mark
carrying the line where the city defined it. Nothing is rewritten. The city's
text stays the citation; the marks are a layer over it.

Marking is not a gate. Almost every dimensional standard is written in defined
words -- lot, street, setback, story -- and a gate that fires on all of them
fires on everything and means nothing. What blocks is narrower and follows
from what FLATS actually does:

``uncaptured``
    This city defines a term FLATS has to *evaluate* on a real lot, and the
    layer has not captured that definition. Geometry still has to decide
    whether a parcel is a corner lot, so it decides with somebody else's
    meaning, uncited, and no citation in the file records the substitution.
    Four codes define corner lot four incompatible ways; this is the rung
    that stops the fifth from being screened with the fourth's test.

``unread``
    The layer relies on the city being *silent* about such a term -- and the
    silence rests on a chapter the glossary could not read whole. "Their code
    does not define it" and "our matcher did not find it" produce the same
    empty result and license opposite conclusions, and only one of them is a
    finding about the code. A chapter reported thin or skimmed cannot support
    the first, so silence there is not evidence yet.

Run it::

    uv run python -m flats.encode.tagging --layer or/multnomah/gresham
    uv run python -m flats.encode.tagging --gaps
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence

from flats.encode.definitions import PHRASE
from flats.encode.glossary import Chapter, Entry, chapters
from flats.encode.qualified import _quoted
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.definitions import TERMS
from flats.rules.loader import load_rules
from flats.rules.model import Layer

#: Shorter than this and marking the word is noise rather than help: "a",
#: "of", and the odd two-letter acronym a code defines in passing.
MIN_MARK = 4

#: A term the city indexed backwards. Codes headline "Lot, Corner" as often as
#: "Corner Lot", and a reader looking at a standard sees the forward form.
_INVERTED = re.compile(r"^(?P<head>[A-Za-z][A-Za-z ]*?)\s*[,(]\s*(?P<tail>[A-Za-z][A-Za-z ]*?)\)?$")

_PUNCT = re.compile(r"[^a-z0-9 ]")
_SPACE = re.compile(r"\s+")


def normal(term: str) -> str:
    """A term as it is matched: case-folded, punctuation dropped, collapsed."""
    return _SPACE.sub(" ", _PUNCT.sub(" ", term.lower())).strip()


def spellings(entry: Entry) -> tuple[str, ...]:
    """Every way this entry's term appears in the body of a code.

    A code that defines "Lot, Corner" writes "corner lot" in the standard, so
    an index built only from the entry's own spelling marks nothing where it
    matters most.
    """
    out = [normal(entry.term)]
    inverted = _INVERTED.match(entry.term.strip())
    if inverted is not None:
        out.append(normal(f"{inverted.group('tail')} {inverted.group('head')}"))
    return tuple(dict.fromkeys(s for s in out if len(s) >= MIN_MARK))


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One defined word, found in the text an encoded value was read from."""

    term: str
    #: How it is spelled at this occurrence, in the city's own line.
    spelled: str
    #: Where the city defined it, as a quote a reviewer can open.
    defined_at: str


@dataclass(frozen=True, slots=True)
class Tagged:
    """One encoded value and this city's vocabulary inside its evidence."""

    layer: str
    zone: str
    field: str
    quote: str
    marks: tuple[Occurrence, ...]


@dataclass(frozen=True, slots=True)
class Gap:
    """A term FLATS must evaluate whose meaning this layer cannot supply."""

    layer: str
    term: str
    #: ``uncaptured`` or ``unread`` -- see the module docstring.
    kind: str
    detail: str
    affected: tuple[tuple[str, str], ...]

    @property
    def blocking(self) -> bool:
        return True


class Index:
    """A jurisdiction's defined vocabulary, ready to mark text with."""

    def __init__(self, chapter: Chapter | None) -> None:
        self.chapter = chapter
        self.by_spelling: dict[str, Entry] = {}
        for entry in chapter.entries if chapter else ():
            for spelling in spellings(entry):
                # First definition wins. A codifier that prints a term twice
                # is usually cross-referencing the first printing.
                self.by_spelling.setdefault(spelling, entry)
        self._pattern = self._compile()

    def _compile(self) -> re.Pattern[str] | None:
        if not self.by_spelling:
            return None
        # Longest first, so "corner lot" marks as one word rather than as
        # "lot" with a stray adjective in front of it.
        alternatives = "|".join(
            re.escape(s).replace(r"\ ", r"\s+")
            for s in sorted(self.by_spelling, key=len, reverse=True)
        )
        return re.compile(rf"(?<![A-Za-z]){alternatives}(?![A-Za-z])", re.I)

    def marks(self, text: str) -> tuple[Occurrence, ...]:
        """Every defined word in a passage, once each, in the order they fall."""
        if self._pattern is None:
            return ()
        seen: dict[str, Occurrence] = {}
        for found in self._pattern.finditer(text):
            spelled = found.group(0)
            entry = self.by_spelling.get(normal(spelled))
            if entry is None:
                continue
            seen.setdefault(
                normal(spelled),
                Occurrence(term=entry.term, spelled=spelled, defined_at=entry.quote),
            )
        return tuple(seen.values())

    def defines(self, term: str) -> Entry | None:
        """Whether the city defined one of *our* terms, by its own spelling.

        Matched through the same phrasing the coverage register uses, because
        a code's spelling of a term is not our name for it -- ``corner_lot``
        is a hook in our vocabulary and "Lot (Corner)" is theirs.
        """
        phrase = PHRASE.get(term)
        for entry in self.chapter.entries if self.chapter else ():
            if phrase is not None and re.search(phrase, entry.term, re.I):
                return entry
            if normal(entry.term) == term.replace("_", " "):
                return entry
        return None


@lru_cache(maxsize=None)
def index(layer_id: str) -> Index:
    """One jurisdiction's vocabulary, read once."""
    found = chapters(layer_id)
    return Index(found[0] if found else None)


def _text(store: ProvenanceStore, quote: str) -> str:
    try:
        return store.quote(quote)
    except (ProvenanceError, FileNotFoundError, ValueError):
        # A quote that does not resolve is a rung of its own, and a louder
        # one. Nothing to mark here.
        return ""


def _evidence(layer: Layer) -> Iterable[tuple[str, str, str]]:
    """Every passage a layer's values rest on, the denominators included.

    A density per net acre rests on two sentences, not one: the table cell
    that prints the rate, and the definition that says what the acre is. The
    second is where a city's vocabulary is thickest -- Milwaukie's net acre
    names floodplains, protected water features, vegetated corridors and Goal
    5 resources in a single sentence -- so leaving it out marked the number
    and skipped the arithmetic under it.
    """
    yield from _quoted(layer)
    for zone_code, zone in sorted(layer.zones.items()):
        for name, value in sorted(zone.values.items()):
            if value.measured_on_quote:
                yield zone_code, f"{name} <{value.measured_on}>", value.measured_on_quote


def tagged(layer_id: str | None = None, *, store: ProvenanceStore | None = None) -> list[Tagged]:
    """Every quoted value in the corpus, with this city's words marked in it."""
    store = store or ProvenanceStore()
    out: list[Tagged] = []
    for identifier, layer in sorted(load_rules().items()):
        if layer_id and identifier != layer_id:
            continue
        vocabulary = index(identifier)
        if not vocabulary.by_spelling:
            continue
        for zone, field, quote in _evidence(layer):
            marks = vocabulary.marks(_text(store, quote))
            if marks:
                out.append(
                    Tagged(layer=identifier, zone=zone, field=field, quote=quote, marks=marks)
                )
    return out


def _affected(layer: Layer, term: str, *, store: ProvenanceStore) -> tuple[tuple[str, str], ...]:
    """The values whose evidence is written in a term we cannot evaluate."""
    phrase = PHRASE.get(term) or re.escape(term.replace("_", " "))
    hits: list[tuple[str, str]] = []
    for zone, field, quote in _evidence(layer):
        if re.search(phrase, _text(store, quote), re.I):
            hits.append((zone, field))
    return tuple(hits)


def gaps(layer_id: str | None = None, *, store: ProvenanceStore | None = None) -> list[Gap]:
    """Terms FLATS must evaluate whose meaning a layer cannot supply."""
    store = store or ProvenanceStore()
    out: list[Gap] = []
    for identifier, layer in sorted(load_rules().items()):
        if layer_id and identifier != layer_id:
            continue
        vocabulary = index(identifier)
        for term in TERMS:
            if term in layer.definitions:
                continue
            entry = vocabulary.defines(term)
            if entry is not None:
                out.append(
                    Gap(
                        layer=identifier,
                        term=term,
                        kind="uncaptured",
                        detail=entry.quote,
                        affected=_affected(layer, term, store=store),
                    )
                )
                continue
            chapter = vocabulary.chapter
            if chapter is not None and not chapter.read_whole:
                out.append(
                    Gap(
                        layer=identifier,
                        term=term,
                        kind="unread",
                        detail=(
                            f"{chapter.doc}: {len(chapter.entries)} entries, "
                            f"{len(chapter.disorder)} out of order, "
                            f"{chapter.density:.1f}/100 lines"
                        ),
                        affected=_affected(layer, term, store=store),
                    )
                )
    return out


def blocked(rows: Iterable[Gap]) -> dict[str, tuple[tuple[str, str], ...]]:
    """Affected values per layer, for the readiness ladder."""
    out: dict[str, list[tuple[str, str]]] = {}
    for gap in rows:
        out.setdefault(gap.layer, []).extend(gap.affected)
    return {layer: tuple(dict.fromkeys(values)) for layer, values in out.items()}


def render(rows: Sequence[Tagged]) -> str:
    """The marks as text, for a terminal."""
    lines = [
        f"{row.layer:<28} {row.zone:<10} {row.field:<26} "
        + ", ".join(f"{m.spelled} -> {m.defined_at}" for m in row.marks[:4])
        for row in rows
    ]
    lines.append("")
    lines.append(
        f"values={len(rows)}  marks={sum(len(r.marks) for r in rows)}  "
        f"jurisdictions={len({r.layer for r in rows})}"
    )
    return "\n".join(lines)


def render_gaps(rows: Sequence[Gap]) -> str:
    """The gate as text."""
    lines = [
        f"{gap.layer:<28} {gap.term:<12} {gap.kind:<11} "
        f"{len(gap.affected):>3} values  {gap.detail}"
        for gap in rows
    ]
    lines.append("")
    lines.append(
        f"gaps={len(rows)}  uncaptured={sum(1 for g in rows if g.kind == 'uncaptured')}  "
        f"unread={sum(1 for g in rows if g.kind == 'unread')}  "
        f"values={sum(len(g.affected) for g in rows)}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    layer = args[args.index("--layer") + 1] if "--layer" in args else None
    if "--gaps" in args:
        print(render_gaps(gaps(layer)))
        return 0
    print(render(tagged(layer)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["Gap", "Index", "Occurrence", "Tagged", "blocked", "gaps", "index", "render", "tagged"]
