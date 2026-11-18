"""FOLLOWUPS 191: on a corner parcel only the plat's corner home lot takes the
corner townhouse number.

Gresham prints its townhouse rows twice, "Width at building line: Interior
lot" and "Corner lot" (4/4.0130.txt#L40,L47), and frontage the same way
(L78-L82). A corner lot is "a lot that has frontage on two or more streets"
and an interior lot "a lot other than a corner lot, with frontage only on one
street" (3/3.0103.txt#L568-L569,L579-L580). The rows mean the lot each home
stands on. The screen asked every middle home lot for the corner lot's 25
ft, so a corner townhouse plat in MDR-24 or the corridor zones could never
pass (pagecheck-34, 2026-11-13).

Now: on a plain corner -- two straight streets meeting at one corner -- the
middle home lots take the interior number. On a through lot every home lot
runs street to street and stays a corner. Anywhere else (a curve, a lot
nothing measured) which home lots are corners is unsettled: a home lot that
clears one number and not the other is a question, MEASURE-CORNER-HOME-LOT,
never a GREEN.
"""

from __future__ import annotations

import json
import math

import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

from flats.fit.frontage import two_straight_streets  # noqa: E402
from flats.ingest.quadfit import lot_from_row, screen_lot, townhouse  # noqa: E402
from flats.rules.loader import load_rules  # noqa: E402
from flats.rules.resolver import RuleSet  # noqa: E402
from flats.score import relief, slack  # noqa: E402
from flats.score.flags import Colour, load_registry  # noqa: E402
from flats.score.screen import (  # noqa: E402
    CORNER_HOME_LOT,
    HOME_LOT_FRONTAGE,
    HOME_LOT_WIDTH,
    LotFacts,
    _home_lots,
    _row_of_home_lots,
)
from flats.tests.test_fire import X0, Y0, bridge_row, pod  # noqa: E402
from flats.tests.test_townhouse_lots import NO_OVERLAYS, wide  # noqa: E402

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
FLAG = "MEASURE-CORNER-HOME-LOT"
SPLIT = ("unit_lots", "corner_lot")


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def _row(points: list[tuple[float, float]], classes: list[str], bearings: list[float]) -> dict:
    lot = Polygon(points)
    edges = [
        [*points[i], *points[(i + 1) % len(points)], classes[i]] for i in range(len(points))
    ]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    width = max(xs) - min(xs)
    return bridge_row(
        jurisdiction="gresham",
        zone="MDR-24",
        tier="B",
        inside_ugb=True,
        area_sqft=lot.area,
        frontage_ft=sum(
            math.dist(points[i], points[(i + 1) % len(points)])
            for i, c in enumerate(classes)
            if c == "F"
        ),
        lot_width_ft=width,
        lot_depth_ft=max(ys) - min(ys),
        edges_json=json.dumps(edges),
        front_bearings_json=json.dumps(bearings),
        wkb=shapely.to_wkb(lot.buffer(-6.0)),
        lot_wkb=shapely.to_wkb(lot),
        driveway_spacing="clear",
        **NO_OVERLAYS,
    )


def corner(width: float = 110.0, depth: float = 120.0) -> dict:
    """Two straight streets, the front along the bottom, the side street up
    the left, meeting square at the lot's corner."""
    pts = [(X0, Y0), (X0 + width, Y0), (X0 + width, Y0 + depth), (X0, Y0 + depth)]
    return _row(pts, ["F", "S", "R", "F"], [0.0, 90.0])


def rounded(width: float = 110.0, depth: float = 120.0, radius: float = 15.0) -> dict:
    """The same corner with its 15 ft radius drawn as three chords."""
    arc = [
        (X0 + radius - radius * math.cos(math.radians(a)), Y0 + radius - radius * math.sin(math.radians(a)))
        for a in (0.0, 30.0, 60.0, 90.0)
    ]
    # arc runs from (X0, Y0+r) round to (X0+r, Y0)
    pts = [*arc, (X0 + width, Y0), (X0 + width, Y0 + depth), (X0, Y0 + depth)]
    return _row(pts, ["F", "F", "F", "F", "S", "R", "F"], [0.0, 90.0])


