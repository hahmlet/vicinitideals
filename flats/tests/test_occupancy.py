"""What stands on the lot (FOLLOWUPS 125): the labels, the measuring, and the
one rule that matters most -- the label never reaches a colour."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from shapely.geometry import box

from flats.ingest.occupancy import (
    DISAGREEMENT_WORDS,
    LABEL_SHORT,
    LABEL_WORDS,
    LABELS,
    Measure,
    label,
    measure_lots,
    measure_pieces,
    pieces_by_lot,
)

FLATS = Path(__file__).resolve().parents[1]


def _one(sqft: float) -> Measure:
    return measure_pieces([sqft], 5000)


@pytest.mark.parametrize(
    ("measure", "bldg", "total", "want"),
    [
        (Measure(lot_sqft=5000), 0, 300_000, ("vacant", None)),
        (Measure(lot_sqft=5000), 4_000, 300_000, ("vacant", None)),
        (Measure(lot_sqft=5000), 80_000, 380_000, ("unclear", "roll_building_no_footprint")),
        (_one(1200), 0, 300_000, ("unclear", "roll_vacant_footprint_stands")),
        (_one(1200), 90_000, 400_000, ("teardown", None)),
        # Over $100,000 but under a quarter of the property: still a teardown.
        (_one(1200), 140_000, 700_000, ("teardown", None)),
        (_one(1200), 260_000, 700_000, ("house", None)),
        (_one(4200), 50_000, 700_000, ("larger", None)),
        (_one(3200), 50_000, 700_000, ("teardown", None)),
        (_one(3200), 300_000, 700_000, ("house", None)),
        (Measure(lot_sqft=5000), 20_000, 300_000, ("vacant", None)),
        (Measure(lot_sqft=5000), 21_000, 300_000, ("unclear", "roll_building_no_footprint")),
        (measure_pieces([1500, 900], 8000), 300_000, 700_000, ("larger", None)),
        # A house and its garage is one main building, not "several".
        (measure_pieces([1500, 480], 8000), 300_000, 700_000, ("house", None)),
        (_one(1200), None, 700_000, ("unclear", "roll_has_no_value")),
        (Measure(lot_sqft=5000), None, None, ("unclear", "roll_has_no_value")),
    ],
)
def test_each_label_follows_steph_s_definitions(measure: Measure, bldg, total, want) -> None:
    assert label(measure, bldg, total) == want


def test_a_roll_record_with_no_land_is_not_a_lot_with_a_building() -> None:
    # A condominium unit: the building is valued, the land is not, and the
    # footprint stands on the common lot next door.
    assert label(Measure(lot_sqft=900), 320_000, 320_000, 0) == ("unclear", "roll_improvements_only")
    # Exempt or common land values nothing at all.
    assert label(_one(2000), 0, 0, 0) == ("unclear", "roll_has_no_value")
    assert label(Measure(lot_sqft=5000), 0, 250_000, 250_000) == ("vacant", None)


def test_a_shed_is_not_a_building() -> None:
    m = measure_pieces([150, 90], 5000)
    assert m.building_count == 0
    assert label(m, 0, 200_000) == ("vacant", None)


def test_coverage_is_the_counted_footprint_over_the_lot() -> None:
    m = measure_pieces([1000, 1500], 10_000)
    assert m.building_count == 2 and m.main_count == 2
    assert m.coverage == pytest.approx(0.25)
    assert Measure(lot_sqft=None).coverage is None


def test_every_label_and_disagreement_has_words() -> None:
    assert set(LABEL_WORDS) == set(LABELS) == set(LABEL_SHORT)
    for name, why in (("unclear", d) for d in DISAGREEMENT_WORDS):
        assert LABEL_WORDS[name] and DISAGREEMENT_WORDS[why]


def test_a_footprint_counts_where_it_stands_not_where_it_drifts() -> None:
    # A 30 x 40 house on the left lot, drawn 2 ft over the line.
    house = box(18, 30, 52, 70)
    # A 90 x 60 block across both lots.
    block = box(5, 120, 95, 180)
    lots = [box(0, 0, 50, 200), box(50, 0, 100, 200)]
    pieces = pieces_by_lot(lots, [house, block])
    assert len(pieces[0]) == 2  # the house and its half of the block
    assert len(pieces[1]) == 1  # only the block: the 2 ft drift (80 sq ft) is not a building
    assert sorted(pieces[0])[0] == pytest.approx(32 * 40)
    assert pieces[1][0] == pytest.approx(45 * 60)


def test_measure_lots_writes_one_row_per_lot_with_the_roll_beside_it() -> None:
    lots = [
        {"county": "multnomah", "tlid": "1S1E01AA  -00100", "geom": box(0, 0, 50, 100), "area_sqft": 5000,
         "BLDGVAL": 60_000, "TOTALVAL": 400_000, "YEARBUILT": 1924, "BLDGSQFT": 900},
        {"county": "multnomah", "tlid": "1S1E01AA  -00200", "geom": box(50, 0, 100, 100), "area_sqft": 5000,
         "BLDGVAL": 0, "TOTALVAL": 250_000, "YEARBUILT": 0, "BLDGSQFT": 0},
    ]
    rows = list(measure_lots(lots, [box(10, 10, 40, 40)]))
    assert [r["tlid"] for r in rows] == ["1S1E01AA  -00100", "1S1E01AA  -00200"]
    assert rows[0]["label"] == "teardown" and rows[0]["building_count"] == 1
    assert rows[0]["coverage"] == pytest.approx(0.18)
    assert rows[0]["year_built"] == 1924
    assert rows[1]["label"] == "vacant" and rows[1]["year_built"] is None


def test_nothing_that_screens_reads_the_label() -> None:
    """Ruling 2026-10-14-existing-buildings-stay-green: the label is shown and
    filtered on, never fed to a colour. No screening package may import it."""
    importing = re.compile(r"^\s*(from|import)\s.*\boccupancy\b", re.MULTILINE)
    offenders = [
        str(path.relative_to(FLATS))
        for package in ("score", "fit", "rules", "geom", "encode", "normalize", "designs")
        for path in (FLATS / package).rglob("*.py")
        if importing.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == []
