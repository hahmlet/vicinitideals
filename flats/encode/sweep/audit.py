"""Compare what a code document states against what FLATS has a slot for.

The gaps ledger answers "which standards that we name do we not hold". This
answers the question underneath it: *which standards does the code state that we
have no name for at all*. Those are invisible to every other check in the
system, because every other check starts from the field registry and a standard
with no field never enters the loop.

Three buckets come out of one sweep:

``covered``   the sweep found a standard, and it maps to a field we encode.
``missed``    we encode a standard whose citation lands in this document and no
              lens found it. This is the recall score, and it is the reason the
              sweep is worth running over ground we are confident about: it
              measures the measurer. A sweep that misses half of what we already
              hold has no authority to claim the other half is complete.
``unmapped``  the sweep found a standard that maps to no field. This is the
              answer to the question — and it is a *candidate*, not a finding.
              A model reading a zoning chapter will report the sign ordinance
              and the chicken-keeping rules with a straight face.

Nothing here writes to a rule file. The output is a queue, and the queue is
worked by a person, exactly like the unread queue it sits beside.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from flats.encode.sweep.ask import Ask, Finding, sweep
from flats.encode.sweep.chunk import chunks
from flats.encode.sweep.journal import Journal
from flats.provenance.store import ProvenanceError, ProvenanceStore
from flats.rules.fields import FIELDS
from flats.rules.model import Layer

#: Words that name a field in the vocabulary a code uses, rather than the one
#: the registry uses. The registry says "Minimum front setback"; a code says
#: "front yard", and a mapping that only knew the registry's wording would
#: report every front yard rule in Oregon as a standard we have no slot for.
_ALSO: dict[str, tuple[str, ...]] = {
    "quadplex_allowed": ("fourplex", "quadplex", "four attached", "four-unit", "middle housing"),
    "setback_front_ft": ("front yard", "front setback"),
    "setback_side_ft": ("side yard", "interior side", "side setback"),
    "setback_rear_ft": ("rear yard", "rear setback", "back yard"),
    "setback_street_side_ft": ("street side", "corner lot", "side facing street", "street yard"),
    "setback_front_max_ft": ("maximum front", "build-to", "build to line"),
    "setback_garage_entrance_ft": ("garage", "vehicle door", "carport"),
    "min_lot_sqft": ("lot area", "lot size", "square feet per", "site area"),
    "min_lot_width_ft": ("lot width", "width at the building line"),
    "min_frontage_ft": ("frontage", "street frontage", "lot frontage"),
    "land_division_parent_standards": ("land division", "partition", "unit lot", "subdivision"),
    "max_height_ft": ("height", "stories", "storeys"),
    "max_far": ("floor area ratio", "far"),
    "max_coverage_pct": ("lot coverage", "building coverage", "site coverage"),
    "coverage_curve": ("lot coverage", "building coverage"),
    "max_units": ("dwelling units", "density", "units per acre"),
    "min_density_trigger_lot_sqft": ("minimum density",),
    "min_units_at_trigger": ("minimum density", "minimum number of units"),
    "parking_min_per_unit": ("parking", "off-street", "spaces", "stalls"),
    "open_space_min_pct": ("open space", "outdoor area", "private open"),
    "orientation_constraint": ("entrance", "orientation", "face the street", "main entrance"),
}


def _vocabulary() -> dict[str, tuple[re.Pattern[str], ...]]:
    """What each field's standard is called, in code words and registry words."""
    out: dict[str, tuple[re.Pattern[str], ...]] = {}
    for name, field in FIELDS.items():
        words = set(_ALSO.get(name, ()))
        said = field.describe.lower()
        # The registry's own description, minus the words every description has.
        words.update(w for w in re.findall(r"[a-z][a-z-]{4,}", said) if w not in _EMPTY)
        out[name] = tuple(re.compile(rf"\b{re.escape(w)}\b", re.I) for w in sorted(words))
    return out


#: Words that appear in half the descriptions and name nothing.
_EMPTY = frozenset(
    {
        "minimum",
        "maximum",
        "building",
        "which",
        "where",
        "applies",
        "required",
        "standard",
        "value",
        "table",
        "zone",
        "encoded",
        "there",
        "their",
        "these",
        "those",
    }
)