def curved(width: float = 110.0, depth: float = 120.0) -> dict:
    """A front that bends through 60 degrees in five chords before the side
    street: one street curving, or two meeting -- the lot's lines cannot say."""
    pts = [(X0, Y0 + depth), (X0, Y0)]
    x, y = X0, Y0
    step = width / 5
    for k in range(5):
        a = math.radians(12.0 * (k + 1) - 6.0)
        x, y = x + step * math.cos(a), y + step * math.sin(a)
        pts.append((x, y))
    pts.append((x, Y0 + depth))
    classes = ["F"] + ["F"] * 5 + ["S", "R"]
    # pts: side-street top -> corner -> 5 chords -> back corner
    return _row(pts, classes, [90.0, 30.0])


def through() -> dict:
    """Streets along the front, the left side and the rear: a through lot."""
    pts = [(X0, Y0), (X0 + 110.0, Y0), (X0 + 110.0, Y0 + 120.0), (X0, Y0 + 120.0)]
    return _row(pts, ["F", "S", "F", "F"], [0.0, 90.0])


def screened(corpus, policies, r: dict, design=None):
    lot = lot_from_row(r, corpus.layers)
    (got,) = screen_lot(
        lot,
        [wide() if design is None else design],
        rules=corpus,
        policy=policies[0],
        relief=policies[1],
        step_deg=30.0,
    )
    return lot, got


def home_binds(got) -> dict:
    return {
        b["check"]: b for b in got.forms["townhomes"]["binds"] if b["check"].startswith("home_lot")
    }


def codes(got) -> set[str]:
    return {f["code"] for f in got.forms["townhomes"]["flags"]}


# --- the resolution -----------------------------------------------------------


def test_a_corner_townhouse_resolution_carries_the_interior_lots(corpus) -> None:
    got = corpus.resolve(GRESHAM, "MDR-24", SPLIT)
    assert got.values["min_frontage_ft"].value == 25
    assert got.interior is not None
    assert "corner_lot" not in got.interior.conditions
    assert got.interior.values["min_frontage_ft"].value == 16
    assert got.interior.values["min_lot_width_ft"].value == 16


def test_only_a_corner_townhouse_plat_resolves_twice(corpus) -> None:
    assert corpus.resolve(GRESHAM, "MDR-24", ("unit_lots",)).interior is None
    assert corpus.resolve(GRESHAM, "MDR-24", ("corner_lot",)).interior is None


# --- the parcel's streets -----------------------------------------------------


def test_two_straight_streets_is_the_plain_corner(corpus) -> None:
    assert two_straight_streets(lot_from_row(corner(), corpus.layers).edges)
    assert two_straight_streets(lot_from_row(rounded(), corpus.layers).edges)


def test_a_curve_a_through_lot_or_one_street_is_not(corpus) -> None:
    assert not two_straight_streets(lot_from_row(curved(), corpus.layers).edges)
    assert not two_straight_streets(lot_from_row(through(), corpus.layers).edges)
    assert not two_straight_streets(lot_from_row(bridge_row(), corpus.layers).edges)
    assert not two_straight_streets(None)


# --- the screen ---------------------------------------------------------------


def test_middle_home_lots_on_a_plain_corner_take_the_interior_number(corpus, policies) -> None:
    """MDR-24 on a 110 x 120 ft corner: 20 ft homes clear the interior 16 ft
    (Table 4.0130 E.1, G.1) though not the corner lot's 25 ft."""
    lot, got = screened(corpus, policies, corner())
    assert lot.observed.get("corner_lot") is True
    assert lot.facts.two_straight_streets
    assert not home_binds(got)
    assert FLAG not in codes(got)
    assert got.forms["townhomes"]["colour"] != "red"


def test_an_unsettled_corner_is_a_question_never_a_green(corpus, policies) -> None:
    """The bent front: a middle home lot may abut the curve and be a corner
    lot too (3/3.0103.txt#L570), so 20 ft clears one reading and not the
    other -- held YELLOW with the flag."""
    lot, got = screened(corpus, policies, curved())
    assert lot.observed.get("corner_lot") is True
    assert not lot.facts.two_straight_streets
    assert not home_binds(got)
    assert FLAG in codes(got)
    assert got.forms["townhomes"]["colour"] != "green"
    assert got.signed.colour is not Colour.green or got.forms["works_as"] == "apartment"


