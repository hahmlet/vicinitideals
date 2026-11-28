"""Lots the county tax roll rules out: public land, tracts, parcels worth $0.

Steph RULED 2026-10-09 (FOLLOWUPS 59), "All red": HOA tracts, common areas,
open space, golf courses and parcels the county values at $0 land + $0
building are RED and never scanned, like the institutional land of
:mod:`flats.geom.institutional`; the public county codes with them.
Churches and charities stay checked, so no tier reads codes 91x or 98x.

The reading is a pure function of one lot's roll fields, in the order of
``flats/config/roll_red.yaml``: the first tier a lot meets answers it. The
tiers, the code book behind each (OAR 150-308-0310) and why Multnomah and
Clackamas have no public-code tier are in that file.

Multnomah's roll does not say who owns an exempt lot, so its public land is
read off a checked-in list of the lots whose owner of record is a public
body (the ``public_owner`` tier, FOLLOWUPS 205): the same answer Washington
County's vacant public codes give, by another road.
"""

from __future__ import annotations

import csv
import functools
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config" / "roll_red.yaml"
#: What ``Reading.category`` carries for a roll reading, so a bind and a
#: report can tell it from a map reading.
PREFIX = "roll_"
VALUE_FIELDS = ("LANDVAL", "BLDGVAL", "TOTALVAL", "ASSESSVAL")
#: OAR 150-308-0310, second digit of an exempt (9xx) class.
EXEMPT_MEANING = {
    "2": "school",
    "3": "cemetery",
    "4": "city",
    "5": "county",
    "6": "state",
    "7": "federal",
    "9": "port or other public body",
}
_NO_ADDRESS = re.compile(r"NO SITUS|LEVY CODE", re.IGNORECASE)
_TRACT_SUFFIX = re.compile(r"^[89]\d{4}$")
_TRACT_WORDS = re.compile(r"TR|-T|NONTL")
#: The owner groups of the ``public_owner`` tier, and how a reading names
#: each. ``housing_authority`` answers as the tier's switch says.
OWNER_GROUPS = {"government": "a public body", "housing_authority": "a housing authority"}
#: What the tier's ``housing_authority`` switch may say: RED as public land,
#: held YELLOW in the scan (Steph 2026-11-18, rulings.yaml
#: 2026-11-18-housing-authority-land-yellow), or screened as a private lot.
HOUSING_ANSWERS = ("red", "yellow", "screened")


@dataclass(frozen=True)
class Tier:
    key: str
    enabled: bool
    words: str
    pattern: re.Pattern[str] | None = None
    counties: frozenset[str] = frozenset()
    built_since: int | None = None
    built_lots: int = 0
    built_within_ft: float = 0.0
    #: ``condo_common``: the intake's condo reasons that mark common ground.
    condo_reasons: frozenset[str] = frozenset()
    #: ``condo_common``: the lot number (last five characters) the county
    #: gives a condominium's common element.
    lot_pattern: re.Pattern[str] | None = None
    #: ``public_owner``: the owner groups that count as public (RED).
    groups: frozenset[str] = frozenset()
    #: ``public_owner``: the owner groups whose bare, untaxed land stays in
    #: the scan and is held YELLOW (:func:`owner_hold`).
    held: frozenset[str] = frozenset()
    #: ``public_owner``: parcel number -> owner group, off the checked-in list.
    owners: Mapping[str, str] = field(default_factory=dict, compare=False)
    #: ``public_owner``: per group, the names that are that group's; and the
    #: words (LLC, church, bank) no public body's name carries.
    owner_patterns: Mapping[str, tuple[re.Pattern[str], ...]] = field(default_factory=dict, compare=False)
    not_owner: re.Pattern[str] | None = None
    #: ``public_owner``: parcel number -> owner of record's name, off the list.
    owner_names: Mapping[str, str] = field(default_factory=dict, compare=False)
    #: ``public_owner`` ``campus``: the owner names that are a public school
    #: body's, and per jurisdiction the zones that are campus zones.
    campus_owners: tuple[re.Pattern[str], ...] = ()
    campus_zones: Mapping[str, frozenset[str]] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class RollRules:
    tiers: tuple[Tier, ...]

    def words(self, category: str) -> str:
        key = category.removeprefix(PREFIX)
        return next((t.words for t in self.tiers if t.key == key), key)

    def tier(self, key: str) -> Tier:
        return next(t for t in self.tiers if t.key == key)


