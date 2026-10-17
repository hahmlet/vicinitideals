"""Steph's ruling of 2026-10-15: "'Townhomes' will have separate lots. If we
build a 4 unit apartment building, they would not."

The pod is screened in either form, whichever the zone allows. As an
apartment building it sits on the one lot, as before. As townhouses the lot
is divided into four unit lots: a use the code grants only to attached
single-unit dwellings / townhouses on their own lots is then no blocker, but
each unit lot has to meet the zone's townhouse standards -- four of them side
by side along the street. The lot takes the better colour, and where only
the townhouse form clears it, it carries LAND-DIVISION ("needs a land
division into 4 unit lots"), severity 2, below the yellow line.

And, Steph the same day: "I need to know which of the two works on every lot
(or if both/neither)." Both forms are screened on every lot and recorded
beside the colour (``Screened.forms``): each form's colour, what holds a form
that is not GREEN, and which works -- ``both``, ``apartment``, ``townhomes``
or ``neither``.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely.geometry import box  # noqa: E402

from flats.designs.model import Plat  # noqa: E402
from flats.ingest import quadfit  # noqa: E402
from flats.ingest.quadfit import (  # noqa: E402
    LAND_DIVISION,
    _screen_plat,
    lot_from_row,
    screen_lot,
    townhouse,
)
from flats.rules.loader import load_rules  # noqa: E402
from flats.rules.net_area import MEASURED  # noqa: E402
from flats.rules.resolver import RuleSet  # noqa: E402
from flats.score import relief, slack  # noqa: E402
from flats.score.flags import Colour, load_registry  # noqa: E402
from flats.score.paper import lot_standard, townhouse_only  # noqa: E402
from flats.score.screen import LotFacts  # noqa: E402
from flats.score.slack import Verdict  # noqa: E402
from flats.tests.test_fire import X0, Y0, bridge_row, pod  # noqa: E402
from flats.tests.test_round2_rulings import fit, run  # noqa: E402
from flats.tests.test_round2_rulings import rules as _rules  # noqa: E402

pytestmark = pytest.mark.unit

#: Every overlay the net-area denominator subtracts, measured and empty, so a
#: density standard on net acres is settled rather than flagged unmeasured.
NO_OVERLAYS = {c: 0.0 for cols in MEASURED.values() for c in cols}


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def policies():
    return slack.load_policy(), relief.load_policy()


def row(jurisdiction: str, zone: str, *, width: float = 80.0, depth: float = 120.0) -> dict:
    """A plain interior lot, ``width`` along the street and ``depth`` back,
    inside the UGB with every net-area overlay measured empty."""
    edges = [
        [X0, Y0, X0 + width, Y0, "F"],
        [X0 + width, Y0, X0 + width, Y0 + depth, "S"],
        [X0 + width, Y0 + depth, X0, Y0 + depth, "R"],
        [X0, Y0 + depth, X0, Y0, "S"],
    ]
    return bridge_row(
        jurisdiction=jurisdiction,
        zone=zone,
        inside_ugb=True,
        area_sqft=width * depth,
        frontage_ft=width,
        lot_width_ft=width,
        lot_depth_ft=depth,
        edges_json=json.dumps(edges),
        wkb=shapely.to_wkb(box(X0 + 5, Y0 + 10, X0 + width - 5, Y0 + depth - 5)),
        lot_wkb=shapely.to_wkb(box(X0, Y0, X0 + width, Y0 + depth)),
        **NO_OVERLAYS,
    )


def wide():
    """The 80 x 25 pod: four homes 20 ft wide."""
    from flats.designs.model import load_catalog

    return load_catalog().latest("pod80x25")


def both(corpus, policies, r: dict, design=None):
    """The apartment form alone, and what the bridge answers."""
    design = pod() if design is None else design
    lot = lot_from_row(r, corpus.layers)
    (one,) = _screen_plat(
        lot, [design], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    (got,) = screen_lot(
        lot, [design], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    return one, got


def land_division(s) -> list:
    return [f for f in s.signed.flags if f.code == LAND_DIVISION]


# --- the ruling, on the lots that asked it ------------------------------------


@pytest.mark.parametrize("zone", ["VMU", "VA"])
def test_a_fairview_village_lot_passes_as_townhouses_with_the_flag(corpus, policies, zone) -> None:
    """FMC 19.135.010 row c (VMU, attached single-unit dwellings) and
    19.125.030(A) (VA, townhouses): the four homes only on their own lots. As
    one apartment building the lot is red on the use table; as four unit lots
    it clears, GREEN, and says it needs the land division."""
    one, got = both(corpus, policies, row("fairview", zone))

    assert one.signed.colour is Colour.red
    assert any(b.check == "use" for b in one.signed.binds)

    assert got.design.plat is Plat.unit_lots
    assert got.design.key == pod().key  # the pod's own row, not a new design
    assert got.signed.colour is Colour.green
    (flag,) = land_division(got)
    assert "land division into 4 unit lots" in flag.source

    forms = got.forms
    assert forms["works_as"] == "townhomes"
    assert forms["kept"] == "townhomes"
    assert forms["townhomes"] == {"colour": "green"}
    assert forms["apartment"]["colour"] == "red"
    assert [b["check"] for b in forms["apartment"]["binds"]] == ["use"]


def test_a_village_townhouse_lot_passes_and_a_narrow_one_stays_red(corpus, policies) -> None:
    """FMC 19.120.020(B): townhouses are permitted outright in VTH and a
    quadplex is not listed. 19.120.040(A)-(B) ask 2,000 sq ft and 20 ft of
    width of every lot. The 80 ft pod's homes are 20 ft wide, so its middle
    lots meet the width and, 120 ft deep, the area: a 100 x 120 lot clears
    with the flag. A 60 ft lot is red on the width."""
    one, got = both(corpus, policies, row("fairview", "VTH", width=100.0), design=wide())
    assert one.signed.colour is Colour.red
    assert got.design.plat is Plat.unit_lots
    assert got.signed.colour is Colour.green
    assert land_division(got)

    one, got = both(corpus, policies, row("fairview", "VTH", width=60.0), design=wide())
    assert got.signed.colour is Colour.red
    assert got.design.plat is Plat.one_lot
    assert not land_division(got)
    # Neither form works, and the record says why each fails: the use table
    # for the apartment building, the unit-lot width for the townhouses.
    assert got.forms["works_as"] == "neither"
    townhomes = {b["check"] for b in got.forms["townhomes"]["binds"]}
    assert "min_lot_width_ft" in townhomes
    assert "use" not in townhomes
    assert "use" in {b["check"] for b in got.forms["apartment"]["binds"]}


def test_a_home_lot_is_one_home_wide_however_big_the_parcel(corpus, policies) -> None:
    """The bound of b1bd20ff: the 56 ft pod GREEN as townhouses on big lots in
    zones whose townhouse lots must be wider than its 14 ft homes. A middle
    home lot runs between two party walls; a bigger parcel does not widen it.
    Fairview VTH's 20 ft (19.120.040(B)) refuses it on a 200 x 200 lot, and
    its 2,000 sq ft area too (14 ft x 120 ft is 1,680)."""
    _, got = both(corpus, policies, row("fairview", "VTH", width=200.0, depth=120.0))
    assert got.signed.colour is Colour.red
    assert got.forms["works_as"] == "neither"
    binds = {b["check"]: b for b in got.forms["townhomes"]["binds"]}
    assert binds["home_lot_width_ft"]["observed"] == 14.0
    assert binds["home_lot_width_ft"]["threshold"] == 20.0
    assert binds["home_lot_area_sqft"]["observed"] == 14.0 * 120.0


def test_the_flag_sits_below_the_yellow_line_and_says_why() -> None:
    entry = load_registry()[LAND_DIVISION]
    assert entry.severity < 3
    assert entry.description.startswith("Needs a land division into 4 unit lots")
    assert "TOWNHOUSE_PLAT" in entry.raised_from


def test_a_lot_that_misses_a_unit_lot_standard_stays_red(corpus, policies) -> None:
    """Milwaukie GMU takes the building only as rowhouses (Table 19.303.2), and
    Table 19.303.3 asks 25 ft of street frontage of every lot (A.2): four unit
    lots need 100 ft, and this deep lot has 80. Red either way, no flag -- the
    apartment answer stands."""
    one, got = both(corpus, policies, row("milwaukie", "GMU", depth=220.0))

    assert one.signed.colour is Colour.red
    assert got.signed.colour is Colour.red
    assert got.design.plat is Plat.one_lot
    assert not land_division(got)
    assert got.forms["works_as"] == "neither"
    assert got.forms["townhomes"]["colour"] == "red"

    lot = lot_from_row(row("milwaukie", "GMU", depth=220.0), corpus.layers)
    (twin,) = _screen_plat(
        lot, [townhouse(pod())], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    frontage = next(c for c in twin.screening.checks if c.check == "min_frontage_ft")
    assert (frontage.threshold, frontage.verdict) == (100.0, Verdict.fails)
    assert not any(b.check == "use" for b in twin.signed.binds)


def test_a_zone_that_says_nothing_of_unit_lots_is_not_asked_twice(
    corpus, policies, monkeypatch
) -> None:
    """Fairview VO refuses four homes in every form (19.130) and states no
    townhouse row: the twin would be the same screen twice, so it is not run,
    and the apartment answer is the answer -- for both forms, which the
    record says."""
    calls = []
    real = quadfit._screen_plat

    def counted(lot, designs, **kw):
        calls.append(tuple(d.plat for d in designs))
        return real(lot, designs, **kw)

    monkeypatch.setattr(quadfit, "_screen_plat", counted)
    lot = lot_from_row(row("fairview", "VO"), corpus.layers)
    (got,) = screen_lot(
        lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )

    assert calls == [(Plat.one_lot,)]
    assert got.signed.colour is Colour.red
    assert got.design.plat is Plat.one_lot
    assert not land_division(got)
    assert got.forms["works_as"] == "neither"
    assert got.forms["townhomes"]["screened"] is False
    assert got.forms["townhomes"]["colour"] == "red"


def test_a_lot_green_as_an_apartment_building_carries_no_flag(
    corpus, policies, monkeypatch
) -> None:
    """Portland RM1 takes the pod on one lot: GREEN, no land division asked.
    The townhouse form is screened all the same -- the zone states its own
    numbers for unit lots -- and works too, so the lot works both ways and
    keeps the apartment answer."""
    calls = []
    real = quadfit._screen_plat

    def counted(lot, designs, **kw):
        calls.append(tuple(d.plat for d in designs))
        return real(lot, designs, **kw)

    monkeypatch.setattr(quadfit, "_screen_plat", counted)
    lot = lot_from_row(row("portland", "RM1"), corpus.layers)
    (got,) = screen_lot(
        lot, [pod()], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )

    assert got.signed.colour is Colour.green
    assert got.design.plat is Plat.one_lot
    assert not land_division(got)
    assert calls == [(Plat.one_lot,), (Plat.unit_lots,)]
    assert got.forms == {
        "works_as": "both",
        "kept": "apartment",
        "apartment": {"colour": "green"},
        "townhomes": {"colour": "green"},
    }


def test_the_record_rides_into_the_bridge_row(corpus, policies) -> None:
    """``row_for`` writes the record as JSON, the loader reads it into
    ``lot_results.checks["forms"]`` -- no new column."""
    from flats.ingest.assign import ROW_COLUMNS
    from scripts.flats_load_bridge import result_checks

    _, got = both(corpus, policies, row("fairview", "VMU"))
    written = quadfit.row_for(got)
    assert "forms" in ROW_COLUMNS  # a synthetic row carries the column too
    assert json.loads(written["forms"])["works_as"] == "townhomes"
    assert result_checks(written)["forms"]["works_as"] == "townhomes"


@pytest.mark.parametrize(
    ("apartment", "townhomes", "word"),
    [(True, True, "both"), (True, False, "apartment"), (False, True, "townhomes"), (False, False, "neither")],
)
def test_works_as_names_the_forms_that_come_out_green(apartment, townhomes, word) -> None:
    assert quadfit.works_as(apartment, townhomes) == word


# --- reading a unit lot -----------------------------------------------------------


def rules(townhouses_only: bool = False, **per_lot):
    """The round-2 test zone with ``per_lot`` standards stated for unit lots
    (``when: [unit_lots]``) and, with ``townhouses_only``, the use opened only
    on unit lots."""
    got = _rules(**per_lot)
    for name in per_lot:
        got.values[name] = replace(got.values[name], when=("unit_lots",))
    if townhouses_only:
        got.values["quadplex_allowed"] = replace(got.values["quadplex_allowed"], when=("unit_lots",))
    return got


SPLIT = townhouse(pod())


def screened(rule_set, lot: LotFacts, design=SPLIT):
    from flats.score.screen import screen

    return screen(rule_set, lot, design, fit(), policy=slack.SlackPolicy(tolerance={"fit_ft": 0.5}))


def check(result, name):
    return next(c for c in result.checks if c.check == name)


def test_a_lot_narrower_than_four_unit_lots_is_red() -> None:
    """A 25 ft townhouse lot width is 100 ft of parent for four of them; an
    80 ft lot misses it however the pod sits, and the miss is RED."""
    lot = LotFacts(lot_sqft=16_000, frontage_ft=80, lot_width_ft=80, lot_depth_ft=200)

    got = screened(rules(min_lot_width_ft=25), lot)

    width = check(got, "min_lot_width_ft")
    assert (width.threshold, width.verdict) == (100.0, Verdict.fails)
    assert got.colour is Colour.red
    # The same lot as one apartment building reads the 25 as written.
    assert check(screened(rules(min_lot_width_ft=25), lot, pod()), "min_lot_width_ft").threshold == 25


def test_frontage_and_area_are_four_lots_side_by_side_and_depth_is_one() -> None:
    lot = LotFacts(lot_sqft=16_000, frontage_ft=80, lot_width_ft=80, lot_depth_ft=200)

    got = screened(
        rules(min_frontage_ft=20, min_lot_sqft=1_500, min_lot_depth_ft=90), lot
    )

    assert check(got, "min_frontage_ft").threshold == 80.0
    assert check(got, "min_lot_area_sqft").threshold == 6_000.0
    assert check(got, "min_lot_depth_ft").threshold == 90.0


def test_a_depth_ratio_is_four_times_as_tight_on_a_quarter_of_the_width() -> None:
    got = rules(max_lot_depth_ratio=3)
    assert lot_standard(got, "max_lot_depth_ratio", per_unit=True, lots=4) == (0.75, True)


def test_a_townhouse_only_zone_reads_its_own_lot_standard_per_unit_lot() -> None:
    """Where the zone takes the pod only as townhouses, ORS 92.031's
    parent-lot reading is not the path: a lot standard the zone prints
    without a townhouse row is every unit lot's (Milwaukie GMU's 25 ft
    frontage). Elsewhere the statute's reading stands."""
    plain = _rules(land_division_parent_standards=True, min_frontage_ft=25)
    assert not townhouse_only(plain)
    assert lot_standard(plain, "min_frontage_ft", per_unit=True, lots=4) == (25.0, True)

    only = rules(townhouses_only=True)
    only.values["min_frontage_ft"] = replace(plain.values["min_frontage_ft"])
    only.values["land_division_parent_standards"] = plain.values["land_division_parent_standards"]
    assert townhouse_only(only)
    assert lot_standard(only, "min_frontage_ft", per_unit=True, lots=4) == (100.0, True)


