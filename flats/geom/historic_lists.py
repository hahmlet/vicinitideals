"""Protected historic buildings outside Portland, off the cities' own lists
(FOLLOWUPS 87).

Steph ruled 2026-10-14 that a lot carrying a protected historic building is
RED (``2026-10-14-protected-historic-red``). :mod:`flats.geom.pdx_overlays`
builds that from Portland's map. Elsewhere the source is a list: the rows in
``flats/config/historic/<list>.csv``, one per listed resource, with the taxlot
the matcher found. ``flats/config/historic/protection.yaml`` holds what each
city's code says a listing does, with the stored lines that say it. Listing a
building protects it only where the code makes demolition wait on a hearing
that can refuse it, so each list reads one of two ways:

* ``protected`` -- the code clearly does that. The lot goes RED, as Portland's
  do (:data:`LISTED_CHECK`).
* ``doubtful`` -- it may. The lot goes YELLOW with :data:`UNSETTLED_FLAG`,
  never GREEN and never RED on a guess.

A listing on a ``protected`` list is still doubtful if it is not a building (a
milepost, a tree, a grave: the ruling speaks of buildings, and the pod may
stand clear of it), or if the match to the lot is less than sure: a street
name that nearly agrees, or an address two lots share, every one of which goes
yellow.

A row that names no lot is never dropped. The bridge writes every row, placed
or not, to :data:`REPORT_NAME` in its output folder (:func:`write_report`) and
says the count, and ``flats/tests/test_historic_lists.py`` holds the count per
list. ``scripts/flats_match_historic.py`` fills in the taxlots from a lot table
(:func:`match_rows`): the county fabric is needed, and only Multnomah's is
local, so the other lists wait on that run.

The lookup is the lot's taxlot id, compared without its spaces and hyphens;
no row field, no snapshot layer. County taxlot ids do not collide across the
three counties' formats (``1S3E10BC  -00700``, ``1S123AA00100``,
``21E14DA00100``).
"""

from __future__ import annotations

import csv
import dataclasses
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from flats.score import flags as flag_plan

LISTS_DIR = Path(__file__).resolve().parents[1] / "config" / "historic"
PROTECTION_FILE = LISTS_DIR / "protection.yaml"

COLUMNS: tuple[str, ...] = (
    "tlid",
    "address_listed",
    "name",
    "listing_id_or_row",
    "source",
    "match_method",
    "match_note",
)

#: Between the taxlots of one row. Never whitespace: a taxlot id holds spaces.
TLID_SEP = ";"

#: Sure enough that a listing on a protected list goes RED.
SURE_MATCH: frozenset[str] = frozenset({"taxlot", "address-exact", "address-range", "point-in-lot"})
#: Near enough to hold the lot yellow, never to call it red.
UNSURE_MATCH: frozenset[str] = frozenset({"address-fuzzy", "address-ambiguous"})
MATCH_METHODS: frozenset[str] = SURE_MATCH | UNSURE_MATCH | {"none"}

PROTECTED = "protected"
DOUBTFUL = "doubtful"

LISTED_CHECK = "historic_listed"
LISTED_REASON = "HISTORIC_LISTED"
UNSETTLED_REASON = "HISTORIC_LISTING_UNSETTLED"
UNSETTLED_FLAG = "HISTORIC-LISTING-UNSETTLED"
REASONS: tuple[str, ...] = (LISTED_REASON, UNSETTLED_REASON)

REPORT_NAME = "historic_lists.csv"


@dataclass(frozen=True, slots=True)
class Listing:
    """One listed resource and what its listing does to the lot it is on."""

    list_name: str
    listing_id: str
    name: str
    address: str
    tlids: tuple[str, ...]
    method: str
    note: str
    #: :data:`PROTECTED` or :data:`DOUBTFUL`, code reading and match together.
    standing: str
    #: Why, in a sentence, and the stored lines that say it.
    why: str
    cite: str

    def said(self) -> str:
        label = self.name or "A listed resource"
        return f"{label} at {self.address} ({self.list_name} {self.listing_id})"


def compact(tlid: object) -> str:
    """A taxlot id without its spaces and hyphens."""
    return re.sub(r"[\s-]", "", str(tlid))


def split_tlids(cell: str) -> tuple[str, ...]:
    """The taxlots of one row's cell, each kept whole, spaces included."""
    return tuple(t.strip() for t in cell.split(TLID_SEP) if t.strip())


