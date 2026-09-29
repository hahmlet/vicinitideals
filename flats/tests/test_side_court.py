"""The court BESIDE the building (FOLLOWUPS 4(a), the court's shape).

The screen charged one arrangement: a row of stalls ACROSS the lot behind
the building, reached by a lane down its flank. quadfit's s6s also draws
the stalls in a row ALONG the lot beside the building, the aisle between
them and the side wall and in from the street (``townhome_side_court``) --
the plan that fits a wide, shallow lot the row behind does not. These
tests hold what :func:`flats.score.paper.side_court` asks of the code
before it is offered, what the fit charges for it, and one real lot where
it is the difference.
"""

from __future__ import annotations

import json
import math

import pytest
import shapely
import yaml

from flats.designs.model import Design, Orientation
from flats.encode.load import load_trusted
from flats.fit.rectangle import Fitter
from flats.ingest.quadfit import lot_from_row, screen_lot
from flats.score import relief, slack
from flats.score.paper import Alley, court_across, paved, side_court
from flats.score.screen import _beside_beyond
from flats.tests.test_quadfit_bridge import row

pytestmark = pytest.mark.unit

POD = """
version: 1
label: Four-plex pod
typology: townhome_rear_court
footprint: {width_ft: 56, depth_ft: 36}
units: 4
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: modular, crane_required: true, crane_reach_ft: 60}
"""


def pod() -> Design:
    return Design(**{**yaml.safe_load(POD), "id": "pod"})


class Rules:
    """A resolution stub: the numbers, and the fields the code exempts."""

    def __init__(self, *exempted: str, **values: object) -> None:
        self.values = values
        self.exempted = exempted

    def get(self, name: str) -> object:
        return self.values.get(name)


OPEN = "parking_side_prohibited"


# --- what the code has to say before the court may stand there -------------


def test_unread_is_not_no() -> None:
    # The side of the building is offered only where the words leave it
    # open: waived, or stated False. Unread and stated True are not.
    assert side_court(pod(), Rules()) is None
    assert side_court(pod(), Rules(parking_side_prohibited=True)) is None
    assert side_court(pod(), Rules(OPEN)) is not None
    assert side_court(pod(), Rules(parking_side_prohibited=False)) is not None


def test_the_court_is_the_row_turned_along_the_lot() -> None:
    got = side_court(pod(), Rules(OPEN))
    row = court_across(pod(), Rules(OPEN))
    # Six stalls (1.5 a home), end to end along the building from its front
    # line; across, the standoff off the wall, the two-way aisle and a stall.
    assert got.stalls == row.stalls == 6
    assert got.length_ft == pytest.approx(6 * row.stall_ft)
    assert got.band_ft == pytest.approx(
        pod().parking.building_gap_ft + got.aisle_ft + got.stall_depth_ft
    )
    # The aisle is also the drive in from the street: never narrower.
    assert got.aisle_ft >= got.drive_ft >= pod().parking.lane_width_ft
    assert "parking_side_prohibited" in got.from_code


def test_a_city_asking_more_widens_it_and_less_does_not_shrink_it() -> None:
    base = side_court(pod(), Rules(OPEN))
    more = side_court(pod(), Rules(OPEN, parking_aisle_two_way_ft=30, parking_building_buffer_ft=8))
    less = side_court(pod(), Rules(OPEN, parking_aisle_two_way_ft=10, parking_stall_depth_ft=12))
    assert more.band_ft - base.band_ft == pytest.approx((30 - base.aisle_ft) + (8 - 5))
    assert less.band_ft == pytest.approx(base.band_ft)


def test_a_parking_setback_from_the_street_pushes_the_row_back() -> None:
    # Happy Valley's parking stands back from the street as far as the house.
    base = side_court(pod(), Rules(OPEN))
    back = side_court(pod(), Rules(OPEN, parking_street_setback_ft=25, setback_front_ft=15))
    assert back.length_ft - base.length_ft == pytest.approx(10.0)
    # Against a front yard nobody read, the distance is not computable.
    assert side_court(pod(), Rules(OPEN, parking_street_setback_ft=25)) is None


def test_the_caps_on_parking_along_the_street_are_charged() -> None:
    base = side_court(pod(), Rules(OPEN))
    facing = base.aisle_ft + base.stall_depth_ft
    assert side_court(pod(), Rules(OPEN, parking_area_max_width_ft=facing - 1)) is None
    assert side_court(pod(), Rules(OPEN, parking_area_max_width_ft=facing)) is not None
    # A share of the frontage: none measured is not offered.
    assert side_court(pod(), Rules(OPEN, parking_area_max_frontage_pct=50)) is None
    assert side_court(pod(), Rules(OPEN, parking_area_max_frontage_pct=50), frontage_ft=2 * facing - 1) is None
    assert side_court(pod(), Rules(OPEN, parking_area_max_frontage_pct=50), frontage_ft=2 * facing) is not None


