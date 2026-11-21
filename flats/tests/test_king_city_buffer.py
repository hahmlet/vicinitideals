"""King City 16.124.110 C: the buffer a drive or court may not stand in.

FOLLOWUPS 146 let the drive lane and the court use an interior side setback
where the code allows it; King City is SILENT (YELLOW at best). 16.124.110 B
keeps "building, accessways or parking areas" out of a BUFFER, and C owes one
on "all portions of the lot abutting a lesser zone": five feet on a
multi-family property beside a single-family zone, ten beside a commercial
zone, ten on a commercial property beside a residential zone. Read by the
zone (conservative). Since FOLLOWUPS 192 (2026-11-14) the two neighbours are
two facts (`abuts_lower_density_zone` single-family, `abuts_commercial_zone`
commercial): beside single-family zones only, 5; beside a commercial zone or
an unplaced neighbour, 10. The strip is one figure off every non-street line.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet
from flats.score.paper import (
    lot_line_buffer_ft,
    side_yard_court_overlap_ft,
    side_yard_lane_overlap_ft,
)

pytestmark = pytest.mark.unit

KING_CITY = "or/washington/king-city"
FIELD = "parking_lot_line_buffer_ft"
LOWER = "abuts_lower_density_zone"
COMMERCIAL = "abuts_commercial_zone"
RESIDENTIAL = "abuts_residential_zone"
#: The pod zones that admit multi-dwellings (16.84.010, Table 16.114-2).
MULTI_FAMILY = ("R-12", "R-15", "R-24", "AT", "KTTC", "KTBB", "KTC", "KTRC")
#: Kingston Terrace zones that also admit retail and offices.
MIXED = ("KTTC", "KTBB")


@pytest.fixture(scope="module")
def corpus() -> dict[str, Layer]:
    return load_rules()


@pytest.fixture(scope="module")
def king_city(corpus: dict[str, Layer]) -> Layer:
    return corpus[KING_CITY]


@pytest.fixture(scope="module")
def rules(corpus: dict[str, Layer]) -> RuleSet:
    return RuleSet(corpus)


def _text(quote: str) -> str:
    return " ".join(ProvenanceStore().quote(quote).split())


def test_the_quote_carries_c2_c3_and_the_ban_on_accessways_and_parking(
    king_city: Layer,
) -> None:
    held = king_city.defaults[FIELD]
    assert held.exempt is True
    by_when = {v.when: v for v in held.variants}
    assert set(by_when) == {(LOWER,), (COMMERCIAL,), (LOWER, COMMERCIAL)}
    five, ten = by_when[(LOWER,)], by_when[(COMMERCIAL,)]
    assert five.value == 5 and ten.value == 10 and by_when[(LOWER, COMMERCIAL)].value == 10
    text = _text(five.prov.quote)
    assert "five-foot wide buffer area" in text
    assert "multi-family property abutting a single-" in text
    assert "No building, accessways or parking" in text
    assert "abutting a lesser" in text
    text = _text(ten.prov.quote)
    assert "ten-foot wide buffer area" in text and "mercial zone" in text
    assert "five-foot" not in text


@pytest.mark.parametrize("zone", MULTI_FAMILY)
def test_a_multi_family_zone_owes_five_beside_single_family_and_ten_beside_commercial(
    rules: RuleSet, zone: str
) -> None:
    for plat in ((), ("unit_lots",)):
        for facts, want in (((COMMERCIAL,), 10), ((LOWER, COMMERCIAL), 10)):
            got = rules.resolve(KING_CITY, zone, (*plat, *facts))
            assert not got.ambiguous and lot_line_buffer_ft(got) == want, (zone, plat, facts)
        # C.2's five; in the mixed zones a single-family neighbour is a
        # residential one too (both facts true), and C.1's ten governs.
        sf = rules.resolve(KING_CITY, zone, (*plat, LOWER, *((RESIDENTIAL,) if zone in MIXED else ())))
        assert not sf.ambiguous, (zone, plat)
        assert lot_line_buffer_ft(sf) == (10 if zone in MIXED else 5), (zone, plat)
        clear = rules.resolve(KING_CITY, zone, plat)
        if zone not in MIXED:
            assert lot_line_buffer_ft(clear) == 0, (zone, plat)


@pytest.mark.parametrize("zone", MIXED)
def test_town_center_and_beef_bend_also_owe_c1_beside_a_residential_zone(
    rules: RuleSet, zone: str
) -> None:
    for facts in (
        (RESIDENTIAL,), (LOWER, RESIDENTIAL), (COMMERCIAL, RESIDENTIAL),
        (LOWER, COMMERCIAL, RESIDENTIAL),
    ):
        got = rules.resolve(KING_CITY, zone, facts)
        assert not got.ambiguous, (zone, facts)
        assert lot_line_buffer_ft(got) == 10, (zone, facts)
    assert lot_line_buffer_ft(rules.resolve(KING_CITY, zone, ())) == 0


def test_r9_admits_no_multi_dwelling_and_owes_none(rules: RuleSet, king_city: Layer) -> None:
    held = king_city.zones["R-9"].values[FIELD]
    assert held.exempt is True and not held.variants
    got = rules.resolve(KING_CITY, "R-9", ("unit_lots", LOWER, COMMERCIAL, RESIDENTIAL))
    assert lot_line_buffer_ft(got) == 0


def test_the_buffer_takes_the_side_yard_away_from_the_lane_and_court(
    rules: RuleSet,
) -> None:
    # KTC's side yard (Table 16.114-4) is narrower than ten feet, so beside a
    # lesser zone nothing of it is left for the lane or the court.
    clear = rules.resolve(KING_CITY, "KTC", ())
    beside = rules.resolve(KING_CITY, "KTC", (COMMERCIAL,))
    assert side_yard_lane_overlap_ft(clear, 12.0) > 0
    assert side_yard_lane_overlap_ft(beside, 12.0) == 0
    assert side_yard_court_overlap_ft(beside, 12.0, lane_ft=12.0) == 0


def test_the_neighbour_lists(king_city: Layer) -> None:
    lower = king_city.neighbours[LOWER]
    assert set(lower.true_for) == {"SF", "R-9"}
    commercial = king_city.neighbours[COMMERCIAL]
    assert set(commercial.true_for) == {"LC", "NMU"}
    # The mixed Kingston Terrace zones are not single-family, but may be
    # commercial to a neighbour: unread on that fact only.
    for zone in MIXED:
        assert zone in lower.false_for
        assert zone not in commercial.true_for and zone not in commercial.false_for
    residential = king_city.neighbours[RESIDENTIAL]
    assert {"SF", "R-9", "R-12", "R-15", "R-24", "AT", "KTC", "KTRC"} == set(
        residential.true_for
    )
    for zone in MIXED:
        assert zone not in residential.true_for and zone not in residential.false_for
    assert "Single-family Residential SF" in _text(lower.quote)


def test_a_line_read_per_neighbour_sorts_into_the_two_facts(king_city: Layer) -> None:
    from flats.geom.neighbour import Line, observed_neighbours

    def facts(*zones: str, unresolved: int = 0) -> dict[str, bool]:
        lines = tuple(Line(zones=((KING_CITY_Q, z),), unresolved=0) for z in zones)
        if unresolved:
            lines = (*lines, Line(zones=(), unresolved=unresolved))
        return observed_neighbours(lines, king_city.neighbours, KING_CITY_Q)

    sf = facts("SF", "R-12")
    assert sf[LOWER] is True and sf[COMMERCIAL] is False
    lc = facts("LC", "R-12")
    assert lc[COMMERCIAL] is True and lc[LOWER] is False
    # A Town Center neighbour may be commercial: that fact is left unread
    # (the ten held), the single-family one is settled.
    kt = facts("SF", "KTTC")
    assert kt[LOWER] is True and COMMERCIAL not in kt
    # An unread line settles neither false.
    assert COMMERCIAL not in facts("R-12", unresolved=2)
    assert LOWER not in facts("R-12", unresolved=2)


#: King City's jurisdiction as the fabric spells it.
KING_CITY_Q = "King City"
