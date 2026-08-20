"""What stands between a jurisdiction and screenable lots.

The encoding effort is a queue of jurisdictions, not a pile of 603 undifferentiated
values, and the two consumers that matter — a person working a review UI and an
agent picking up work — both need the same thing from it: *for this jurisdiction,
what is the next blocking action?*

``review status`` answers "0.0% verified", which is true and useless. It cannot
distinguish a city nobody has found a code URL for from one where every number is
written, quoted and waiting on a signature. Those are hours apart in effort and
they belong in different places in a queue.

So readiness is a **ladder**, and a jurisdiction sits on the first rung it fails:

===============  =========================================================
stage            what it means
===============  =========================================================
``no_zones``     nothing encoded here at all -- no zones, or zones with no
                 standards written under them
``no_source``    zones written, no document declared to read them from
``unfetched``    documents declared, not in the store
``unquoted``     values that point at no text — unreviewable as written
``no_evidence``  quotes that do not resolve to stored text
``misquoted``    quotes that resolve, to text that does not state the number
``undefined``    the evidence is written in a word this city defined and this
                 layer never captured, so geometry would decide it by
                 somebody else's code
``footnoted``    the quoted lines sit under a footnote nobody has ruled on
``unsigned``     everything present; waiting on somebody to read it
``stale``        read, but the source has moved since
``ready``        every value verified against text that still says it
===============  =========================================================

The ladder is ordered by what blocks what, not by severity. Signing values whose
evidence was never fetched is not possible, so ``unfetched`` outranks ``unsigned``
however few documents are missing. That ordering is the whole product: it turns
"603 drafts" into one sentence per jurisdiction that names the next command.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from flats.encode.despace import repair_text
from flats.encode.load import Trusted
from flats.encode.qualified import qualified
from flats.encode.tagging import blocked, gaps
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.model import LIKE, Layer, Status

#: Rungs, blocking-order first. A jurisdiction reports the first one it fails.
STAGES = (
    "no_zones",
    "no_source",
    "unfetched",
    "unquoted",
    "no_evidence",
    "misquoted",
    "undefined",
    "footnoted",
    "unsigned",
    "stale",
    "ready",
)

#: What to do about each, phrased as the thing somebody would actually run or
#: read. `{layer}` is filled in; anything else is prose on purpose, because the
#: first two rungs are human work with no command behind them.
ACTION = {
    # Reached by a jurisdiction with no zones and by one whose zones hold no
    # standards; the work is the same sentence either way.
    "no_zones": "encode this jurisdiction's zones: nothing is written yet",
    "no_source": "find the URL that serves the ordinance text, and declare it under `code:`",
    "unfetched": "python -m flats.provenance.fetch --layer {layer}",
    # Not attach. Most unquoted values are not attachable — the document
    # footnotes the number, states two of them, or never mentions it — and
    # sending every jurisdiction to a command that will refuse them reads as
    # citation work remaining when the real work is finding a chapter. `gaps`
    # sorts them by cause and names attach only where attach can act.
    "unquoted": "python -m flats.encode.review gaps --layer {layer} --verbose",
    "no_evidence": "python -m flats.provenance.fetch --layer {layer} (quotes point at text that is not stored)",
    "misquoted": (
        "python -m flats.encode.attach {layer} --doc {doc} — quotes resolve to text that "
        "does not state the number, which is what a re-fetch does to line numbers"
    ),
    # A number is written in the city's words, and one of those words is one
    # geometry has to decide on a real parcel. Without this city's meaning
    # captured, the parcel gets decided by somebody else's -- four codes give
    # four incompatible corner lots -- and nothing in the file records the
    # substitution. It outranks the footnote rung because it is about the
    # vocabulary the footnote is written in.
    "undefined": (
        "python -m flats.encode.tagging --layer {layer} --gaps, then capture the term "
        "under `definitions:` in this jurisdiction's YAML with its quote"
    ),
    # Signing a number while an unread footnote governs the lines it was read
    # from is how a conditional standard gets encoded as an unconditional one.
    # The footnote may halve the number, or apply it only to a use we are not.
    # Either way the reviewer cannot know until somebody reads it.
    "footnoted": (
        "python -m flats.encode.qualified --layer {layer} --blocking, then rule on each "
        "footnote in flats/config/footnotes/{layer}.yaml"
    ),
    "unsigned": "python -m flats.encode.review queue --layer {layer}, then read and sign",
    "stale": "re-read the values whose source moved, then re-sign",
    "ready": "nothing: every value is verified against text that still says it",
}


@dataclass(frozen=True, slots=True)
class Readiness:
    """One jurisdiction's position on the ladder, and the counts behind it."""

    layer: str
    label: str
    stage: str
    zones: int = 0
    values: int = 0
    verified: int = 0
    #: Declared documents that are not in the store.
    unfetched: tuple[str, ...] = ()
    #: (zone, field) pairs carrying no quote.
    unquoted: tuple[tuple[str, str], ...] = ()
    #: (zone, field) pairs whose quote does not resolve.
    no_evidence: tuple[tuple[str, str], ...] = ()
    #: (zone, field) pairs whose quote resolves to text without the number in
    #: it. The silent one: re-extracting a document moves every line, so a
    #: citation keeps pointing at line 136 while line 136 becomes a nav bar.
    #: Nothing else in the ladder can see that, because the value still has a
    #: quote and the quote still resolves.
    misquoted: tuple[tuple[str, str], ...] = ()
    #: (zone, field) pairs whose evidence is written in a term this city
    #: defines and this layer has not captured -- or one it is silent on in a
    #: chapter we could not read whole, which is the same gap wearing the
    #: other face: their code saying nothing and our matcher finding nothing
    #: look identical and license opposite conclusions.
    undefined: tuple[tuple[str, str], ...] = ()
    #: (zone, field) pairs whose quoted lines sit under a footnote nobody has
    #: ruled on. Not a claim the value is wrong -- a claim that we do not yet
    #: know, which is the only honest state until the note is read.
    footnoted: tuple[tuple[str, str], ...] = ()
    #: Values demoted because their evidence moved.
    stale: int = 0
    #: A declared document, for actions that name one. The first is as good as
    #: any: a jurisdiction with several is one where somebody has to choose,
    #: and printing all of them would bury the sentence.
    doc: str = ""

    @property
    def rung(self) -> int:
        return STAGES.index(self.stage)

    @property
    def ready(self) -> bool:
        return self.stage == "ready"

    @property
    def pct_verified(self) -> float:
        return 100.0 * self.verified / self.values if self.values else 0.0

    @property
    def action(self) -> str:
        return ACTION[self.stage].format(layer=self.layer, doc=self.doc or "<document>")

    def line(self) -> str:
        return (
            f"{self.stage:12} {self.layer:34} {self.verified:>4}/{self.values:<4} verified"
            f"  -> {self.action}"
        )


