"""What stands on each lot today: vacant / teardown candidate / a house / larger.

FOLLOWUPS 125. A LABEL, never a colour: the standing ruling
``2026-10-14-existing-buildings-stay-green`` (flats/config/rulings.yaml) keeps
the map answering "does the pod fit", not "is it buyable". Nothing in the
screen, the fit or the score reads this module; the Lots page filters on it and
the lot page says it, and that is all.

Two sources, read side by side and never merged into one answer:

* **the footprint map** -- Metro RLIS's Building Footprint Database (the
  regional layer the statewide Oregon GEOHub layer was compiled from, and the
  newer of the two: Portland's footprints were reloaded from the city in 2025,
  where the statewide copy is mostly 2007-2009 digitising reviewed on 2019
  imagery). Each footprint is cut against each lot; the piece inside a lot
  counts for that lot when it is at least :data:`MIN_STRUCTURE_SQFT` and at
  least :data:`MIN_PIECE_SHARE` of the footprint (so a footprint drawn a foot
  over the line does not put a building on the neighbour, and an apartment
  block across three lots stands on all three).
* **the county roll** -- ``BLDGVAL`` (the improvements' market value),
  ``TOTALVAL``, ``YEARBUILT``, ``BLDGSQFT``, adopted as the lot table carries
  them.

The labels (Steph 2026-11-07, "vacancy or extremely low value house, like a
teardown"):

* ``vacant`` -- no building on the footprint map and the roll's building value
  is about nothing (at most :data:`VACANT_BLDGVAL`).
* ``teardown`` -- one main building, under :data:`LARGE_SQFT`, worth under
  :data:`TEARDOWN_VALUE` or under :data:`TEARDOWN_SHARE` of the property.
* ``house`` -- one main building under :data:`LARGE_SQFT` the roll values
  above that.
* ``larger`` -- a building of :data:`LARGE_SQFT` or more, or two or more main
  buildings.
* ``unclear`` -- the two sources disagree (the roll says vacant and a
  footprint stands, or the roll carries a building and the map shows none),
  the roll values a building with no land (a condominium unit), or the roll
  holds no value to test. The reason is named in ``disagreement`` and the
  lots are listed in the build's report.

A "main" building is the largest structure on the lot plus any other of at
least :data:`MAIN_SQFT` -- a detached garage or a shed does not make a house
"several buildings".

The measuring half (:func:`measure_lots`) needs shapely and runs where the lot
polygons are (LXC 137, or a laptop with a lot table); the label half is plain
Python and is what the tests hold. ``scripts/flats_lot_occupancy.py`` fetches,
builds and loads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Sequence

#: A structure smaller than this is not counted: Oregon's residential code
#: exempts a detached accessory building of 200 sq ft or less from a permit,
#: and the footprint map draws sheds as often as it misses them.
MIN_STRUCTURE_SQFT = 200.0

#: The share of a footprint that has to fall inside a lot before the piece
#: counts there (drift along a shared line stays off the neighbour).
MIN_PIECE_SHARE = 0.2

#: A second building this big is a main building, not a garage (a two-car
#: garage is 24 x 24 = 576 sq ft).
MAIN_SQFT = 600.0

#: One building this big or bigger is "larger" -- past any house a teardown
#: test should be run on.
LARGE_SQFT = 4000.0

#: The roll's building value at or under this reads as "no building" (fences,
#: paving and yard improvements carry a few thousand dollars on vacant lots).
VACANT_BLDGVAL = 20_000.0

#: A building worth under this, or under this share of the whole property, is
#: a teardown candidate (Steph 2026-11-07).
TEARDOWN_VALUE = 100_000.0
TEARDOWN_SHARE = 0.25

LABELS = ("vacant", "teardown", "house", "larger", "unclear")

#: What each label says on the page.
LABEL_WORDS = {
    "vacant": "Vacant: no building on the footprint map and next to no building value on the tax roll",
    "teardown": "Teardown candidate: one small building the tax roll values under $100,000 or under a quarter of the property",
    "house": "A house: one building the tax roll values above the teardown line",
    "larger": "Larger or several buildings: a building of 4,000 sq ft or more, or two or more main buildings",
    "unclear": "Unclear: the footprint map and the tax roll disagree about what stands here",
}

#: Short names for the filter and the badge.
LABEL_SHORT = {
    "vacant": "Vacant",
    "teardown": "Teardown candidate",
    "house": "House",
    "larger": "Larger / several buildings",
    "unclear": "Unclear (sources disagree)",
}

DISAGREEMENTS = (
    "roll_vacant_footprint_stands",
    "roll_building_no_footprint",
    "roll_improvements_only",
    "roll_has_no_value",
)

DISAGREEMENT_WORDS = {
    "roll_vacant_footprint_stands": "the tax roll carries no building value, but a building stands on the footprint map (a new build the roll has not caught, or a roll that values the building at nothing)",
    "roll_building_no_footprint": "the tax roll carries a building value, but the footprint map shows no building (demolished since the map was drawn, a building the map never drew, or a value for something that is not a building)",
    "roll_improvements_only": "the tax roll values a building here but no land -- a condominium unit or a building assessed apart from its land -- so this record is not a lot with a building on it",
    "roll_has_no_value": "the tax roll holds no value for this lot (a blank, or nothing for land and building alike, as on exempt or common land), so the teardown test cannot be run",
}


@dataclass(frozen=True)
class Measure:
    """What the footprint map shows on one lot."""

    building_count: int = 0
    footprint_sqft: float = 0.0
    largest_sqft: float = 0.0
    main_count: int = 0
    lot_sqft: float | None = None

    @property
    def coverage(self) -> float | None:
        if not self.lot_sqft or self.lot_sqft <= 0:
            return None
        return min(1.0, self.footprint_sqft / self.lot_sqft)


def measure_pieces(pieces: Sequence[float], lot_sqft: float | None) -> Measure:
    """A lot's measure from the areas (sq ft) of the footprint pieces counted on it."""
    kept = sorted((p for p in pieces if p >= MIN_STRUCTURE_SQFT), reverse=True)
    if not kept:
        return Measure(lot_sqft=lot_sqft)
    main = 1 + sum(1 for p in kept[1:] if p >= MAIN_SQFT)
    return Measure(
        building_count=len(kept),
        footprint_sqft=float(sum(kept)),
        largest_sqft=float(kept[0]),
        main_count=main,
        lot_sqft=lot_sqft,
    )


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def label(
    measure: Measure, building_value: Any, total_value: Any, land_value: Any = None
) -> tuple[str, str | None]:
    """``(label, disagreement)`` for one lot. Never a colour.

    ``land_value`` separates two roll records that are not a lot with a
    building on it: a building valued with no land (a condominium unit, a
    building assessed apart from its land) and a record that values nothing
    at all (exempt or common land) -- neither can say vacant or teardown.
    """
    bldg = _number(building_value)
    total = _number(total_value)
    land = _number(land_value)
    stands = measure.building_count > 0
    if bldg is None or (bldg <= 0 and land is not None and land <= 0):
        return "unclear", "roll_has_no_value"
    if bldg > VACANT_BLDGVAL and land is not None and land <= 0:
        return "unclear", "roll_improvements_only"
    roll_vacant = bldg <= VACANT_BLDGVAL
    if not stands:
        return ("vacant", None) if roll_vacant else ("unclear", "roll_building_no_footprint")
    if roll_vacant:
        return "unclear", "roll_vacant_footprint_stands"
    if measure.main_count >= 2 or measure.largest_sqft >= LARGE_SQFT:
        return "larger", None
    cheap = bldg < TEARDOWN_VALUE or (total is not None and total > 0 and bldg < TEARDOWN_SHARE * total)
    return ("teardown", None) if cheap else ("house", None)


