"""The building's share of the street frontage (FOLLOWUPS 109).

Three codes ask a building to fill a share of the street it stands on:

* **Beaverton** 60.05.15.6.A: 60 percent of the Primary Frontage between the
  minimum and the maximum setback, 35 of a secondary one, the driveway's
  width off the frontage (CM-CS under B: 50 / 35, no band, so unmeasured).
* **Beaverton Downtown** Table 70.20.05.4.A S1-S2: 50 to 90 percent by a
  street type FLATS does not hold. Below 50 the pod fails on any street;
  between, the street type decides and the lot is held out of GREEN.
* **Washington County** 392-8 / 392-9.5: 50 percent within the 20-foot
  maximum setback, on every frontage of a corner lot and one of a through
  lot.

And **King City** 16.114.060 C.4: each dwelling's entrance within eight feet
of the longest street-facing wall, facing the street -- held as
``orientation_constraint: axis_required``, as Gresham 7.0420(J)(1) is.

One pod fills at most its own width of a street, so on a wide lot the share
is a measured standard the pod fails: RED (Steph 2026-10-14) -- unless
enough pods to fill it could stand side by side along that street, which is
YELLOW with FRONTAGE-MORE-BUILDINGS (Steph 2026-10-21, rulings.yaml
2026-10-21-wide-lot-frontage-more-pods). Unmeasured is never GREEN.

Each share is measured on what the code measures it on (rulings.yaml
2026-10-21-frontage-share-measured-as-coded): every code here says site or
development, so both forms are measured on the original lot
(``building_frontage_basis: site``); a code that measured each lot would
hold the townhouse form out of GREEN.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from flats.designs.model import Plat
from flats.fit.frontage import building_runs
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score import relief, slack
from flats.score.flags import Colour
from flats.score.paper import drive_at_street
from flats.score.screen import (
    BUILDING_FRONTAGE,
    BUILDING_OTHER_SHARE,
    BUILDING_SHARE,
    CHECK_FIELD,
    DEFAULT_BUILDING_SEPARATION_FT,
    FRONTAGE_STREET,
    MORE_BUILDINGS,
    screen,
)
from flats.score.slack import Verdict
from flats.tests.test_frontage_caps import quoted
from flats.tests.test_round2_rulings import (
    DESIGN,
    LOT,
    F,
    R,
    S,
    _edges,
    check,
    facts,
    fit,
    rules,
    run,
)

pytestmark = pytest.mark.unit

BEAVERTON = "or/washington/beaverton"
GRESHAM = "or/multnomah/gresham"
WASHCO = "or/washington/_unincorporated"
KING_CITY = "or/washington/king-city"
BEAVERTON_605 = ("CM-HDR", "NS", "CS", "CC", "GC", "RC-E", "TC-MU", "TC-HDR", "SC-MU", "SC-HDR", "SC-S")
DOWNTOWN = ("RC-BC", "RC-OT", "RC-MU", "RC-DT")

#: A 60 percent share in a 16-foot band, Beaverton's 60.05 shape.
SHARE = {"building_frontage_min_pct": 60, "setback_front_max_ft": 16}


def codes(result) -> set[str]:
    return {f.code for f in result.flags}


# --- the measure ------------------------------------------------------------


def test_the_building_fills_the_feet_it_stands_in_front_of_within_the_band() -> None:
    interior = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, S), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0])
    near = box(4, 10, 60, 46)
    ((pct, net),) = building_runs(LOT, interior, near, 16.0)
    assert net == pytest.approx(80.0)
    assert pct == pytest.approx(100.0 * 56 / 80, abs=2.0)
    # Set back past the band, it fills nothing.
    far = box(4, 20, 60, 56)
    assert building_runs(LOT, interior, far, 16.0)[0][0] == pytest.approx(0.0)


def test_the_driveway_comes_off_the_frontage_where_the_code_takes_it() -> None:
    interior = _edges([(0, 0, 80, 0, F), (80, 0, 80, 120, S), (80, 120, 0, 120, R), (0, 120, 0, 0, S)], [0.0])
    near = box(4, 10, 60, 46)
    lane = box(62, 0, 76, 120)
    ((pct, net),) = building_runs(LOT, interior, near, 16.0, lane=lane)
    assert net == pytest.approx(66.0, abs=2.0)
    assert pct == pytest.approx(100.0 * 56 / 66, abs=2.0)


# --- the check --------------------------------------------------------------


def test_the_check_is_named_for_its_field() -> None:
    assert CHECK_FIELD[BUILDING_SHARE] == "building_frontage_min_pct"
    assert CHECK_FIELD[BUILDING_OTHER_SHARE] == "building_frontage_other_pct"


def test_a_frontage_one_pod_cannot_fill_and_two_cannot_stand_on_is_red() -> None:
    # 56 ft of pod over 110 ft of street is 51 percent, under 60; two pods
    # need 56 + 10 + 56 ft and a 2 ft wider drive than the gap: 124 ft.
    got = run(facts(street_lines_ft=(110.0,)), rules(**SHARE))
    assert check(got, BUILDING_SHARE).verdict is not Verdict.passes
    assert got.colour is Colour.red
    assert "FRONTAGE-MORE-BUILDINGS" not in codes(got)


def test_a_street_more_pods_could_fill_is_yellow_with_the_flag() -> None:
    # 200 ft: one pod is 28 percent; three side by side (168 ft built, two
    # 10 ft gaps) are 84 and stand in 188 ft. Steph 2026-10-21: yellow.
    got = run(facts(street_lines_ft=(200.0,)), rules(**SHARE))
    assert check(got, BUILDING_SHARE) is None
    assert BUILDING_SHARE in got.unchecked
    assert got.colour is Colour.yellow
    assert "FRONTAGE-MORE-BUILDINGS" in codes(got)
    # The yards and the zone's own separation count: with 10 ft side yards
    # and 30 ft between buildings two pods (56 + 30 + 56) need 162 ft of a
    # 140 ft street less its yards (120). RED.
    tight = rules(**SHARE, setback_side_ft=10, min_building_separation_ft=30)
    assert run(facts(street_lines_ft=(140.0,)), tight).colour is Colour.red
    # With the default gap two pods need 124 ft: 130 less its yards (110)
    # does not hold them; 150 (130) does.
    yards = rules(**SHARE, setback_side_ft=10)
    assert run(facts(street_lines_ft=(130.0,)), yards).colour is Colour.red
    assert run(facts(street_lines_ft=(150.0,)), yards).colour is Colour.yellow
    assert DEFAULT_BUILDING_SEPARATION_FT == 10.0
    assert MORE_BUILDINGS != BUILDING_FRONTAGE


def test_a_drawn_share_that_clears_is_green_and_unmeasured_is_not() -> None:
    passed = run(facts(street_lines_ft=(80.0,), building_frontage_pct=(70.0,)), rules(**SHARE))
    assert check(passed, BUILDING_SHARE).verdict is Verdict.passes
    assert passed.colour is Colour.green
    unmeasured = run(facts(street_lines_ft=(80.0,)), rules(**SHARE))
    assert check(unmeasured, BUILDING_SHARE) is None
    assert BUILDING_SHARE in unmeasured.unchecked
    assert unmeasured.colour is not Colour.green
    assert "MEASURE-BUILDING-FRONTAGE" in codes(unmeasured)
    # Drawn short where turning the pod would clear: held, not failed.
    short = run(facts(street_lines_ft=(80.0,), building_frontage_pct=(45.0,)), rules(**SHARE))
    assert short.colour is Colour.yellow
    assert "MEASURE-BUILDING-FRONTAGE" in codes(short)


def test_no_band_and_no_street_are_unmeasured() -> None:
    no_band = run(facts(street_lines_ft=(80.0,), building_frontage_pct=(70.0,)), rules(building_frontage_min_pct=50))
    assert BUILDING_SHARE in no_band.unchecked
    assert no_band.colour is not Colour.green
    no_street = run(facts(), rules(**SHARE))
    assert BUILDING_SHARE in no_street.unchecked
    assert no_street.colour is not Colour.green


def test_the_driveway_off_the_frontage_saves_a_lot_it_would_fail() -> None:
    lane = drive_at_street(DESIGN, rules(**SHARE))
    assert lane and lane > 0
    # Just wide enough that the pod's 56 ft misses 60 percent of the whole
    # street but clears it once the drive is taken off.
    line = 56 / 0.6 + lane / 2
    plain = run(facts(street_lines_ft=(line,)), rules(**SHARE))
    assert plain.colour is Colour.red
    less = run(facts(street_lines_ft=(line,)), rules(**SHARE, building_frontage_less_drive=True))
    assert less.colour is not Colour.red
    assert check(less, BUILDING_SHARE) is None


def test_a_plaza_the_plan_does_not_draw_saves_a_lot_from_red_never_to_green() -> None:
    # 56 ft over 110 ft is 51 percent; with a fifth of the frontage off as a
    # plaza (88 ft left) it is 64: the pod might meet it, so not RED.
    plain = run(facts(street_lines_ft=(110.0,)), rules(**SHARE))
    assert plain.colour is Colour.red
    plaza = {**SHARE, "building_frontage_plaza_pct": 20}
    saved = run(facts(street_lines_ft=(110.0,), building_frontage_pct=(51.0,)), rules(**plaza))
    assert saved.colour is Colour.yellow
    assert check(saved, BUILDING_SHARE) is None
    # Past what a plaza can take off and too short for a second pod, RED.
    assert run(facts(street_lines_ft=(120.0,)), rules(**plaza)).colour is Colour.red


def test_a_share_by_street_type_fails_below_the_least_and_holds_between() -> None:
    banded = {"building_frontage_min_pct": 90, "building_frontage_min_pct_least": 50, "setback_front_max_ft": 20}
    # 56 over 120 is 47 percent: under 50, whatever the street, and two
    # pods do not stand on it.
    assert run(facts(street_lines_ft=(120.0,)), rules(**banded)).colour is Colour.red
    # 130: two pods fill 86 percent of it, past even the 50; a second
    # building, not a miss.
    two = run(facts(street_lines_ft=(130.0,)), rules(**banded))
    assert two.colour is Colour.yellow
    assert "FRONTAGE-MORE-BUILDINGS" in codes(two)
    # 56 over 100 is 56 percent: a Major Street's 50 passes, a Local's 75 not.
    between = run(facts(street_lines_ft=(100.0,), building_frontage_pct=(56.0,)), rules(**banded))
    assert between.colour is Colour.yellow
    assert "MEASURE-FRONTAGE-STREET" in codes(between)
    assert FRONTAGE_STREET != BUILDING_FRONTAGE


def test_a_corner_lot_owes_the_other_street_and_a_through_lot_one() -> None:
    corner = {**SHARE, "building_frontage_other_pct": 35}
    # The width on the 80-ft street (70 percent) leaves the 36-ft depth on a
    # 120-ft one (30 percent); the depth on the 80 (45) misses 60 itself.
    # A second pod along the 120 (36 + 10 + 56 + 2 = 104 ft) cannot stand
    # inside 10 ft yards (100 ft): RED.
    got = run(facts(street_lines_ft=(80.0, 120.0), corner=True), rules(**corner, setback_side_ft=10))
    assert got.colour is Colour.red
    # On a 200-ft side street it can: a second building, YELLOW.
    more = run(facts(street_lines_ft=(80.0, 200.0), corner=True), rules(**corner))
    assert more.colour is Colour.yellow
    assert "FRONTAGE-MORE-BUILDINGS" in codes(more)
    # A through lot that owes one street: the near street alone decides.
    through = {**corner, "building_frontage_through_one": True}
    one = run(facts(street_lines_ft=(80.0, 200.0)), rules(**through))
    assert one.colour is not Colour.red
    assert one.colour is not Colour.green  # GREEN would need both drawn
    # A street-type share states no floor on the other street: never RED on it.
    banded = {**SHARE, "building_frontage_min_pct": 90, "building_frontage_min_pct_least": 50,
              "building_frontage_other_pct": 70}
    held = run(facts(street_lines_ft=(80.0, 200.0), corner=True), rules(**banded))
    assert held.colour is not Colour.red


def test_a_share_measured_per_lot_holds_the_townhouse_form_and_not_the_plex() -> None:
    # Measured on each lot, the townhouse form's end lots carry the long
    # street line: nothing measures that, so it is held, never passed on the
    # original lot's share. The one-lot form is measured as before.
    split = DESIGN.model_copy(update={"plat": Plat.unit_lots})
    per_lot = rules(**SHARE, building_frontage_basis="lot")
    lot = facts(street_lines_ft=(80.0,), building_frontage_pct=(70.0,))

    def under(design):
        return screen(
            per_lot, lot, design, fit(),
            policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}), relief=relief.load_policy(),
        )

    town = under(split)
    assert BUILDING_SHARE in town.unchecked
    assert "MEASURE-BUILDING-FRONTAGE" in codes(town)
    assert town.colour is not Colour.green
    plex = under(DESIGN)
    assert check(plex, BUILDING_SHARE).verdict is Verdict.passes
    # `site` is today's reading for both forms.
    site = rules(**SHARE, building_frontage_basis="site")
    got = screen(
        site, lot, split, fit(),
        policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}), relief=relief.load_policy(),
    )
    assert check(got, BUILDING_SHARE).verdict is Verdict.passes


# --- the corpus -------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


@pytest.mark.parametrize("zone", BEAVERTON_605)
def test_beavertons_mixed_use_zones_ask_sixty_and_thirty_five(corpus: RuleSet, zone: str) -> None:
    got = corpus.resolve(BEAVERTON, zone).values
    assert got["building_frontage_min_pct"].value == 60
    assert got["building_frontage_other_pct"].value == 35
    assert got["building_frontage_less_drive"].value is True
    assert got["building_frontage_plaza_pct"].value == 20
    assert "Plazas up to 20 percent" in quoted(got["building_frontage_plaza_pct"].prov.quote)
    assert got["setback_front_max_ft"].value is not None
    text = quoted(got["building_frontage_min_pct"].prov.quote)
    assert "60 percent" in text and "Primary Frontage" in text


def test_cm_cs_asks_fifty_with_no_band(corpus: RuleSet) -> None:
    got = corpus.resolve(BEAVERTON, "CM-CS").values
    assert got["building_frontage_min_pct"].value == 50
    assert got["building_frontage_plaza_pct"].value == 20
    assert "CM-CS" in quoted(got["building_frontage_min_pct"].prov.quote)


@pytest.mark.parametrize("zone", DOWNTOWN)
def test_downtown_asks_fifty_to_ninety_by_street_type(corpus: RuleSet, zone: str) -> None:
    got = corpus.resolve(BEAVERTON, zone).values
    assert got["building_frontage_min_pct"].value == 90
    assert got["building_frontage_min_pct_least"].value == 50
    assert got["building_frontage_other_pct"].value == 70
    assert "building_frontage_other_pct_least" not in got
    assert "building_frontage_plaza_pct" not in got
    assert got["building_frontage_less_drive"].value is True
    text = quoted(got["building_frontage_min_pct"].prov.quote)
    assert "90 percent" in text and "50 percent" in text


@pytest.mark.parametrize("zone", ("NMU", "CCMU"))
def test_washington_county_asks_half_of_every_corner_frontage(corpus: RuleSet, zone: str) -> None:
    got = corpus.resolve(WASHCO, zone).values
    assert got["building_frontage_min_pct"].value == 50
    assert got["building_frontage_other_pct"].value == 50
    assert got["building_frontage_through_one"].value is True
    assert got["setback_front_max_ft"].value == 20
    assert "building_frontage_less_drive" not in got
    assert "50%" in quoted(got["building_frontage_min_pct"].prov.quote)


@pytest.mark.parametrize(
    ("layer", "zone"),
    [(BEAVERTON, z) for z in (*BEAVERTON_605, "CM-CS", *DOWNTOWN)]
    + [(WASHCO, "NMU"), (WASHCO, "CCMU")]
    + [(GRESHAM, z) for z in ("MDR-12", "MDR-24", "OFR", "CMF", "CMU", "SC", "SC-RJ", "DRL-1", "DRL-2")],
)
def test_every_share_is_measured_on_the_site(corpus: RuleSet, layer: str, zone: str) -> None:
    # Steph 2026-10-21, measured as coded: every code here says site (or
    # development, or parcel) -- the original lot -- and quotes the
    # definition that makes the townhouse form's four lots one site.
    got = corpus.resolve(layer, zone).values["building_frontage_basis"]
    assert got.value == "site"
    text = quoted(got.prov.quote)
    assert "Site" in text or "Lot" in text


@pytest.mark.parametrize("zone", ("MDR-12", "MDR-24", "OFR", "CMF", "CMU"))
def test_gresham_measures_the_plex_share_and_only_rockwood_asks_it_of_townhouses(
    corpus: RuleSet, zone: str
) -> None:
    plex = corpus.resolve(GRESHAM, zone)
    assert plex.get("building_frontage_min_pct") == 50
    assert plex.get("building_frontage_less_drive") is False
    assert plex.get("orientation_constraint") == "axis_required"
    assert "plexes" in quoted(plex.values["building_frontage_min_pct"].prov.quote)
    # 7.0420(J)(1) names plexes; 7.0431, the townhouse chapter, no share.
    town = corpus.resolve(GRESHAM, zone, ("unit_lots",))
    assert town.get("building_frontage_min_pct") is None
    assert "building_frontage_min_pct" in town.exempted
    assert town.get("orientation_constraint") == "entrance_only"
    # Inside Rockwood 7.0512(A)(2) S2 names townhouses, and takes the drive off.
    rock = corpus.resolve(GRESHAM, zone, ("unit_lots", "rockwood_design_district"))
    assert rock.get("building_frontage_min_pct") == 50
    assert rock.get("building_frontage_less_drive") is True
    assert rock.get("orientation_constraint") == "axis_required"
    assert "townhouse" in quoted(rock.values["building_frontage_min_pct"].prov.quote)


@pytest.mark.parametrize("zone", ("SC", "SC-RJ"))
def test_gresham_station_centers_keep_the_share_on_both_forms(corpus: RuleSet, zone: str) -> None:
    # Not in 7.0431's list: the townhouse form keeps the share everywhere.
    town = corpus.resolve(GRESHAM, zone, ("unit_lots",))
    assert town.get("building_frontage_min_pct") == 50
    assert town.get("orientation_constraint") == "axis_required"


@pytest.mark.parametrize("zone", ("DRL-1", "DRL-2"))
def test_gresham_downtown_townhouses_owe_no_share(corpus: RuleSet, zone: str) -> None:
    assert corpus.resolve(GRESHAM, zone).get("building_frontage_min_pct") == 50
    town = corpus.resolve(GRESHAM, zone, ("unit_lots",))
    assert town.get("building_frontage_min_pct") is None
    assert town.get("orientation_constraint") == "entrance_only"


@pytest.mark.parametrize("zone", ("KTTC", "KTBB", "KTC", "KTRC"))
def test_king_city_turns_the_entrances_to_the_street(corpus: RuleSet, zone: str) -> None:
    got = corpus.resolve(KING_CITY, zone).values
    assert got["orientation_constraint"].value == "axis_required"
    assert "eight feet" in quoted(got["orientation_constraint"].prov.quote).lower()


# --- the bridge -------------------------------------------------------------


def _beaverton_lot(corpus: RuleSet, width: float):
    import json

    import shapely

    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.tests.test_fire import X0, Y0, bridge_row

    depth = 120.0
    edges = [
        [X0, Y0, X0 + width, Y0, "F"],
        [X0 + width, Y0, X0 + width, Y0 + depth, "S"],
        [X0 + width, Y0 + depth, X0, Y0 + depth, "R"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    row = bridge_row(
        jurisdiction="beaverton",
        zone="NS",
        edges_json=json.dumps(edges),
        frontage_ft=width,
        lot_width_ft=width,
        area_sqft=width * depth,
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + width - 5, Y0 + depth - 5)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + width, Y0 + depth)),
    )
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(
        lot, [DESIGN], rules=corpus, policy=slack.load_policy(), relief=relief.load_policy(), step_deg=30.0
    )
    return s


def test_the_bridge_measures_the_drawn_share_and_holds_a_wide_lot(corpus: RuleSet) -> None:
    narrow = _beaverton_lot(corpus, 80.0)
    assert narrow.facts.street_lines_ft == pytest.approx((80.0,))
    drawn = narrow.facts.building_frontage_pct
    assert drawn is not None and drawn[0] >= 60.0
    assert check(narrow.screening, BUILDING_SHARE).verdict is Verdict.passes
    # 160 ft: one pod cannot fill 60 percent of it, two side by side can.
    wide = _beaverton_lot(corpus, 160.0)
    assert check(wide.screening, BUILDING_SHARE) is None
    assert "FRONTAGE-MORE-BUILDINGS" in codes(wide.screening)
    assert wide.screening.colour is not Colour.green