def _quoted_parts(layer: Layer) -> Iterable[tuple[str, str, str | None, object]]:
    """Every (zone, field, quote, number) in a layer, exceptions included.

    A variant citing a different chapter and an incorporation clause are both
    values somebody has to read, so both are counted here. Leaving either out
    would report a jurisdiction as finished with unread rules in it.
    """
    yield from (
        ("defaults", name, v.prov.quote, getattr(v, "value", None))
        for name, v in layer.defaults.items()
    )
    for zone_code, zone in layer.zones.items():
        for name, value in zone.values.items():
            # A derived standard is checked against the figure the code prints
            # rather than the one arithmetic made of it. MCC 39.4862(C) states
            # 5,000 square feet for each dwelling unit and prints 20,000
            # nowhere; Portland's Table 120-4 asks one unit per 2,500 sq ft of
            # site area and prints 17.424 units per acre nowhere.
            yield (
                zone_code,
                name,
                value.prov.quote,
                value.per_dwelling
                if value.per_dwelling is not None
                else value.sqft_per_unit
                if value.sqft_per_unit is not None
                else getattr(value, "value", None),
            )
            if value.measured_on_quote:
                # The denominator's definition is a rule somebody read, and a
                # citation nothing checks is the provenance hole this field
                # was added to close. No number to corroborate -- what is
                # being verified is that the sentence is still where the file
                # says it is.
                yield (
                    zone_code,
                    f"{name} <{value.measured_on}>",
                    value.measured_on_quote,
                    None,
                )
            for variant in value.variants:
                yield (
                    zone_code,
                    f"{name} [{'+'.join(sorted(variant.when))}]",
                    variant.prov.quote,
                    # A reduction is checked against the percentage the code
                    # states, not against the product. Portland's 33.110 prints
                    # 12,000 and prints 10 and prints 10,800 nowhere, so
                    # looking for the result would flag the one encoding that
                    # did not invent it.
                    variant.reduce_pct
                    if variant.reduce_pct is not None
                    else getattr(variant, "value", None),
                )
        if zone.like is not None:
            yield zone_code, LIKE, zone.like.prov.quote, None
    for w in layer.wanted:
        # Quarantined out of the zones, still owed. Dropping them here would
        # report a jurisdiction as finished the moment its worst values left.
        yield w.zone, w.field, None, getattr(w.value, "value", None)


