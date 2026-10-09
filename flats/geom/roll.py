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
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RollRules:
    tiers: tuple[Tier, ...]

    def words(self, category: str) -> str:
        key = category.removeprefix(PREFIX)
        return next((t.words for t in self.tiers if t.key == key), key)

    def tier(self, key: str) -> Tier:
        return next(t for t in self.tiers if t.key == key)


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


def read(row: Mapping[str, Any], rules: RollRules, built: Mapping[tuple[str, str], list[tuple[str, Any]]] | None = None) -> dict[str, Any] | None:
    """The reading for one lot -- ``category``, ``share`` (always 1: the roll
    names the whole parcel), ``source``, ``name`` -- or ``None``.

    ``row`` carries county, tlid, PROP_CODE, LANDVAL, BLDGVAL, TOTALVAL,
    ASSESSVAL, site_address and YEARBUILT, as the normalized lot table does.
    ``built`` is :func:`built_lots` over the whole table; without it, or
    without the lot's own geometry, a lot with no address is never spared.
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
        elif tier.key == "tract":
            if zero and tract_number(tlid):
                return hit(tier.key, f"{county} roll, parcel number {tlid}, value $0")
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