# --- measuring (shapely) -------------------------------------------------------


def pieces_by_lot(lot_geoms: Sequence[Any], footprints: Iterable[Any]) -> list[list[float]]:
    """For each lot, the areas of the footprint pieces that count on it.

    ``lot_geoms`` and ``footprints`` are shapely geometries in the same feet
    (EPSG:2913). A piece counts where it is at least :data:`MIN_STRUCTURE_SQFT`
    and at least :data:`MIN_PIECE_SHARE` of its footprint.
    """
    import shapely
    from shapely.strtree import STRtree

    tree = STRtree(list(lot_geoms))
    prepared = [False] * len(lot_geoms)
    out: list[list[float]] = [[] for _ in lot_geoms]
    for fp in footprints:
        if fp is None or fp.is_empty:
            continue
        if not fp.is_valid:
            fp = shapely.make_valid(fp)
        whole = fp.area
        if whole < MIN_STRUCTURE_SQFT:
            continue
        for i in tree.query(fp, predicate="intersects"):
            lot = lot_geoms[i]
            if not prepared[i]:
                shapely.prepare(lot)
                prepared[i] = True
            if shapely.contains(lot, fp):
                piece = whole
            else:
                piece = shapely.intersection(lot, fp).area
            if piece >= MIN_STRUCTURE_SQFT and piece >= MIN_PIECE_SHARE * whole:
                out[i].append(piece)
    return out


def measure_lots(
    lots: Sequence[dict[str, Any]], footprints: Iterable[Any]
) -> Iterator[dict[str, Any]]:
    """One occupancy row per lot.

    Each lot dict holds ``county``, ``tlid``, ``geom`` (shapely, EPSG:2913),
    ``area_sqft`` and the roll's ``BLDGVAL`` / ``TOTALVAL`` / ``YEARBUILT`` /
    ``BLDGSQFT``.
    """
    pieces = pieces_by_lot([lot["geom"] for lot in lots], footprints)
    for lot, found in zip(lots, pieces):
        area = _number(lot.get("area_sqft")) or (lot["geom"].area if lot["geom"] is not None else None)
        m = measure_pieces(found, area)
        name, why = label(m, lot.get("BLDGVAL"), lot.get("TOTALVAL"), lot.get("LANDVAL"))
        coverage = m.coverage
        year = _number(lot.get("YEARBUILT"))
        yield {
            "county": lot["county"],
            "tlid": lot["tlid"],
            "label": name,
            "disagreement": why,
            "building_count": m.building_count,
            "main_count": m.main_count,
            "footprint_sqft": round(m.footprint_sqft, 1),
            "largest_sqft": round(m.largest_sqft, 1),
            "coverage": None if coverage is None else round(coverage, 4),
            "building_value": _number(lot.get("BLDGVAL")),
            "total_value": _number(lot.get("TOTALVAL")),
            "year_built": int(year) if year and year > 0 else None,
            "roll_building_sqft": _number(lot.get("BLDGSQFT")),
        }


#: The build's CSV columns, in order; the loader reads the same list.
OCCUPANCY_COLUMNS = (
    "county",
    "tlid",
    "label",
    "disagreement",
    "building_count",
    "main_count",
    "footprint_sqft",
    "largest_sqft",
    "coverage",
    "building_value",
    "total_value",
    "year_built",
    "roll_building_sqft",
)
