"""Frontage caps read against each city's own wording (FOLLOWUPS 84).

Steph 2026-10-14: a cap on how much of a street frontage the parking may
take applies on ANY street the lot has. Wilsonville, Hillsboro, Clackamas
845.02 and Beaverton S11 were wired first; this file holds the next five:

* **Oregon City** 17.16.030 D.1: "shall not exceed a total of forty feet
  wide or fifty percent of the lot frontage, whichever is less". Both limbs:
  the share and the feet (``parking_area_max_width_ft``), in the front
  yard only (phase 3: 17.04.490, 17.04.1515, 17.04.1530; a through lot has
  a front yard on each street, 17.08.045.B).
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


def test_oregon_city_caps_the_front_yard_not_every_street(corpus: RuleSet) -> None:
    # 17.16.060.D caps "off-street parking areas in the front yard"; the
    # front yard runs off the front lot line (17.04.1515), a corner lot's is
    # the narrowest frontage (17.04.490), and the corner side yard is a yard
    # of its own (17.04.1530). A through lot keeps a front yard on each
    # street (17.08.045.B). The stated words govern (FOLLOWUPS 84 phase 3).
    got = corpus.resolve("or/clackamas/oregon-city", "R-5").values
    assert got["parking_area_max_frontage_pct"].value == 50
    assert got["parking_area_frontage_any_street"].value is False
    front_yard = got["parking_area_frontage_front_yard"]
    assert front_yard.value is True
    text = quoted(front_yard.prov.quote)
    for words in (
        "off-street parking areas in the front yard",
        "the front lot line is that with the nar",
        "from the front lot line to the main building",
        "front yard on each street",
        "forty feet wide or fifty per",
    ):
        assert words in text, words


def test_oregon_city_carries_the_forty_feet_limb(corpus: RuleSet) -> None:
    for zone in ("R-10", "R-5", "R-2"):
        got = corpus.resolve("or/clackamas/oregon-city", zone).values
        assert got["parking_area_max_width_ft"].value == 40, zone
    text = quoted(got["parking_area_max_width_ft"].prov.quote)
    assert "whichever is less" in text


@pytest.mark.parametrize("zone", ["MUC-1", "MUC-2", "MUD", "C", "WFDD"])
def test_oregon_city_mixed_use_takes_e_not_d(corpus: RuleSet, zone: str) -> None:
    # D opens "In residential zones"; the mixed-use and commercial districts
    # (17.06.030) take E: parking behind the street facade, below, or beside
    # the building -- a location rule with no width or share. Its escape
    # needs a topographic constraint nothing measures, so the ban binds.
    got = corpus.resolve("or/clackamas/oregon-city", zone)
    assert {"parking_area_max_width_ft", "parking_area_max_frontage_pct"} <= set(got.exempted)
    assert got.get("parking_area_max_width_ft") is None
    assert got.get("parking_area_max_frontage_pct") is None
    ban = got.values["parking_front_prohibited"]
    assert ban.value is True
    assert "In mixed-use and commercial zones" in quoted(ban.prov.quote)
    assert "parking_side_prohibited" in got.exempted


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


@pytest.mark.parametrize(
    ("corner", "line", "frontage", "verdict"),
    [
        # A corner lot: 30 ft front, 140 ft side street. Summed, 35 percent
        # of 170 ft is 59.5 ft and the drive passes; on the 30 ft line it is
        # 10.5 ft and the drive does not.
        (True, 30.0, 170.0, "fails"),
        (True, 100.0, 170.0, "passes"),
        # A corner nobody measured street by street (the bridge always
        # measures one; this is a bare LotFacts): the sum would be the
        # lenient reading, so the cap is unrun rather than passed.
        (True, None, 170.0, "unchecked"),
        # One street: its line is the frontage.
        (False, None, 60.0, "passes"),
    ],
)
def test_the_driveway_share_is_of_one_street_line_not_the_sum(
    corner: bool, line: float | None, frontage: float, verdict: str
) -> None:
    from flats.score.screen import LotFacts

    lot = LotFacts(
        lot_sqft=12000, frontage_ft=frontage, lot_width_ft=60, corner=corner, street_line_min_ft=line
    )
    got = run(lot, rules(driveway_max_frontage_pct=35))
    share = check(got, "driveway_frontage_share")
    if verdict == "unchecked":
        assert share is None
        assert "driveway_frontage_share" in got.unchecked
        return
    assert share is not None
    assert share.threshold == pytest.approx(0.35 * (line if line is not None else frontage))
    assert (share.verdict is Verdict.passes) is (verdict == "passes")
    if verdict == "fails":
        assert got.colour is not Colour.green


def test_the_court_beside_the_building_is_held_to_one_street_line() -> None:
    from flats.score.paper import side_court
    from flats.score.screen import LotFacts

    lot = LotFacts(lot_sqft=12000, frontage_ft=200.0, corner=True, street_line_min_ft=60.0)
    assert lot.cap_frontage_ft == 60.0
    assert LotFacts(lot_sqft=12000, frontage_ft=200.0, corner=True).cap_frontage_ft is None
    cap = rules(parking_area_max_frontage_pct=50, parking_front_prohibited=False, parking_side_prohibited=False)
    # 50 percent of 200 ft would take the court's aisle and stall; of 60 ft it
    # does not.
    assert side_court(DESIGN, cap, None, corner=True, frontage_ft=lot.frontage_ft) is not None
    assert side_court(DESIGN, cap, None, corner=True, frontage_ft=lot.cap_frontage_ft) is None


# --- the bridge, on real coordinates ----------------------------------------

OREGON_CITY = (7_662_529.0, 614_687.0)
BEAVERTON_AT = (7_600_226.0, 661_811.0)
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


def test_oregon_city_leaves_a_corner_lots_side_street_court_alone(corpus: RuleSet) -> None:
    # The court behind the building faces the side street: the corner side
    # yard, not the front yard 17.16.060.D caps. The front street sees none.
    s = _screen(corpus, "oregon_city", "R-5", OREGON_CITY, 140.0, 160.0, "corner")
    width = check(s.screening, "parking_frontage_width")
    assert width is not None
    assert width.threshold == 40.0
    assert width.observed == 0.0
    assert width.verdict is Verdict.passes
    share = check(s.screening, "parking_frontage_share")
    assert share is not None and share.verdict is Verdict.passes


def test_oregon_city_measures_the_feet_on_a_through_lots_far_street(corpus: RuleSet) -> None:
    # A through lot has a front yard on each street (17.08.045.B): the court
    # behind the building faces the far street, and is held to forty feet.
    s = _screen(corpus, "oregon_city", "R-5", OREGON_CITY, 140.0, 200.0, "through")
    run_ft = s.facts.parking_frontage_run_ft
    assert run_ft is not None and run_ft > 0.0
    width = check(s.screening, "parking_frontage_width")
    assert width is not None
    assert width.observed == pytest.approx(run_ft)
    assert width.threshold == 40.0


def test_the_front_yard_reads_the_named_front_streets_only() -> None:
    corner = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, F), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0, 90.0])
    row = box(36, 60, 76, 102)
    every = street_runs(LOT, corner, row, BUILDING)
    assert max(ft for _, ft in every) > 0.0
    assert street_runs(LOT, corner, row, BUILDING, front_deg=0.0) == ((0.0, 0.0),)
    assert parking_share(LOT, corner, [row], BUILDING, front_deg=0.0) == (0.0, 0.0)
    # Named the other way, the side street IS the front and is read.
    assert street_runs(LOT, corner, row, BUILDING, front_deg=90.0) == (every[1],)
    through = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, S), (80, 120, 0, 120, F), (0, 120, 0, 0, S)], [0.0])
    assert street_runs(LOT, through, ROW, BUILDING, front_deg=0.0) == street_runs(LOT, through, ROW, BUILDING)


# --- one street, one line: pieces merged, never dropped (phase 3) ------------


def _lengths(edges) -> list[float]:
    from flats.fit.frontage import street_chains

    return sorted(round(sum(e.length_ft for e in c), 1) for c in street_chains(edges))


def test_a_rounded_corner_and_a_step_are_pieces_of_the_two_streets() -> None:
    # A corner lot whose county line rounds the corner in three chords and
    # steps 6 ft in along the side street. Cut at every turn, that was five
    # "streets" -- the shortest 6 ft, against which a 12 ft drive is 200
    # percent. It is two: the front and the side street, every foot of each.
    lines = [
        (0, 0, 90, 0, F),
        (90, 0, 96, 1.6, F),  # chords of the rounded corner
        (96, 1.6, 98.4, 4, F),
        (98.4, 4, 100, 10, F),
        (100, 10, 100, 70, F),
        (100, 70, 106, 70, F),  # a 6 ft step out along the side street
        (106, 70, 106, 140, F),
        (106, 140, 0, 140, R),
        (0, 140, 0, 0, S),
    ]
    edges = _edges(lines, [0.0, 90.0])
    total = sum(e.length_ft for e in edges.edges if e.cls is F)
    got = _lengths(edges)
    assert len(got) == 2
    assert sum(got) == pytest.approx(total, abs=0.2)
    # The front street with the chords nearer it; the side street with the
    # step and the chord that turns into it.
    assert got == pytest.approx([99.6, 142.2], abs=0.2)


def test_a_genuinely_short_street_line_still_binds() -> None:
    # 30 ft on the front street, 140 on the side: the 30 ft line is a street
    # of its own and stays 30 ft (Beaverton 1S126BC01400 is this lot).
    edges = _edges([(0, 0, 30, 0, F), (30, 0, 30, 140, F), (30, 140, 0, 140, R), (0, 140, 0, 0, S)], [0.0, 90.0])
    assert _lengths(edges) == [30.0, 140.0]
    from flats.ingest.quadfit import street_line_min_ft

    assert street_line_min_ft(edges) == pytest.approx(30.0)


def test_a_corner_lots_two_streets_stay_two() -> None:
    # A rounded corner joins two streets; it does not make them one.
    lines = [
        (0, 0, 70, 0, F),
        (70, 0, 77, 3, F),
        (77, 3, 80, 10, F),
        (80, 10, 80, 120, F),
        (80, 120, 0, 120, R),
        (0, 120, 0, 0, S),
    ]
    edges = _edges(lines, [0.0, 90.0])
    got = _lengths(edges)
    # The rounded corner goes whole to one of the two streets it joins.
    assert len(got) == 2
    assert sum(got) == pytest.approx(sum(e.length_ft for e in edges.edges if e.cls is F), abs=0.2)
    assert got[0] >= 70.0 and got[1] >= 110.0


def test_a_lot_round_a_block_end_keeps_three_streets() -> None:
    # Streets on three sides: the line turns and comes BACK along the first
    # direction, so the far side is a street of its own, not a step.
    lines = [
        (0, 0, 0, 30, S),
        (0, 30, 100, 30, F),
        (100, 30, 100, 0, F),
        (100, 0, 0, 0, F),
    ]
    got = _lengths(_edges(lines, [0.0, 90.0]))
    assert got == [30.0, 100.0, 100.0]


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


def test_beaverton_holds_a_corner_lots_drive_to_its_short_street(corpus: RuleSet) -> None:
    # 30 ft on the front street, 140 ft on the side street: the summed
    # frontage (170 ft) would allow a 59.5 ft drive; the 30 ft line allows
    # 10.5 ft, and the pod's drive is wider than that.
    s = _screen(corpus, "beaverton", "CM-HDR", BEAVERTON_AT, 30.0, 140.0, "corner")
    assert s.lot.facts.street_line_min_ft == pytest.approx(30.0)
    share = check(s.screening, "driveway_frontage_share")
    assert share is not None
    assert share.threshold == pytest.approx(0.35 * 30.0)
    assert 0.35 * 170.0 > share.observed > share.threshold
    assert share.verdict is not Verdict.passes
    assert s.screening.colour is not Colour.green
