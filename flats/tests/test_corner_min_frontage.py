"""A corner lot's minimum frontage is one street's, unless the code says it is all of them.

FOLLOWUPS 175. The minimum street frontage was read against every street line
the lot has, added together, plus the whole rounded corner. On a corner lot
that is two streets, and most codes state the minimum as one street's --
Gresham's corner row in so many words: "40 ft. as measured from the corner
radius end point to the property corner" (Table 4.0130 G.2). A lot 30 ft along
one street and 80 along the other cleared a 40 ft minimum on 110 ft.

So, by what the code says (:func:`flats.score.screen.frontage_readings`):
GREEN only where the strictest reading clears it, a question where only a
lenient one does, and a fail only where every reading fails.

The side check: a parking share that is exactly half its street was read as
50.00000000000001 percent and failed a 50 percent cap it meets.
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import box

from flats.fit.frontage import street_chains, street_lines_to_curve_ft, street_runs
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.flags import Colour
from flats.score.screen import FRONTAGE_LINE, LotFacts
from flats.score.slack import Verdict
from flats.tests.test_round2_rulings import F, R, S, _edges, check, rules, run

pytestmark = pytest.mark.unit

FLAG = "MEASURE-FRONTAGE-LINE"


def corner(streets: tuple[float, ...], *, ends: tuple[float, ...] = (), corner: bool = True) -> LotFacts:
    """A corner lot (big enough for everything else) whose street lines are
    ``streets``; ``frontage_ft`` their sum, as s4 measures it."""
    return LotFacts(
        lot_sqft=12000,
        frontage_ft=sum(streets),
        lot_width_ft=80,
        corner=corner,
        street_lines_ft=streets,
        street_line_min_ft=min(streets),
        street_line_max_ft=max(streets),
        street_lines_curve_end_ft=ends,
    )


def flagged(got) -> bool:
    return any(f.code == FLAG for f in got.flags)


# --- unstated: one street or all of them ------------------------------------


def test_a_corner_lot_short_on_one_street_is_a_question_not_green() -> None:
    # 30 ft along one street, 80 along the other: 110 ft added together
    # clears 40, the short street alone does not, and the code does not say.
    got = run(corner((30.0, 80.0)), rules(min_frontage_ft=40))
    assert got.colour is not Colour.green
    assert check(got, "min_frontage_ft") is None
    assert "min_frontage_ft" in got.unchecked
    assert flagged(got)


def test_a_corner_lot_whose_shortest_street_clears_it_stays_green() -> None:
    got = run(corner((50.0, 80.0)), rules(min_frontage_ft=40))
    assert got.colour is Colour.green
    measured = check(got, "min_frontage_ft")
    assert measured is not None and measured.observed == pytest.approx(50.0)
    assert not flagged(got)


def test_a_corner_lot_short_on_every_reading_fails() -> None:
    got = run(corner((15.0, 20.0)), rules(min_frontage_ft=40))
    measured = check(got, "min_frontage_ft")
    assert measured is not None and measured.verdict is Verdict.fails
    # Reported on the most lenient reading: the least it misses by.
    assert measured.observed == pytest.approx(35.0)
    assert got.colour is Colour.red


def test_a_lot_with_one_street_is_measured_as_before() -> None:
    lot = LotFacts(lot_sqft=12000, frontage_ft=45, lot_width_ft=45, street_lines_ft=(45.0,))
    measured = check(run(lot, rules(min_frontage_ft=40)), "min_frontage_ft")
    assert measured is not None and measured.observed == pytest.approx(45.0)
    assert measured.verdict is Verdict.passes


# --- the code says ------------------------------------------------------------


def test_on_any_one_street_the_longest_answers() -> None:
    # PCC 33.120.206.C.1, "at least 90 feet of frontage on a street".
    got = run(corner((30.0, 80.0)), rules(min_frontage_ft=40, min_frontage_one_street=True))
    assert got.colour is Colour.green
    assert check(got, "min_frontage_ft").observed == pytest.approx(80.0)


def test_on_the_front_line_the_streets_are_never_added_together() -> None:
    # MCC 39.4245 "Minimum Front Lot Line Length": 30 + 35 = 65 clears 40,
    # and neither street that could be the front does.
    got = run(corner((30.0, 35.0)), rules(min_frontage_ft=40, min_frontage_line="front"))
    measured = check(got, "min_frontage_ft")
    assert measured is not None and measured.verdict is Verdict.fails
    assert measured.observed == pytest.approx(35.0)


def test_on_the_front_line_an_unnamed_front_is_a_question() -> None:
    got = run(corner((30.0, 80.0)), rules(min_frontage_ft=40, min_frontage_line="front"))
    assert got.colour is not Colour.green
    assert flagged(got)


def test_on_the_front_line_a_front_fixed_as_the_shortest_answers() -> None:
    # Tigard 18.40.060 B with 18.30's front lot line: the shortest street.
    got = run(
        corner((30.0, 80.0)),
        rules(min_frontage_ft=40, min_frontage_line="front", front_lot_line_corner="shortest"),
    )
    measured = check(got, "min_frontage_ft")
    assert measured is not None and measured.verdict is Verdict.fails
    assert measured.observed == pytest.approx(30.0)


# --- Gresham: from the corner radius end point --------------------------------


def test_gresham_measures_each_street_from_the_end_of_the_curve() -> None:
    # 45 and 60 ft with the curve split between them; 38 and 52 ft from where
    # the curve ends. 38 misses 40, 52 clears it, and which street is not said.
    lot = corner((45.0, 60.0), ends=(38.0, 52.0))
    got = run(lot, rules(min_frontage_ft=40, min_frontage_line="radius_end"))
    assert got.colour is not Colour.green
    assert flagged(got)
    ok = run(corner((45.0, 60.0), ends=(42.0, 52.0)), rules(min_frontage_ft=40, min_frontage_line="radius_end"))
    assert ok.colour is Colour.green
    assert check(ok, "min_frontage_ft").observed == pytest.approx(42.0)


def test_gresham_fails_a_corner_short_on_both_streets_past_the_curve() -> None:
    # 41 + 43 = 84 ft added together; past the curve 36 and 38.
    got = run(corner((41.0, 43.0), ends=(36.0, 38.0)), rules(min_frontage_ft=40, min_frontage_line="radius_end"))
    measured = check(got, "min_frontage_ft")
    assert measured is not None and measured.verdict is Verdict.fails
    assert measured.observed == pytest.approx(38.0)


def test_gresham_unmeasured_curve_ends_hold_the_lot() -> None:
    got = run(corner((45.0, 60.0)), rules(min_frontage_ft=40, min_frontage_line="radius_end"))
    assert got.colour is not Colour.green
    assert flagged(got)
    assert FRONTAGE_LINE == "min_frontage_line"


def test_the_curve_end_is_where_the_rounded_corner_begins() -> None:
    # Beaverton 1S121BA00807's shape: 60 ft straight on each street and a
    # four-chord corner of about 80 ft shared between them. Split, each
    # street is 100 ft; to the end of the curve, 60.
    pts = [(0.0, 0.0), (60.0, 0.0)]
    for a in (25.0, 38.0, 55.0, 68.0):
        x, y = pts[-1]
        pts.append((x + 20 * math.cos(math.radians(a)), y + 20 * math.sin(math.radians(a))))
    x, y = pts[-1]
    pts.append((x, y + 60.0))
    lines = [(*pts[i], *pts[i + 1], F) for i in range(len(pts) - 1)]
    x_end, y_end = pts[-1]
    lines += [(x_end, y_end, 0.0, y_end, R), (0.0, y_end, 0.0, 0.0, S)]
    edges = _edges(lines, [0.0, 90.0])
    split = [sum(e.length_ft for e in c) for c in street_chains(edges)]
    assert sorted(split) == pytest.approx([100.0, 100.0], abs=0.2)
    assert sorted(street_lines_to_curve_ft(edges)) == pytest.approx([60.0, 60.0], abs=0.2)


def test_a_square_corner_and_a_through_lot_measure_as_their_streets() -> None:
    square = _edges([(0, 0, 30, 0, F), (30, 0, 30, 140, F), (30, 140, 0, 140, R), (0, 140, 0, 0, S)], [0.0, 90.0])
    assert sorted(street_lines_to_curve_ft(square)) == pytest.approx([30.0, 140.0])
    through = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, S), (80, 120, 0, 120, F), (0, 120, 0, 0, S)], [0.0])
    assert street_lines_to_curve_ft(through) == pytest.approx((80.0, 80.0))


# --- the corpus -----------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules())


@pytest.mark.parametrize(
    ("where", "zone", "field", "value"),
    [
        ("or/multnomah/gresham", "TR", "min_frontage_line", "radius_end"),
        ("or/multnomah/gresham", "LDR-5", "min_frontage_line", "radius_end"),
        ("or/multnomah/gresham", "MDR-24", "min_frontage_line", "radius_end"),
        ("or/multnomah/gresham", "DRL-1", "min_frontage_line", "radius_end"),
        ("or/multnomah/gresham", "CMU", "min_frontage_line", "radius_end"),
        # The corner cell states no measure: unstated.
        ("or/multnomah/gresham", "LDR-7", "min_frontage_line", None),
        ("or/multnomah/gresham", "LDR-PV", "min_frontage_line", None),
        ("or/multnomah/_unincorporated", "LR7", "min_frontage_line", "front"),
        ("or/washington/hillsboro", "R-7", "min_frontage_line", "front"),
        ("or/washington/tigard", "RES-C", "min_frontage_line", "front"),
        ("or/washington/sherwood", "LDR", "min_frontage_line", "front"),
        ("or/washington/durham", "SDR", "min_frontage_one_street", True),
        ("or/washington/_unincorporated", "R-6", "min_frontage_one_street", True),
        # R-5's east-Hillsboro rows are Hillsboro's front-line frontage.
        ("or/washington/_unincorporated", "R-5", "min_frontage_one_street", None),
    ],
)
def test_each_code_names_its_line(corpus: RuleSet, where: str, zone: str, field: str, value) -> None:
    got = corpus.resolve(where, zone, ("corner_lot",)).values.get(field)
    assert (None if got is None else got.value) == value


# --- the side check: exactly half is not over half ------------------------------


def test_parking_on_exactly_half_the_street_meets_a_half_cap() -> None:
    # 79.3 ft of street is 80 looks of 0.99125 ft; parking seen from 40 of
    # them is half. Feet over feet put it at 50.00000000000001 percent.
    lot = box(0, 0, 79.3, 120)
    edges = _edges(
        [(0, 0, 79.3, 0, F), (79.3, 0, 79.3, 120, S), (79.3, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0]
    )
    row = box(0, 5, 39.65, 25)
    building = box(4, 60, 70, 96)
    ((pct, ft),) = street_runs(lot, edges, row, building)
    assert pct == 50.0
    assert ft == pytest.approx(39.65)