def _standing(
    policy: Mapping[str, Any], listing_id: str, method: str
) -> tuple[str, str, str]:
    """The standing of one row, why, and the stored lines that say so."""
    reading = policy["reading"]
    if reading not in (PROTECTED, DOUBTFUL):
        raise ValueError(f"reading must be protected or doubtful: {reading!r}")
    cite, why = policy["cite"], policy["why"]
    not_buildings = policy.get("not_buildings") or {}
    if reading == PROTECTED and listing_id in (not_buildings.get("ids") or ()):
        return DOUBTFUL, not_buildings["why"], not_buildings["cite"]
    if reading == PROTECTED and method in UNSURE_MATCH:
        return DOUBTFUL, f"the address only nearly fixes the lot, and {why}", cite
    return reading, why, cite


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def load_policy() -> dict[str, dict[str, Any]]:
    """``protection.yaml``, list name to what its code says."""
    return yaml.safe_load(PROTECTION_FILE.read_text(encoding="utf-8"))["lists"]


@lru_cache(maxsize=1)
def load_lists() -> tuple[Listing, ...]:
    """Every row of every list. A list with no reading is refused: a row the
    code was never read for must not pass as no answer."""
    policy = load_policy()
    out: list[Listing] = []
    for path in sorted(LISTS_DIR.glob("*.csv")):
        if path.stem not in policy:
            raise ValueError(f"{path.name} has no reading in {PROTECTION_FILE.name}")
        for row in read_rows(path):
            method = row["match_method"]
            if method not in MATCH_METHODS:
                raise ValueError(f"{path.name}: unknown match method {method!r}")
            tlids = split_tlids(row["tlid"])
            if bool(tlids) == (method == "none"):
                raise ValueError(f"{path.name}: {row['listing_id_or_row']} says {method!r} with taxlots {tlids}")
            standing, why, cite = _standing(policy[path.stem], row["listing_id_or_row"], method)
            out.append(
                Listing(
                    list_name=path.stem,
                    listing_id=row["listing_id_or_row"],
                    name=row["name"],
                    address=row["address_listed"],
                    tlids=tlids,
                    method=method,
                    note=row["match_note"],
                    standing=standing,
                    why=" ".join(why.split()),
                    cite=cite,
                )
            )
    return tuple(out)


@lru_cache(maxsize=1)
def _index() -> Mapping[str, tuple[Listing, ...]]:
    held: dict[str, list[Listing]] = defaultdict(list)
    for listing in load_lists():
        for tlid in listing.tlids:
            held[compact(tlid)].append(listing)
    return {k: tuple(v) for k, v in held.items()}


def listings_on(tlid: object) -> tuple[Listing, ...]:
    """The listings that name this lot."""
    return _index().get(compact(tlid), ())


def unmatched() -> tuple[Listing, ...]:
    """The rows that name no lot yet: reported, never dropped."""
    return tuple(x for x in load_lists() if not x.tlids)


# --- the check ---------------------------------------------------------------


def binds_for(listings: Iterable[Listing]) -> tuple[flag_plan.Bind, ...]:
    """A bind per protected listing on the lot, as Portland's are."""
    return tuple(
        flag_plan.Bind(
            LISTED_CHECK,
            None,
            None,
            None,
            source=f"{x.cite}: {x.why} -- {x.said()} (Steph 2026-10-14: a protected building is red)",
        )
        for x in listings
        if x.standing == PROTECTED
    )


def flags_for(listings: Iterable[Listing]) -> tuple[flag_plan.Flag, ...]:
    """A flag per doubtful listing on the lot."""
    return tuple(
        flag_plan.Flag(
            UNSETTLED_FLAG,
            flag_plan.LOT,
            UNSETTLED_REASON,
            source=f"{x.cite}: {x.why} -- {x.said()}",
        )
        for x in listings
        if x.standing == DOUBTFUL
    )