#: How a number can be printed in an ordinance: 7500, 7,500, 7500.0, 7.5.
#: A number as an ordinance prints one: grouped by commas, possibly decimal,
#: and not preceded by a digit or a dot — the second guard is what keeps the
#: tail of a citation like 33.110.220 from reading as the number 220.
_NUMBER = re.compile(r"(?<![\d.,])\d[\d,]*(?:\.\d+)?")


def _states(text: str, number: float) -> bool:
    """Whether the text states this number, as a number.

    Compared by value rather than by spelling, because a code prints 0.60 for
    six tenths and 7,500 for seven and a half thousand, and every attempt to
    enumerate the spellings either misses one or matches inside a longer
    number — 350 reading as 35, or any line with a 20 in it reading as a
    zero, which matters now that zero is how the corpus says "no minimum".
    """
    for found in _NUMBER.finditer(text):
        try:
            if math.isclose(float(found.group(0).replace(",", "")), number):
                return True
        except ValueError:  # pragma: no cover - the pattern only matches numbers
            continue
    return False


#: An ordinance written as prose spells its numbers: Wilsonville's OTR zone
#: says "Minimum side yard setback: One story: five feet; Two or more stories:
#: seven feet". Encoded as 5 and 7, correctly, against a line in which neither
#: digit appears — 46 of that jurisdiction's values read as misquoted for this
#: reason alone, which is the check disagreeing with the language rather than
#: with the encoding.
_UNITS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
_TENS = {
    20: "twenty", 30: "thirty", 40: "forty", 50: "fifty",
    60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety",
}

#: What a spelled number has to be followed by to count. "One" and "two" are
#: ordinary English words — "one story", "two or more" — and a bare match on
#: them would let a citation about anything at all corroborate a setback of 1.
#: A dimension in a code is always said with its unit close behind.
#:
#: The optional bracket in the middle is the drafting convention this whole
#: corpus is written in -- "Five (5) feet", "seven and one-half (7 1/2)
#: feet". A whole number restated that way is found by the digit scan and
#: never reaches here, but a half is not: Troutdale prints "seven and
#: one-half (7" and breaks the line before the vulgar fraction, which leaves
#: too much whitespace between the two for the fraction repair to join them.
#: The words in front carry the value on their own -- the numeral in brackets
#: is the same number said twice, and stepping over it is what lets the unit
#: behind it be seen.
_UNIT_WORD = re.compile(
    r"^[\s.,:;)\-]{0,3}"
    r"(?:\(\s*[\d\s.,¼½¾⅓⅔⅛⅜⅝⅞]*\)"
    r"[\s.,:;\-]{0,3})?"
    r"(?:and\s+)?(?:feet|foot|ft|inch|inches|stor(?:y|ies)|percent"
    r"|unit|units|space|spaces|square|sq|acre|acres|dwelling|dwellings|percent|%)\b",
    re.I,
)