def test_a_relief_path_that_names_unit_lots_is_townhouse_only() -> None:
    got = _rules(quadplex_allowed=False)
    got.values["quadplex_allowed"] = replace(
        got.values["quadplex_allowed"],
        relief=((("unit_lots", "conditional_use"), True, "FMC 19.135.010 row c"),),
    )
    assert townhouse_only(got)


def test_the_corpus_doors_are_townhouse_only(corpus) -> None:
    """The zones whose use table opens to the pod only on unit lots."""
    for layer, zone in [
        ("or/multnomah/fairview", "VMU"),
        ("or/multnomah/fairview", "VA"),
        ("or/clackamas/tualatin", "RH"),
        ("or/clackamas/milwaukie", "GMU"),
        # Opened by the 2026-10-15 ruling itself: townhouses permitted
        # outright, a quadplex not.
        ("or/multnomah/fairview", "VTH"),
        ("or/clackamas/_unincorporated", "R2.5"),
        ("or/multnomah/troutdale", "HDR"),
        ("or/multnomah/troutdale", "MU-1"),
    ]:
        got = corpus.resolve(layer, zone, ("multi_story", "unit_lots"))
        assert townhouse_only(got), (layer, zone)
    assert not townhouse_only(corpus.resolve("or/multnomah/portland", "RM1", ("multi_story", "unit_lots")))