@functools.lru_cache(maxsize=8)
def _owner_rows(path: Path) -> tuple[tuple[str, str, str], ...]:
    """``(parcel number, group, owner)`` off a public-owner list
    (``tlid,group,owner``). Parcel numbers hold spaces: a row is read whole,
    never split on them."""
    with path.open(encoding="utf-8", newline="") as fh:
        return tuple((row["tlid"].rstrip(), row["group"], row["owner"]) for row in csv.DictReader(fh))


def _owner_list(path: Path) -> dict[str, str]:
    """``parcel number -> group`` off a public-owner list."""
    return {tlid: group for tlid, group, _owner in _owner_rows(path)}


def _owner_names(path: Path) -> dict[str, str]:
    """``parcel number -> owner of record`` off a public-owner list."""
    return {tlid: owner for tlid, _group, owner in _owner_rows(path)}


def owner_group(owner: Any, tier: Tier) -> str | None:
    """The group an owner of record's name falls in (``government``,
    ``housing_authority``) by the tier's patterns, or None: a private name,
    or one carrying a word no public body's does."""
    name = re.sub(r"\s+", " ", str(owner or "")).strip().upper()
    if not name or (tier.not_owner is not None and tier.not_owner.search(name)):
        return None
    for group, patterns in tier.owner_patterns.items():
        if any(p.search(name) for p in patterns):
            return group
    return None


def _housing(body: Mapping[str, Any]) -> str:
    answer = str(body.get("housing_authority") or "screened")
    if answer not in HOUSING_ANSWERS:
        raise ValueError(f"housing_authority: {answer!r} is not one of {HOUSING_ANSWERS}")
    return answer


def _groups(body: Mapping[str, Any]) -> frozenset[str]:
    if "owners" not in body:
        return frozenset()
    on = set(body["owners"])
    if _housing(body) != "red":
        on.discard("housing_authority")
    return frozenset(on)


def _held(body: Mapping[str, Any]) -> frozenset[str]:
    if "housing_authority" not in (body.get("owners") or {}) or _housing(body) != "yellow":
        return frozenset()
    return frozenset({"housing_authority"})


def load_rules(path: Path = CONFIG) -> RollRules:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    tiers = tuple(
        Tier(
            key=key,
            enabled=bool(body.get("enabled")),
            words=str(body["words"]),
            pattern=re.compile(body["pattern"]) if body.get("pattern") else None,
            counties=frozenset(body.get("counties") or ()),
            built_since=int(keep["since"]) if (keep := body.get("keep_checked_when_block_built")) else None,
            built_lots=int(keep["lots"]) if keep else 0,
            built_within_ft=float(keep["within_ft"]) if keep else 0.0,
            condo_reasons=frozenset(body.get("condo_reasons") or ()),
            lot_pattern=re.compile(body["lot_pattern"]) if body.get("lot_pattern") else None,
            groups=_groups(body),
            held=_held(body),
            owners=_owner_list(path.parent / body["list"]) if body.get("list") else {},
            owner_patterns={g: tuple(re.compile(p) for p in ps) for g, ps in (body.get("owners") or {}).items()},
            not_owner=re.compile(body["not_owners"]) if body.get("not_owners") else None,
            owner_names=_owner_names(path.parent / body["list"]) if body.get("list") else {},
            campus_owners=tuple(re.compile(p) for p in ((body.get("campus") or {}).get("owners") or ())),
            campus_zones={j: frozenset(zs) for j, zs in ((body.get("campus") or {}).get("zones") or {}).items()},
        )
        for key, body in (doc.get("tiers") or {}).items()
    )
    if not tiers:
        raise ValueError(f"{path}: no tiers")
    return RollRules(tiers)


def _number(v: Any) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def zero_value(row: Mapping[str, Any]) -> bool:
    """Land, building, total and assessed value all exactly 0 on the roll.

    A value the roll does not carry is not zero: it is unknown, and unknown
    is screened.
    """
    return all(_number(row.get(f)) == 0 for f in VALUE_FIELDS)


def taxed(row: Mapping[str, Any]) -> bool:
    """The roll shows an assessed value above 0: the lot pays tax. A value
    the roll does not carry is not shown."""
    n = _number(row.get("ASSESSVAL"))
    return n is not None and n > 0