def test_a_through_lot_keeps_the_corner_number_on_every_home_lot(corpus, policies) -> None:
    """Each home lot runs from the front street to the rear one: frontage on
    two streets, a corner lot under Gresham's definition."""
    _, got = screened(corpus, policies, through())
    binds = home_binds(got)
    assert binds[HOME_LOT_FRONTAGE]["threshold"] == 25.0
    assert binds[HOME_LOT_FRONTAGE]["observed"] == 20.0
    assert got.forms["townhomes"]["colour"] == "red"


def test_the_flag_type_is_registered_below_nothing_and_says_why() -> None:
    entry = load_registry()[FLAG]
    assert "FACT_UNOBSERVED" in entry.raised_from
    assert entry.severity >= 3  # holds a lot out of GREEN


# --- the home lots one at a time ----------------------------------------------


def _asked(rules, facts: LotFacts, design) -> tuple[dict, list, set]:
    got: dict[str, float] = {}
    unchecked: list[str] = []
    unmeasured: set[str] = set()

    def check(name: str, observed: float, threshold: float | None, *, is_maximum: bool) -> None:
        got[name] = threshold

    _home_lots(rules, facts, design, check, unchecked, unmeasured)
    return got, unchecked, unmeasured


PLAIN = LotFacts(lot_sqft=13_200, lot_width_ft=110, lot_depth_ft=120, two_straight_streets=True)
UNSETTLED = LotFacts(lot_sqft=13_200, lot_width_ft=110, lot_depth_ft=120)
THROUGH = LotFacts(lot_sqft=13_200, lot_width_ft=110, lot_depth_ft=120, through_lot=True)


def test_known_layout_reads_the_interior_figure(corpus) -> None:
    got, unchecked, unmeasured = _asked(corpus.resolve(GRESHAM, "MDR-24", SPLIT), PLAIN, townhouse(wide()))
    assert got[HOME_LOT_FRONTAGE] == 16 and got[HOME_LOT_WIDTH] == 16
    assert not unmeasured


def test_through_lot_reads_the_corner_figure(corpus) -> None:
    got, _, unmeasured = _asked(corpus.resolve(GRESHAM, "MDR-24", SPLIT), THROUGH, townhouse(wide()))
    assert got[HOME_LOT_FRONTAGE] == 25 and got[HOME_LOT_WIDTH] == 25
    assert not unmeasured


def test_unsettled_between_the_two_is_unchecked_and_flagged(corpus) -> None:
    got, unchecked, unmeasured = _asked(
        corpus.resolve(GRESHAM, "MDR-24", SPLIT), UNSETTLED, townhouse(wide())
    )
    assert HOME_LOT_FRONTAGE not in got and HOME_LOT_FRONTAGE in unchecked
    assert CORNER_HOME_LOT in unmeasured


def test_unsettled_clearing_both_passes_on_the_stricter(corpus) -> None:
    """LDR-5: 20 ft corner townhouse width, 16 ft interior (4/4.0130.txt#L45,
    L54); a 20 ft home clears both, and is asked the stricter."""
    got, _, unmeasured = _asked(corpus.resolve(GRESHAM, "LDR-5", SPLIT), UNSETTLED, townhouse(wide()))
    assert got[HOME_LOT_WIDTH] == 20
    assert CORNER_HOME_LOT not in unmeasured


def test_unsettled_clearing_neither_fails_on_the_lenient(corpus) -> None:
    """The 56 ft pod's 14 ft homes miss MDR-24's 16 and 25 alike: a fail,
    measured against the 16."""
    got, _, unmeasured = _asked(corpus.resolve(GRESHAM, "MDR-24", SPLIT), UNSETTLED, townhouse(pod()))
    assert got[HOME_LOT_FRONTAGE] == 16
    assert CORNER_HOME_LOT not in unmeasured


def test_the_far_end_lot_is_interior_on_a_plain_corner(corpus) -> None:
    rules = corpus.resolve(GRESHAM, "MDR-24", SPLIT)
    design = townhouse(wide())
    plain = _row_of_home_lots(rules, design, "min_frontage_ft", 0.0, lot=PLAIN)
    unsettled = _row_of_home_lots(rules, design, "min_frontage_ft", 0.0, lot=UNSETTLED)
    corner_only = _row_of_home_lots(rules, design, "min_frontage_ft", 0.0, lot=THROUGH)
    assert plain <= unsettled == corner_only
    # Without a lot nothing is known: the corner number on both ends, as before.
    assert _row_of_home_lots(rules, design, "min_frontage_ft", 0.0) == corner_only