# --- the round-1 bound's three causes (b1bd20ff) --------------------------------


def test_the_townhouse_form_faces_the_street_where_its_lots_are_townhouse_lots(corpus) -> None:
    """Every townhouse lot fronts a street, so the row of homes keeps its
    long side to it: turned end-on, three of the four homes would sit on
    lots with no street line. That holds where the zone states its own
    townhouse-lot standards (Tualatin RMH) or takes the building only as
    townhouses (Fairview VMU) -- and not on the apartment form, nor where
    the four lots would be a middle housing land division's, which reach
    the street by easement (ORS 92.031(3)(c)(B)): Wilsonville PDR-4 states
    nothing of townhouse lots beyond a density."""
    from flats.score.paper import faces_the_street, townhouse_lots

    for layer, zone in [
        ("or/clackamas/tualatin", "RMH"),
        ("or/multnomah/fairview", "VMU"),
        ("or/multnomah/troutdale", "LDR-1"),
        ("or/clackamas/oregon-city", "R-10"),
    ]:
        got = corpus.resolve(layer, zone, ("multi_story", "unit_lots"))
        assert townhouse_lots(got), (layer, zone)
        assert faces_the_street(got, SPLIT), (layer, zone)
        assert not faces_the_street(corpus.resolve(layer, zone, ("multi_story",)), pod())
    pdr = corpus.resolve("or/clackamas/wilsonville", "PDR4", ("multi_story", "unit_lots"))
    assert not townhouse_lots(pdr)
    assert not faces_the_street(pdr, SPLIT)


