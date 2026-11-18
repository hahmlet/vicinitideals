"""What the USDA soil survey says lies under each lot -- a NOTE, never a colour.

FOLLOWUPS 196 (Steph 2026-11-17: "start with green lots ... Then continue on the
rest"). Nothing in the screen, the fit, the score or the flags reads this
module; the lot page and the lot report say it, and that is all. It never adds a
reason code and never carries a flag severity.

The source is USDA NRCS SSURGO (``scripts/flats_lot_soil.py``): the state
GeoPackage NRCS publishes on its public soils share ("SQLite SSURGO", Oregon),
which holds the same tables Soil Data Access serves, each survey area stamped
with its version date (``sacatalog.saverest``). The survey is drawn at
farm-field scale, so on one city lot it is a hint, not a soils report -- the
page says so beside every figure.

Three tables, never repeated on every lot (Steph 2026-11-17):

* **map units** (``flats.soil_map_units``), keyed by ``mukey``: the survey area
  (``areasymbol``, ``areaname``) and its version date (``saverest``),
  ``musym``, ``nationalmusym``, ``muname``, ``mukind``, the survey's own
  map-unit aggregates (``muaggatt``: drainage class, hydrologic group, hydric
  presence, shallowest annual water table, shallowest bedrock, the dwellings
  rating) as printed, and the two building ratings by dominant condition;
* **components** (``flats.soil_components``), keyed by ``cokey`` and pointing
  at their ``mukey``: name, percent, kind, major-component flag, the taxonomic
  classification, and every property value the note reads -- drainage class,
  hydric rating, hydrologic group, the shallowest wet-soil depth and its
  month, the highest linear extensibility of any layer, the shallowest
  restrictive layer and its kind, and the two building interpretations
  (rating class and, where the source carries them, the limiting reasons);
* **lot rows** (``flats.lot_soil``): one per lot per map unit touching it, with
  its square feet on the lot and its share of the lot, plus one row with no
  ``mukey`` for any part the survey does not cover. Areas are measured in
  EPSG:2913 (Oregon North, feet), the CRS every FLATS lot area is measured in,
  and a lot's rows sum to its area.

A map unit's rating is its **dominant condition** -- the rating class held by
the largest total component percent, a tie going to the more limiting class --
the aggregation Web Soil Survey and NRCS's Soil Data Viewer use by default.
(The survey's own ``muaggatt.engdwobdcd`` is that same figure for dwellings,
kept beside it as printed.) Its soil properties come from its **rated
component**: the largest component the survey holds soil data for (the main
one, unless that is "Urban land" or water with nothing measured). A lot's
headline is its **dominant** map unit (most square feet) and, where it spans
several, its **worst-rated** one: the most limiting dwellings rating, then
small commercial buildings, then the larger share.

Values are stored as the survey prints them. The one class this module names
that the survey does not store is the shrink-swell class of a linear
extensibility figure, from the NRCS National Soil Survey Handbook, Part 618
(linear extensibility percent: low < 3, moderate 3 to < 6, high 6 to < 9, very
high >= 9), labelled as that on the page.

The measuring half (:func:`measure_lots`) needs shapely and runs where the lot
polygons are (LXC 137); the rest is plain Python and is what the tests hold.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Mapping, Sequence

#: The two SSURGO interpretations the note reads (``cointerp.mrulename``, as
#: the October 2026 Oregon download and Soil Data Access name them).
DWELLINGS = "ENG - Dwellings W/O Basements"
SMALL_COMMERCIAL = "ENG - Small Commercial Buildings"
INTERPRETATIONS = {DWELLINGS: "dwellings", SMALL_COMMERCIAL: "small_commercial"}

#: Rating classes as SSURGO prints them, least to most limiting. "Not rated"
#: and an empty rating rank lowest: they say nothing.
RATING_ORDER = ("Not rated", "Not limited", "Somewhat limited", "Very limited")

#: How many limiting reasons a rating keeps (Web Soil Survey shows the top few).
REASONS_KEPT = 3

#: A piece of a soil polygon smaller than this inside a lot is the two
#: drawings meeting, not a map unit on the lot (square feet).
MIN_PIECE_SQFT = 1.0

#: A lot's rows must sum to its area within this share.
SUM_TOLERANCE = 0.005

#: NRCS National Soil Survey Handbook, Part 618 -- linear extensibility
#: percent classes (upper bounds exclusive).
LEP_CLASSES = ((3.0, "low"), (6.0, "moderate"), (9.0, "high"), (float("inf"), "very high"))

#: Every column of a lot row of a build, in file order.
LOT_COLUMNS = ("county", "tlid", "mukey", "area_sqft", "share", "lot_area_sqft")

#: Map-unit columns of an extract, in file order.
MAP_UNIT_COLUMNS = (
    "mukey", "areasymbol", "areaname", "saverest", "musym", "nationalmusym", "muname", "mukind",
    "drclassdcd", "hydgrpdcd", "hydclprs", "wtdepannmin", "brockdepmin", "engdwobdcd",
    "dwellings_dcd", "small_commercial_dcd",
    "wet_season_status", "wet_season_cm", "wet_season_months", "wet_season_cokey",
)

#: Component columns of an extract, in file order.
COMPONENT_COLUMNS = (
    "cokey", "mukey", "compname", "comppct_r", "majcompflag", "compkind",
    "taxclname", "taxorder", "taxsuborder", "taxgrtgroup", "taxsubgrp", "taxpartsize",
    "drainagecl", "hydricrating", "hydgrp",
    "water_table_cm", "water_table_month", "lep_max", "restriction_cm", "restriction_kind",
    "dwellings_rating", "dwellings_reasons", "small_commercial_rating", "small_commercial_reasons",
    "wet_season_status", "wet_season_cm", "wet_season_months", "months",
)

#: The wet season the foundation analysis asks about: November through April
#: (``comonth.monthseq``).
WET_SEASON = (11, 12, 1, 2, 3, 4)
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December")

#: ``wet_season_status``: the survey records a wet layer in the season; it holds
#: monthly water rows but no wet layer in the season ("none recorded"); or it
#: holds no monthly water rows at all ("no data"). The last two never merge.
WATER_RECORDED, WATER_NONE_RECORDED, WATER_NO_DATA = "recorded", "none_recorded", "no_data"

#: How the note names where it comes from (the reader asked which agency).
SOURCE_NAME = "USDA Natural Resources Conservation Service (NRCS) soil survey, SSURGO"

#: The properties that make a component "rated": any one present.
_PROPERTIES = ("drainagecl", "hydgrp", "lep_max", "restriction_cm", "water_table_cm")

CAVEAT = (
    "The USDA soil survey is drawn at farm-field scale, so on one city lot it is a hint, "
    "not a soils report. A note only: it never changes the lot's colour."
)


def rating_rank(rating: str | None) -> int:
    """0 for no rating or "Not rated", then up the scale; an unknown word ranks 0."""
    try:
        return RATING_ORDER.index(str(rating or "Not rated"))
    except ValueError:
        return 0


def lep_class(lep: float | None) -> str | None:
    """The NSSH Part 618 shrink-swell class of a linear extensibility percent."""
    if lep is None:
        return None
    for bound, name in LEP_CLASSES:
        if lep < bound:
            return name
    return None  # pragma: no cover -- the last bound is infinite


def fold_interpretations(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str | None]]:
    """``cointerp`` rows -> per cokey: ``dwellings_rating`` / ``_reasons`` and
    ``small_commercial_rating`` / ``_reasons``.

    ``ruledepth`` 0 is the rating (``interphrc``); ruledepth 1 rows are the
    limiting reasons, kept when their value (``interphr``) is above 0, highest
    first, as "reason (value)" -- the form Web Soil Survey prints. A source
    with no ruledepth 1 rows leaves ``_reasons`` unset (not read), never empty.
    """
    ratings: dict[str, dict[str, str | None]] = {}
    reasons: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for row in rows:
        key = INTERPRETATIONS.get(str(row.get("mrulename") or ""))
        cokey = str(row.get("cokey") or "")
        if not key or not cokey:
            continue
        depth = int(_num(row.get("ruledepth")) or 0)
        if depth == 0:
            ratings.setdefault(cokey, {})[f"{key}_rating"] = row.get("interphrc") or None
        elif depth == 1:
            value = _num(row.get("interphr"))
            name = str(row.get("interphrc") or row.get("rulename") or "").strip()
            if value is not None and value > 0 and name:
                reasons.setdefault((cokey, key), []).append((value, name))
    for (cokey, key), found in reasons.items():
        found.sort(key=lambda vn: (-vn[0], vn[1]))
        ratings.setdefault(cokey, {})[f"{key}_reasons"] = "; ".join(
            f"{name} ({value:.2f})" for value, name in found[:REASONS_KEPT]
        )
    return ratings


def fold_months(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """``comonth`` left-joined to its ``cosoilmoist`` rows -> per cokey, one entry
    per month: ``monthseq``, ``month``, ``wet_top_cm`` (the shallowest top of a
    layer the survey calls Wet that month, as printed, in cm; None when none),
    ``flood`` and ``pond`` (``flodfreqcl`` / ``pondfreqcl`` as printed)."""
    months: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        cokey = str(row.get("cokey") or "")
        seq = _int(row.get("monthseq"))
        if not cokey or seq is None:
            continue
        entry = months[cokey].setdefault(seq, {
            "monthseq": seq,
            "month": row.get("month") or MONTH_NAMES[(seq - 1) % 12],
            "wet_top_cm": None,
            "flood": row.get("flodfreqcl") or None,
            "pond": row.get("pondfreqcl") or None,
        })
        depth = _num(row.get("soimoistdept_r"))
        if str(row.get("soimoiststat") or "") == "Wet" and depth is not None:
            if entry["wet_top_cm"] is None or depth < entry["wet_top_cm"]:
                entry["wet_top_cm"] = depth
    return {cokey: [by_seq[k] for k in sorted(by_seq)] for cokey, by_seq in months.items()}


def wet_season(months: Sequence[Mapping[str, Any]] | None) -> tuple[str, float | None, list[str]]:
    """``(status, shallowest cm, the months it occurs)`` over November-April."""
    season = [m for m in (months or ()) if m.get("monthseq") in WET_SEASON]
    if not season:
        return WATER_NO_DATA, None, []
    wet = [m for m in season if m.get("wet_top_cm") is not None]
    if not wet:
        return WATER_NONE_RECORDED, None, []
    low = min(float(m["wet_top_cm"]) for m in wet)
    order = {seq: i for i, seq in enumerate(WET_SEASON)}
    hits = sorted((m for m in wet if float(m["wet_top_cm"]) == low), key=lambda m: order[m["monthseq"]])
    return WATER_RECORDED, low, [str(m["month"]) for m in hits]


def unit_wet_season(components: Sequence[Mapping[str, Any]]) -> tuple[str, float | None, list[str], str | None]:
    """A map unit's shallowest wet-season depth over all its components:
    ``(status, cm, months, cokey it comes from)``. "Recorded" if any component
    records one, else "none recorded" if any holds monthly rows, else "no data"."""
    best: tuple[float, str, list[str]] | None = None
    statuses = set()
    for comp in _by_size(components):
        status = comp.get("wet_season_status") or WATER_NO_DATA
        statuses.add(status)
        cm = _num(comp.get("wet_season_cm"))
        if status == WATER_RECORDED and cm is not None and (best is None or cm < best[0]):
            best = (cm, str(comp.get("cokey")), _months_list(comp.get("wet_season_months")))
    if best is not None:
        return WATER_RECORDED, best[0], best[2], best[1]
    if WATER_NONE_RECORDED in statuses:
        return WATER_NONE_RECORDED, None, [], None
    return WATER_NO_DATA, None, [], None


def _months_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def wet_season_words(status: str | None, cm: float | None, months: Any) -> str:
    """The seasonal high water table in a sentence."""
    if status == WATER_RECORDED and cm is not None:
        names = _months_list(months)
        when = f" ({', '.join(names)})" if names else ""
        return f"{_depth_words(cm)} below the surface at its highest, November to April{when}"
    if status == WATER_NONE_RECORDED:
        return "none recorded: the survey shows no wet layer from November to April"
    return "no data: the survey holds no monthly water-table record here"


def dominant_condition(components: Sequence[Mapping[str, Any]], column: str) -> str | None:
    """The rating class held by the largest total component percent; a tie
    goes to the more limiting class. None when no component carries one."""
    totals: dict[str, float] = defaultdict(float)
    for comp in components:
        rating = comp.get(column)
        if rating:
            totals[str(rating)] += _num(comp.get("comppct_r")) or 0.0
    if not totals:
        return None
    return max(totals, key=lambda r: (totals[r], rating_rank(r), r))


def _by_size(components: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        components,
        key=lambda c: (
            -(_num(c.get("comppct_r")) or 0.0),
            0 if str(c.get("majcompflag") or "").lower().startswith("y") else 1,
            str(c.get("cokey") or ""),
        ),
    )


def main_component(components: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The component with the largest percent; ties to the major one, then the lower cokey."""
    ordered = _by_size(components)
    return ordered[0] if ordered else None