def checked(s: Any, tlid: object) -> Any:
    """Apply the lot's listings: RED for a protected one, YELLOW and a flag
    for a doubtful one. Adds nothing twice, so a screen that runs again over
    its own answer is unchanged."""
    listings = listings_on(tlid)
    if not listings:
        return s
    binds = binds_for(listings)
    flags = flags_for(listings)
    from flats.score.screen import Triage

    reg = flag_plan.registry()
    line = flag_plan.colour_rules().yellow_at_severity

    def apply(x: Any) -> Any:
        have = {(b.check, b.source) for b in x.binds}
        new = tuple(b for b in binds if (b.check, b.source) not in have)
        held = {(f.code, f.source) for f in x.flags}
        raised = tuple(f for f in flags if (f.code, f.source) not in held)
        if not new and not raised:
            return x
        reasons = list(x.reasons)
        triage = x.triage
        if new and LISTED_REASON not in reasons:
            reasons.append(LISTED_REASON)
        for f in raised:
            if flag_plan.severity_of(f, reg) >= line:
                if f.by not in reasons:
                    reasons.append(f.by)
                if triage is Triage.green:
                    triage = Triage.yellow
        if new:
            triage = Triage.red
        return dataclasses.replace(
            x, triage=triage, binds=(*x.binds, *new), flags=(*x.flags, *raised), reasons=tuple(reasons)
        )

    return dataclasses.replace(s, screening=apply(s.screening), signed=apply(s.signed))


# --- what the bridge says ----------------------------------------------------


def write_report(rows: Sequence[Mapping[str, Any]], out: Path) -> dict[str, int]:
    """Every list row and where it landed in this run, to ``out``/
    :data:`REPORT_NAME`: ``on_lot`` (a lot of this run), ``not_in_run`` (it
    names a lot this run does not hold: a scoped run, or a taxlot the county
    has since retired), ``unmatched`` (it names no lot). The counts come back
    for the log."""
    present = {compact(r.get("TLID")) for r in rows}
    counts: dict[str, int] = {"on_lot": 0, "not_in_run": 0, "unmatched": 0}
    with (out / REPORT_NAME).open("w", encoding="utf-8", newline="") as sink:
        writer = csv.writer(sink, lineterminator="\n")
        writer.writerow(["list", "listing", "name", "address", "standing", "method", "tlid", "status"])
        for x in load_lists():
            if not x.tlids:
                status = "unmatched"
            elif any(compact(t) in present for t in x.tlids):
                status = "on_lot"
            else:
                status = "not_in_run"
            counts[status] += 1
            writer.writerow(
                [x.list_name, x.listing_id, x.name, x.address, x.standing, x.method, TLID_SEP.join(x.tlids), status]
            )
    return counts


# --- the matcher -------------------------------------------------------------

_SUFFIXES: Mapping[str, str] = {
    "AVENUE": "AVE", "AVE": "AVE", "STREET": "ST", "ST": "ST", "DRIVE": "DR", "DR": "DR",
    "ROAD": "RD", "RD": "RD", "BOULEVARD": "BLVD", "BLVD": "BLVD", "COURT": "CT", "CT": "CT",
    "LANE": "LN", "LN": "LN", "HIGHWAY": "HWY", "HWY": "HWY", "PLACE": "PL", "PL": "PL",
    "TERRACE": "TER", "TER": "TER", "CIRCLE": "CIR", "CIR": "CIR", "PARKWAY": "PKWY",
    "PKWY": "PKWY", "WAY": "WAY", "LOOP": "LOOP",
}
_DIRECTIONS = frozenset({"N", "S", "E", "W", "NE", "NW", "SE", "SW"})
_UNIT = re.compile(r"\b(UNIT|APT|STE|SUITE|BLDG)\b.*$|#.*$")
_NUMBER = re.compile(r"^(\d+)(?:-(\d+))?$")


@dataclass(frozen=True, slots=True)
class Address:
    low: int
    high: int
    direction: str
    street: str
    suffix: str


def parse_address(text: object) -> Address | None:
    """A situs or listed address in parts; None where it is no single street
    address (an intersection, a description, nothing)."""
    words = str(text or "").upper().replace(".", "")
    words = words.replace(",", " ")
    words = re.sub(r"\bHISTORIC\s+CRH\b", "HIST COLUMBIA RIVER HWY", words)
    words = re.sub(r"\bHISTORIC\b", "HIST", words)
    words = _UNIT.sub("", words)
    tokens = words.split()
    if len(tokens) < 2:
        return None
    number = _NUMBER.match(tokens[0])
    if number is None:
        return None
    low = int(number.group(1))
    high = int(number.group(2)) if number.group(2) else low
    rest = tokens[1:]
    direction = rest[0] if len(rest) > 1 and rest[0] in _DIRECTIONS else ""
    if direction:
        rest = rest[1:]
    suffix = _SUFFIXES.get(rest[-1], "") if len(rest) > 1 else ""
    if suffix:
        rest = rest[:-1]
    return Address(low, high, direction, " ".join(rest), suffix)