def test_a_turned_row_of_townhouses_is_not_screened(corpus, policies) -> None:
    """The bound found Tualatin RMH lots GREEN as townhouses only with the
    56 ft pod end-on. On a 45 x 200 lot it fits only that way, so as
    townhouses it does not fit at all: the twin is searched at the street's
    bearing alone."""
    lot = lot_from_row(row("tualatin", "RMH", width=45.0, depth=200.0), corpus.layers)
    (twin,) = _screen_plat(
        lot, [SPLIT], rules=corpus, policy=policies[0], relief=policies[1], step_deg=30.0
    )
    assert twin.signed.colour is Colour.red
    assert any(b.check == "fit_ft" for b in twin.signed.binds)
    assert twin.fit.orientation is None or twin.fit.orientation.value == "width_facing"


def test_the_end_lots_carry_the_side_yards() -> None:
    """Four home lots abreast: two middle lots one home wide, two end lots a
    home and its side yard each, or the standard where that is wider. With a
    20 ft townhouse-lot width and a 5 ft side yard, the 80 ft pod's 20 ft
    homes ask 2 x 20 + 2 x 25 = 90 ft of the parcel, not 4 x 20 = 80."""
    from flats.score.screen import _row_of_home_lots

    got = rules(min_lot_width_ft=20)
    got.values["setback_side_ft"] = _rules(setback_side_ft=5).values["setback_side_ft"]
    parent, _ = lot_standard(got, "min_lot_width_ft", per_unit=True, lots=4)
    assert parent == 80
    assert _row_of_home_lots(got, SPLIT, "min_lot_width_ft", parent) == 80  # never under 4 x 20
    assert _row_of_home_lots(got, townhouse(wide()), "min_lot_width_ft", parent) == 90
    # The apartment form's lot standards are untouched.
    assert _row_of_home_lots(got, pod(), "min_lot_width_ft", 20.0) == 20.0


