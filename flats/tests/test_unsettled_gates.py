"""A `false` a footnote might lift is not a `false` you can stop reading at.

A zone whose ``quadplex_allowed`` is false and *uncapped* owes nothing: the
screen returns RED at the use gate and never reads a setback. A zone whose
false is capped owes everything, because the cap is the admission that we
cannot say the gate stays shut. This file is about the second kind -- and,
since 2026-08-26, about how a zone stops being one.

Portland CI1 is the live case. Table 150-1 reads N for Household Living, the
cell carries no marker of its own, and it sits in a region note [3] governs --
the PCC Sylvania FAR boundary on Map 150-5 -- which is ruled ``unmeasured``:
read, understood, waiting on a map nobody holds. Note [3] cannot plausibly turn
an N into a Y. That is not the point. The census scopes a footnote to its whole
region on purpose, because telling a cell marker from a row marker from a
column marker in extracted text is exactly the judgement that gets made wrong
silently, and an over-scoped footnote costs a review while an under-scoped one
costs a false GREEN.

Gresham RTC, MC and CC were here too and are not any more, and the difference
is that somebody read the note. Table 4.0420 note 2 names CMF twice -- its
first sentence is the L2 marker on that column's own cells, its second limits
middle housing land divisions in that district -- and it reached six other
columns only because it shares a notes block with them. It is narrowed to CMF
now, by ``zones:`` on the ruling; the three NPs are settled; and the column of
Table 4.0430 encoded for them on 2026-08-21 stays encoded, correct, and no
longer owed. That is the balance the scoping rule is meant to strike: the wide
reading by default, the narrowing written down when the reading is done.

809 lots, and they were invisible for a fortnight because the shipped coverage
ledger was stale. The last test here is the guard against that recurring.
"""

from __future__ import annotations

import pytest

from flats.rules.caps import caps_for
from flats.rules.ledger import read_coverage
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

#: Shut, and not settled: the unmeasured fact whose footnote levers each gate.
UNSETTLED = {
    ("or/multnomah/portland", "CI1"): "site_specific_limitation",
}

#: Shut and settled, after the narrowing. These three carried `civic_corridor`
#: on every field until 2026-08-26.
SETTLED = (
    ("or/multnomah/gresham", "RTC"),
    ("or/multnomah/gresham", "MC"),
    ("or/multnomah/gresham", "CC"),
)


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.mark.parametrize(("key", "fact"), sorted(UNSETTLED.items()))
def test_the_use_gate_is_shut_but_not_settled(
    rules: RuleSet, key: tuple[str, str], fact: str
) -> None:
    """Both halves, together. Either alone is a different zone.

    A zone whose `quadplex_allowed` is false and *uncapped* owes nothing: the
    screen returns RED at the use gate and never reads a setback. A zone whose
    false is capped owes everything, because the cap is the admission that we
    cannot say the gate stays shut."""
    layer, zone = key
    resolved = rules.resolve(layer, zone)

    assert resolved.values["quadplex_allowed"].value is False
    assert caps_for(layer, zone)["quadplex_allowed"] == (fact,)


@pytest.mark.parametrize("key", sorted(UNSETTLED) + list(SETTLED))
def test_and_so_it_owes_the_standards_behind_it(
    rules: RuleSet, key: tuple[str, str]
) -> None:
    layer, zone = key

    assert rules.resolve(layer, zone).missing_required == ()


@pytest.mark.parametrize("key", SETTLED)
def test_a_narrowed_note_settles_the_gate_it_never_spoke_to(
    rules: RuleSet, key: tuple[str, str]
) -> None:
    """The other direction, and the one that was wrong for a fortnight.

    Nothing about these three columns changed in the code; what changed is that
    the note over them was read and found to be somebody else's. A settled NP
    is RED at the use gate and owes nothing, which is the whole point of the
    resolver's shortcut -- reporting a missing setback for a building the code
    forbids is how an encoding queue fills with work that cannot move a
    verdict.
    """
    layer, zone = key
    resolved = rules.resolve(layer, zone)

    assert resolved.values["quadplex_allowed"].value is False
    assert resolved.values["quadplex_allowed"].levers == frozenset()
    assert "quadplex_allowed" not in caps_for(layer, zone)


def test_but_the_district_the_note_was_written_about_still_carries_it(
    rules: RuleSet,
) -> None:
    """Narrowing is not deleting. CMF permits the quadplex outright, and
    whether the split-plat path exists there turns on a corridor nothing maps.
    """
    use = rules.resolve("or/multnomah/gresham", "CMF").values["quadplex_allowed"]

    assert use.value is True
    assert "civic_corridor" in use.levers


