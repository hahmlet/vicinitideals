"""Hillsboro 12.50.110 D.4 line by line: no lot frontage on a stub street end.

D.4 (or/washington/hillsboro/12.50/12.50.110.txt#L35): "Property abutting
the end of a public or private street not ending in a cul-de-sac ... shall
not be considered as having lot frontage." 7ea92302 held every lot near a
street end; :mod:`flats.geom.stub_end` reads which street LINE abuts the
end, so a lot that also fronts a through street keeps that frontage, a lot
whose only street line is an end has none, a cul-de-sac lot is untouched,
and a lot whose ends were not read stays held (test_street_end.py).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import shapely
from shapely.geometry import LineString, box

from flats.geom.stub_end import (
    ABUT_FT,
    STREET_END_FRONTAGE_FACT,
    decode_rays,
    observed_street_end_frontage,
    rays_near,
    street_lines_off_end_ft,
    stub_end_rays,
)
from flats.score.slack import Verdict
from flats.tests.test_quadfit_bridge import X0, Y0

HILLSBORO = "or/washington/hillsboro"


def edge(x1: float, y1: float, x2: float, y2: float) -> SimpleNamespace:
    return SimpleNamespace(x1=x1, y1=y1, x2=x2, y2=y2, length_ft=((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)


def ring_of(x0: float, y0: float, x1: float, y1: float) -> list[SimpleNamespace]:
    """South, east, north, west."""
    return [edge(x0, y0, x1, y0), edge(x1, y0, x1, y1), edge(x1, y1, x0, y1), edge(x0, y1, x0, y0)]


# --- the geometry


def test_a_stub_end_carries_the_way_its_street_runs() -> None:
    main, main2, stub = LineString([(0, 0), (500, 0)]), LineString([(500, 0), (1000, 0)]), LineString([(500, 0), (500, 300)])
    rays = stub_end_rays([main, main2, stub], [1300, 1300, 1300], [False, False, False])
    assert (500.0, 300.0, 0.0, 1.0, True) in rays
    assert all((x, y) != (500.0, 0.0) for x, y, *_ in rays)
    # A public street running on as a private road ends only for the public
    # network: an end, but not a sure one.
    private = LineString([(500, 300), (500, 450)])
    rays = stub_end_rays([main, main2, stub, private], [1300, 1300, 1300, 1700], [False] * 4)
    assert (500.0, 300.0, 0.0, 1.0, False) in rays


def test_the_line_across_the_end_abuts_it_and_the_street_side_does_not() -> None:
    ray = (500.0, 300.0, 0.0, 1.0, True)
    # The lot the stub runs into: its south line is the end.
    head = ring_of(450, 310, 550, 410)
    assert street_lines_off_end_ft(head, [[head[0]]], [ray]) == ((0.0, 0.0),)
    # The lot beside the stub: its west line runs along the street.
    side = ring_of(530, 200, 630, 300)
    assert street_lines_off_end_ft(side, [[side[3]]], [ray]) == ((100.0, 100.0),)
    # A through lot: the far street is kept, the end line is not.
    through = ring_of(450, 310, 550, 410)
    got = street_lines_off_end_ft(through, [[through[0]], [through[2]]], [ray])
    assert got == ((0.0, 0.0), (100.0, 100.0))


def test_a_line_that_may_be_the_end_leaves_only_the_strict_reading() -> None:
    head = ring_of(450, 310, 550, 410)
    # Not a sure end (the street may run on privately).
    assert street_lines_off_end_ft(head, [[head[0]]], [(500.0, 300.0, 0.0, 1.0, False)]) == ((0.0, 100.0),)
    # The centreline stops short: the line lies farther than ABUT_FT along.
    far = ring_of(450, 300 + ABUT_FT + 30, 550, 500)
    assert street_lines_off_end_ft(far, [[far[0]]], [(500.0, 300.0, 0.0, 1.0, True)]) == ((0.0, 100.0),)


def test_a_rear_line_met_first_shields_the_street_behind_it() -> None:
    # The stub runs into the lot's rear line; its street is on the far side.
    lot = ring_of(450, 310, 550, 410)
    assert street_lines_off_end_ft(lot, [[lot[2]]], [(500.0, 300.0, 0.0, 1.0, True)]) == ((100.0, 100.0),)


def test_a_cul_de_sac_lot_keeps_every_line() -> None:
    head = ring_of(450, 310, 550, 410)
    got = street_lines_off_end_ft(head, [[head[0]]], [(500.0, 300.0, 0.0, 1.0, True)], cul_de_sac=True)
    assert got == ((100.0, 100.0),)


def test_unread_is_none_and_the_fact_is_never_true() -> None:
    head = ring_of(450, 310, 550, 410)
    assert street_lines_off_end_ft(head, [[head[0]]], None) is None
    assert street_lines_off_end_ft(head, [], []) is None
    assert decode_rays(None) is None and decode_rays("not json") is None
    assert decode_rays("[]") == []
    assert observed_street_end_frontage(40.0, False, None) == {}
    assert observed_street_end_frontage(None, False, None) == {}
    assert observed_street_end_frontage(400.0, False, None) == {STREET_END_FRONTAGE_FACT: False}
    assert observed_street_end_frontage(40.0, True, None) == {STREET_END_FRONTAGE_FACT: False}
    assert observed_street_end_frontage(40.0, False, ((0.0, 0.0),)) == {STREET_END_FRONTAGE_FACT: False}


def test_rays_near_keeps_only_the_ends_within_reach() -> None:
    lots = [box(450, 310, 550, 410), box(5000, 5000, 5100, 5100), None]
    got = rays_near(lots, [(500.0, 300.0, 0.0, 1.0, True)])
    assert decode_rays(got[0]) == [(500.0, 300.0, 0.0, 1.0, True)]
    assert got[1] == "[]" and got[2] is None


# --- the screen, on a Hillsboro R-7 lot 100 ft by 200 ft


@pytest.fixture(scope="module")
def screen():
    from flats.designs.model import load_catalog
    from flats.encode.load import load_trusted
    from flats.ingest.quadfit import lot_from_row, screen_lot, townhouse
    from flats.score import relief, slack
    from flats.tests.test_utility_easement import lot_row

    rules = load_trusted(strict=False).rules
    policy, rel = slack.load_policy(), relief.load_policy()
    # The townhouse form: four unit lots, each owing the zone's frontage. The
    # apartment form on the one existing lot is let off its frontage by
    # 12.30.300 A (lot_of_record_relief: lot_shape), so D.4 binds here.
    design = townhouse(load_catalog().latest("pod56x36"))

    def run(**over: object):
        row = lot_row(TLID="1N231AA00100", jurisdiction="hillsboro", zone="R-7", street_end_ft=10.0, **over)
        lot = lot_from_row(row, rules.layers)
        (s,) = screen_lot(lot, [design], rules=rules, policy=policy, relief=rel, step_deg=30.0)
        return lot, s.signed

    return run


def frontage(signed) -> Verdict | None:
    got = [c for c in signed.checks if c.check == "min_frontage_ft"]
    return got[0].verdict if got else None


W, D = 100.0, 200.0
#: A stub running north into the lot's south (front) line, ending 10 ft short.
INTO_FRONT = json.dumps([[X0 + W / 2, Y0 - 10, 0.0, 1.0, True]])
#: A stub running south into the lot's north line, ending 10 ft short.
INTO_NORTH = json.dumps([[X0 + W / 2, Y0 + D + 10, 0.0, -1.0, True]])
THROUGH = json.dumps(
    [[X0, Y0, X0 + W, Y0, "F"], [X0 + W, Y0, X0 + W, Y0 + D, "S"], [X0 + W, Y0 + D, X0, Y0 + D, "F"], [X0, Y0 + D, X0, Y0, "S"]]
)


def test_a_lot_whose_only_street_is_a_stub_end_has_no_frontage(screen) -> None:
    lot, signed = screen(stub_ends_json=INTO_FRONT)
    assert lot.facts.street_lines_off_end_ft == ((0.0, 0.0),)
    assert lot.observed[STREET_END_FRONTAGE_FACT] is False
    assert frontage(signed) is Verdict.fails


def test_a_through_lot_keeps_its_through_street_frontage(screen) -> None:
    from flats.score.flags import Colour, fact_code

    lot, signed = screen(stub_ends_json=INTO_NORTH, edges_json=THROUGH)
    assert lot.facts.street_lines_off_end_ft is not None
    assert sorted(lot.facts.street_lines_off_end_ft) == [(0.0, 0.0), (W, W)]
    assert lot.observed[STREET_END_FRONTAGE_FACT] is False
    assert frontage(signed) is Verdict.passes
    assert fact_code(STREET_END_FRONTAGE_FACT) not in {f.code for f in signed.flags}
    # (The pod's 26 ft height misses R-7's 25 ft on this fixture whatever the
    # frontage, so the colour itself is not the test here.)
    # 7ea92302 held this lot: the same lot with its ends unread still is.
    held_lot, held = screen(edges_json=THROUGH)
    assert STREET_END_FRONTAGE_FACT not in held_lot.observed
    assert fact_code(STREET_END_FRONTAGE_FACT) in {f.code for f in held.flags}
    assert held.colour is not Colour.green


def test_a_cul_de_sac_lot_is_not_a_street_end_lot(screen) -> None:
    lot, signed = screen(stub_ends_json=INTO_FRONT, fronts_cul_de_sac=True)
    assert lot.facts.street_lines_off_end_ft == ((W, W),)
    assert lot.observed[STREET_END_FRONTAGE_FACT] is False
    assert frontage(signed) is Verdict.passes


def test_an_unsure_end_holds_the_lot_and_never_fails_it(screen) -> None:
    from flats.score.flags import Colour

    unsure = json.dumps([[X0 + W / 2, Y0 - 10, 0.0, 1.0, False]])
    lot, signed = screen(stub_ends_json=unsure)
    assert lot.facts.street_lines_off_end_ft == ((0.0, W),)
    assert frontage(signed) is None
    assert "min_frontage_ft" in signed.unchecked
    assert signed.colour is not Colour.green


def test_the_frontage_rule_is_hillsboros_alone_and_cited() -> None:
    from flats.rules.loader import load_rules

    rules = load_rules()
    have = [j for j, layer in rules.items() if "min_frontage_street_end" in layer.defaults]
    assert have == [HILLSBORO]
    v = rules[HILLSBORO].defaults["min_frontage_street_end"]
    assert v.value == "excluded"
    assert v.prov.quote == "or/washington/hillsboro/12.50/12.50.110.txt#L35"
