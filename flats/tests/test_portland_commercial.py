"""Portland's commercial, employment, industrial and open-space zones.

Thirteen zones over 23,127 lots stood at ``zone_missing`` -- not a verdict but
an admission, and the largest block of unread land left in the corpus. Six of
them turn out to be the most permissive land in the city for a four-unit pod:
Household Living is a plain "Y" and 33.130.200 states there is no minimum lot
size at all. Six others forbid the use, and encoding them is worth as much,
because a RED with a citation is a decision and ``zone_missing`` is not.

What is pinned here is the part that is easy to get wrong. The permissive
zones are permissive on the standards a screen usually reads and binding on
two it usually does not: a *maximum* front setback that puts the building at
the street, and side and rear setbacks that turn on the zoning of the lot next
door rather than on anything in this parcel's record.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import condition
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"

#: The chapter's own list, and the order Table 130-2 prints its columns in.
COMMERCIAL = ("CR", "CM1", "CM2", "CM3", "CE", "CX")
#: Employment, industrial and open space, where the use gate closes.
BARRED = ("IG1", "IG2", "IH", "EG1", "EG2", "OS")


@pytest.fixture(scope="module")
def layers() -> dict[str, Layer]:
    return load_rules()


@pytest.fixture(scope="module")
def portland(layers: dict[str, Layer]) -> Layer:
    return layers[PORTLAND]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_every_commercial_zone_allows_the_use(portland: Layer) -> None:
    """Table 130-1 gives Household Living a bare Y in all six columns, and
    33.130.250.B.2.a names the building type in its own words -- the small
    housing standards apply to "attached houses ... and fourplexes in the
    commercial/mixed use zones"."""
    for zone in COMMERCIAL:
        assert portland.zones[zone].values["quadplex_allowed"].value is True, zone


def test_no_commercial_zone_states_a_minimum_lot_size(portland: Layer) -> None:
    """"There is no required minimum lot size for development of land in
    commercial/mixed use zones." That is an absence, not a minimum of zero,
    and the difference is the whole reason `exempt` exists: one says the code
    states no such test, the other says every lot passes one."""
    for zone in COMMERCIAL:
        value = portland.zones[zone].values["min_lot_sqft"]
        assert value.exempt, zone
        assert value.value is None, zone


def test_the_binding_street_standard_is_a_maximum_not_a_minimum(
    portland: Layer, store: ProvenanceStore
) -> None:
    """The row that decides a pod here is easy to read past. Minimum street
    setback is none; maximum street setback is 10 feet, which forbids the
    layout a rear-court plan reaches for first -- parking at the front and the
    building set back behind it."""
    for zone in COMMERCIAL:
        values = portland.zones[zone].values
        assert values["setback_front_ft"].value == 0, zone
        assert values["setback_front_max_ft"].value == 10, zone

    text = store.quote(portland.zones["CM2"].values["setback_front_max_ft"].prov.quote)
    assert "Max. Building Setbacks" in text
    assert "10 ft." in text


def test_the_side_and_rear_setback_is_the_neighbours_zoning(portland: Layer) -> None:
    """Ten feet from a lot line abutting an RF through RM4, RMP or IR zone;
    none from a lot line abutting OS, RX, C, E or I. The same building is
    legal against one neighbour and illegal against the next, and which one
    this lot has is not in this lot's record -- so 10 is the base and the
    relief waits on a fact nobody measures."""
    for zone in COMMERCIAL:
        for field in ("setback_side_ft", "setback_rear_ft"):
            value = portland.zones[zone].values[field]
            assert value.value == 10, f"{zone}.{field}"
            assert [v.value for v in value.variants] == [0], f"{zone}.{field}"
            assert value.variants[0].when == ("abuts_nonresidential_zone",)


def test_the_neighbours_zoning_is_not_a_lever(portland: Layer) -> None:
    """A relief that rests on an unmeasured fact must not be reachable, or
    every commercial lot screens as though its neighbours were industrial.
    The condition is registered as unknown, so resolution keeps the 10."""
    assert condition("abuts_nonresidential_zone").assume is None

    resolved = RuleSet(load_rules()).resolve(PORTLAND, "CM2").values
    assert resolved["setback_side_ft"].value == 10
    assert resolved["setback_rear_ft"].value == 10


def test_the_heights_are_read_off_one_row(portland: Layer, store: ProvenanceStore) -> None:
    """Table 130-2 prints all six cells of a row on a single line, so the
    header is quoted with the row and position is what names the column. The
    check that this was read correctly is that the six numbers are the six
    numbers, in the chapter's own order."""
    got = [portland.zones[z].values["max_height_ft"].value for z in COMMERCIAL]
    assert got == [30, 35, 45, 65, 45, 75]

    text = store.quote(portland.zones["CM3"].values["max_height_ft"].prov.quote)
    assert "Base Height" in text
    for cell in ("30 ft.", "35 ft.", "45 ft.", "65 ft.", "75 ft."):
        assert cell in text


def test_the_pod_clears_every_commercial_height(portland: Layer) -> None:
    """26 feet against a 30-foot floor in the tightest of the six. Height is
    not what decides a lot in this chapter, which is worth stating because it
    is what decides one in most of the others."""
    assert min(portland.zones[z].values["max_height_ft"].value for z in COMMERCIAL) == 30


def test_the_coverage_encoded_is_the_lower_of_the_two_pattern_areas(portland: Layer) -> None:
    """Two rows, and which applies is a pattern area on Map 130-2 that this
    screen does not read. Taking the Inner figure would hand an Eastern lot
    100 percent coverage where its own row says 85."""
    got = [portland.zones[z].values["max_coverage_pct"].value for z in COMMERCIAL]
    assert got == [75, 75, 85, 85, 75, 100]


