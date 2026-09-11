"""The two ledgers. Neither substitutes for the other.

**Coverage ledger** — *which zones are missing.* Enumerates every
``(jurisdiction, zone)`` pair **observed in the GIS data**, joins it against the
encoded rules, and ranks the gaps by how many lots they block. This is the
encoding work queue, generated rather than hand-maintained.

Quadfit's failure mode was that an unencoded zone vanished into a
``zone_not_in_rules`` bucket and stopped being anyone's problem — 88,947 lots,
40,500 of them multi-dwelling Portland land nobody had decided to exclude. A
coverage ledger makes that impossible to miss: the gap is a top row, not an
absence.

It has a blind spot of its own, and ``unweighed`` is what reports it: the
ledger ranks only jurisdictions the parcel corpus contains, so a layer the
corpus has never held a lot for is not a zero on the report -- it is missing
from the report. See that function.

**Clause ledger** — *within an encoded zone, which sentences of code are
unaccounted for.* Coverage alone would have caught RM1; it would never catch a
missed exception clause inside a zone we believed was finished. Every clause of
a cited code section is tagged with a RASE operator; an unclassified clause is
a gap that blocks the zone from ``verified``.
"""

from __future__ import annotations

import csv
import enum
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from flats.rules.model import Status
from flats.rules.resolver import RuleSet, Verdict


class Coverage(str, enum.Enum):
    """Encoding state of one observed (jurisdiction, zone) pair."""

    #: Every value present and verified.
    verified = "verified"
    #: Encoded, some values still draft or encoded.
    partial = "partial"
    #: Encoded, but a cited source has changed since it was verified.
    stale = "stale"
    #: Jurisdiction encoded, this zone is not.
    zone_missing = "zone_missing"
    #: No layer for this jurisdiction at all.
    jurisdiction_missing = "jurisdiction_missing"

    @property
    def blocks(self) -> bool:
        """True when lots in this pair cannot reach GREEN as things stand."""
        return self is not Coverage.verified


@dataclass(frozen=True, slots=True)
class ObservedZone:
    """A (jurisdiction, zone) pair seen in the parcel data, with its weight."""

    jurisdiction: str
    zone: str
    lots: int
    acres: float = 0.0


@dataclass(frozen=True, slots=True)
class CoverageRow:
    jurisdiction: str
    zone: str
    lots: int
    acres: float
    status: str
    verified_fields: int
    total_fields: int
    missing_required: str
    untrusted_fields: str
    #: Lots that would leave REVIEW if this row were verified. Sort key.
    blocking: int


def build_coverage(
    observed: Iterable[ObservedZone], rules: RuleSet, *, eligible_only: bool = False
) -> list[CoverageRow]:
    """Join observed zones against encoded rules, ranked by lots blocked.

    ``eligible_only`` drops jurisdictions toggled off. Off by default: a
    jurisdiction can be re-enabled with a report-time re-run, so its encoding
    backlog is still worth seeing.
    """
    rows: list[CoverageRow] = []
    for obs in observed:
        if eligible_only and not rules.eligible(obs.jurisdiction):
            continue

        res = rules.resolve(obs.jurisdiction, obs.zone)
        if res.verdict is Verdict.jurisdiction_not_encoded:
            status, verified_n, total_n = Coverage.jurisdiction_missing, 0, 0
        elif res.verdict is Verdict.zone_not_encoded:
            status, verified_n, total_n = Coverage.zone_missing, 0, 0
        else:
            total_n = len(res.values)
            verified_n = sum(1 for r in res.values.values() if r.trusted)
            if any(r.status is Status.stale for r in res.values.values()):
                status = Coverage.stale
            elif res.verdict is Verdict.trusted:
                status = Coverage.verified
            else:
                status = Coverage.partial

        rows.append(
            CoverageRow(
                jurisdiction=obs.jurisdiction,
                zone=obs.zone,
                lots=obs.lots,
                acres=round(obs.acres, 2),
                status=status.value,
                verified_fields=verified_n,
                total_fields=total_n,
                missing_required=";".join(res.missing_required),
                untrusted_fields=";".join(res.untrusted),
                blocking=obs.lots if status.blocks else 0,
            )
        )

    rows.sort(key=lambda r: (-r.blocking, -r.lots, r.jurisdiction, r.zone))
    return rows


