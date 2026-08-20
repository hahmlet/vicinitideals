"""Wood Village, where two thirds of the city talks about housing in code.

The four residential zones came from the quadfit port in July and list housing
types by name -- Tables 210-2 and 220-2 go all the way down to "Attached or
Detached Tri- or Quadplex". Nothing else in the city does. The commercial,
manufacturing and mixed industrial zones state one row, `Household Living`, and
leave what that covers to a definition three hundred sections away at WVDC
710.100. A reader searching those tables for the use by name finds nothing and
calls five zones silent; they are not silent, and 120 lots turn on it.

The interesting zone is NC, and it is interesting twice.

Its use answer is two sentences, not one. Table 230-1 reads CU on the Household
Living row -- so a hearing, not a refusal. Then 230.315.A.1 says residential is
permitted in NC "only when part of a mixed use development". Encoding the first
without the second would say a conditional use permit is enough to put a
stand-alone pod on a Halsey Street lot, and it is not.

And it has no lot standard at all. Not a small one, not a deferred one: WVDC
230.310.A states in prose that "there is no minimum lot size or dimension for
development of land or creation of new lots in commercial zones", Table 230-2
reads None on all three rows, and footnote (1) repeats it for residential uses
specifically. That is an absence somebody read, which is a different thing from
an absence nobody has looked at yet, and `exempt` is how the two stay apart.

O is left unread on purpose -- see the layer notes and the last test here.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules import conditions
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

WV = "or/multnomah/wood-village"
#: What the pod is, every time it is screened.
POD = ("multi_story", "attached_wall")
#: The four added here. Every one of them is answered by a `Household Living`
#: row rather than by a named housing type.
ADDED = ("NC", "TC", "C/I", "GM", "LM")
#: Settled refusals -- one cell each, and nothing else worth reading.
REFUSED = ("C/I", "GM", "LM")
#: Ported in July, off tables that do name the housing type.
PORTED = ("LR 7.5", "LR 12", "MR 2", "MR 4")


@pytest.fixture(scope="module")
def wv() -> Layer:
    return load_rules()[WV]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_layer_carries_nine_zones(wv: Layer) -> None:
    assert set(wv.zones) == set(ADDED) | set(PORTED)
    # Read and deliberately left out; see the O test below.
    assert "O" not in wv.zones


def test_the_non_residential_zones_answer_on_a_use_category(wv: Layer) -> None:
    """`Household Living`, defined at 710.100 and nowhere near the table.

    The definition is "the residential occupancy of a dwelling unit or a
    structure by a household" at thirty days or longer. It names no housing
    type and excludes none, so a four-unit attached townhome is inside it. Each
    of the four zones added here cites that definition alongside its own table,
    because the table alone does not say what its row means.
    """
    for zone in ADDED:
        notes = wv.zones[zone].notes or ""
        assert "Household Living" in notes, zone
        assert "710.100" in notes, zone
        assert "710.100" in wv.zones[zone].section, zone


def test_a_settled_refusal_owns_the_use_flag_and_nothing_else(wv: Layer) -> None:
    """Three zones, three values.

    Table 250-1 and Table 240-1 read N on both residential rows. General
    Manufacturing permits no dwelling of any kind -- not even the caretaker
    unit Troutdale's industrial zones carry -- and a zone that refuses the
    building never reaches a setback.
    """
    for zone in REFUSED:
        held = wv.zones[zone]
        assert set(held.values) == {"quadplex_allowed"}, zone
        assert held.values["quadplex_allowed"].value is False, zone
        assert held.values["quadplex_allowed"].variants == (), zone


def test_the_conditional_use_is_not_enough_on_its_own(
    wv: Layer, rules: RuleSet
) -> None:
    """NC needs a hearing AND a mixed use development, and the pod is neither.

    Table 230-1 says CU. 230.315.A.1 then says residential uses "shall be
    permitted only when part of a mixed use development" -- vertical or
    horizontal, but a development with a non-residential component in it. The
    section even lists what satisfies that: a thousand square feet of enclosed
    commercial space, a four-cart food pod, or a micro retail pod. None of them
    is a thing a fixed-dimension townhome does by itself.

    So the relief is a pair, and holding only half of it leaves the base false.
    That distinction is the whole reason the condition registry separates an
    `elective` from a `relief`: one is a business decision with a cost, the
    other is an application, and NC asks for both at once.
    """
    nc = wv.zones["NC"].values["quadplex_allowed"]
    assert nc.value is False
    assert {v.when for v in nc.variants} == {("conditional_use", "mixed_use")}

    assert rules.resolve(WV, "NC", POD).values["quadplex_allowed"].value is False
    only_hearing = rules.resolve(WV, "NC", (*POD, "conditional_use"))
    assert only_hearing.values["quadplex_allowed"].value is False
    both = rules.resolve(WV, "NC", (*POD, "conditional_use", "mixed_use"))
    assert both.values["quadplex_allowed"].value is True

    assert conditions.condition("conditional_use").kind == "relief"
    assert conditions.condition("mixed_use").kind == "elective"


def test_the_commercial_zone_states_no_lot_standard_at_all(wv: Layer) -> None:
    """Three rows reading None, and a footnote that means it.

    Encoded `exempt` rather than left off. An absent field and a field holding
    "the code was read and states no such standard" produce the same screen and
    a completely different ledger -- the first is work outstanding and the
    second is work done.
    """
    held = wv.zones["NC"].values
    for field in ("min_lot_sqft", "min_lot_width_ft", "min_lot_depth_ft"):
        assert held[field].exempt, field
        assert held[field].value is None, field
    # Same for the two yards Table 230-2 leaves open.
    for field in ("setback_side_ft", "setback_rear_ft"):
        assert held[field].exempt, field


def test_the_front_setback_is_bounded_from_both_ends(wv: Layer) -> None:
    """Three feet minimum and ten feet maximum, printed as one table row.

    The maximum is the standard that actually bites on Halsey Street, and it is
    not a lot test: 230.330.B.3.a asks seventy-five percent of the ground-level
    street-facing facade to sit inside the ten feet. A screen can place a
    building three feet off the line; it cannot say the facade qualifies.
    """
    held = wv.zones["NC"].values
    assert held["setback_front_ft"].value == 3
    assert held["setback_front_max_ft"].value == 10
    assert "seventy-five percent" in (wv.zones["NC"].notes or "")


def test_the_height_is_a_range_handed_to_a_map(wv: Layer) -> None:
    """Table 230-2 prints "45 - 55 feet (see Figure 230-3)".

    Figure 230-3 is a map and this system cannot read it, so 45 is encoded --
    the end of the range that is true everywhere in the zone rather than the
    end that is true somewhere. 230.335.C then steps the base down to 35 feet
    within twenty-five feet of an LR7.5 site, and to 45 within twenty-five feet
    of an MR2 site, each on a PORTION of the site rather than the whole of it.

    The pod is 26 feet. It clears the floor 230.335.A sets on Halsey Street --
    eighteen feet -- and clears every ceiling including the lowest step-down,
    so the unread map changes no verdict here. Recorded in the notes because
    the next building screened against this zone may not be 26 feet.
    """
    assert wv.zones["NC"].values["max_height_ft"].value == 45
    notes = wv.zones["NC"].notes or ""
    assert "Figure\n      230-3" in notes or "Figure 230-3" in notes
    assert "35 feet" in notes, "the step-down has to be readable where the 45 is"
    assert "eighteen feet" in notes, "so does the minimum height"


def test_every_encoded_zone_owes_nothing_more(rules: RuleSet) -> None:
    for zone in (*ADDED, *PORTED):
        assert rules.resolve(WV, zone).missing_required == (), zone


def test_the_open_space_zone_is_unread_rather_than_missed(wv: Layer) -> None:
    """WVDC 260.200 names Table 260-1 three times and never prints it.

    Outright uses, conditional uses, prohibited uses -- all three point at a
    table that does not come down with the page under this extractor. Six lots,
    and the honest state is unread. The section is declared and the document is
    stored anyway, so the absence is checkable by anyone who fetches it again
    rather than remembered by whoever hit it first.
    """
    assert "O" not in wv.zones
    assert "Table\n  260-1" in wv.notes or "Table 260-1" in wv.notes
    assert "260.200" in wv.notes
    ids = {d.id for d in wv.code}
    assert "260.200" in ids, "the unreadable page is stored, not skipped"


def test_the_new_citations_all_point_at_their_own_sentence(wv: Layer) -> None:
    ready = readiness_for(wv, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()


# --- the footnotes the census could not see until it learned Municode ------


def test_the_townhouse_standard_lives_in_a_footnote_and_is_ruled_on() -> None:
    """Table 210-3 states 12,000 square feet and 80 feet of width for LR12.

    Note (2) under it states the townhouse standard instead -- 1,500 square
    feet, 20 feet of width, no minimum depth, a zero side setback on the
    attached wall -- and none of that appears in the table. The July port had
    already read it and encoded it as the `unit_lots` band, so nothing screened
    wrong; but nothing said so, and a number that is right by luck is
    indistinguishable from one that is right on purpose until somebody writes
    down which.
    """
    from flats.encode.dispositions import notes

    ruled = {
        (n.doc.rsplit("/", 1)[-1], n.mark): n
        for n in notes()
        if n.layer == WV
    }
    townhouse = ruled[("210.320.txt", "2")]
    assert townhouse.state == "encoded"
    assert "unit_lots" in townhouse.encoded_as
    assert "1500" in townhouse.encoded_as


def test_the_band_the_footnote_became_is_the_one_the_pod_lands_in(
    rules: RuleSet,
) -> None:
    """A four-unit attached townhome on its own unit lots gets the 1,500.

    The point of ruling the note `encoded` is that the claim can be checked
    against the encoding rather than believed, so this checks it.
    """
    for zone, base in (("LR 7.5", 7500), ("LR 12", 12000)):
        plain = rules.resolve(WV, zone, POD)
        assert plain.values["min_lot_sqft"].value == base, zone
        divided = rules.resolve(WV, zone, (*POD, "unit_lots"))
        assert divided.values["min_lot_sqft"].value == 1500, zone
        assert divided.values["min_lot_width_ft"].value == 20, zone
        assert divided.values["setback_side_ft"].value == 0, zone


def test_a_footnote_is_scoped_to_the_table_it_sits_under() -> None:
    """Table 220-4 starts at five units; a quadplex is on Table 220-3.

    Three of this city's notes are dismissed on that one sentence, and they
    share it on purpose -- deleting the reason returns all three to `unread` in
    a single pass, which is what makes the rejection re-runnable rather than a
    decision nobody can revisit.
    """
    from flats.encode.dispositions import notes

    scoped = [
        n
        for n in notes()
        if n.layer == WV and "scoped to the table it sits under" in n.reason
    ]
    assert len(scoped) == 2
    assert all(n.state == "dismissed" for n in scoped)
    assert all(n.doc.endswith("220.320.txt") for n in scoped)


def test_every_footnote_in_this_city_is_ruled_on() -> None:
    """Sixteen captured, sixteen decided, and nothing left blocking.

    The five under Table 235-2 were held `unread` until the Town Center zone
    existed to rule them against, which is the order that keeps an `encoded`
    claim checkable.
    """
    from flats.encode.dispositions import notes

    unread = [
        n for n in notes() if n.layer == WV and n.state == "unread"
    ]
    assert unread == []


# --- the Town Center, where the zone does not work lot by lot -------------


def test_the_town_centre_adopts_the_mid_density_zone_by_reference(
    wv: Layer, rules: RuleSet
) -> None:
    """Table 235-2 says "Same as MR2 zone (see Tables 220-3 and 220-4)".

    Encoded as a pointer rather than a copy. Copies stop tracking their source
    the first time MR2 is amended, silently, and no reviewer looking at TC
    would have any way to notice -- so TC holds the reference and whatever it
    states for itself, and every value resolved through it still cites the 220
    section it was actually read from.
    """
    assert wv.zones["TC"].like is not None
    assert wv.zones["TC"].like.zone == "MR 2"
    assert wv.zones["TC"].like.wins == "local"

    tc = rules.resolve(WV, "TC", POD).values
    mr2 = rules.resolve(WV, "MR 2", POD).values
    for field in ("min_lot_sqft", "min_lot_width_ft", "min_lot_depth_ft"):
        assert tc[field].value == mr2[field].value, field
    # And what the table states for itself wins over what it points at.
    assert tc["setback_garage_entrance_ft"].value == 20
    assert mr2["setback_garage_entrance_ft"].value == 22


def test_the_two_columns_of_the_town_centre_table(wv: Layer) -> None:
    """35 feet of residential height against 115 nonresidential.

    The widest split in this city's tables, and note (1) is the switch between
    them: residential floors inside a mixed use structure are regulated as the
    mixed use. The pod is a stand-alone residential building, so the residential
    column is what is encoded -- and it is the stricter one on every row, which
    is the safe direction to have read it.
    """
    held = wv.zones["TC"].values
    assert held["max_height_ft"].value == 35
    assert held["setback_side_ft"].value == 5
    assert held["setback_rear_ft"].value == 15


def test_the_step_down_the_pod_is_one_foot_from_failing_caps_the_zone() -> None:
    """Note (2) puts 25 feet within 25 feet of a light residential zone.

    The pod is 26. The marker is glued to the nonresidential column's 115 feet
    rather than the residential column's 35, which is an argument for
    dismissing it and not a good enough one -- a step-down exists to transition
    to the neighbours and a 35-foot residential building is no less of a
    transition. So it is ruled `unmeasured` on a fact nobody holds, which costs
    the zone its GREEN and keeps the reading honest.
    """
    from flats.encode.dispositions import notes

    capped = [
        n
        for n in notes()
        if n.layer == WV and n.state == "unmeasured"
    ]
    assert len(capped) == 2
    assert {n.fact for n in capped} == {"abuts_lower_density_zone"}
    assert conditions.condition("abuts_lower_density_zone").assume is None


def test_the_town_centre_records_what_a_green_there_does_not_mean(
    wv: Layer,
) -> None:
    """This is the one zone in the city that is not screened lot by lot.

    235.490 runs Town Center development through a Development Plan, 235.410
    organises every street onto Figure 235-1 and 235.420 requires intersections,
    gateways and plazas at locations shown on it, and Table 235-5 then states
    frontage standards by the street type a parcel fronts. None of that is
    readable here. What is encoded is the dimensional envelope Table 235-2
    states -- which is the half a fitment screen exists to answer, and 167 lots
    is too many to leave unread because the other half is out of reach.
    """
    notes_text = wv.zones["TC"].notes or ""
    for phrase in ("Development Plan", "Figure 235-1", "Table 235-5", "0.4"):
        assert phrase in notes_text, phrase
    # The open space requirement is a number, so it is encoded rather than
    # described -- twenty percent of the plan area under 235.465.
    assert wv.zones["TC"].values["open_space_min_pct"].value == 20