def _listed_addresses(text: str) -> list[Address]:
    """A row's addresses: some list a second in brackets."""
    got = [parse_address(part) for part in re.split(r"[()]", text) if part.strip()]
    return [a for a in got if a is not None]


def _overlap(want: Address, situs: Address) -> bool:
    """Whether a listed number falls on a situs. The two sides of a street run
    odd and even: 1420 is not in 1411-1429, and 112 not in 101-117."""
    same_side = want.low % 2 == situs.low % 2
    return same_side and want.low <= situs.high and situs.low <= want.high


def match_address(
    address_listed: str, lots: Mapping[str, Sequence[tuple[str, Address, str]]]
) -> tuple[tuple[str, ...], str, str]:
    """The taxlots, method and note for one listed address. ``lots`` is
    street name to (taxlot, parsed situs, situs as written)."""
    listed = _listed_addresses(address_listed)
    if not listed:
        return (), "none", "The listed location is an intersection or description, not a street address."
    tiers: dict[str, dict[str, str]] = {"exact": {}, "range": {}, "fuzzy": {}}
    for want in listed:
        for tlid, situs, written in lots.get(want.street, ()):
            if not _overlap(want, situs):
                continue
            same_dir, same_suffix = situs.direction == want.direction, situs.suffix == want.suffix
            if same_dir and same_suffix:
                same_span = (want.low, want.high) == (situs.low, situs.high)
                tiers["exact" if same_span else "range"][tlid] = written
            elif same_dir or same_suffix:
                tiers["fuzzy"][tlid] = written
    if not any(tiers.values()):
        return (), "none", "No lot in the county's table has a situs address that agrees."
    if tiers["exact"]:
        found, method = tiers["exact"], "address-exact"
    elif tiers["range"]:
        found, method = tiers["range"], "address-range"
    else:
        found, method = tiers["fuzzy"], "address-fuzzy"
    if len(found) > 1 and method != "address-fuzzy":
        method = "address-ambiguous"
    tlids = tuple(sorted(found))
    said = "; ".join(sorted(set(found.values())))
    return tlids, method, f"{method}: situs {said}"


def lots_by_street(frame: Any, cities: Iterable[str]) -> dict[str, list[tuple[str, Address, str]]]:
    """A lot table's situs addresses in ``cities``, by street name. ``frame``
    holds ``TLID``, ``SITEADDR``, ``SITECITY`` and ``JURIS_CITY``. A city's
    lots are those it governs or the postal city names."""
    wanted = {c.upper() for c in cities}
    by_street: dict[str, list[tuple[str, Address, str]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for tlid, addr, site, juris in zip(
        frame["TLID"], frame["SITEADDR"], frame["SITECITY"], frame["JURIS_CITY"], strict=True
    ):
        if str(site).upper() not in wanted and str(juris).upper() not in wanted:
            continue
        parsed = parse_address(addr)
        if parsed is None or (str(tlid), str(addr)) in seen:
            continue
        seen.add((str(tlid), str(addr)))
        by_street[parsed.street].append((str(tlid), parsed, str(addr)))
    return by_street


def match_rows(
    rows: Sequence[Mapping[str, str]], lots: Mapping[str, Sequence[tuple[str, Address, str]]]
) -> list[dict[str, str]]:
    """Each row with its taxlots matched. A row a source names by taxlot keeps
    it (``taxlot``, ``point-in-lot``): an address cannot overrule that."""
    out: list[dict[str, str]] = []
    for row in rows:
        new = dict(row)
        if row["match_method"] not in ("taxlot", "point-in-lot"):
            tlids, method, note = match_address(row["address_listed"], lots)
            new.update(tlid=TLID_SEP.join(tlids), match_method=method, match_note=note)
        out.append(new)
    return out


def write_rows(path: Path, rows: Iterable[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as sink:
        writer = csv.DictWriter(sink, COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


__all__ = [
    "COLUMNS",
    "DOUBTFUL",
    "LISTED_CHECK",
    "LISTED_REASON",
    "LISTS_DIR",
    "Listing",
    "MATCH_METHODS",
    "PROTECTED",
    "PROTECTION_FILE",
    "REASONS",
    "REPORT_NAME",
    "SURE_MATCH",
    "UNSETTLED_FLAG",
    "UNSETTLED_REASON",
    "checked",
    "compact",
    "listings_on",
    "load_lists",
    "load_policy",
    "lots_by_street",
    "match_address",
    "match_rows",
    "parse_address",
    "read_rows",
    "split_tlids",
    "unmatched",
    "write_report",
    "write_rows",
]