def write_coverage(rows: Sequence[CoverageRow], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CoverageRow.__slots__))
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)
    return path


#: Where the generated coverage ledger is written. Data rather than
#: configuration — rebuilt by ``python -m flats.encode.backlog`` from the parcel
#: corpus, and committed so that a deploy carries the counts with the rules.
COVERAGE = Path(__file__).resolve().parents[2] / "data" / "flats" / "coverage.csv"


def read_coverage(path: Path | None = None) -> list[CoverageRow] | None:
    """The written ledger, read back, or None where nobody has generated one.

    None and an empty list are opposite answers and must not be confused: the
    first says nothing has counted the lots, the second says nothing is blocked.
    Reading the ledger from disk rather than rebuilding it is deliberate — the
    build reads a 62 MB parcel corpus, which is a command, not a page load.
    """
    try:
        with (path or COVERAGE).open(newline="", encoding="utf-8") as fh:
            return [
                CoverageRow(
                    jurisdiction=row["jurisdiction"],
                    zone=row["zone"],
                    lots=int(row["lots"] or 0),
                    acres=float(row["acres"] or 0),
                    status=row["status"],
                    verified_fields=int(row["verified_fields"] or 0),
                    total_fields=int(row["total_fields"] or 0),
                    missing_required=row["missing_required"],
                    untrusted_fields=row["untrusted_fields"],
                    blocking=int(row["blocking"] or 0),
                )
                for row in csv.DictReader(fh)
            ]
    except (OSError, KeyError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class UnweighedLayer:
    """An encoded jurisdiction the parcel corpus holds no lot for."""

    jurisdiction: str
    zones: int
    eligible: bool


def unweighed(rows: Sequence[CoverageRow], rules: RuleSet) -> list[UnweighedLayer]:
    """Encoded jurisdictions that never appear in the coverage ledger at all.

    The coverage ledger answers "which of the zones we can see are missing
    rules". It cannot answer the mirror question, and the mirror question is
    the one that hides the larger hole: which of the rules we have written has
    nothing ever counted lots against?

    A layer with zones and no observed parcel is not a zero on a report. It is
    absent from the report, and absence reads as done. Every ranking the
    backlog prints, every "N lots blocked" headline, and every judgement about
    what to encode next is computed over the jurisdictions the corpus happens
    to contain — so a layer outside it is not merely unranked, it is silently
    excluded from the denominator.

    That was not hypothetical, and for months this docstring described the
    live case: the parcel corpus was Multnomah County only, ten encoded
    Clackamas jurisdictions had never had a lot weighed against them, and Lake
    Oswego looked like the exception without being one -- its rows came from
    the sliver of the city inside Multnomah, 757 lots in the four zones that
    happened to be encoded, which is exactly why the six zones it was missing
    could not surface here.

    **Closed 2026-09-08.** The ledger was regenerated over the two-county
    corpus the screening pipeline already runs on -- 333 pairs over 334,959
    lots against 155 over 236,889, eighteen jurisdictions against fourteen --
    and this function now returns an empty list. It stays because an empty
    answer from a check like this is worth something only while the check is
    still asked, and because the failure it guards against is not a one-off:
    it recurred the same day it was found, when a district audit ranked
    fourteen cities at zero lots apiece from the stale ledger and nearly
    closed its own queue on the number.

    What it still cannot see is a city the pipeline is switched off for. An
    ineligible jurisdiction gets no zoning join at all, so its lots arrive
    under ``UNZONED`` rather than absent -- Lake Oswego is 14,256 of them --
    and a layer with one such row is not "unweighed" even though every zone in
    it is. That is a different hole and it is named in the plan, not fixed
    here.

    Reported from the written ledger rather than the parcel corpus on purpose.
    The corpus is a 130 MB read and a command; the ledger is what shipped, and
    what shipped is what a reader is entitled to be told the shape of.
    """
    seen = {row.jurisdiction for row in rows}
    return [
        UnweighedLayer(name, len(layer.zones), bool(layer.eligible))
        for name, layer in sorted(rules.layers.items())
        if layer.zones and name not in seen
    ]


#: What a parcel whose zoning join came back blank is called in the ledger.
#: Spelled here as well as in ``flats.encode.backlog`` on purpose: this module
#: is imported by the web app and must not pull in the parquet reader to learn
#: the name of its own sentinel.
UNZONED_LABEL = "(unzoned in parcel data)"


class ZoneMiss(str, enum.Enum):
    """Why an encoded zone has never had a lot weighed against it.

    Three causes, and the point of separating them is that they take three
    different actions. Collapsing them into "not weighed" produces a list
    nobody can work.
    """

    #: The zoning join produced nothing for this city, so every lot arrived
    #: under ``UNZONED_LABEL`` and every zone in the layer is unweighed at
    #: once. Not an encoding gap -- the encoding is fine and the join is
    #: absent. Usually a jurisdiction the pipeline is switched off for.
    unzoned = "unzoned"
    #: The map does carry this district, under a label we do not hold -- a
    #: suffix the code text does not print, or dirty data. The lots are
    #: sitting in the ``zone_missing`` queue as "go encode this" when the
    #: encoding already exists. Fix the join, not the rules.
    near_miss = "near_miss"
    #: The map carries real districts for this city and none of them is this
    #: one. Either the district was repealed and our text is superseded, or
    #: it exists on paper and was never mapped. Both need a human; neither is
    #: answerable from inside this repo.
    unmapped = "unmapped"


@dataclass(frozen=True, slots=True)
class UnweighedZone:
    """An encoded zone the parcel corpus has never counted a lot against."""

    jurisdiction: str
    zone: str
    cause: ZoneMiss
    eligible: bool
    #: Observed labels that look like this zone, biggest first. Populated only
    #: for :attr:`ZoneMiss.near_miss`; the evidence for the claim, so a reader
    #: can check the match rather than take it.
    candidates: tuple[tuple[str, int], ...] = ()

    @property
    def lots(self) -> int:
        """Lots sitting under a near-miss label. Zero for the other causes."""
        return sum(n for _, n in self.candidates)


def _norm_zone(zone: str) -> str:
    """A zone label reduced to what is invariant across a map and a code book.

    Case, whitespace and punctuation are exactly the characters that differ
    between the two, and never the characters that distinguish two districts:
    no city has both an ``R-5`` and a separate ``R5``. Stripping them is
    therefore safe in the direction that matters -- it can merge two spellings
    of one district, and cannot merge two districts.
    """
    return re.sub(r"[^A-Z0-9]", "", zone.upper())


def near_label(encoded: str, observed: str) -> bool:
    """Could ``observed`` on the map be ``encoded`` in the code, mis-joined?

    Deliberately narrow. Two shapes only:

    * **Identical once normalised** -- ``MURM2`` / ``' MURM2'`` / ``MURm2``.
      Dirty data, and three rows in the queue for one district.
    * **One is the other plus a short tail** -- ``MURM`` against ``MURM1``,
      ``MURM2``, ``MURM3``. A code book that prints a family under its stem
      and a map that prints the members.

    It refuses the obvious third shape, a substitution, and that refusal is
    the whole reason this is usable. Tualatin encodes ``RML`` and its map
    prints ``RMH``; those are one character apart and they are two real
    districts in the city's own code. An edit-distance rule flags that pair
    and sends a reader to repair something that is not broken. Measured over
    the committed ledger, this rule fires on exactly one encoded zone
    corpus-wide and does not fire on ``RML``/``RMH``.

    A hit is a question for a person, never an alias. Nothing here writes a
    rule: see the module docstring on why a machine agreeing with a machine is
    still nobody having read the sentence.
    """
    a, b = _norm_zone(encoded), _norm_zone(observed)
    if not a or not b:
        return False
    if a == b:
        return True
    lo, hi = (a, b) if len(a) < len(b) else (b, a)
    return hi.startswith(lo) and len(hi) - len(lo) <= 2


def unweighed_zones(
    rows: Sequence[CoverageRow], rules: RuleSet
) -> list[UnweighedZone]:
    """Encoded **zones** no lot has ever been weighed against.

    :func:`unweighed` asks the same question one level up and, since
    2026-09-08, correctly returns nothing: every encoded jurisdiction appears
    in the ledger. That empty answer is what hides these. A city is "weighed"
    the moment one of its zones is, so a layer can sit in the ledger looking
    covered while ten of its eleven districts have never been counted.

    Measured on the committed ledger the day this was written: **14 of 220
    encoded (layer, zone) pairs had never had a lot weighed against them, and
    :func:`unweighed` reported zero**, because all fourteen live in
    jurisdictions that do appear.

    They split by :class:`ZoneMiss` into three causes taking three actions:

    * ``unzoned`` -- 12 zones over 3 cities, 14,485 lots arriving with no
      zone at all (Lake Oswego 14,256, Rivergrove 222, Johnson City 7). The
      hole :func:`unweighed` names in its own docstring and says is "not
      fixed here". At zone granularity it is caught automatically, including
      the two cities nobody had named.
    * ``near_miss`` -- Happy Valley ``MURM``, against five map labels holding
      **486 lots**: ``MURM1`` (172), ``MURM2`` (300), ``MURM3`` (8), plus
      ``' MURM2'`` (5) and ``'MURm2'`` (1), which are the same district spelled
      with a leading space and a lowercase letter. All five sit in the
      ``zone_missing`` queue as work to do, and the reading that answers them
      was already written -- ``happy-valley.yaml`` records "if the layer does
      print them, they are three ``like`` entries and this note is the reading
      behind them." The layer does print them. Nothing joined the note to the
      ledger, because a ``zone_missing`` row carries no hint that a sibling
      zone in the same file already holds its answer.
    * ``unmapped`` -- Tualatin ``RML``: encoded, and the map's residential
      districts are ``RL`` and ``RMH``. Either repealed or never mapped, and
      the published base rates say to expect this at roughly 3% and 15% of
      districts respectively, so it will recur.

    **No disposition is recorded here and that is deliberate.** An ``extinct``
    member was proposed for :class:`Coverage`, but ``Coverage`` types an
    *observed* pair, and a district that was repealed or never mapped is by
    definition not observed -- the member would be unreachable by
    construction. The finding belongs on this dataclass, where the zone is the
    subject. Where a ruling should eventually live is with the zone in its
    jurisdiction YAML, and that is worth building when there is a ruling to
    store rather than a schema to admire.

    Reported from the written ledger, like :func:`unweighed`, for the same
    reason: what shipped is what a reader is entitled to be told the shape of.
    """
    by_layer: dict[str, list[CoverageRow]] = {}
    for row in rows:
        by_layer.setdefault(row.jurisdiction, []).append(row)

    out: list[UnweighedZone] = []
    for name, layer in sorted(rules.layers.items()):
        seen = by_layer.get(name, [])
        weighed = {row.zone for row in seen}
        # Labels still wanted by the queue, minus the blank-join sentinel --
        # which is not a label and must never be matched against one.
        missing = [
            row
            for row in seen
            if row.status == Coverage.zone_missing.value and row.zone != UNZONED_LABEL
        ]
        # A layer whose every row is the sentinel was never joined at all.
        joined = any(row.zone != UNZONED_LABEL for row in seen)

        for zone in sorted(layer.zones):
            if zone in weighed:
                continue
            hits = sorted(
                ((row.zone, row.lots) for row in missing if near_label(zone, row.zone)),
                key=lambda c: (-c[1], c[0]),
            )
            if not joined:
                cause = ZoneMiss.unzoned
            elif hits:
                cause = ZoneMiss.near_miss
            else:
                cause = ZoneMiss.unmapped
            out.append(
                UnweighedZone(
                    jurisdiction=name,
                    zone=zone,
                    cause=cause,
                    eligible=bool(layer.eligible),
                    candidates=tuple(hits) if cause is ZoneMiss.near_miss else (),
                )
            )

    out.sort(key=lambda u: (-u.lots, u.jurisdiction, u.zone))
    return out


def coverage_summary(rows: Sequence[CoverageRow]) -> dict[str, int]:
    """Headline counts for the dashboard and the run summary."""
    out: dict[str, int] = {"lots_total": 0, "lots_blocked": 0}
    for r in rows:
        out["lots_total"] += r.lots
        out["lots_blocked"] += r.blocking
        out[f"lots_{r.status}"] = out.get(f"lots_{r.status}", 0) + r.lots
        out[f"zones_{r.status}"] = out.get(f"zones_{r.status}", 0) + 1
    return out


# --- clause ledger ---------------------------------------------------


class Rase(str, enum.Enum):
    """RASE operators. Every normative clause is exactly one of these.

    Tagging is what makes completeness checkable: a code section is covered when
    every clause in it carries a tag, so "did we miss an exception?" becomes a
    query rather than a worry.
    """

    #: When the clause applies at all — "in the R5 zone", "for a fourplex".
    applicability = "A"
    #: Which subset within applicability — "on a corner lot".
    selection = "S"
    #: The normative constraint — "the front setback shall be at least 10 feet".
    requirement = "R"
    #: Negates or overrides a requirement — "except where an alley abuts".
    exception = "E"
    #: Definitions, cross-references, purpose statements. Carries no rule.
    non_normative = "N"


@dataclass(frozen=True, slots=True)
class Clause:
    """One tagged sentence of code text."""

    id: str
    jurisdiction: str
    #: Code section this clause belongs to, e.g. "PCC 33.110.220".
    section: str
    #: Path into flats/provenance/ with a line range.
    quote: str
    text: str
    tag: Rase | None = None
    #: Rule field this clause produces a value for, when it is a requirement.
    field: str | None = None
    resolved: bool = False


@dataclass(frozen=True, slots=True)
class ClauseGap:
    jurisdiction: str
    section: str
    clause_id: str
    problem: str


def clause_gaps(clauses: Iterable[Clause]) -> list[ClauseGap]:
    """Clauses that block their section from being called complete.

    Two gap kinds, both fatal to ``verified``:

    * **untagged** — nobody has decided what this sentence does. It may be the
      exception that invalidates a whole zone.
    * **unresolved requirement** — tagged as normative but no encoded value
      carries it, so the screen is ignoring a rule it knows exists.
    """
    gaps: list[ClauseGap] = []
    for c in clauses:
        if c.tag is None:
            gaps.append(ClauseGap(c.jurisdiction, c.section, c.id, "untagged"))
        elif c.tag in (Rase.requirement, Rase.exception) and not c.resolved:
            gaps.append(
                ClauseGap(c.jurisdiction, c.section, c.id, f"unresolved_{c.tag.name}")
            )
    return gaps


def sections_complete(clauses: Iterable[Clause]) -> dict[tuple[str, str], bool]:
    """Per (jurisdiction, section): is every clause accounted for?"""
    seen: dict[tuple[str, str], bool] = {}
    for c in clauses:
        key = (c.jurisdiction, c.section)
        ok = c.tag is not None and (
            c.tag not in (Rase.requirement, Rase.exception) or c.resolved
        )
        seen[key] = seen.get(key, True) and ok
    return seen