def test_only_two_zones_carry_a_density_floor(portland: Layer) -> None:
    """CM2 and CM3, stated as an area per unit rather than a rate, so what is
    compared against the table is the operand the table prints."""
    floors = {
        z: portland.zones[z].values["min_density_du_per_acre"].sqft_per_unit
        for z in COMMERCIAL
        if "min_density_du_per_acre" in portland.zones[z].values
    }
    assert floors == {"CM2": 1450, "CM3": 1000}


def test_the_one_density_ceiling_is_encoded_and_then_preempted(portland: Layer) -> None:
    """Note [1] applies to exactly the building this screen places -- a site
    with no Retail Sales And Service or Office use -- and caps Household
    Living at one unit per 2,500 sq ft. It is encoded because the city wrote
    it, and it does not survive resolution, because OAR 660-046-0220(2)(b)
    bars a Large City from applying a density maximum to a quadplex.

    Both halves matter. A ceiling that vanishes should vanish visibly, with
    the city's sentence and the state's sentence both on the record, rather
    than never having been read."""
    encoded = portland.zones["CR"].values["max_density_du_per_acre"]
    assert encoded.sqft_per_unit == 2500

    resolved = RuleSet(load_rules()).resolve(PORTLAND, "CR").values
    assert "max_density_du_per_acre" not in resolved


def test_the_main_entrance_is_bound_and_the_building_is_not(portland: Layer) -> None:
    """33.130.250.B.3 puts a main entrance within 8 feet of the longest
    street-facing wall and makes it face the street, angle up to 45 degrees,
    or open onto a porch. That is a constraint on the entrance, not on the
    building's long axis -- which is the difference `entrance_only` carries,
    and the difference between halving the orientations the fit stage may try
    and not."""
    for zone in COMMERCIAL:
        value = portland.zones[zone].values["orientation_constraint"]
        assert value.value == "entrance_only", zone


def test_the_industrial_zones_are_a_decided_no(portland: Layer, store: ProvenanceStore) -> None:
    """Table 140-1 shows a conditional use, and the regulation behind the
    bracket closes it: Household Living in houseboats is sent to another
    chapter and "Household and Group Living in other structures is
    prohibited". A townhome is another structure, so the CU column is not a
    door this building can walk through."""
    for zone in ("IG1", "IG2", "IH"):
        value = portland.zones[zone].values["quadplex_allowed"]
        assert value.value is False, zone
        assert value.variants == (), f"{zone}: a settled false with a lever is not settled"

    text = store.quote(portland.zones["IG1"].values["quadplex_allowed"].prov.quote)
    assert "in other structures is prohibited" in text
    assert "CU [2]" in text


def test_the_employment_zones_allow_only_a_conversion(
    portland: Layer, store: ProvenanceStore
) -> None:
    """EG1 and EG2 read "L [1]", and [1] is not a limitation a new building
    can meet: an existing hotel or motel converted to dwelling units, all of
    them affordable at 60 percent of median income under a 30-year covenant.
    Then it says so in the negative, which is the sentence encoded."""
    for zone in ("EG1", "EG2"):
        assert portland.zones[zone].values["quadplex_allowed"].value is False, zone

    text = store.quote(portland.zones["EG1"].values["quadplex_allowed"].prov.quote)
    assert "hotel or motel is converted" in text
    # The sentence breaks across two lines of the extraction, so the half
    # that carries the verb is what is matched.
    assert "Group Living use are prohibited" in text


def test_open_space_says_no_in_one_character(portland: Layer, store: ProvenanceStore) -> None:
    assert portland.zones["OS"].values["quadplex_allowed"].value is False
    assert "Household Living" in store.quote(portland.zones["OS"].values["quadplex_allowed"].prov.quote)


def test_a_barred_zone_owes_no_dimensions(portland: Layer) -> None:
    """The screen returns RED at the use gate without reading a setback, so a
    height lookup in an industrial zone could never move a verdict. Encoding
    one would be work that reads as coverage and buys nothing."""
    for zone in BARRED:
        assert set(portland.zones[zone].values) == {"quadplex_allowed"}, zone


def test_the_one_employment_zone_that_allows_it_is_encoded_whole(portland: Layer) -> None:
    """EX is Central Employment and the odd one out in its own chapter:
    Household Living is a plain Y with no bracket. Table 140-3 bands its
    residential setbacks by wall height, and a 26-foot pod is always in the
    taller band, so the 15-ft-or-less row never applies to it."""
    values = portland.zones["EX"].values

    assert values["quadplex_allowed"].value is True
    assert values["min_lot_sqft"].exempt
    assert values["max_height_ft"].value == 65
    assert values["setback_front_ft"].value == 0
    assert values["setback_side_ft"].value == 10
    assert values["setback_rear_ft"].value == 10
    assert values["max_coverage_pct"].value == 100


def test_every_new_citation_resolves(portland: Layer, store: ProvenanceStore) -> None:
    """The rung that catches a line number typed from a page number. Nothing
    in this chapter was quoted from a document the store cannot open, and
    nothing quoted a span that runs backwards."""
    assert readiness_for(portland, store=store).no_evidence == ()
    assert readiness_for(portland, store=store).misquoted == ()


def test_the_zones_that_were_unread_are_no_longer_unread(portland: Layer) -> None:
    """The point of the exercise, stated as a count. Thirteen zones, 23,127
    lots, previously reported by the coverage ledger as `zone_missing` --
    which is not a screen returning RED, it is a screen with nothing to say."""
    for zone in (*COMMERCIAL, "EX", *BARRED):
        assert zone in portland.zones, zone