#: The row key that carries the footprint map's area on the lot (sq ft, the
#: occupancy build's ``footprint_sqft``, :mod:`flats.ingest.occupancy`).
#: Absent or None: the footprint map was not read for this lot.
FOOTPRINT_FIELD = "footprint_sqft"
#: What a lot the footprint map was not read for answers to "is it built?"
#: (:func:`improved`): ``sqft`` -- the roll's building area alone, the
#: conservative answer for a final reading (a public lot is red unless the
#: roll measures a building); ``value`` -- a building value or area, the
#: test as it stood before 2026-11-28, for a pre-filter that must not leave
#: out of the scan a lot a later reading with the map would keep.
UNMAPPED = ("sqft", "value")


def footprint(row: Mapping[str, Any]) -> float | None:
    """The footprint map's building area on the lot, or None when the map
    was not read for it."""
    return _number(row.get(FOOTPRINT_FIELD))


def improved(row: Mapping[str, Any], unmapped: str = "sqft") -> bool:
    """The roll shows a building.

    A building VALUE alone is not a building (FOLLOWUPS 64 round 5, fg5 #40:
    the University of Oregon's lot 1N1E13BD -09900 carries $8,220 of
    improvements, no building area and no footprint -- paving, a fence -- and
    was screened as built). Built means the roll MEASURES a building (a
    building area above 0), or the footprint map draws one where the roll
    values one (both). A footprint the roll gives no value is the map's
    alone and leaves the lot bare, as before: the test only ever finds more
    land bare, never less. Where the footprint map was not read for the lot,
    ``unmapped`` answers (:data:`UNMAPPED`).
    """
    if unmapped not in UNMAPPED:
        raise ValueError(f"unmapped: {unmapped!r} is not one of {UNMAPPED}")
    value, area = _number(row.get("BLDGVAL")), _number(row.get("BLDGSQFT"))
    if area is not None and area > 0:
        return True
    valued = value is not None and value > 0
    drawn = footprint(row)
    if drawn is None:
        return valued and unmapped == "value"
    return valued and drawn > 0


def vacant_class(code: str) -> bool:
    """The assessor's own class says vacant land: a class ending ``00``
    (OAR 150-308-0310: 100 residential vacant, 700 multi-family vacant)."""
    return len(code) == 3 and code.isdigit() and code[1:] == "00"


def tract_number(tlid: str) -> bool:
    """The parcel number is one the counties give tracts and common land:
    a lot number of 8xxxx or 9xxxx, or a TR / NONTL mark."""
    compact = re.sub(r"\s+", "", str(tlid))
    return bool(_TRACT_SUFFIX.match(compact[-5:]) or _TRACT_WORDS.search(compact))


def real_address(row: Mapping[str, Any]) -> bool:
    addr = str(row.get("site_address") or "").strip()
    return bool(addr) and addr.lower() != "nan" and not _NO_ADDRESS.search(addr)


def _code(row: Mapping[str, Any]) -> str:
    code = row.get("PROP_CODE")
    return "" if code is None or str(code).lower() == "nan" else str(code).strip()


def block(row: Mapping[str, Any]) -> tuple[str, str]:
    """``(county, tax map page)``: the parcel number without punctuation or
    spaces, less its last five characters (the tax lot)."""
    county = str(row.get("county") or "")
    compact = re.sub(r"[^0-9A-Za-z]", "", str(row.get("tlid") or row.get("TLID") or ""))
    return county, compact[:-5]


def year_built(row: Mapping[str, Any]) -> int | None:
    n = _number(row.get("YEARBUILT"))
    return int(n) if n is not None and 1000 <= n <= 2100 else None


def geometry(row: Mapping[str, Any]) -> Any:
    """The lot's shapely geometry from its ``wkb``, or None when it has none
    or cannot be read."""
    raw = row.get("wkb")
    if raw is None or isinstance(raw, float):
        return None
    from shapely import wkb as shapely_wkb

    try:
        geom = shapely_wkb.loads(bytes(raw))
    except Exception:
        return None
    return None if geom.is_empty else geom


