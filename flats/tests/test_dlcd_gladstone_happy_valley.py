"""Two DLCD notices that each could have left a false GREEN (FOLLOWUPS 88, 89).

Gladstone Ordinance 1545 (TXT-26-02), adopted 2026-07-14 and in force
2026-08-13, rewrote GMC 17.10 for R-7.2: the minimum lot for a duplex through
a quadplex goes from 3,600 to 7,200 square feet. The codified chapter we hold
predates it, so R-7.2 (and R10, which this layer reads on R-7.2's standards)
carry an ``amended:`` entry quoting the exhibit, as Portland's RICAP 11 does.

Happy Valley Ordinance 603 (8/18/2026) put a corner-access sentence and a
driveway-approach sentence in LDC 16.44.120.B.4.b: lots with more than one
frontage take access from the lowest-classified street, and an approach is
12 to 35 feet and no more than half the frontage. The layer said ``any``
because it did not hold Chapter 16.44.
"""

from __future__ import annotations

from datetime import date

import pytest

from flats.provenance.pages import read as read_pages
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import amendments_in_force, law_in_force, load_rules
from flats.rules.resolver import RuleSet
from flats.tests.test_frontage_caps import quoted

pytestmark = pytest.mark.unit

GLADSTONE = "or/clackamas/gladstone"
EXHIBIT = "or/clackamas/gladstone/amended/ord1545.txt"
EFFECTIVE = date(2026, 8, 13)
DAY_BEFORE = date(2026, 8, 12)
HAPPY_VALLEY = "or/clackamas/happy-valley"
CHAPTER_16_44 = "or/clackamas/happy-valley/16.44/16.44.120.txt"


@pytest.fixture(scope="module")
def written():
    return load_rules()


def _labels(quote: str) -> set[str]:
    pages = read_pages(ProvenanceStore(), EXHIBIT)
    assert pages is not None
    out: set[str] = set()
    for span in quote.partition("#")[2].split(","):
        start, _, end = span.lstrip("L").partition("-L")
        out |= {p.label for p in pages.span(int(start), int(end or start))}
    return out


# --- Gladstone, Ordinance 1545 ----------------------------------------------------


@pytest.mark.parametrize("zone", ["R7.2", "R10"])
def test_r72_and_r10_carry_ordinance_1545_with_its_dates(written, zone) -> None:
    (a,) = written[GLADSTONE].zones[zone].amended
    assert (a.id, a.adopted, a.effective) == ("ord1545", date(2026, 7, 14), EFFECTIVE)
    assert a.prov.url == "https://www.ci.gladstone.or.us/media/30151"
    assert _labels(a.prov.quote) == {"9-2", "9-5"}
    words = quoted(a.prov.quote)
    assert "30 days" in words or "thirty" in words.lower()
    assert "7,200" in words


def test_the_minimum_lot_and_the_side_yard_quote_their_exhibit_pages(written) -> None:
    (a,) = written[GLADSTONE].zones["R7.2"].amended
    lot = a.zone.values["min_lot_sqft"]
    assert lot.value == 7200
    assert _labels(lot.prov.quote) == {"9-5"}
    assert "quadplex" in quoted(lot.prov.quote) and "7,200" in quoted(lot.prov.quote)
    assert "(p. 9-5)" in lot.prov.cite
    side = a.zone.values["setback_side_ft"]
    assert side.value == 5
    assert _labels(side.prov.quote) <= {"9-5", "9-6"}
    for name, value in a.zone.values.items():
        assert value.prov.quote and value.prov.quote.startswith(EXHIBIT + "#"), name
        assert "p. 9-" in value.prov.cite or "pp. 9-" in value.prov.cite, name


@pytest.mark.parametrize("zone", ["R7.2", "R10"])
def test_before_the_date_the_codified_3600_and_from_it_7200(written, zone) -> None:
    before = RuleSet(law_in_force(written, DAY_BEFORE)).resolve(GLADSTONE, zone).values
    after = RuleSet(law_in_force(written, EFFECTIVE)).resolve(GLADSTONE, zone).values
    assert before["min_lot_sqft"].value == 3600
    assert after["min_lot_sqft"].value == 7200
    assert after["quadplex_allowed"].value is True
    assert (after["setback_front_ft"].value, after["setback_rear_ft"].value) == (20, 15)
    assert after["setback_side_ft"].value == 5


def test_only_r72_r10_and_c1_move_in_gladstone(written) -> None:
    """C-1 moves with R-7.2 and should: GMC 17.16.040(6) sends a C-1 dwelling
    to "GMC Sections 17.10.050(1) through (4)" by number, so the amended
    sections are the ones it reads. It stays red on its conditional use."""
    on = law_in_force(written, EFFECTIVE)
    assert sorted(a for a in amendments_in_force(on) if a.startswith(GLADSTONE)) == [
        f"{GLADSTONE}:R10:ord1545",
        f"{GLADSTONE}:R7.2:ord1545",
    ]
    old, new = RuleSet(law_in_force(written, DAY_BEFORE)), RuleSet(on)
    for code in on[GLADSTONE].zones:
        if code in {"R7.2", "R10", "C1"}:
            continue
        a, b = old.resolve(GLADSTONE, code), new.resolve(GLADSTONE, code)
        assert {k: v.value for k, v in a.values.items()} == {k: v.value for k, v in b.values.items()}, code
    c1 = new.resolve(GLADSTONE, "C1")
    assert c1.values["min_lot_sqft"].value == 7200
    assert c1.values["setback_side_ft"].value == 15  # its own abutting-residential figure


# --- Happy Valley, 16.44.120.B.4.b --------------------------------------------------


@pytest.mark.parametrize("zone", ["R5", "SFA", "VTH"])
def test_happy_valley_corner_lots_take_the_lowest_classed_street(written, zone) -> None:
    got = RuleSet(written).resolve(HAPPY_VALLEY, zone).values["corner_access_street"]
    assert got.value == "lowest_class"
    assert got.prov.quote.startswith(CHAPTER_16_44 + "#")
    words = quoted(got.prov.quote)
    assert "quadplexes" in words
    assert "access the street with the lowest street classification" in words


def test_happy_valley_driveway_approach_is_12_to_35_feet_and_half_the_frontage(written) -> None:
    got = RuleSet(written).resolve(HAPPY_VALLEY, "R5").values
    assert got["driveway_approach_min_width_ft"].value == 12
    assert got["driveway_approach_max_width_ft"].value == 35
    assert got["driveway_max_frontage_pct"].value == 50
    for name in ("driveway_approach_min_width_ft", "driveway_approach_max_width_ft", "driveway_max_frontage_pct"):
        words = quoted(got[name].prov.quote)
        assert "limited to half the parcel frontage width" in words, name
        assert "16.44.120.B.4.b.iii" in got[name].prov.cite, name
    assert "One driveway is allowed per frontage" in quoted(got["driveway_max_frontage_pct"].prov.quote)
    # The 16.41 two-way minimum stands beside the approach.
    assert got["driveway_min_width_two_way_ft"].value == 20