def test_a_whole_project_figure_is_divided_back_to_one_home_lot() -> None:
    """Gladstone's "1,500 sf" townhouse average arrives multiplied out to the
    building (``whole_project``): one home lot holds a quarter of it."""
    from flats.score.paper import home_lot_standard

    got = rules(min_lot_sqft=6000)
    got.values["min_lot_sqft"] = replace(got.values["min_lot_sqft"], whole_project=True)
    assert home_lot_standard(got, "min_lot_sqft", lots=4) == 1500
    assert lot_standard(got, "min_lot_sqft", per_unit=True, lots=4) == (6000.0, True)


def test_a_parent_lot_reading_asks_nothing_of_one_home_lot() -> None:
    """ORS 92.031(2)(b): a middle housing land division's children inherit no
    standards, so nothing is asked of one of them."""
    from flats.score.paper import home_lot_standard

    plain = _rules(land_division_parent_standards=True, min_frontage_ft=25)
    assert home_lot_standard(plain, "min_frontage_ft", lots=4) is None
    lot = LotFacts(lot_sqft=16_000, frontage_ft=80, lot_width_ft=80, lot_depth_ft=200)
    assert not any(c.check.startswith("home_lot_") for c in screened(plain, lot).checks)


def test_troutdale_townhouses_get_four_times_the_detached_density(corpus, policies) -> None:
    """TDC 3.140.B.3.a: in LDR-1 and LDR-2 "townhouse projects are allowed four
    (4) times the allowed density for detached single-family dwellings" --
    one house per 10,000 sq ft in LDR-1 (3.130.A), so four townhouses need
    10,000 sq ft of net area. B.3.b gives MDR three times its 5,000. The pod
    on one lot stays exempt (B.4)."""
    for zone, rate in (("LDR-1", 17.424), ("LDR-2", 24.892), ("MDR", 26.136)):
        split = corpus.resolve("or/multnomah/troutdale", zone, ("multi_story", "unit_lots"))
        whole = corpus.resolve("or/multnomah/troutdale", zone, ("multi_story",))
        assert split.get("max_density_du_per_acre") == rate, zone
        assert whole.get("max_density_du_per_acre") is None, zone

    lot = lot_from_row(row("troutdale", "LDR-1", width=100.0, depth=88.0), corpus.layers)
    (twin,) = _screen_plat(
        lot, [townhouse(wide())], rules=corpus, policy=policies[0], relief=policies[1],
        step_deg=30.0,
    )
    density = next(c for c in twin.screening.checks if c.check == "density_du_per_acre")
    assert density.verdict is Verdict.fails


