"""Section 350 is four articles and only one of them dimensions this parking.

Every parking reading in this corpus has had to answer some version of "is a
quadplex the thing this row is about". Troutdale and Gladstone counted units in
a definition. West Linn had no definition to count and took the multifamily
rules by elimination against a gap. Wood Village is the clean case: the code
splits its parking standards into an article for one and two unit dwellings
(350.050-350.055) and one for all other uses (350.060-350.065), each article
states its own scope, and WVDC 720.030 defines every noun in both scopes
including this building.

What makes the split worth the work is that only 350.065 states an aisle. On
the other branch the city could not be laid out at all -- there would be a
stall and no width to reach it by. So the elimination is not a technicality
about which citation to print; it is the difference between the eleventh city
on the dimensioned list and a twelfth on the declined one.

And what makes the elimination SAFE is that the stall is the same on both
branches. 350.055(C) says 9 feet by 19 feet for a house; Table 350-3's
90-degree Standard row says 9 by 19. A reviewer who reads the split the other
way gets the same rectangle out of it, so the reading can only be wrong about
things that make the screen looser to check, never about the number the pod is
measured against.
"""

from __future__ import annotations

import pytest

from flats.encode.refusals import refusals
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

WOOD_VILLAGE = "or/multnomah/wood-village"
GENERAL = "or/multnomah/wood-village/350.030.general-regulations.txt"
REQUIRED = "or/multnomah/wood-village/350.045.required-spaces.txt"
ONE_AND_TWO = "or/multnomah/wood-village/350.055.one-and-two-unit.txt"
ALL_OTHER = "or/multnomah/wood-village/350.065.all-other-uses.txt"
DEFINITIONS = "or/multnomah/wood-village/720.030.definitions.txt"

#: Every residential zone in the city, and every one of them sets the building
#: ten feet off the front lot line -- which is what makes the five-foot parking
#: setback inert.
RESIDENTIAL = ("LR 12", "LR 7.5", "MR 2", "MR 4")

#: municipal.codes separates a paragraph's letter from its heading with an EN
#: SPACE, and the extractor keeps it. Written out here rather than normalised
#: away: a test that quietly repairs its own evidence has stopped checking it,
#: and the day this becomes a plain space is a day the extraction changed.
EN = " "


@pytest.fixture(scope="module")
def wood_village() -> Layer:
    return load_rules()[WOOD_VILLAGE]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _lines(store: ProvenanceStore, path: str) -> list[str]:
    return store.load(path).text.splitlines()


# -- which article reaches ----------------------------------------------------


def test_each_article_states_its_own_scope_and_they_do_not_overlap(
    store: ProvenanceStore,
) -> None:
    """The split is written down twice, once from each side.

    350.065 says what it does not reach and points at the sections by number;
    350.055 says what it does reach and points at four named structure types.
    Neither is inferred from a heading.
    """
    other = _lines(store, ALL_OTHER)[59]
    assert other.startswith(f"A.{EN}Where These Standards Apply.")
    assert "all vehicle areas whether required or excess parking" in other
    assert (
        "except for residential parking areas subject to the standards of "
        "Section 350.050 through 350.055" in other
    )

    one_and_two = _lines(store, ONE_AND_TWO)[59]
    assert one_and_two.startswith(f"A.{EN}Structures These Regulations Apply To.")
    assert (
        "apply to houses, attached houses, duplexes, and manufactured homes"
        in one_and_two
    )


