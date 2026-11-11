"""Beaverton's middle-housing zones let the parking court stand between the
building and the street, behind the 10 ft front yard, on the plex path
(fg4-fixes, false-green round 4 batch D, 5755 SW Elm Ave).

Beaverton is not a silent code (ruling 2026-11-08-no-front-yard-parking-
silent-codes does not reach it): its front yard is the setback depth, its
60.30.10.9.B places middle-housing parking by yard, and Table 60.05.60.2 S11
caps garages and outdoor parking at half of any street frontage. The
townhouse table bars the driveway in front of the facade (60.05.60.3 S13.c),
so the townhouse form keeps the hold.
"""

from __future__ import annotations

import pytest

from flats.ingest.quadfit import court_in_front_yard
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.tests.test_clackamas_front_parking import NARROW, WIDE, _corner_plan, _plan, _quoted

pytestmark = pytest.mark.unit

BEAVERTON = "or/washington/beaverton"
MIDDLE = ("RMA", "RMB", "RMC", "CM-RM")


@pytest.fixture(scope="module")
def corpus() -> RuleSet:
    return RuleSet(load_rules(strict=True))


@pytest.mark.parametrize("zone", MIDDLE)
def test_the_plex_path_may_park_in_front_within_half_the_frontage(corpus: RuleSet, zone: str) -> None:
    quad = corpus.resolve(BEAVERTON, zone).values
    assert quad["parking_front_share_allowed"].value is True
    assert quad["parking_area_max_frontage_pct"].value == 50
    text = _quoted(quad["parking_front_share_allowed"].prov.quote)
    assert "shall not occupy more than 50 percent of any public or private street frontage" in text
    town = corpus.resolve(BEAVERTON, zone, ("unit_lots",)).values
    assert town["parking_front_share_allowed"].value is False
    text = _quoted(town["parking_front_share_allowed"].prov.quote)
    assert "not allowed in the area between the front building façade and front lot line" in text


@pytest.mark.parametrize("zone", MIDDLE)
def test_no_outright_ban_stands_in_these_zones(corpus: RuleSet, zone: str) -> None:
    got = corpus.resolve(BEAVERTON, zone)
    assert got.get("parking_front_prohibited") is not True or "parking_front_prohibited" in set(got.exempted)


def test_a_plex_court_in_front_is_clear_within_the_cap_and_held_over_it(corpus: RuleSet) -> None:
    quad = corpus.resolve(BEAVERTON, "RMC")
    narrow = _plan(NARROW)
    narrow.rules = quad
    assert not court_in_front_yard(narrow)
    wide = _plan(WIDE)
    wide.rules = quad
    assert court_in_front_yard(wide)  # 60 of 100 ft is over S11's half


def test_a_townhouse_court_in_front_is_held(corpus: RuleSet) -> None:
    town = _corner_plan(corpus.resolve(BEAVERTON, "RMC", ("unit_lots",)), NARROW)
    assert court_in_front_yard(town)


@pytest.mark.parametrize("zone", ("MR", "CM-HDR", "NS"))
def test_the_other_zones_keep_their_own_rules(corpus: RuleSet, zone: str) -> None:
    assert corpus.resolve(BEAVERTON, zone).get("parking_front_share_allowed") is None
