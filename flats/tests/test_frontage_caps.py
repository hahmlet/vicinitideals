"""Frontage caps read against each city's own wording (FOLLOWUPS 84).

Steph 2026-10-14: a cap on how much of a street frontage the parking may
take applies on ANY street the lot has. Wilsonville, Hillsboro, Clackamas
845.02 and Beaverton S11 were wired first; this file holds the next five:

* **Oregon City** 17.16.030 D.1: "shall not exceed a total of forty feet
  wide or fifty percent of the lot frontage, whichever is less". Both limbs:
  the share and the feet (``parking_area_max_width_ft``), every street.
* **Fairview** FMC 19.30.040(E)(2): "50 percent of the property street
  frontage". Every street.
* **Troutdale** TDC 8.120.C.4.d: "fifty percent (50%) of the street
  frontage". Every street; and the parking-in-front field is ``exempt``
  rather than empty, so a corner lot is no longer refused the court the
  code lets through inside half the frontage.
* **Sandy** SDC 17.90.160 F: "shall not occupy more than 50 percent of the
  frontage of any public street abutting the lot or building".
* **Beaverton** 60.05.15.6.C: "within 10 feet of a street lot line ... no
  more than 35 percent of the length of any street lot line". Parking keeps
  20 ft from the right-of-way (60.05.20.6.A.1), so only the driveway
  crosses that strip: ``driveway_max_frontage_pct``, not the parking cap.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapely
from shapely.geometry import box

from flats.fit.frontage import parking_share, street_runs
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.screen import CHECK_FIELD
from flats.score.slack import Verdict
from flats.tests.test_round2_rulings import (
    BUILDING,
    DESIGN,
    LOT,
    ROW,
    F,
    R,
    S,
    SS,
    _edges,
    check,
    facts,
    fit,
    rules,
    run,
)

pytestmark = pytest.mark.unit

DOCS = Path(__file__).resolve().parents[1] / "provenance" / "docs"
BEAVERTON = "or/washington/beaverton"
BEAVERTON_35 = (
    "CM-HDR", "CM-CS", "NS", "CS", "CC", "GC", "RC-E", "TC-MU", "TC-HDR", "SC-MU", "SC-HDR", "SC-S",
)


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


def quoted(ref: str) -> str:
    """The stored code text a ``quote:`` points at, lines joined."""
    path, _, ranges = ref.partition("#")
    lines = (DOCS / path).read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for part in ranges.split(","):
        start, _, end = part.lstrip("L").partition("-L")
        out += lines[int(start) - 1 : int(end or start)]
    return " ".join(" ".join(out).split())


# --- the encodings -------------------------------------------------------------


@pytest.mark.parametrize(
    ("layer", "zone", "words"),
    [
        ("or/clackamas/oregon-city", "R-5", "forty feet wide or fifty per"),
        ("or/multnomah/fairview", "R-6", "50 percent of the property street frontage"),
        ("or/multnomah/troutdale", "MDR", "fifty percent (50%) of the street frontage"),
        ("or/clackamas/sandy", "R-2", "50 percent of the frontage of any public street"),
    ],
)
def test_the_half_frontage_cap_is_read_on_any_street(
    corpus: RuleSet, layer: str, zone: str, words: str
) -> None:
    got = corpus.resolve(layer, zone).values
    assert got["parking_area_max_frontage_pct"].value == 50
    any_street = got["parking_area_frontage_any_street"]
    assert any_street.value is True
    assert words in quoted(any_street.prov.quote)
    assert words in quoted(got["parking_area_max_frontage_pct"].prov.quote)


def test_oregon_city_carries_the_forty_feet_limb(corpus: RuleSet) -> None:
    for zone in ("R-10", "R-5", "R-2", "MUC-1"):
        got = corpus.resolve("or/clackamas/oregon-city", zone).values
        assert got["parking_area_max_width_ft"].value == 40, zone
    text = quoted(got["parking_area_max_width_ft"].prov.quote)
    assert "whichever is less" in text


def test_troutdale_lets_the_court_stand_in_front_inside_half_the_frontage(corpus: RuleSet) -> None:
    got = corpus.resolve("or/multnomah/troutdale", "MDR")
    assert "parking_front_prohibited" in got.exempted
    # The townhouse branch (8.130.C.4.b.i) still bans it.
    townhouse = corpus.resolve("or/multnomah/troutdale", "MDR", ("unit_lots",))
    assert townhouse.values["parking_front_prohibited"].value is True


def test_beaverton_35_percent_is_the_driveway_inside_the_ten_foot_strip(corpus: RuleSet) -> None:
    for zone in BEAVERTON_35:
        got = corpus.resolve(BEAVERTON, zone).values
        cap = got["driveway_max_frontage_pct"]
        assert cap.value == 35, zone
        assert "parking_area_max_frontage_pct" not in got, zone
        assert "parking_area_frontage_any_street" not in got, zone
    text = quoted(cap.prov.quote)
    assert "within 10 feet of a street lot line" in text
    assert "closer than 20 feet to the right-of-way" in text
    # Nothing else in Beaverton reads the 35 as a parking cap.
    for zone in corpus.layers[BEAVERTON].zones:
        got = corpus.resolve(BEAVERTON, zone).values
        if "parking_area_max_frontage_pct" in got:
            assert got["parking_area_max_frontage_pct"].value == 50, zone


# --- the measure: share and feet from the same row --------------------------


def test_street_runs_gives_the_feet_with_the_share() -> None:
    through = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, S), (80, 120, 0, 120, F), (0, 120, 0, 0, S)], [0.0])
    (near_pct, near_ft), (far_pct, far_ft) = street_runs(LOT, through, ROW, BUILDING)
    assert near_pct == near_ft == 0.0
    assert far_ft == pytest.approx(40.0, abs=2.0)
    assert far_pct == pytest.approx(100.0 * far_ft / 80.0)


def test_the_worst_row_gives_both_numbers() -> None:
    corner = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, SS), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0, 90.0])
    against = box(36, 60, 76, 102)
    away = box(4, 60, 44, 102)
    pct, ft = parking_share(LOT, corner, [against, away], BUILDING)
    best = min((street_runs(LOT, corner, r, BUILDING) for r in (against, away)), key=lambda runs: max(runs))
    assert (pct, ft) == max(best)
    assert parking_share(LOT, corner, [], BUILDING) is None


# --- the check: the feet limb -----------------------------------------------

CAP = {
    "parking_area_max_frontage_pct": 50,
    "parking_area_frontage_any_street": True,
    "parking_area_max_width_ft": 40,
}


def test_the_forty_feet_binds_where_the_share_does_not() -> None:
    assert CHECK_FIELD["parking_frontage_width"] == "parking_area_max_width_ft"
    # A 43 ft court on a 100 ft street: 43 percent, inside the share, over 40 ft.
    over = run(facts(parking_frontage_share_pct=43.0, parking_frontage_run_ft=43.0), rules(**CAP))
    assert check(over, "parking_frontage_share").verdict is Verdict.passes
    assert check(over, "parking_frontage_width").verdict is not Verdict.passes
    assert over.colour is Colour.red
    under = run(facts(parking_frontage_share_pct=36.0, parking_frontage_run_ft=36.0), rules(**CAP))
    assert check(under, "parking_frontage_width").verdict is Verdict.passes
    assert under.colour is Colour.green


def test_the_feet_unmeasured_is_unrun_and_not_asked_off_the_any_street_cap() -> None:
    got = run(facts(parking_frontage_share_pct=36.0), rules(**CAP))
    assert check(got, "parking_frontage_width") is None
    assert "parking_frontage_width" in got.unchecked
    front_only = {k: v for k, v in CAP.items() if k != "parking_area_frontage_any_street"}
    plain = run(facts(parking_frontage_run_ft=90.0), rules(**front_only))
    assert check(plain, "parking_frontage_width") is None
    assert "parking_frontage_width" not in plain.unchecked


# --- Beaverton: the driveway's share ----------------------------------------


@pytest.mark.parametrize(("frontage", "passes"), [(30.0, False), (60.0, True)])
def test_beaverton_holds_the_driveway_to_35_percent_of_the_frontage(
    corpus: RuleSet, frontage: float, passes: bool
) -> None:
    from flats.score.screen import LotFacts, screen

    got = screen(
        corpus.resolve(BEAVERTON, "CM-HDR"),
        LotFacts(lot_sqft=12000, frontage_ft=frontage, lot_width_ft=frontage),
        DESIGN,
        fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}),
        relief=relief.load_policy(),
    )
    share = check(got, "driveway_frontage_share")
    assert share is not None
    assert share.threshold == pytest.approx(0.35 * frontage)
    assert (share.verdict is Verdict.passes) is passes


# --- the bridge, on real coordinates ----------------------------------------

OREGON_CITY = (7_662_529.0, 614_687.0)
SANDY = (7_749_541.0, 635_766.0)
TROUTDALE = (7_717_882.0, 688_269.0)


def _screen(corpus: RuleSet, jurisdiction: str, zone: str, at, w: float, d: float, kind: str):
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.tests.test_fire import bridge_row

    x0, y0 = at
    if kind == "corner":
        edges = [[x0, y0, x0 + w, y0, "F"], [x0 + w, y0, x0 + w, y0 + d, "F"],
                 [x0 + w, y0 + d, x0, y0 + d, "R"], [x0, y0 + d, x0, y0, "S"]]
        bearings, frontage = "[0.0, 90.0]", w + d
    else:
        edges = [[x0, y0, x0 + w, y0, "F"], [x0 + w, y0, x0 + w, y0 + d, "S"],
                 [x0 + w, y0 + d, x0, y0 + d, "F"], [x0, y0 + d, x0, y0, "S"]]
        bearings, frontage = "[0.0, 180.0]", 2 * w
    row = bridge_row(
        jurisdiction=jurisdiction,
        zone=zone,
        edges_json=json.dumps(edges),
        front_bearings_json=bearings,
        frontage_ft=frontage,
        lot_width_ft=w,
        lot_depth_ft=d,
        area_sqft=w * d,
        wkb=shapely.to_wkb(box(x0 + 5, y0 + 10, x0 + w - 5, y0 + d - 10)),
        lot_wkb=shapely.to_wkb(box(x0, y0, x0 + w, y0 + d)),
    )
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(
        lot, [DESIGN], rules=corpus, policy=slack.load_policy(), relief=relief.load_policy(), step_deg=30.0
    )
    return s


def test_oregon_city_measures_the_feet_on_a_corner_lot(corpus: RuleSet) -> None:
    s = _screen(corpus, "oregon_city", "R-5", OREGON_CITY, 140.0, 160.0, "corner")
    run_ft = s.facts.parking_frontage_run_ft
    assert run_ft is not None and run_ft > 0.0
    width = check(s.screening, "parking_frontage_width")
    assert width is not None
    assert width.observed == pytest.approx(run_ft)
    assert width.threshold == 40.0


def test_sandy_holds_a_through_lots_far_street_to_half(corpus: RuleSet) -> None:
    # A 70 ft through lot: the court behind the building faces the far
    # street across more than half of it.
    s = _screen(corpus, "sandy", "R-2", SANDY, 70.0, 200.0, "through")
    share = check(s.screening, "parking_frontage_share")
    assert share is not None and share.threshold == 50.0
    assert share.observed == pytest.approx(s.facts.parking_frontage_share_pct)
    assert share.verdict is not Verdict.passes


def test_troutdale_measures_the_side_street_on_a_corner_lot(corpus: RuleSet) -> None:
    s = _screen(corpus, "troutdale", "MDR", TROUTDALE, 120.0, 140.0, "corner")
    share = check(s.screening, "parking_frontage_share")
    assert share is not None and share.threshold == 50.0