def _spelled(number: float) -> str:
    """How a code would write this number out in words, or "" for none.

    Whole numbers to ninety-nine, and halves, which is the whole of what any
    ordinance in this corpus spells. Beyond that they print digits.
    """
    whole = int(number)
    if whole != number:
        return f"{_spelled(whole)} and one-half" if abs(number - whole - 0.5) < 1e-9 else ""
    if 0 <= whole < len(_UNITS):
        return _UNITS[whole]
    if whole in _TENS:
        return _TENS[whole]
    if 20 < whole < 100:
        return f"{_TENS[whole // 10 * 10]}-{_UNITS[whole % 10]}"
    return ""


def _says(text: str, number: float) -> bool:
    """Whether the text states this number in words, with a unit behind it."""
    word = _spelled(number)
    if not word:
        return False
    pattern = re.compile(r"\b" + word.replace("-", "[- ]").replace(" ", r"\s+") + r"\b", re.I)
    return any(_UNIT_WORD.match(text[found.end():]) for found in pattern.finditer(text))


#: How an ordinance prints a standard it does not impose. A zero encoded
#: against one of these is not a misquote — it is the only way this system has
#: to say "the code states no minimum here", and the alternative (leaving the
#: field out) inherits the standard for a different housing type.
_STATES_NONE = ("none", "n/a", "no min", "—", "--")

#: The same statement made in a sentence rather than in a table cell. Prose
#: codes do not print an em dash: Wilsonville writes "No setback is required
#: along property lines where townhouses are attached", which states zero as
#: plainly as a zero would and appears in none of the spellings above. The
#: patterns are kept narrow on purpose -- this is the permissive direction,
#: and a bare "no" anywhere in a passage is not a standard being waived.
_NO_STANDARD = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\bno\s+minimum\b",
        r"\bno\s+maximum\b",
        r"\bnot\s+required\b",
        r"\bno\s+[a-z][a-z ]{0,24}?\s+(?:is|are)\s+required\b",
        r"\bthere\s+is\s+no\s+[a-z]+\s+requirement\b",
        # "may be reduced to zero" -- Happy Valley's townhouse footnote, and
        # the one spelled number `_says` cannot see, because it is not
        # followed by a unit the way "five feet" is.
        r"\bzero\b",
    )
)


#: A vulgar fraction is one character, and the number scan reads the digits
#: around it: Clackamas ZDO 315 states the VR-5/7 garage setback as "19½
#: feet to the garage door", which is stored as 19 followed by U+00BD and
#: matches no spelling of 19.5. Rewritten to a decimal before the scan, the
#: way the letter-spacing repair rewrites a scanned line.
_VULGAR = {
    "¼": 0.25, "½": 0.5, "¾": 0.75,
    "⅓": 1 / 3, "⅔": 2 / 3,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}
_FRACTION = re.compile(r"(\d*)\s?([" + "".join(_VULGAR) + r"])")


def _decimalise(text: str) -> str:
    """19½ -> 19.5, and a bare ½ -> 0.5."""

    def sub(m: re.Match[str]) -> str:
        whole = int(m.group(1)) if m.group(1) else 0
        return f"{whole + _VULGAR[m.group(2)]:g}"

    return _FRACTION.sub(sub, text)


#: A number with a footnote marker stuck to it, in a document that says it
#: does that: "154" for fifteen with note 4, and "8.71" for eight point seven
#: with note 1. Only a single trailing digit is tried, and only on a token
#: carrying no comma -- cutting a digit off "7,500" would leave 750 standing
#: in the text as a number the table never printed.
#:
#: The decimal half of this was learned from Gresham's Downtown table, which
#: states its densities to a tenth and its ceilings to a hundredth and marks
#: both: 8.7 units per acre arrives as "8.71" and 12.45 as "12.458". The
#: earlier pattern skipped any token containing a point, so a whole column of
#: correctly cited rates read as misquoted -- the check disagreeing with the
#: flag that was set to tell it about this exact document.
_GLUED = re.compile(r"(?<![\d.,])(\d+(?:\.\d+)?)(?![\d.,])")