def test_gresham_cc_and_mc_are_one_column_printed_twice(rules: RuleSet) -> None:
    """Every cell of Table 4.0430 reads alike in both districts, so any drift
    between these two is a transcription error rather than a code difference.
    The one thing that legitimately differs is where the extraction wrapped."""
    cc = rules.resolve("or/multnomah/gresham", "CC").values
    mc = rules.resolve("or/multnomah/gresham", "MC").values

    assert {k: v.value for k, v in cc.items()} == {k: v.value for k, v in mc.items()}

    # Only what the zone rows themselves carry. A citywide standard reaches
    # every Gresham zone identically by construction, so it can say nothing
    # about whether two table columns were transcribed alike -- and pinning it
    # here means the next citywide standard anyone encodes fails this test
    # while the columns it guards are still perfectly in agreement. That is the
    # shape of a test that goes red for doing the work right.
    citywide = {k for layer in rules.chain_for("or/multnomah/gresham")
                for k in layer.defaults}
    assert {"parking_min_per_unit", "land_division_parent_standards"} <= citywide
    assert cc["parking_min_per_unit"].value == 0
    assert cc["land_division_parent_standards"].value is True
    assert {k: v.value for k, v in cc.items() if k not in citywide} == {
        "quadplex_allowed": False,
        "max_height_ft": 45,
        "min_density_du_per_acre": 12,
        "setback_front_ft": 0,
        "setback_side_ft": 0,
        "setback_rear_ft": 0,
        "setback_street_side_ft": 0,
        # Row H prints 10 feet. Note 3c drops it to five on a Collector,
        # Community or Local street, for any building, and street class is not
        # read here. This is a MAXIMUM, so the small number is the strict one --
        # the opposite of every minimum setback in the corpus, and the reason
        # this line is pinned rather than left to a reviewer's eye.
        "setback_front_max_ft": 5,
    }


def test_gresham_cc_is_a_window_rather_than_a_floor(rules: RuleSet) -> None:
    """The density pair is what binds here, and only together. Neither row says
    so on its own, which is why the zone notes say it and this test holds it:
    twelve units per net acre puts four units on no more than about 14,520 sq
    ft, forty per acre puts them on no less than about 4,356, and the lot-size
    row is None."""
    values = rules.resolve("or/multnomah/gresham", "CC").values
    layer = load_rules()["or/multnomah/gresham"]

    assert values["min_density_du_per_acre"].value == 12
    assert layer.zones["CC"].values["max_density_du_per_acre"].value == 40
    assert layer.zones["CC"].values["min_lot_sqft"].exempt is True
    assert layer.zones["CC"].values["min_frontage_ft"].exempt is True


def test_gresham_rtc_answers_the_height_question_in_storeys(rules: RuleSet) -> None:
    """Six storeys inside the Stark/Burnside/181st Triangle for exclusively
    commercial or institutional buildings, four inside it for buildings that
    include any other use, ten outside it. A building with dwellings in it is
    never the six-storey case; whether a lot is inside the Triangle is a map
    nothing here reads. Four is taken, and it cannot bind a 26 ft pod either
    way -- what this pins is that the field is answered at all, since
    `max_height_stories` stands in for `max_height_ft` in the required check."""
    values = rules.resolve("or/multnomah/gresham", "RTC").values

    assert values["max_height_stories"].value == 4
    assert "max_height_ft" not in values
    assert values["setback_front_ft"].value == 5
    assert values["setback_side_ft"].value == 0
    assert values["setback_rear_ft"].value == 15


def test_portland_ci1_takes_the_neighbours_setback_on_every_line(
    rules: RuleSet,
) -> None:
    """Table 150-2 gives CI1 three minimums by what the lot line faces -- 15 ft
    against OS or RF-R2.5, 10 against RM1-RMP or IR, 0 against a C, CI, E or I
    lot -- and no residual. Every line takes one of the three, and which one is
    the neighbour's zoning rather than this lot's, which nothing here reads. So
    15 on all four sides: the figure that cannot turn a RED lot green.

    IR one column over escapes this entirely; its column is a single merged
    cell measured off the building. See that zone's notes."""
    values = rules.resolve("or/multnomah/portland", "CI1").values

    assert values["setback_front_ft"].value == 15
    assert values["setback_side_ft"].value == 15
    assert values["setback_rear_ft"].value == 15
    # CI1's maximum building setback reads None, so note [5] -- no minimum
    # setback where a maximum applies -- never fires here. CI2 and IR both get
    # that relief on a transit street or in a Pedestrian District; CI1 does not.
    assert "setback_front_max_ft" not in values