def test_the_glossary_defines_all_four_names_and_the_building(
    store: ProvenanceStore,
) -> None:
    """The elimination, one definition at a time.

    A quadplex is four units on one lot. A house is one unit, detached, on its
    own lot. An attached house is a townhouse by the glossary's own aside, and
    a townhouse puts each unit on an individual lot. A duplex is two. A
    manufactured home is a transportable HUD structure. None of the four is
    this building, and the noun that IS this building is defined in the same
    block eight lines away.
    """
    lines = _lines(store, DEFINITIONS)
    assert lines[351] == "RESIDENTIAL STRUCTURE TYPES"

    assert lines[367].startswith(
        "QUADPLEX. A structure that contains four (4) primary dwelling units on one (1) lot."
    )
    assert lines[361] == "HOUSE. A detached dwelling unit located on its own lot."
    assert "located on an individual lot or parcel" in lines[369]
    assert "attached house" in lines[369]  # the townhouse's other name, in the code
    assert lines[355].startswith("DUPLEX. A structure that contains two (2)")
    assert lines[363].startswith("MANUFACTURED HOME. A structure transportable")


def test_multi_dwelling_starts_at_five_so_nothing_catches_the_pod_above_it(
    store: ProvenanceStore,
) -> None:
    """The other end of the elimination, and the one that usually bites.

    Troutdale, Tualatin and unincorporated Multnomah all turned on where the
    multi-unit noun starts. Here it starts at five, so a quadplex is not swept
    up into a multi-dwelling row on the way out of the one-and-two-unit
    article -- it lands in "all other uses", which states no threshold at all.
    """
    assert _lines(store, DEFINITIONS)[365].startswith(
        "MULTI-DWELLING STRUCTURE. A structure that contains five (5) or more dwelling units"
    )


def test_only_the_article_that_reaches_states_an_aisle(store: ProvenanceStore) -> None:
    """Why the split had to be settled rather than left as a doubt.

    350.055 dimensions a stall and a residential driveway and stops. There is
    no aisle in it, at any angle, under any name -- so read the other way this
    city has a rectangle and no way to reach it, and would have joined
    Milwaukie and Wilsonville on the declined list.
    """
    one_and_two = store.load(ONE_AND_TWO).text
    assert "9 feet by 19 feet" in one_and_two
    assert "aisle" not in one_and_two.lower()

    assert "Aisle Width" in _lines(store, ALL_OTHER)[97]