#: Things a zoning code regulates that are not this building and not its lot.
#: A code states them in the same vocabulary — "no fence in a required front
#: yard may exceed three feet" names a front yard and a height and is neither
#: standard. Mapped to nothing rather than to the nearest field, because a
#: mismatch that lands in ``covered`` silently inflates the recall score, and
#: recall is the number the entire sweep is judged by.
_NOT_OURS = re.compile(
    r"\b(?:fence|fencing|wall\s+height|sign|signage|billboard|awning|antenna|"
    r"satellite|dish|tower|flagpole|swimming\s+pool|spa|hot\s+tub|hedge|tree|"
    r"shrub|mailbox|trash|refuse|dumpster|chicken|poultry|livestock|beehive|"
    r"kennel|shipping\s+container|mechanical\s+equipment|air\s+conditioner|"
    r"solar\s+collector|wind\s+turbine)\b",
    re.I,
)


def field_for(text: str, vocabulary: dict[str, tuple[re.Pattern[str], ...]] | None = None) -> str:
    """Which field a described standard belongs to, or "" for none.

    Best match rather than first, because "minimum lot width at the building
    line" names both a width and a setback and only one of them is what it is.

    Returning "" carries two meanings and the caller cannot tell them apart:
    a standard we ought to have a field for and do not, and a standard about
    something that is not our building at all. That is the right way round —
    the output is a queue a person reads, and a person disposes of a fence rule
    in a second. Attaching it to a field takes a reviewer's whole minute and
    corrupts the score besides.
    """
    if _NOT_OURS.search(text):
        return ""
    vocab = vocabulary if vocabulary is not None else _vocabulary()
    best, score = "", 0
    for name, patterns in vocab.items():
        hit = sum(1 for p in patterns if p.search(text))
        if hit > score:
            best, score = name, hit
    return best


@dataclass(frozen=True, slots=True)
class Hole:
    """A standard the sweep found that the field registry has no name for."""

    document: str
    line: int
    standard: str
    applies_to: str
    states: str
    lenses: tuple[str, ...]

    @property
    def quote(self) -> str:
        return f"{self.document}#L{self.line}"


@dataclass(frozen=True, slots=True)
class Report:
    """What one sweep of one layer establishes, and how much to trust it."""

    layer: str
    documents: tuple[str, ...]
    #: Encoded values whose citation is in these documents and which some lens
    #: found. The numerator of recall.
    covered: tuple[str, ...]
    #: Encoded values in these documents that no lens found. The denominator's
    #: other half, and the reason a hole list is or is not worth reading.
    missed: tuple[str, ...]
    holes: tuple[Hole, ...]
    #: How many findings the sweep produced in total, before mapping.
    found: int

    @property
    def recall(self) -> float:
        """Share of the standards we already hold that the sweep rediscovered."""
        known = len(self.covered) + len(self.missed)
        return len(self.covered) / known if known else 0.0

    def summary(self) -> str:
        known = len(self.covered) + len(self.missed)
        return (
            f"{self.layer}: {self.found} finding(s) across {len(self.documents)} document(s); "
            f"recall {self.recall:.0%} ({len(self.covered)}/{known} known standards refound); "
            f"{len(self.holes)} candidate hole(s)"
        )


def _encoded_in(layer: Layer, document: str) -> dict[int, str]:
    """Line -> field, for every value this layer cites into one document.

    Held-out values are included. A standard nobody could cite is still one the
    sweep ought to find, and if it does, the finding is the citation.
    """
    out: dict[int, str] = {}
    for zone in layer.zones.values():
        for name, value in zone.values.items():
            for prov in (value.prov, *(v.prov for v in value.variants)):
                quote = getattr(prov, "quote", "") or ""
                path, _, mark = quote.partition("#L")
                if path != document or not mark:
                    continue
                try:
                    out[int(mark.split("-")[0].lstrip("L"))] = name
                except ValueError:
                    continue
    return out