def component_has_data(comp: Mapping[str, Any] | None) -> bool:
    """Does the survey hold a soil fact for this component? "Urban land" and
    water carry a name and a percent, and usually nothing else."""
    if not comp:
        return False
    if any(comp.get(k) not in (None, "") for k in _PROPERTIES):
        return True
    return any(rating_rank(comp.get(f"{k}_rating")) > 0 for k in INTERPRETATIONS.values())


def rated_component(components: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The largest component the survey holds soil data for, or None."""
    return next((c for c in _by_size(components) if component_has_data(c)), None)


def unit_has_data(unit: Mapping[str, Any], components: Sequence[Mapping[str, Any]]) -> bool:
    if rated_component(components) is not None:
        return True
    return any(unit.get(k) not in (None, "") for k in ("drclassdcd", "hydgrpdcd", "wtdepannmin", "brockdepmin"))


@dataclass(frozen=True)
class LotUnit:
    """One map unit on one lot."""

    mukey: str
    area_sqft: float
    share: float
    unit: Mapping[str, Any]
    components: tuple[Mapping[str, Any], ...]

    @property
    def severity(self) -> tuple[int, int]:
        dwellings = self.unit.get("dwellings_dcd") or self.unit.get("engdwobdcd")
        return rating_rank(dwellings), rating_rank(self.unit.get("small_commercial_dcd"))


def lot_units(
    rows: Iterable[Mapping[str, Any]],
    units: Mapping[str, Mapping[str, Any]],
    components: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[LotUnit], float]:
    """A lot's rows -> its map units, largest first, and its uncovered square feet."""
    found: list[LotUnit] = []
    uncovered = 0.0
    for row in rows:
        area = _num(row.get("area_sqft")) or 0.0
        mukey = row.get("mukey") or None
        if mukey is None:
            uncovered += area
            continue
        found.append(
            LotUnit(
                mukey=str(mukey),
                area_sqft=area,
                share=_num(row.get("share")) or 0.0,
                unit=units.get(str(mukey), {}),
                components=tuple(components.get(str(mukey), ())),
            )
        )
    found.sort(key=lambda u: (-u.area_sqft, u.mukey))
    return found, uncovered


def pick(found: Sequence[LotUnit]) -> tuple[LotUnit | None, LotUnit | None]:
    """The dominant map unit (most square feet) and the worst-rated one.

    Worst: the most limiting dwellings rating, then small commercial
    buildings, then the larger share. When no other unit is rated worse than
    the dominant one, the worst is the dominant itself.
    """
    if not found:
        return None, None
    dominant = found[0]
    worst = dominant
    for unit in found[1:]:
        if unit.severity > worst.severity:
            worst = unit
    return dominant, worst


# --- words ----------------------------------------------------------------------


def _depth_words(cm: float | None) -> str | None:
    """Centimetres as printed, with feet and inches alongside."""
    if cm is None:
        return None
    inches = round(cm / 2.54)
    return f"{cm:g} cm ({inches // 12} ft {inches % 12} in)"


def component_words(comp: Mapping[str, Any]) -> dict[str, Any]:
    """Every value the note reads from one component, tied to its ``cokey``."""
    lep = _num(comp.get("lep_max"))
    water = _num(comp.get("water_table_cm"))
    restriction = _num(comp.get("restriction_cm"))
    month = comp.get("water_table_month")
    return {
        "cokey": comp.get("cokey"),
        "compname": comp.get("compname"),
        "comppct_r": _int(comp.get("comppct_r")),
        "majcompflag": comp.get("majcompflag"),
        "compkind": comp.get("compkind"),
        "taxclname": comp.get("taxclname"),
        "taxorder": comp.get("taxorder"),
        "taxsuborder": comp.get("taxsuborder"),
        "taxgrtgroup": comp.get("taxgrtgroup"),
        "taxsubgrp": comp.get("taxsubgrp"),
        "taxpartsize": comp.get("taxpartsize"),
        "has_data": component_has_data(comp),
        "drainage": comp.get("drainagecl"),
        "hydric": comp.get("hydricrating"),
        "hydrologic_group": comp.get("hydgrp"),
        "water_table_cm": water,
        "water_table_month": month,
        "water_table_words": (f"{_depth_words(water)}{f', shallowest in {month}' if month else ''}"
                              if water is not None else None),
        "lep_max": lep,
        "lep_class": lep_class(lep),
        "restriction_cm": restriction,
        "restriction_kind": comp.get("restriction_kind"),
        "restriction_words": (f"{comp.get('restriction_kind') or 'restrictive layer'} at {_depth_words(restriction)}"
                              if restriction is not None else None),
        "dwellings_rating": comp.get("dwellings_rating"),
        "dwellings_reasons": comp.get("dwellings_reasons"),
        "small_commercial_rating": comp.get("small_commercial_rating"),
        "small_commercial_reasons": comp.get("small_commercial_reasons"),
        "wet_season_status": comp.get("wet_season_status") or WATER_NO_DATA,
        "wet_season_cm": _num(comp.get("wet_season_cm")),
        "wet_season_months": _months_list(comp.get("wet_season_months")),
        "wet_season_words": wet_season_words(comp.get("wet_season_status"), _num(comp.get("wet_season_cm")),
                                             comp.get("wet_season_months")),
        "months": [
            {**m, "wet_top_words": _depth_words(_num(m.get("wet_top_cm")))}
            for m in (_load_months(comp.get("months")) or [])
        ],
        "technical": " · ".join(
            str(p) for p in (
                f"cokey {comp.get('cokey')}",
                f"{comp.get('compname')} {_int(comp.get('comppct_r'))}%" if comp.get("compname") else None,
                "major" if str(comp.get("majcompflag") or "").lower().startswith("y") else None,
                comp.get("taxclname"),
            ) if p
        ),
    }


def unit_words(found: LotUnit) -> dict[str, Any]:
    """One map unit on a lot, in words, with every identifier kept."""
    unit = found.unit
    rated = rated_component(found.components)
    main = main_component(found.components)
    data = unit_has_data(unit, found.components)
    return {
        "mukey": found.mukey,
        "area_sqft": round(found.area_sqft, 1),
        "share_pct": round(found.share * 100, 1),
        "areasymbol": unit.get("areasymbol"),
        "areaname": unit.get("areaname"),
        "saverest": unit.get("saverest"),
        "musym": unit.get("musym"),
        "nationalmusym": unit.get("nationalmusym"),
        "muname": unit.get("muname"),
        "mukind": unit.get("mukind"),
        "drainage": unit.get("drclassdcd"),
        "hydrologic_group": unit.get("hydgrpdcd"),
        "hydric_pct": _int(unit.get("hydclprs")),
        "water_table_cm": _num(unit.get("wtdepannmin")),
        "water_table_words": _depth_words(_num(unit.get("wtdepannmin"))),
        "bedrock_cm": _num(unit.get("brockdepmin")),
        "bedrock_words": _depth_words(_num(unit.get("brockdepmin"))),
        "wet_season_status": unit.get("wet_season_status") or WATER_NO_DATA,
        "wet_season_cm": _num(unit.get("wet_season_cm")),
        "wet_season_months": _months_list(unit.get("wet_season_months")),
        "wet_season_cokey": unit.get("wet_season_cokey"),
        "wet_season_words": wet_season_words(unit.get("wet_season_status"), _num(unit.get("wet_season_cm")),
                                             unit.get("wet_season_months")),
        "source_words": (f"{SOURCE_NAME}: {unit.get('areaname') or unit.get('areasymbol')}"
                         f" ({unit.get('areasymbol')}), survey version of {unit.get('saverest')}")
                        if unit.get("areasymbol") else SOURCE_NAME,
        "dwellings": unit.get("dwellings_dcd") or unit.get("engdwobdcd"),
        "dwellings_printed": unit.get("engdwobdcd"),
        "small_commercial": unit.get("small_commercial_dcd"),
        "has_data": data,
        "no_data_words": None if data else
            f"Mapped as {unit.get('muname') or 'an unnamed map unit'}: the survey holds no soil data for it.",
        "main_name": main.get("compname") if main else None,
        "main_pct": _int(main.get("comppct_r")) if main else None,
        "main_has_data": component_has_data(main),
        "rated": component_words(rated) if rated else None,
        "components": [component_words(c) for c in _by_size(found.components)],
        "technical": " · ".join(
            str(p) for p in (
                f"{unit.get('areasymbol')} (survey version {unit.get('saverest')})" if unit.get("areasymbol") else None,
                f"musym {unit.get('musym')}" if unit.get("musym") else None,
                f"mukey {found.mukey}",
                f"nationalmusym {unit.get('nationalmusym')}" if unit.get("nationalmusym") else None,
                unit.get("mukind"),
            ) if p
        ),
    }


def describe(
    rows: Iterable[Mapping[str, Any]],
    units: Mapping[str, Mapping[str, Any]],
    components: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    source: str | None = None,
) -> dict[str, Any] | None:
    """A lot's soil note: every map unit largest first, the uncovered part,
    the dominant and the worst-rated one. None when the lot was not measured."""
    rows = list(rows)
    if not rows:
        return None
    found, uncovered = lot_units(rows, units, components)
    dominant, worst = pick(found)
    total = sum(u.area_sqft for u in found) + uncovered
    return {
        "measured": True,
        "covered": bool(found),
        "no_coverage_words": None if found else "The USDA soil survey has no map unit under this lot.",
        "units": [unit_words(u) for u in found],
        "uncovered_sqft": round(uncovered, 1),
        "uncovered_pct": round(uncovered / total * 100, 1) if total else None,
        "lot_area_sqft": round(total, 1),
        "dominant": unit_words(dominant) if dominant else None,
        "worst": unit_words(worst) if worst is not None and worst is not dominant else None,
        "spans_several": len(found) > 1,
        "caveat": CAVEAT,
        "lep_classes_from": "NRCS National Soil Survey Handbook, Part 618 (linear extensibility percent)",
        "source": source,
        "source_name": SOURCE_NAME,
        "never_a_colour": True,
    }


# --- measuring (shapely) -----------------------------------------------------------


def measure_lots(
    lots: Sequence[Mapping[str, Any]],
    soils: Sequence[tuple[str, Any]],
    *,
    min_piece_sqft: float = MIN_PIECE_SQFT,
) -> Iterator[dict[str, Any]]:
    """Cut every soil polygon against every lot; yield lot rows (:data:`LOT_COLUMNS`).

    ``lots`` carry ``county``, ``tlid`` and ``geom`` (a shapely polygon in
    EPSG:2913, feet); ``soils`` are ``(mukey, polygon)`` in the same CRS, one
    part each. Each lot gets one row per map unit with at least
    ``min_piece_sqft`` on it, and one row with no ``mukey`` for whatever the
    survey leaves uncovered (at least ``min_piece_sqft``; the whole lot when
    nothing covers it). Where two survey areas overlap at their edge, the
    pieces are scaled to the union of the pieces, so the rows still sum to
    the lot.
    """
    import numpy as np
    import shapely

    geoms = np.array([s[1] for s in soils], dtype=object)
    keys = [str(s[0]) for s in soils]
    tree = shapely.STRtree(geoms)
    shapely.prepare(geoms)
    lot_geoms = np.array([lot["geom"] for lot in lots], dtype=object)
    valid = np.array([g is not None and not shapely.is_empty(g) for g in lot_geoms], dtype=bool)
    index = np.flatnonzero(valid)
    by_lot: dict[int, list[int]] = defaultdict(list)
    if index.size:
        pairs = tree.query(lot_geoms[index], predicate="intersects")
        for li, si in zip(index[pairs[0]], pairs[1]):
            by_lot[int(li)].append(int(si))
    for i, lot in enumerate(lots):
        if not valid[i]:
            continue
        geom = lot_geoms[i]
        lot_area = float(shapely.area(geom))
        if lot_area <= 0:
            continue
        base = {"county": lot["county"], "tlid": lot["tlid"], "lot_area_sqft": round(lot_area, 1)}
        areas: dict[str, float] = defaultdict(float)
        pieces = []
        for si in by_lot.get(i, ()):
            soil = geoms[si]
            piece = geom if shapely.contains_properly(soil, geom) else shapely.intersection(geom, soil)
            a = float(shapely.area(piece))
            if a > 0:
                areas[keys[si]] += a
                pieces.append(piece)
        total = sum(areas.values())
        covered = min(total, lot_area)
        if total > lot_area * (1 + SUM_TOLERANCE / 10) and len(pieces) > 1:
            covered = min(float(shapely.area(shapely.union_all(pieces))), lot_area)
        scale = covered / total if total else 1.0
        kept = {k: a * scale for k, a in areas.items() if a * scale >= min_piece_sqft}
        uncovered = max(0.0, lot_area - covered)
        for mukey, a in sorted(kept.items(), key=lambda kv: (-kv[1], kv[0])):
            yield {**base, "mukey": mukey, "area_sqft": round(a, 1), "share": round(a / lot_area, 5)}
        if not kept:
            uncovered = lot_area
        if uncovered >= min_piece_sqft or not kept:
            yield {**base, "mukey": None, "area_sqft": round(uncovered, 1), "share": round(uncovered / lot_area, 5)}


# --- helpers ----------------------------------------------------------------------


def _load_months(value: Any) -> list[dict[str, Any]] | None:
    """A component's months: a list already, or the JSON text a build file holds."""
    if value is None or value == "":
        return None
    if isinstance(value, list):
        return value
    import json

    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return None
    return loaded if isinstance(loaded, list) else None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    n = _num(value)
    return None if n is None else int(round(n))