def test_the_stall_comes_out_the_same_on_either_branch(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    """The reason the reading above is safe rather than merely argued.

    9 by 19 in 350.055(C) for a house, 9 by 19 in Table 350-3's 90-degree
    Standard row for everything else. Whichever article a reviewer thinks
    applies, the pod is measured against the same rectangle, and the
    elimination can only be wrong about the aisle and about rules that do not
    reach.
    """
    residential = _lines(store, ONE_AND_TWO)[63]
    assert "The minimum size of a required parking space is 9 feet by 19 feet." in residential

    table = _lines(store, ALL_OTHER)[110].split()
    assert table[:2] == ["90°", "Standard"]
    assert table[2:4] == ["9", "ft"]  # Width (B)
    assert table[-2:] == ["19", "ft"]  # Stall Depth (E)

    d = wood_village.defaults
    assert (d["parking_stall_width_ft"].value, d["parking_stall_depth_ft"].value) == (9, 19)


# -- the numbers --------------------------------------------------------------


def test_the_aisle_is_one_pair_of_figures_at_every_angle(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    """Table 350-3 varies the stall by angle and does not vary the aisle.

    Fifteen rows, five angles, three stall types, and every one of them prints
    12 feet one way and 24 feet two way. So there is no branch to choose here
    and no angle to argue about -- unusual enough in this corpus to pin.
    """
    lines = _lines(store, ALL_OTHER)
    rows = [line for line in lines[98:113] if "ft" in line]
    assert len(rows) == 15
    for row in rows:
        assert "12 ft" in row and "24 ft" in row, row

    d = wood_village.defaults
    assert d["parking_aisle_one_way_ft"].value == 12
    assert d["parking_aisle_two_way_ft"].value == 24


def test_the_standard_stall_is_taken_and_not_the_compact_one(
    store: ProvenanceStore,
) -> None:
    """Half of this building's stalls could legally be 7 ft 6 in by 15 ft.

    350.065(D)(2)(b) requires only that "at least 50% of required parking
    spaces" meet the standard dimensions, so two of the pod's four could be
    compact. A court drawn to the standard stall everywhere fits on every lot
    where the mixed court fits, and the reverse is not true -- so the strict
    branch is the one encoded and the slack it leaves is real.
    """
    lines = _lines(store, ALL_OTHER)
    assert lines[90] == (
        f"(b){EN}At least 50% of required parking spaces must comply with the "
        "minimum dimensions for standard spaces."
    )
    compact = lines[111].split()
    assert compact[:2] == ["90°", "Compact"]
    assert "7 ft 6 in" in lines[111] and "15 ft" in lines[111]


def test_the_setback_cell_holds_two_compliance_paths_and_the_minimum_is_taken(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    """"5 ft/L2 10 ft/L1" is one cell, not a botched extraction.

    Five feet if the strip is planted to the L2 standard, ten if only to L1 --
    a developer buys lighter planting with the extra five feet. Five is what
    the code requires as a minimum, and this model checks no landscaping
    standard either way, so five is the number.
    """
    lines = _lines(store, ALL_OTHER)
    assert lines[71] == "Table 350-2. Minimum Parking Area Setbacks and Perimeter Landscaping"
    assert lines[73].split() == ["Location", "except", "GM", "GM"]
    assert lines[74].startswith("Lot line abutting street")
    assert lines[74].split()[-8:] == ["5", "ft/L2", "10", "ft/L1"] * 2

    assert wood_village.defaults["parking_street_setback_ft"].value == 5


def test_the_parking_setback_is_inert_because_the_building_owes_twice_it(
    wood_village: Layer,
) -> None:
    """Five feet of parking setback against ten feet of front setback.

    This is what separates Wood Village's side-and-rear refusal from
    Tualatin's. There, RML's side yard was five and the unheld half of the
    rule wanted ten, so the refusal would have bitten had the zone held lots.
    Here every residential zone sets the building ten feet off the front line
    and at least five off each side, so the envelope is already cut back
    further than any row of Table 350-2 asks.
    """
    rules = RuleSet(load_rules())
    for zone in RESIDENTIAL:
        resolved = rules.resolve(WOOD_VILLAGE, zone)
        assert resolved.get("parking_street_setback_ft") == 5
        assert resolved.get("setback_front_ft") >= 10, zone
        assert resolved.get("setback_side_ft") >= 5, zone


def test_the_ceiling_is_read_off_a_table_that_has_numbers_in_it(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    """Household Living prints "no maximum"; the table around it does not.

    An exemption is only worth the word if the apparatus exists and was
    pointed elsewhere. Table 350-1B caps a restaurant at 23 spaces per 1,000
    sq ft and a college at 0.3, and prints a second tighter column for
    anything within a quarter mile of 20-minute transit.
    """
    lines = _lines(store, REQUIRED)
    assert lines[145] == "Table 350-1B. Maximum Parking Ratios"
    assert "Within 1/4 mile of fixed route transit with 20-minute service" in lines[147]
    assert lines[148].split() == ["Household", "Living", "no", "maximum", "no", "maximum"]
    assert lines[151].split() == ["Restaurant", "23", "19.1"]
    assert lines[163].split() == ["Colleges", "0.3", "0.3"]

    d = wood_village.defaults
    assert d["parking_max_per_unit"].exempt is True
    assert d["parking_min_per_unit"].value == 1


# -- what the code does not state ---------------------------------------------


def test_the_only_sentence_about_an_access_point_states_no_width(
    wood_village: Layer, store: ProvenanceStore
) -> None:
    """A redirect that names no document, which is worse than P100.

    Clackamas County sends a reader to Standard Drawing P100 -- a real sheet
    with the dimension drawn on it, refused only because the number is in the
    picture rather than the text. Wood Village sends a reader to "established
    City standards" and there is no such document in the code. So the drive
    and the cut fall to the design defaults, and 350.055(C)'s nine-foot
    residential driveway is not borrowed for them: it belongs to the article
    that does not reach this building.
    """
    curb = _lines(store, GENERAL)[65]
    assert curb.startswith(f"D.{EN}Curb Cuts.")
    assert "shall be the minimum necessary" in curb
    assert "Curb cuts shall be designed to established City standards." in curb
    assert "ft" not in curb and "feet" not in curb

    assert "9 feet for residential uses" in _lines(store, ONE_AND_TWO)[63]
    for field in (
        "driveway_min_width_one_way_ft",
        "driveway_min_width_two_way_ft",
        "driveway_approach_min_width_ft",
        "driveway_approach_max_width_ft",
    ):
        assert field not in wood_village.defaults, field


def test_the_rules_that_do_not_reach_are_the_ones_the_split_decides(
    store: ProvenanceStore,
) -> None:
    """Three standards that would have moved lots, all on the wrong branch.

    350.055(B) bans parking in the first ten feet of a front lot line and caps
    the front yard at 40 percent paved -- Portland's and Milwaukie's rule,
    which this corpus does hold a field for. 350.055(C) sets a nine-foot
    residential driveway, narrower than the twelve-foot design lane. Neither
    reaches, and the interior-landscaping rule in the article that DOES reach
    starts at more than ten spaces, where the pod owes four.
    """
    residential = _lines(store, ONE_AND_TWO)[61]
    assert "not allowed within the first 10 feet from a front lot line" in residential
    assert "no more than 40 percent of the land area" in residential

    landscaping = _lines(store, ALL_OTHER)[120]
    assert landscaping.startswith(f"(1){EN}Amount of Landscaping.")
    assert "surface parking areas with more than 10 spaces" in landscaping


def test_forward_access_reaches_this_building_and_no_field_holds_it(
    store: ProvenanceStore,
) -> None:
    """Gladstone's rule, one stall the other way.

    Gladstone's forward-access standard starts at more than four spaces and
    the pod owes exactly four, so it stops short. Wood Village's excepts
    parking areas of one or two spaces, so four is caught twice over. The
    fourth city to state it flat rather than by street class, and the fourth
    with no field for it -- the site plan draws a rear court with a turning
    bay because the typology says so, which is why the refusal is written down
    rather than waved off.
    """
    forward = _lines(store, ALL_OTHER)[84]
    assert "enter and exit the roadway in a forward motion" in forward
    assert "does not apply to parking areas with one or two spaces" in forward


def test_three_refusals_against_seven_values(wood_village: Layer) -> None:
    """The smallest ratio any parking reading in this corpus has produced.

    Because the chapter is essentially one table. Table 350-3 states the stall
    and both aisles at every angle and Table 350-2 states three setbacks, of
    which the street one has a field. What is left over is the side-and-rear
    pair, the curb cut that points at nothing, and forward access.

    Filtered to Section 350 on purpose. The layer refuses a fourth thing --
    Figure 710-1, the drawing WVDC 720.030 points at for what a corner lot
    looks like -- and it arrived in the same reading because storing the
    glossary is what made the corner lot visible at all. It is not a parking
    refusal and does not belong in this count.

    Seven counts the minimum read on 2026-08-20 along with the six read on
    2026-08-30, because that is what a reviewer opening this layer sees. The
    contrast worth holding is with unincorporated Multnomah, which refused
    eleven against six out of a code that regulates the same four stalls in
    two chapters and a design-review section.
    """
    mine = [r for r in refusals(WOOD_VILLAGE) if r.kind == "comments"]
    parking = [
        r
        for r in mine
        if r.text.startswith("NOT ENCODED") and "350" in r.text
    ]
    assert len(parking) == 3, [r.text[:60] for r in parking]

    encoded = [f for f in wood_village.defaults if f.startswith("parking_")]
    assert len(encoded) == 7