def judge(
    layer: Layer,
    document: str,
    found: Iterable[Finding],
    *,
    near: int = 3,
    swept: Iterable[tuple[int, int]] | None = None,
) -> tuple[list[str], list[str], list[Hole]]:
    """Sort one document's findings into covered, missed and unmapped.

    ``near`` is how far from an encoded citation a finding may sit and still be
    the same standard. Extraction is line-accurate to a row, not to a character:
    a table row and the heading above it are the same fact two lines apart, and
    an exact-line test would score a sweep that read the table perfectly as
    having missed all of it.

    ``swept`` is the line ranges actually read. A standard on a line no lens was
    shown is not a miss, and counting it as one makes a partial run report a
    recall of zero — which reads as "this model cannot find anything" when what
    happened is "this model was not shown anything". Omit it and the whole
    document is assumed read, which is true of a full run and only of that.
    """
    vocab = _vocabulary()
    encoded = _encoded_in(layer, document)
    if swept is not None:
        windows = list(swept)
        encoded = {
            line: name
            for line, name in encoded.items()
            if any(first <= line <= last for first, last in windows)
        }
    hits = [(f, field_for(f"{f.standard} {f.applies_to}", vocab)) for f in found]

    covered: list[str] = []
    missed: list[str] = []
    for line, name in sorted(encoded.items()):
        if any(
            field == name and abs(one.line - line) <= near for one, field in hits
        ):
            covered.append(f"{document}#L{line} {name}")
        else:
            missed.append(f"{document}#L{line} {name}")

    holes = [
        Hole(
            document=one.document,
            line=one.line,
            standard=one.standard,
            applies_to=one.applies_to,
            states=one.states,
            lenses=one.lenses,
        )
        for one, field in hits
        if not field
    ]
    return covered, missed, holes


def run(
    layer: Layer,
    ask: Ask,
    *,
    store: ProvenanceStore | None = None,
    size: int = 120,
    overlap: int = 60,
    limit: int = 0,
    only: str = "",
    journal: Journal | None = None,
    log: object = None,
) -> Report:
    """Sweep every document this layer declares, and report what it establishes.

    ``only`` narrows it to one document id. Comparing two configurations is the
    routine use of this whole module — is a smaller chunk worth the wall-clock,
    is a larger model worth five times it — and a comparison across different
    documents measures the documents.

    ``journal`` makes the run resumable: a passage already answered there is not
    asked again. The scoring is unchanged either way, because a chunk read an
    hour ago and a chunk read now produce the same findings — what changes is
    that the run may be stopped.
    """
    keeper = store if store is not None else ProvenanceStore()
    documents: list[str] = []
    covered: list[str] = []
    missed: list[str] = []
    holes: list[Hole] = []
    total = 0

    for entry in layer.code:
        if only and entry.id != only:
            continue
        path = f"{layer.layer}/{entry.id}.txt"
        try:
            text = keeper.load(path).text
        except (ProvenanceError, OSError):
            continue
        documents.append(path)
        pieces = chunks(text, document=path, size=size, overlap=overlap)
        if limit:
            pieces = pieces[:limit]
        found: list[Finding] = []
        for n, piece in enumerate(pieces, 1):
            if journal is not None and journal.has(piece):
                found.extend(journal.get(piece))
                continue
            got = sweep(piece, ask)
            if journal is not None:
                # Before the next question, not after the document. A run that
                # dies mid-document must not lose the passages it did read.
                journal.put(piece, got)
            found.extend(got)
            if callable(log):
                log(f"  {path} {n}/{len(pieces)} — {len(found)} finding(s) so far")
        total += len(found)
        was_covered, was_missed, was_holes = judge(
            layer, path, found, swept=[(p.first, p.last) for p in pieces]
        )
        covered.extend(was_covered)
        missed.extend(was_missed)
        holes.extend(was_holes)

    return Report(
        layer=layer.layer,
        documents=tuple(documents),
        covered=tuple(covered),
        missed=tuple(missed),
        holes=tuple(holes),
        found=total,
    )


def write(report: Report, path: Path) -> Path:
    """The report as JSON, ranked so the queue opens on the strongest candidate.

    Ranked by how many lenses saw it. That is a confidence in the *reading*
    rather than in the standard being one of ours, which is why the whole file
    is a queue for a person rather than an input to anything.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    ranked = sorted(report.holes, key=lambda h: (-len(h.lenses), h.document, h.line))
    body = {
        "layer": report.layer,
        "documents": list(report.documents),
        "found": report.found,
        "recall": round(report.recall, 4),
        "covered": list(report.covered),
        "missed": list(report.missed),
        "common": Counter(h.standard.lower() for h in report.holes).most_common(25),
        "holes": [asdict(h) for h in ranked],
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=False), encoding="utf-8")
    return path
