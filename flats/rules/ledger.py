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

    That is not hypothetical. The parcel corpus this ledger is built from is
    Multnomah County only, and ten encoded Clackamas jurisdictions have never
    had a lot weighed against them. Lake Oswego looked like the exception and
    was not: its rows come from the sliver of the city that lies inside
    Multnomah, 757 lots in the four zones that happened to be encoded, which
    is exactly why the six zones it was missing could not surface here.

    Reported from the written ledger rather than the parcel corpus on purpose.
    The corpus is a 62 MB read and a command; the ledger is what shipped, and
    what shipped is what a reader is entitled to be told the shape of.
    """
    seen = {row.jurisdiction for row in rows}
    return [
        UnweighedLayer(name, len(layer.zones), bool(layer.eligible))
        for name, layer in sorted(rules.layers.items())
        if layer.zones and name not in seen
    ]


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