def test_wilsonville_townhouses_are_held_to_four_times_table_1_or_25(corpus) -> None:
    """WC 4.124(.05) Table 1 note c: "the less of: (1) four times the maximum
    net density listed in Table 1; or (2) net density of 25 units per acre".
    The R zone's row turns on a plan map nothing reads, so its lowest row's
    is carried."""
    want = {"R": 12.0, "PDR1": 4.0, "PDR2": 12.0, "PDR3": 20.0, "PDR4": 25, "PDR5": 25, "PDR6": 25}
    for zone, rate in want.items():
        got = corpus.resolve("or/clackamas/wilsonville", zone, ("multi_story", "unit_lots"))
        assert got.get("max_density_du_per_acre") == rate, zone
        whole = corpus.resolve("or/clackamas/wilsonville", zone, ("multi_story",))
        assert whole.get("max_density_du_per_acre") is None, zone


def test_oregon_city_townhouse_lots_are_20_ft_wide(corpus) -> None:
    """OCMC Table 17.08.040, "Except townhouse 20 feet": wider than the 56 ft
    pod's 14 ft homes, as wide as the 80 ft pod's."""
    from flats.score.paper import home_lot_standard

    assert pod().unit_width_ft == 14 and wide().unit_width_ft == 20
    for zone in ("R-10", "R-8", "R-6"):
        got = corpus.resolve("or/clackamas/oregon-city", zone, ("multi_story", "unit_lots"))
        assert home_lot_standard(got, "min_lot_width_ft", lots=4) == 20, zone


def test_washington_county_townhouse_review_is_the_conditions_tier(corpus) -> None:
    """CDC 375-4.2: the TO townhouse row is Type II, "Approval may be further
    conditioned by the Review Authority pursuant to Section 207-5" -- the
    yellow tier of 2026-10-14, held by ORS 197A.400 to its clear standards
    inside a UGB (CLEAR-OBJECTIVE)."""
    for zone in ("TO:BUS", "TO:R24-40", "TO:R40-80"):
        got = corpus.resolve("or/washington/_unincorporated", zone, ("multi_story", "unit_lots"))
        assert got.get("review_discretion") == "conditions", zone