def test_a_corner_lot_needs_the_front_ban_answered_no() -> None:
    # The fit does not say which flank the court stands on; on a corner one
    # of them faces the side street.
    assert side_court(pod(), Rules(OPEN), corner=True) is None
    assert side_court(pod(), Rules(OPEN, parking_front_prohibited=True), corner=True) is None
    assert side_court(pod(), Rules(OPEN, parking_front_prohibited=False), corner=True) is not None
    assert (
        side_court(
            pod(), Rules(OPEN, parking_front_prohibited=False, corner_access_street="side"), corner=True
        )
        is None
    )


def test_under_a_front_ban_the_row_stops_at_the_rear_wall() -> None:
    # Portland and Milwaukie keep parking out from in front of the building;
    # an interior lot's row may stand beside it but not run past its back.
    got = side_court(pod(), Rules(OPEN, parking_front_prohibited=True))
    assert got.within_building
    assert got.overhang_ft(56.0) == 0.0  # 54 ft of stalls beside a 56 ft flank
    assert math.isinf(got.overhang_ft(36.0))
    free = side_court(pod(), Rules(OPEN))
    assert not free.within_building
    assert free.overhang_ft(36.0) == pytest.approx(18.0)


def test_an_alley_the_code_sends_the_driveway_to_is_not_bypassed() -> None:
    rules = Rules(OPEN, parking_alley_access_required=True)
    assert side_court(pod(), rules, Alley(width_ft=16.0)) is None
    assert side_court(pod(), rules) is not None


def test_the_overhang_shares_the_rear_yard_as_the_court_behind_does() -> None:
    got = side_court(pod(), Rules(OPEN))
    rules = Rules(OPEN, setback_rear_ft=10)
    # 18 ft past a 36 ft wall, against a 10 ft rear yard the envelope cut.
    assert _beside_beyond(got, 36.0, rules) == pytest.approx(8.0)
    # No overhang: the rear yard the envelope already lost owes nothing more.
    assert _beside_beyond(got, 56.0, rules) == pytest.approx(0.0)


def test_the_court_beside_is_paved_along_its_length() -> None:
    got = side_court(pod(), Rules(OPEN))
    area = paved(pod(), Rules(OPEN, setback_front_ft=10), beside=got, deep_ft=56.0)
    assert area == pytest.approx(
        6 * got.stall_ft * got.stall_depth_ft + got.aisle_ft * got.length_ft + got.drive_ft * 10
    )
    assert paved(pod(), Rules(OPEN), beside=got, deep_ft=56.0) is None, "front yard unread"


# --- the search -------------------------------------------------------------


def test_the_search_asks_for_the_building_and_the_band_side_by_side() -> None:
    # An 85 x 66 envelope: the pod turned deep (36 across, 56 deep) plus a
    # 47 ft band is 83 across -- it stands; the pod broadside (56 + 47 =
    # 103) does not.
    got = side_court(pod(), Rules(OPEN))
    fitter = Fitter(shapely.box(0, 0, 85, 66), angles=(0.0,))
    fit = fitter.fit_beside(56, 36, band_ft=got.band_ft, beyond=lambda deep: 0.0, angles=(0.0,))
    assert fit.beside and fit.fits
    assert fit.orientation is Orientation.depth_facing
    assert fit.across_ft == pytest.approx(36 + got.band_ft)
    # Where the row may not run past the wall, an orientation it would is
    # never offered.
    banned = side_court(pod(), Rules(OPEN, parking_front_prohibited=True))
    none = fitter.fit_beside(
        56, 36, band_ft=banned.band_ft, beyond=lambda deep: _beside_beyond(banned, deep, Rules(OPEN)),
        angles=(0.0,), allow_flip=False,
    )
    assert none is None or not none.fits
    # No street direction known, no court beside.
    assert fitter.fit_beside(56, 36, band_ft=got.band_ft, beyond=lambda deep: 0.0, angles=()) is None


def test_the_court_beside_is_searched_only_along_the_street() -> None:
    # A 57 ft wide, 89 ft deep envelope, street along the bottom (bearing 0).
    # Turned a quarter, the pod broadside to the side line and the 47 ft
    # band behind it fit (83 of the 89 ft deep, 56 of the 57 wide) -- but
    # that is a building with its court BEHIND it and no lane down its
    # flank to reach it, the arrangement the row search refuses. Along the
    # street the 83 ft does not fit the 57, and the court is not offered.
    # Portland R2.5, 1N2E33DC -06600, read in the bound of 2026-09-29.
    got = side_court(pod(), Rules(OPEN))
    fitter = Fitter(shapely.box(0, 0, 57, 89), angles=(0.0, 90.0))
    turned = fitter.fit_beside(56, 36, band_ft=got.band_ft, beyond=lambda deep: 0.0, angles=(90.0,))
    assert turned.fits, "the quarter turn does hold the rectangle"
    along = fitter.fit_beside(56, 36, band_ft=got.band_ft, beyond=lambda deep: 0.0, angles=(0.0,))
    assert not along.fits
    assert fitter.holds(36 + got.band_ft, 56, angles=(90.0,))
    assert not fitter.holds(36 + got.band_ft, 56, angles=(0.0,))