def built_lots(rows: Iterable[Mapping[str, Any]], rules: RollRules) -> dict[tuple[str, str], list[tuple[str, Any]]]:
    """Per block, ``(tlid, geometry)`` of each lot the assessor roll says was
    built since the year in the ``no_address`` tier and whose geometry reads.
    Empty when the rule is off or no row has a year."""
    since = rules.tier("no_address").built_since
    found: dict[tuple[str, str], list[tuple[str, Any]]] = {}
    if since is None:
        return found
    for row in rows:
        year = year_built(row)
        if year is not None and year >= since and (geom := geometry(row)) is not None:
            found.setdefault(block(row), []).append((str(row.get("tlid") or row.get("TLID") or "").rstrip(), geom))
    return found


def _campus(row: Mapping[str, Any], tier: Tier, tlid: str) -> str | None:
    """The roll's account of a lot a public school body (a school district,
    a community college, a public university) owns in a campus or
    institutional zone, or None. Such land is school land whatever stands on
    it and whatever the roll taxes: Steph RULED 2026-10-06 (rulings.yaml
    2026-10-06-institutional-land-red) that "lots with institutional uses;
    hospitals, schools ..." are red "for any reason", and a public school
    body's land in the zone the city drew for its campus is a school's lot.
    The map reading (flats/config/institutional.yaml) misses a lot the
    campus outline stops short of (fg5 #40: 12 ft short)."""
    zones = tier.campus_zones.get(str(row.get("jurisdiction") or ""))
    zone = str(row.get("zone") or "").strip()
    if not zones or zone not in zones:
        return None
    owner = tier.owner_names.get(tlid, "")
    if not any(p.search(owner) for p in tier.campus_owners):
        return None
    return f"{row.get('county')} owner of record ({owner}, a public school body), on land zoned {zone}, a campus zone"


def _public_owner(row: Mapping[str, Any], tier: Tier, groups: frozenset[str], unmapped: str = "sqft") -> str | None:
    """The roll's account of a lot one of ``groups`` owns bare and untaxed
    (no assessed value; a vacant class, or no building on the roll by
    :func:`improved`, whose ``unmapped`` this is), or a public school body
    owns in a campus zone (:func:`_campus`), or None."""
    county = str(row.get("county") or "")
    code = _code(row)
    tlid = str(row.get("tlid") or row.get("TLID") or "").rstrip()
    group = tier.owners.get(tlid) if county in tier.counties else None
    if group not in groups:
        return None
    if group == "government" and (why := _campus(row, tier, tlid)) is not None:
        return why
    if taxed(row) or not (vacant_class(code) or not improved(row, unmapped)):
        return None
    who = OWNER_GROUPS.get(str(group), "a public body")
    bare = f"vacant class {code}" if vacant_class(code) else "no building on the roll"
    return f"{county} owner of record ({who}), with no assessed value and {bare}"


def owner_hold(row: Mapping[str, Any], rules: RollRules, unmapped: str = "value") -> str | None:
    """The roll's account of a lot a HELD owner group (a housing authority)
    owns bare and untaxed, or None. Such a lot is not RED and not left out of
    the scan: the screen holds it YELLOW (Steph 2026-11-18, rulings.yaml
    2026-11-18-housing-authority-land-yellow). ``row`` carries county, tlid,
    PROP_CODE, BLDGVAL, BLDGSQFT and ASSESSVAL; a value it lacks is neither
    taxed nor built, so the hold stands. The bridge reads the hold without
    the footprint map, so a lot the map was not read for is built by value
    or area (``unmapped="value"``, the test as it stood): on run 134 no
    housing-authority lot with a building value, no building area and no
    footprint was screened, so the stricter answer would have moved none."""
    for tier in rules.tiers:
        if tier.enabled and tier.key == "public_owner" and tier.held:
            return _public_owner(row, tier, tier.held, unmapped)
    return None


