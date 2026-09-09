"""Oregon City's non-residential side, eleven districts read at once.

The coverage ledger had 1,162 Oregon City lots sitting in ``zone_missing``
and every one of them was in a district nobody had opened: the two mixed-use
corridors, the mixed-use downtown, general commercial, the Willamette Falls
downtown district, employment, two industrials, the campus-industrial, the
historic corridor and the neighbourhood commercial node. Eleven chapters.
Six of them refuse this building and five of them permit it, and the six
refusals are encoded rather than left out, because an unencoded zone is not
a refusal -- it is a hole, and a hole is invisible to every ledger that
counts fields.

Three findings the errand was not for, each with a test below:

**A permitted-use list can contain the word and still prohibit the pod.**
Historic Corridor's 17.26.020.C permits "conversions of an existing
single-family detached residential unit or duplex into a triplex or
quadplex", and 17.26.035.B prohibits "triplexes and quadplexes". Any search
that stops at the first hit reports HC as open. It is closed, and the only
thing that catches this is reading the prohibited-uses section that sits
sixty lines below the permitted one.

**Commercial land states its setbacks twice over, on the neighbour.** Four
of the five permitting districts print zero at every lot line and then print
twenty feet where the site abuts a residential zone. Zero is the loosest
number in this corpus and it is not a licence to build on the line: the
condition that decides which of the two applies is a fact about the parcel
next door, and nothing in this project measures it. The new
``abuts_residential_zone`` condition carries no assumption, so a lot in
these districts routes to review rather than certifying on the zero.

**The under-five-units exemption is a paragraph, not a policy.** OCMC
17.29.050.I exempts a standalone residential development of fewer than five
units from "maximum setbacks and minimum density requirements". It is
paragraph I of MUC-1's own dimensional-standards section. MUD's two
equivalents say "maximum setbacks" and stop. MUC-2, four lines further down
the same chapter as MUC-1, has no counterpart at all. Four districts, three
different answers, in two chapters -- which is what a per-chapter reading
buys and what a copied one would have destroyed.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS, condition
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

OC = "or/clackamas/oregon-city"
TITLE_17 = "or/clackamas/oregon-city/17.zoning.txt"

#: The five that permit a quadplex, with the chapter each was read out of.
PERMITS = {
    "MUC-1": "17.29.",
    "MUC-2": "17.29.",
    "MUD": "17.34.",
    "C": "17.32.",
    "WFDD": "17.35.",
}

#: The six that do not, and the sentence that closes each one. Encoded, not
#: omitted: the difference between "this city says no" and "nobody looked".
REFUSES = {
    "MUE": "17.31.",
    "I": "17.39.",
    "GI": "17.36.",
    "CI": "17.37.",
    "HC": "17.26.",
    "NC": "17.24.",
}


@pytest.fixture(scope="module")
def layer():
    return load_rules(strict=True)[OC]


@pytest.fixture(scope="module")
def rules():
    return RuleSet(load_rules(strict=True))


@pytest.fixture(scope="module")
def title17():
    return ProvenanceStore().load(TITLE_17).text.splitlines()


def test_eleven_districts_answered_and_six_of_the_answers_are_no(layer) -> None:
    """A refusal is a reading. The count that matters is 11, not 5."""
    for zone, chapter in PERMITS.items():
        assert layer.zones[zone].values["quadplex_allowed"].value is True, zone
        assert chapter in layer.zones[zone].section, zone
    for zone, chapter in REFUSES.items():
        assert layer.zones[zone].values["quadplex_allowed"].value is False, zone
        assert chapter in layer.zones[zone].section, zone

    # And a refusal states nothing else. Encoding a height for a district
    # that prohibits the use is inventing a standard nobody will ever apply.
    for zone in REFUSES:
        assert set(layer.zones[zone].values) == {"quadplex_allowed"}, zone


def test_a_use_list_containing_the_word_quadplex_can_still_prohibit_it(
    layer, title17
) -> None:
    """The near-miss worth a test of its own.

    Chapter 17.26 says "quadplex" exactly twice. The first is on the
    permitted list and reaches only a conversion of a building that already
    exists; the second is the prohibition. A keyword search returns the
    first, and a keyword search is how this district would have been encoded
    as open.
    """
    chapter = [
        (n, line)
        for n, line in enumerate(title17, start=1)
        if 6740 <= n <= 6900 and "uadplex" in line
    ]
    assert [n for n, _ in chapter] == [6784, 6888]

    permitted, prohibited = (line for _, line in chapter)
    assert "residential unit or duplex into a triplex or quadplex" in permitted
    assert prohibited.strip() == "B. Triplexes and quadplexes."

    # The pod is a new building, not a conversion of one. HC is closed.
    assert layer.zones["HC"].values["quadplex_allowed"].value is False


def test_a_zero_setback_here_is_a_question_about_the_neighbour(layer, rules) -> None:
    """Zero at every line, and twenty where the neighbour is residential.

    The variant is what makes the zero safe to hold. Encoding the zero flat
    would green a lot the city would refuse; encoding the twenty flat would
    red a downtown block the city would permit. The condition decides, and
    the resolver has to surface it as a lever or nothing downstream can act
    on it.
    """
    for zone in ("MUC-1", "MUC-2", "MUD", "C"):
        for field in ("setback_side_ft", "setback_rear_ft"):
            value = layer.zones[zone].values[field]
            assert value.value == 0, (zone, field)
            assert [(v.value, tuple(v.when)) for v in value.variants] == [
                (20, ("abuts_residential_zone",))
            ], (zone, field)

        assert "abuts_residential_zone" in rules.resolve(OC, zone).levers, zone


def test_the_condition_carries_no_assumption_so_the_zero_cannot_certify() -> None:
    """The mechanism the test above depends on, asserted where it lives.

    ``assume=None`` is what keeps this out of the ASSUMED set and puts it in
    ``Configuration.unknown``, which is what the screen turns into
    FACT_UNOBSERVED on any standard that leans on it. Change the assumption
    to False and every commercial lot in Oregon City silently becomes
    certifiable against a zero setback.
    """
    defn = condition("abuts_residential_zone")
    assert defn.kind == "site_fact"
    assert defn.assume is None
    assert defn.evidence

    # Held apart from the older condition it reads like. That one compares
    # two residential districts by intensity; this one asks which side of the
    # residential line the neighbour sits on, and a denser neighbour trips it.
    assert "abuts_lower_density_zone" in CONDITIONS
    assert defn.name != "abuts_lower_density_zone"


def test_the_one_district_whose_zero_really_is_zero(layer, rules) -> None:
    """Willamette Falls Downtown states no abutting limb at all.

    The contrast is the point. Without it the test above would pass just as
    well against an encoding that had stapled the condition onto every zero
    in the city out of caution, and caution that is applied everywhere
    measures nothing.
    """
    for field in ("setback_front_ft", "setback_side_ft", "setback_rear_ft"):
        value = layer.zones["WFDD"].values[field]
        assert value.value == 0, field
        assert not value.variants, field

    assert "abuts_residential_zone" not in rules.resolve(OC, "WFDD").levers


def test_the_under_five_units_exemption_was_read_per_chapter(layer, title17) -> None:
    """Three different answers from one sentence printed three times.

    17.29.050.I is a paragraph of MUC-1's section and exempts a sub-five-unit
    residential development from maximum setbacks *and* minimum density.
    17.34.060.K and 17.34.070.K exempt it from maximum setbacks only. MUC-2
    and C have no such paragraph, so both standards bind there in full.
    """
    where = [n for n, line in enumerate(title17, start=1) if "Standalone residential" in line]
    assert where == [7137, 7889, 7930]

    muc1 = " ".join(title17[7136:7139])
    assert "maximum setbacks and minimum" in muc1 and "density requirements" in muc1
    for start in (7889, 7930):
        mud = " ".join(title17[start - 1 : start + 2])
        assert "exempt from maximum setbacks of the underly" in mud
        assert "density" not in mud

    held = {
        zone: (
            "setback_front_max_ft" in layer.zones[zone].values,
            "min_density_du_per_acre" in layer.zones[zone].values,
        )
        for zone in PERMITS
    }
    assert held == {
        "MUC-1": (False, False),  # exempted from both by 17.29.050.I
        "MUD": (False, True),  # setbacks only; the density still binds
        "MUC-2": (True, True),  # same chapter as MUC-1, no such paragraph
        "C": (True, True),  # different chapter, no such paragraph
        "WFDD": (True, False),  # a maximum setback, and no density stated
    }


def test_the_minimum_FARs_are_refused_on_scope_not_for_want_of_a_field(title17) -> None:
    """Two chapters say in their own words what their minimum FARs reach.

    This model has no minimum-FAR field, which would normally make these a
    model gap. It is better than that in MUC and MUD -- the code confines
    them to "all nonresidential and mixed-use building development", and a
    standalone quadplex is neither -- and worse than it looks in WFDD, whose
    chapter states no such confinement, so its 1.0 is a real hole over four
    lots. Refusing on scope where scope is available is what keeps the
    model-gap list honest.
    """
    muc = " ".join(title17[7180:7186])
    mud = " ".join(title17[7947:7951])
    for text in (muc, mud):
        assert "apply to all nonresidential and" in text
        assert "mixed-use building development" in text

    # 17.35 is the exception, and the refusal file has to say so.
    wfdd = "\n".join(title17[8150:8260])
    assert "nonresidential and" not in wfdd


def test_the_lot_area_exemptions_are_the_printed_kind(layer) -> None:
    """Five chapters, five printed cells, all saying the same thing.

    "Minimum lot area: None." is the code answering the question rather than
    failing to ask it, which is the only shape of exemption that is safe to
    hold. Each is quoted from its own district's section -- not one quote
    reused five times, which would look identical in the ledger and prove
    nothing about four of the five.
    """
    seen = set()
    for zone in PERMITS:
        value = layer.zones[zone].values["min_lot_sqft"]
        assert value.exempt is True, zone
        assert value.value is None, zone
        quote = value.prov.quote if value.prov else None
        assert quote and quote.startswith(TITLE_17 + "#"), zone
        seen.add(quote)
    assert len(seen) == len(PERMITS)


def test_the_density_denominator_is_the_citys_own_and_is_not_measured(layer) -> None:
    """17.4 units per acre, of net developable area.

    Three districts state it and none of them mean gross lot area. The
    ``measured_on`` is what stops the screen dividing four units by a
    denominator this project does not hold and reporting a pass.
    """
    for zone in ("MUC-2", "MUD", "C"):
        value = layer.zones[zone].values["min_density_du_per_acre"]
        assert value.value == 17.4, zone
        assert value.measured_on == "net_developable_area", zone

    assert "min_density_du_per_acre" not in layer.zones["MUC-1"].values
    assert "min_density_du_per_acre" not in layer.zones["WFDD"].values


def test_parking_location_is_stated_here_and_the_residential_rule_is_not(layer) -> None:
    """Two paragraphs of 17.16.060, and only one of them reaches this land.

    D opens "In residential zones" and carries the widths this layer holds as
    defaults; E is the mixed-use and commercial paragraph and is what these
    five districts are entitled to. The defaults are left inherited on
    purpose -- they are stricter than E, and stricter is the safe direction
    when the alternative is guessing -- but the location rule is restated per
    zone from E rather than borrowed from D, because that one is a
    prohibition and inheriting a prohibition from the wrong paragraph is how
    a district gets refused for a rule that does not apply to it.
    """
    for zone in PERMITS:
        value = layer.zones[zone].values["parking_front_prohibited"]
        assert value.value is True, zone
        assert "17.16.060.E" in (value.prov.cite if value.prov else ""), zone

    defaults = load_rules(strict=True)[OC].defaults
    assert defaults["parking_front_prohibited"].exempt is True
    assert defaults["parking_area_max_width_ft"].value == 40


def test_the_state_parking_cap_reaches_commercial_land_it_may_not_reach(rules) -> None:
    """The live exposure, pinned so it cannot be forgotten at signing.

    Oregon City states no parking minimum for these districts, so
    ``parking_min_per_unit`` falls through to the state layer, which caps it
    under OAR 660-046-0220. But OAR 660-046-0010(2)(a) excuses lots "not
    zoned for residential use, including but not limited to Lots or Parcels
    zoned primarily for commercial, industrial, agricultural, or public
    uses" -- and these eleven districts are exactly that. The state layer
    applies its defaults to every zone regardless, which was harmless while
    the corpus held only residential districts and is not harmless now.

    This test asserts what is true today, not what ought to be. If somebody
    scopes the state layer, it goes red, and the red is the notification.
    """
    for zone in ("MUC-1", "MUC-2", "MUD", "C", "WFDD"):
        resolved = rules.resolve(OC, zone).values["parking_min_per_unit"]
        assert resolved.layer == "or", zone
        assert resolved.origin == "defaults", zone
        assert "OAR 660-046-0220" in resolved.prov.cite, zone