def _unmarked(text: str) -> str:
    """The same text with one trailing digit dropped from each bare number."""

    def cut(match: re.Match[str]) -> str:
        token = match.group(0)
        # A marker only ever hangs off the end, and taking it off has to leave
        # a figure behind: "154" -> "15" and "8.71" -> "8.7", but "5" -> ""
        # and "7.1" -> "7." are not numbers any table prints.
        trimmed = token[:-1]
        return trimmed if trimmed and trimmed[-1].isdigit() else token

    return _GLUED.sub(cut, text)


def quotes_the_number(
    text: str, value, *, spaced: bool = False, glued: bool = False
) -> bool:
    """Whether the cited text actually states the value's number.

    Deliberately generous: a code writes "7,500 sq ft" and "0.60" and "7.5
    ft", and a check that demanded one spelling would flag half the corpus.
    Non-numeric values — permission flags, enums, curves — are nothing this
    can check, so they pass. What it does catch is the citation that no
    longer points at its own sentence.

    Spelled numbers count too, where a unit follows them: half this corpus is
    prose rather than tables, and prose says "five feet".

    ``spaced`` repairs a letter-spaced OCR line before looking. Oregon City's
    Title 17 is a scan, and its ten-thousand square feet is stored as
    "1 0 , 000 squ are f eet" — a correct quote that no spelling of 10000
    appears in. Fifteen of its values read as misquoted for that reason alone,
    which is a check disagreeing with itself: the same flag that tells the
    readers to repair this document told this one to compare it raw.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    hay = _decimalise(repair_text(text) if spaced else text)
    if _states(hay, float(value)) or _says(hay, float(value)):
        return True
    if glued and _states(_unmarked(hay), float(value)):
        return True
    if value != 0:
        return False
    lowered = hay.lower()
    return any(word in lowered for word in _STATES_NONE) or any(
        pattern.search(hay) for pattern in _NO_STANDARD
    )


def _statuses(layer: Layer) -> list[Status]:
    out = [v.status for v in layer.defaults.values()]
    for zone in layer.zones.values():
        for value in zone.values.values():
            out.append(value.status)
            out.extend(v.status for v in value.variants)
        if zone.like is not None:
            out.append(zone.like.status)
    return out


def readiness_for(
    layer: Layer,
    *,
    store: ProvenanceStore,
    stale: int = 0,
    footnoted: Sequence[tuple[str, str]] = (),
    undefined: Sequence[tuple[str, str]] = (),
) -> Readiness:
    """Place one jurisdiction on the ladder."""
    statuses = _statuses(layer)
    verified = sum(1 for s in statuses if s is Status.verified)

    unfetched = tuple(sorted(p for p in layer.documents() if not store.exists(p)))
    spaced = frozenset(p for p, doc in layer.documents().items() if doc.spaced)
    glued = frozenset(p for p, doc in layer.documents().items() if doc.glued_markers)
    unquoted: list[tuple[str, str]] = []
    no_evidence: list[tuple[str, str]] = []
    misquoted: list[tuple[str, str]] = []
    parts = list(_quoted_parts(layer))
    for zone_code, name, quote, number in parts:
        if not quote:
            unquoted.append((zone_code, name))
            continue
        try:
            cited = store.quote(quote)
        except (ProvenanceError, KeyError, ValueError):
            # Whatever went wrong — document absent, line range past the end,
            # malformed reference — the reviewer's problem is the same: there
            # is nothing on screen to compare the number against.
            no_evidence.append((zone_code, name))
            continue
        doc_id = quote.split("#", 1)[0]
        if not quotes_the_number(
            cited, number, spaced=doc_id in spaced, glued=doc_id in glued
        ):
            misquoted.append((zone_code, name))

    if not parts:
        # Not `not layer.zones`: a zone may be declared and still hold nothing.
        # Johnson City is one zone block with a label, no standards under it
        # and no ordinance published to write any from. Every later rung asks a
        # question about a value, so with no values every one of them passes,
        # and the ladder called the emptiest jurisdiction in the corpus
        # finished. `parts` rather than `statuses` because a quarantined value
        # is still an encoded one -- it is why the rung above this exists.
        stage = "no_zones"
    elif not layer.code:
        stage = "no_source"
    elif unfetched:
        stage = "unfetched"
    elif unquoted:
        stage = "unquoted"
    elif no_evidence:
        stage = "no_evidence"
    elif misquoted:
        stage = "misquoted"
    elif undefined:
        stage = "undefined"
    elif footnoted:
        stage = "footnoted"
    elif verified < len(statuses):
        stage = "unsigned"
    elif stale:
        stage = "stale"
    else:
        stage = "ready"

    return Readiness(
        layer=layer.layer,
        label=layer.label,
        stage=stage,
        zones=len(layer.zones),
        values=len(statuses),
        verified=verified,
        unfetched=unfetched,
        unquoted=tuple(unquoted),
        no_evidence=tuple(no_evidence),
        misquoted=tuple(misquoted),
        undefined=tuple(undefined),
        footnoted=tuple(footnoted),
        stale=stale,
        doc=next(iter(layer.documents()), ""),
    )


def readiness(
    trusted: Trusted,
    store: ProvenanceStore,
    *,
    footnoted: dict[str, list[tuple[str, str]]] | None = None,
    undefined: dict[str, tuple[tuple[str, str], ...]] | None = None,
) -> list[Readiness]:
    """Every jurisdiction, worst rung first.

    Ties break on how much is already verified, descending — among cities at the
    same rung, the one closest to done is the cheapest to finish, and finishing
    one jurisdiction is worth more than advancing three, because a half-encoded
    city screens no lots at all.
    """
    stale_by_layer: dict[str, int] = {}
    for s in trusted.stale:
        stale_by_layer[s.layer] = stale_by_layer.get(s.layer, 0) + 1

    # Computed once for the whole corpus: the join reads every stored document
    # to find its footnotes, which is cheap once and silly per jurisdiction.
    # Injectable because it is the one input that does not come from the store
    # this function was handed -- a caller working against a different corpus
    # has to be able to say so, or it reads the real one behind their back.
    footnoted_by_layer: dict[str, list[tuple[str, str]]] = {}
    if footnoted is None:
        for row in qualified():
            if row.blocking:
                footnoted_by_layer.setdefault(row.layer, []).append((row.zone, row.field))
    else:
        footnoted_by_layer = footnoted

    # Same argument, same injection: the vocabulary gate reads every stored
    # definitions chapter, which is cheap once and wrong to do behind the back
    # of a caller working against a corpus of their own.
    undefined_by_layer = blocked(gaps(store=store)) if undefined is None else undefined

    out = [
        readiness_for(
            layer,
            store=store,
            stale=stale_by_layer.get(layer_id, 0),
            footnoted=footnoted_by_layer.get(layer_id, ()),
            undefined=undefined_by_layer.get(layer_id, ()),
        )
        for layer_id, layer in trusted.layers.items()
    ]
    out.sort(key=lambda r: (r.rung, -r.pct_verified, r.layer))
    return out


def by_stage(reports: Iterable[Readiness]) -> dict[str, int]:
    """How many jurisdictions sit on each rung, in ladder order."""
    counts = {stage: 0 for stage in STAGES}
    for r in reports:
        counts[r.stage] += 1
    return {k: v for k, v in counts.items() if v}


__all__ = [
    "ACTION",
    "STAGES",
    "Readiness",
    "by_stage",
    "readiness",
    "readiness_for",
]