def read(
    row: Mapping[str, Any],
    rules: RollRules,
    built: Mapping[tuple[str, str], list[tuple[str, Any]]] | None = None,
    *,
    unmapped: str = "sqft",
) -> dict[str, Any] | None:
    """The reading for one lot -- ``category``, ``share`` (always 1: the roll
    names the whole parcel), ``source``, ``name`` -- or ``None``.

    ``row`` carries county, tlid, PROP_CODE, LANDVAL, BLDGVAL, TOTALVAL,
    ASSESSVAL, site_address and YEARBUILT, as the normalized lot table does.
    ``built`` is :func:`built_lots` over the whole table; without it, or
    without the lot's own geometry, a lot with no address is never spared.
    ``footprint_sqft`` (:data:`FOOTPRINT_FIELD`) is the footprint map's area
    on the lot, and ``unmapped`` answers where it is missing
    (:func:`improved`); ``jurisdiction`` and ``zone`` place a public school
    body's campus land (:func:`_campus`).
    """
    county = str(row.get("county") or "")
    code = _code(row)
    tlid = str(row.get("tlid") or row.get("TLID") or "").rstrip()
    zero = zero_value(row)

    def hit(key: str, why: str) -> dict[str, Any]:
        return {"category": PREFIX + key, "share": 1.0, "source": f"roll:{why}", "name": None}

    for tier in rules.tiers:
        if not tier.enabled:
            continue
        if tier.key == "public_land":
            if county in tier.counties and tier.pattern and tier.pattern.match(code):
                meaning = EXEMPT_MEANING.get(code[1], "public")
                return hit(tier.key, f"{county} roll code {code} ({meaning})")
        elif tier.key == "public_owner":
            if (why := _public_owner(row, tier, tier.groups, unmapped)) is not None:
                return hit(tier.key, why)
        elif tier.key == "tract":
            if zero and tract_number(tlid):
                return hit(tier.key, f"{county} roll, parcel number {tlid}, value $0")
        elif tier.key == "condo_common":
            reason = str(row.get("condo_reason") or "")
            if reason and reason in tier.condo_reasons:
                return hit(tier.key, f"{county} roll code {code}, marked {reason} at intake")
            if (
                zero
                and county in tier.counties
                and tier.pattern
                and tier.pattern.match(code)
                and _number(row.get("BLDGSQFT")) == 0
                and tier.lot_pattern
                and tier.lot_pattern.match(re.sub(r"\s+", "", tlid)[-5:])
            ):
                return hit(tier.key, f"{county} roll code {code}, parcel number {tlid}, value $0, no building")
        elif tier.key == "open_space":
            if zero and tier.pattern and tier.pattern.match(code):
                return hit(tier.key, f"{county} roll code {code}, value $0")
        elif tier.key == "no_address":
            if zero and not real_address(row):
                if built and tier.built_since is not None and (own := geometry(row)) is not None:
                    near = sum(1 for other, geom in built.get(block(row), ()) if other != tlid and own.distance(geom) <= tier.built_within_ft)
                    if near >= tier.built_lots:
                        continue
                return hit(tier.key, f"{county} roll, value $0, no street address")
    return None


#: The site fact the roll answers for Wilsonville's Village zone (FOLLOWUPS
#: 110): the lot holds no home. 4.125(.23)'s quadplex standards are written
#: "For lots previously developed with at least one residential unit".
NO_DWELLING_FACT = "no_existing_dwelling"
#: RLIS LANDUSE codes that say a home stands on the lot.
RESIDENTIAL_LANDUSE = frozenset({"SFR", "MFR"})


def no_existing_dwelling(row: Mapping[str, Any]) -> bool | None:
    """Whether the roll says the lot holds no home: True, False, or None
    where it does not settle it.

    True: no building value (BLDGVAL exactly 0) AND the roll marks the land
    vacant -- RLIS LANDUSE ``VAC`` or a vacant property class (OAR
    150-308-0310, a class ending ``00``: 100 residential vacant, 700
    multi-family vacant). False: a building value above 0 on a residential
    land use (``SFR``, ``MFR``) or a residential class (1xx, 7xx), with no
    vacant mark. Anything else is unanswered: a building value the roll
    does not carry, a house on land the roll still calls vacant, a building
    of value on commercial or tract land. The two answers are not
    symmetric and need not be: False is the one that opens (.23)'s route to
    GREEN, so it asks for both a building and a residential use; True and
    unanswered both leave the lot an open question.
    """
    bldg = _number(row.get("BLDGVAL"))
    if bldg is None:
        return None
    landuse = str(row.get("LANDUSE") or "").strip().upper()
    code = _code(row)
    classed = len(code) == 3 and code.isdigit()
    vacant = landuse == "VAC" or (classed and code[1:] == "00")
    residential = landuse in RESIDENTIAL_LANDUSE or (classed and code[0] in "17" and code[1:] != "00")
    if bldg == 0 and vacant:
        return True
    if bldg > 0 and residential and not vacant:
        return False
    return None