def test_portland_ci1_gets_its_lot_minimum_from_the_far(rules: RuleSet) -> None:
    """33.150.200 states no minimum lot size anywhere in the campus zones, and
    then Table 150-2 sets CI1's floor area ratio at 0.5 to 1, the tightest in
    the corpus. Four units of a 56 by 36 ft pod over two floors is roughly
    4,000 sq ft of floor area, which at 0.5 asks for roughly 8,000 sq ft of
    site. The lot minimum arrives by the back door."""
    layer = load_rules()["or/multnomah/portland"]
    values = rules.resolve("or/multnomah/portland", "CI1").values

    assert layer.zones["CI1"].values["min_lot_sqft"].exempt is True
    assert values["max_far"].value == 0.5
    assert values["max_coverage_pct"].value == 50
    assert values["min_landscaped_pct"].value == 25


#: The zones allowed to owe a required standard, and the argument for each.
#: A silent gap and a declared one look identical in the ledger, which is the
#: whole reason this dictionary exists rather than a bare ``== []``: the first
#: is a zone somebody forgot to finish, the second is a city that states no
#: number and a corpus that refuses to invent one. Both cannot reach GREEN.
#: Only the second is allowed to.
#:
#: Both of these arrived on 2026-09-08, when the coverage ledger was rebuilt
#: over both counties. Neither is new encoding -- they were written months ago
#: with the deferral spelled out in the zone's own notes. What was new was a
#: ledger that could see the lots, and therefore ask.
DECLARED_OWING = {
    "or/clackamas/wilsonville/OTR": (
        "max_height_ft. 4.123(.06)A hands height, setbacks and lot coverage to "
        "the Old Town Residential Design Standards Book by name, and the book "
        "is not a stored document. There is no citywide figure to fall back "
        "on: 4.113(.03) Height Guidelines is discretionary -- a list of what "
        "the Development Review Board may regulate -- and states no number. "
        "Fetching the book is the close; guessing a height would be a "
        "false GREEN on 103 lots."
    ),
    "or/clackamas/happy-valley/MURX": (
        "max_height_ft, min_lot_sqft, setback_front_ft, setback_rear_ft and "
        "setback_side_ft. Table 16.22.060-2 is headed MUR-M1, MUR-M2 and "
        "MUR-M3 and carries no MUR-X column, so the chapter governing this "
        "district prints no dimensional standard for it at all -- not "
        "'Variable', not deferred, absent. MUR-M's 65 feet is deliberately not "
        "carried across, because that figure is printed in a table this "
        "district is not named in. quadplex_allowed is false here except on "
        "unit lots, so the gap keeps a live path and is left owing rather "
        "than exempted."
    ),
}


def test_every_zone_that_owes_a_required_field_says_why() -> None:
    """The guard, and the reason this file exists at all.

    Four zones once sat in the ledger owing five standards apiece and nobody
    saw it, because the committed `coverage.csv` predated the resolver change
    that started asking. A ledger is only a report of the run that wrote it, so
    the invariant has to be asserted somewhere that runs every time.

    It ran for months as ``owing == []`` and that was right while it held. It
    stopped holding the moment the ledger learned to count Clackamas: two zones
    that had always owed became visible, and both owe on purpose. An empty list
    would now be a lie in the other direction -- it would say the corpus states
    every required number, when what it states is that two cities do not and we
    declined to invent for them.

    A failure here means one of three things and all are worth stopping for: a
    zone was encoded without its required standards, a footnote ruling moved
    and unsettled a gate that used to be settled, or one of the two declared
    gaps was closed and this list was not."""
    owing = {
        f"{row.jurisdiction}/{row.zone}": row.missing_required
        for row in read_coverage()
        if row.missing_required
    }

    assert sorted(owing) == sorted(DECLARED_OWING)


def test_every_declared_gap_argues_from_the_page() -> None:
    """A reason with no section number in it is not a reason, it is a shrug.

    The same rule the district rulings are held to. Each of these has to name
    the clause that hands the number away, because the next reader's only
    defence against a stale deferral is being able to go and look."""
    for zone, reason in DECLARED_OWING.items():
        assert len(reason) > 120, zone
        assert any(ch.isdigit() for ch in reason), zone


def test_a_declared_gap_owes_exactly_what_it_says_it_owes() -> None:
    """The declaration names its fields, so the fields can be checked against
    it. A zone that quietly starts owing a sixth standard would otherwise hide
    behind a reason written for five."""
    owing = {
        f"{row.jurisdiction}/{row.zone}": row.missing_required.split(";")
        for row in read_coverage()
        if row.missing_required
    }

    for zone, fields in owing.items():
        reason = DECLARED_OWING[zone]
        for field in fields:
            assert field in reason, f"{zone} owes {field}, unmentioned"