# --- one lot, at its real coordinates ----------------------------------------

#: 1N2E26AB -01000, 13640 NE Fremont Ct, Portland R7, at real coordinates
#: (EPSG:2913, from quadfit_2026-09-28 s4). 94.8 ft of street on the north,
#: 86 ft deep. quadfit green, drawn townhome_side_court; the screen called
#: it yellow: the row of six behind the pod needs 83 ft behind the street
#: yard and the lot has about 71.
REAL_LOT = shapely.from_wkt(
    "POLYGON ((7684193.43 692118.06, 7684181.28 692023.02, 7684087.65 692056.63, "
    "7684099.65 692131.89, 7684193.43 692118.06))"
)
REAL_EDGES = [
    [7684193.43, 692118.06, 7684181.28, 692023.02, "S"],
    [7684181.28, 692023.02, 7684087.65, 692056.63, "R"],
    [7684087.65, 692056.63, 7684099.65, 692131.89, "S"],
    [7684099.65, 692131.89, 7684193.43, 692118.06, "F"],
]
REAL_ENVELOPE = shapely.from_wkt(
    "POLYGON ((7684093.24 692059.94, 7684102.23 692116.35, 7684186.58 692103.91, "
    "7684177.11 692029.83, 7684093.24 692059.94))"
)


def real_row() -> dict[str, object]:
    return row(
        TLID="1N2E26AB  -01000",
        zone="R7",
        area_sqft=float(REAL_LOT.area),
        frontage_ft=94.8,
        lot_width_ft=96.66,
        lot_depth_ft=86.0,
        edges_json=json.dumps(REAL_EDGES),
        front_bearings_json="[171.61]",
        lot_wkb=shapely.to_wkb(REAL_LOT),
        wkb=shapely.to_wkb(REAL_ENVELOPE),
    )


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


def test_a_real_wide_shallow_lot_seats_the_court_beside_the_pod(corpus) -> None:
    policy, rel = slack.load_policy(), relief.load_policy()
    lot = lot_from_row(real_row(), corpus.layers)
    assert lot.facts.corner is False and lot.facts.alley is None
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policy, relief=rel, step_deg=1.0)
    # Portland's one-lot path leaves the side of the building open, and its
    # front ban keeps the row within the building's flank: the pod turned
    # deep, the six stalls along it.
    assert s.fit.beside is True
    assert s.fit.orientation is Orientation.depth_facing
    court = side_court(pod(), s.rules, corner=False, frontage_ft=94.8)
    assert court.within_building
    assert court.overhang_ft(s.fit.required_ft) == 0.0
    check = next(c for c in s.screening.checks if c.check == "fit_ft")
    assert check.threshold == pytest.approx(56.0)  # the flank, nothing behind it
    assert check.verdict.value == "pass"
    assert s.screening.stalls_seated >= court.stalls
    # The drawing stands the court beside the building, not behind it.
    assert s.drawing is not None


def test_the_outdoor_square_is_measured_beside_the_court_beside(corpus, monkeypatch) -> None:
    """A plan with its court beside the building leaves its outdoor square
    around THAT court (FOLLOWUPS 4(a) x 7(b1)). Drawn as the court behind
    the building it does not have, the same lot showed a 40 ft square where
    the real plan leaves 21."""
    import dataclasses

    from flats.ingest import quadfit

    seen: list[tuple[bool, float | None, tuple, dict]] = []
    measure = quadfit.outdoor_square

    def spy(*a, **k):
        got = measure(*a, **k)
        seen.append((a[3].beside, got, a, k))
        return got

    monkeypatch.setattr(quadfit, "outdoor_square", spy)
    policy, rel = slack.load_policy(), relief.load_policy()
    lot = lot_from_row(real_row(), corpus.layers)
    (s,) = screen_lot(lot, [pod()], rules=corpus, policy=policy, relief=rel, step_deg=1.0)
    assert s.fit.beside is True
    ((beside, square, a, k),) = seen
    assert beside is True and square == pytest.approx(21.0, abs=0.5)
    shape = next(c for c in s.screening.checks if c.check == "open_space_shape")
    assert shape.observed == pytest.approx(square)
    behind = measure(*a[:3], dataclasses.replace(a[3], beside=False), *a[4:], **k)
    assert behind is not None and behind > square
