"""The two files that hold a zone's dimensions, checked against each other.

`config/rules.yaml` is what the pipeline screens with. The FLATS corpus is what
was actually read -- every figure quoted to a line of a stored document. They
were written a month apart by the same hand from different sources and had
never been compared. The first comparison found twenty-eight differences.

Twenty-one of those were drift and all twenty-one are now resolved, every one
of them in the corpus's favour. The mistake behind most of them was a single
recurring one worth naming, because it will happen again: **rules.yaml had been
reading the detached house's row of a table that prints one row per housing
type.** A quadplex is not a house, and the codes say so in the same table --
Oregon City gives it 70 percent lot coverage where the house gets 50, Happy
Valley 60 against 50, Milwaukie a 3,000 sq ft minimum lot against the 5,000
that governs "all other uses". Screening on the house's row threw those lots
away for nothing. It ran the other way once: Milwaukie R-HD was drawn on a
5-foot front setback that the code applies only to properties mapped in a
figure, where the general standard is 20.

What is left is not drift, and each kind has its own list below because each
closes in a different way. Nothing here is a clean bill: the lists are a
ratchet. A new divergence fails, and so does resolving one without editing this
file. That is the friction you want, because each row needs a reader deciding
which side was right, and a silent list would grow forever.
"""

from __future__ import annotations

import io

import pytest
import yaml

pytestmark = pytest.mark.unit

#: Dimensions where one file was edited and the other was not. Empty, and it
#: took working through twenty-one rows to get there -- see the module
#: docstring for the pattern. It closes by somebody reading the code and
#: editing whichever file was wrong.
KNOWN_DIVERGENT: frozenset[str] = frozenset()

#: Empty since 2026-09-02, and it took the feature rather than seven edits.
#: These were the seven dimensions where rules.yaml held the number the district
#: table PRINTS and the corpus held what a 26-foot building actually stands at:
#: Gresham 7.0420(G)(1) caps the roof at 21 ft on the rear setback line and lets
#: it rise a foot per foot beyond; Milwaukie states the same rule as a
#: 45-degree side yard height plane. rules.yaml now declares the plane beside
#: the printed setback and `common.StepBack` derives the rest, so no file holds
#: a figure a reader could not find on the page.
#:
#: The list stays because the thing it caught can happen again, and always in
#: the dangerous direction: a corpus step-back the pipeline has not declared
#: means the screen thinks the pod can stand closer to the line than it can.
KNOWN_STEP_BACK_GAPS: frozenset[str] = frozenset()

#: Also not drift, and the one place rules.yaml is RIGHT and the corpus is
#: merely richer. Lake Oswego asks 5 feet on one side and 15 across both.
#: rules.yaml has one symmetric side field and no combined field, so 7.5 is the
#: only number it can hold that satisfies the rule; "correcting" it to the
#: corpus's per-side 5 would screen a 10-foot combined yard against a code that
#: demands 15, which is a false green. Closes when the pipeline grows a
#: combined-side-yard field, not before.
KNOWN_SIDE_TOTAL_COLLAPSE: frozenset[str] = frozenset({
    "lake_oswego/R-7.5.setback_side_ft",
})

#: Dimensions inside a zone whose permission the two files dispute. Reconciling
#: these one number at a time would be answering a question nobody has asked:
#: if Wilsonville's RN really does bar the quadplex, none of its lots is
#: screened and none of these five figures matters. Closes with the permission
#: question, in one go.
KNOWN_PERMISSION_BLOCKED: frozenset[str] = frozenset({
    "wilsonville/RN.setback_front_ft",
    "wilsonville/RN.setback_rear_ft",
    "wilsonville/RN.min_lot_sqft",
    "wilsonville/RN.max_coverage_pct",
    "wilsonville/RN.min_frontage_ft",
})

#: Zones where the two files disagree about whether a quadplex is permitted.
#: Both of these have rules.yaml saying yes and the corpus saying no, which is
#: the dangerous direction -- if the corpus is right, every lot in the zone is
#: being screened for a building the code does not allow.
KNOWN_PERMISSION_SPLITS: frozenset[str] = frozenset({
    "multnomah_unincorporated/LR7",
    "wilsonville/RN",
})


def _audit():
    """The quadfit conftest puts this directory on the path, as it does for
    `common`; loading the file by hand instead leaves the module out of
    `sys.modules`, and a dataclass whose module cannot be found back fails to
    build its own fields."""
    import audit_zone_mirror

    return audit_zone_mirror


def _rules() -> dict:
    audit = _audit()
    doc = yaml.safe_load(io.open(audit.RULES, encoding="utf-8"))
    return doc.get("jurisdictions", doc)


def _zone(juris: str, zone: str) -> dict:
    return [z for z in _rules()[juris]["zones"] if z["zone"] == zone][0]


def test_the_two_files_no_longer_drift() -> None:
    """A ratchet in both directions, now sitting at zero.

    Frozen as a set of keys rather than a count, so the failure message names
    the zone. A new row means somebody edited one file and not the other; a
    missing row means somebody resolved a divergence, which is good and still
    has to be recorded here.
    """
    audit = _audit()
    diverge, _uncited, agree = audit.scan()
    found = {d.key for d in diverge if d.is_drift}

    new = sorted(found - KNOWN_DIVERGENT)
    fixed = sorted(KNOWN_DIVERGENT - found)
    detail = {d.key: str(d) for d in diverge}
    assert not new, (
        "rules.yaml and the corpus have drifted apart on a dimension nobody "
        f"recorded: {[detail[k] for k in new]}"
    )
    assert not fixed, (
        f"these divergences are gone -- remove them from KNOWN_DIVERGENT: {fixed}"
    )
    # The agreements are the reason the small lists are worth keeping small.
    assert agree > 440


def test_the_quadplex_row_is_the_one_that_gets_read() -> None:
    """The eight numbers that came out of the drift work, pinned.

    Every one of them was rules.yaml reading a housing-type table on the
    detached house's line. They are pinned individually rather than left to the
    drift test because the drift test only proves the two files agree -- if
    somebody "corrects" both back to the house's row it would still pass, and
    these lots would go quietly missing again.
    """
    # Oregon City Table 17.10.040: "Triplex, quadplex and townhouse" coverage,
    # against 50/55 for "Single-family detached and duplex".
    assert _zone("oregon_city", "R-5")["max_coverage_pct"] == 70
    assert _zone("oregon_city", "R-3.5")["max_coverage_pct"] == 80

    # Happy Valley Table 16.22.040-2, same shape: the quadplex has its own lot
    # size row (7,000 against 5,000) and shares the 60 percent coverage row
    # with the duplex, triplex and townhome.
    hv = _zone("happy_valley", "R5")
    assert (hv["min_lot_sqft"], hv["max_coverage_pct"]) == (7000, 60)

    # Milwaukie bands permitted dwelling type by lot size; the quadplex starts
    # at the 3,000-4,999 band. The 5,000 both zones carried is the "all other
    # uses" line. R-HD's front setback of 5 ft is a mapped-properties rule.
    hd = _zone("milwaukie", "R-HD")
    assert (hd["min_lot_sqft"], hd["setback_front_ft"], hd["setback_rear_ft"]) == (
        3000, 20, 15
    )
    assert _zone("milwaukie", "R-MD")["min_lot_sqft"] == 3000

    # Gladstone prints "Detached single household 7,200 / Middle housing 3,600"
    # in R-7.2 and a quadplex row of its own in R-5. Opposite directions, same
    # mistake.
    assert _zone("gladstone", "R7.2")["min_lot_sqft"] == 3600
    assert _zone("gladstone", "R5")["min_lot_sqft"] == 7000


def test_no_step_back_in_the_corpus_is_missing_from_the_pipeline() -> None:
    """The seven are closed, and the guard that found them still runs.

    This list held seven dimensions for as long as the pipeline had no way to
    say "the roof is capped at the setback line". It has one now: rules.yaml
    declares the plane next to the printed setback and the envelope derives
    what a `DESIGN_HEIGHT_FT` building owes.

    What must never come back is the failure that put them here. A corpus
    step-back the pipeline has not declared means the screen is standing the
    pod closer to the line than the code allows, which is a green that should
    not exist. Nobody has to remember to check; this does.
    """
    audit = _audit()
    diverge, _uncited, _agree = audit.scan()
    found = {d.key for d in diverge
             if not d.is_permission_blocked and d.is_step_back}
    assert found == KNOWN_STEP_BACK_GAPS, sorted(found ^ KNOWN_STEP_BACK_GAPS)


def test_the_declared_planes_derive_the_corpus_figure() -> None:
    """The seven numbers are computed, and this is what they compute to.

    Pinned as arithmetic rather than as constants, because that is the point of
    the feature: change `DESIGN_HEIGHT_FT` and every one of these moves on its
    own. A 20-foot pod would owe Gresham nothing extra at all -- the roof is
    allowed to be 21 at the line -- and this asserts that too, so a future
    reader can see the plane is a rule and not a fudge.

    Gresham 7.0420(G)(1) and Milwaukie's Table 19.301.4 / 19.302.4 planes state
    the same geometry two ways: a rate ("one foot in height for every one foot
    of distance") and an angle ("Slope of plane (degrees) 45"). Both spellings
    are carried, so this walks both.
    """
    from common import DESIGN_HEIGHT_FT, load_rules

    rules = load_rules()

    def rule(juris: str, zone: str):
        return rules.jurisdictions[juris].rule_for(zone)

    # Gresham: 21 ft allowed at the line, 1 ft of height per foot beyond.
    for zone, printed in (("LDR-5", 15), ("LDR-7", 15), ("TR", 15),
                          ("LDR-SW", 15), ("LDR-PV", 10)):
        zr = rule("gresham", zone)
        assert zr.setback_rear_ft == printed, "the printed figure must not move"
        assert zr.step_back_rear is not None and zr.step_back_rear.height_ft == 21
        assert zr.effective_setback_rear_ft() == printed + (DESIGN_HEIGHT_FT - 21)
        # A building short enough to fit under the plane owes nothing.
        assert zr.effective_setback_rear_ft(21) == printed
        assert zr.effective_setback_rear_ft(12) == printed

    # Milwaukie: the same 1:1 plane written as 45 degrees, starting at the
    # required yard rather than the lot line (MMC 19.200).
    for zone, at_ft, effective in (("R-MD", 20, 11), ("R-HD", 25, 6)):
        zr = rule("milwaukie", zone)
        assert zr.setback_side_ft == 5, "the printed figure must not move"
        sb = zr.step_back_side
        assert sb is not None and sb.slope_degrees == 45
        assert round(sb.rise, 6) == 1.0, "45 degrees is a 1:1 plane"
        assert zr.effective_setback_side_ft() == pytest.approx(effective)
        assert zr.effective_setback_side_ft(at_ft) == 5

    # And the plane only ever pushes the building AWAY from the line.
    for juris, zones in (("gresham", ("LDR-5", "LDR-7", "TR", "LDR-SW", "LDR-PV")),
                         ("milwaukie", ("R-MD", "R-HD"))):
        for zone in zones:
            zr = rule(juris, zone)
            assert zr.effective_setback_rear_ft() >= zr.setback_rear_ft
            assert zr.effective_setback_side_ft() >= zr.setback_side_ft


def test_a_collapsed_combined_side_yard_is_not_a_mistake() -> None:
    """The one row where rules.yaml is right and the corpus is only richer.

    Lake Oswego states both halves of the rule -- 5 feet on one side, 15 across
    both -- and the corpus holds both. rules.yaml has a single symmetric side
    field, so the only number it can carry that satisfies the combined test is
    half of it. Editing it to the corpus's per-side 5 would look like fixing a
    divergence and would screen a 10-foot combined yard against a code that
    asks 15.
    """
    audit = _audit()
    diverge, _uncited, _agree = audit.scan()
    found = {d.key for d in diverge
             if not d.is_permission_blocked and not d.is_step_back
             and d.is_side_total_collapse}
    assert found == KNOWN_SIDE_TOTAL_COLLAPSE, sorted(
        found ^ KNOWN_SIDE_TOTAL_COLLAPSE
    )

    for d in diverge:
        if d.is_side_total_collapse:
            assert d.shipped * 2 == d.side_total
            # The corpus base is the SMALLER number here, which is exactly why
            # this cannot be treated as drift and reconciled downward.
            assert d.shipped > d.corpus[0]


def test_the_two_files_disagree_about_the_use_in_exactly_two_zones() -> None:
    """The worst kind of divergence, and the shortest list.

    A setback that is five feet out moves a lot between green and review. A
    `quadplex_allowed` that is out decides whether the zone is screened at all,
    and both of these have the pipeline screening a zone the corpus reads as
    closed to the pod. Neither is resolved: unincorporated Multnomah never
    wrote HB 2001 into MCC, and Wilsonville's RN was flipped to false on
    4.127(.02)B.1.a.ii, "quadplexes are not permitted", against a state
    preemption argument that is real but untested.
    """
    audit = _audit()
    splits = audit.permission_splits()
    keys = {s.split(":")[0] for s in splits}
    assert keys == KNOWN_PERMISSION_SPLITS, splits


def test_rn_dimensions_wait_on_the_rn_permission() -> None:
    """Five numbers held behind one question.

    RN's dimensional differences are real, but reconciling them would mean
    picking a Frog Pond West sub-district table on behalf of a zone that may
    turn out to be closed to this building entirely. They are listed so they
    are not mistaken for agreement, and pinned to the permission split so that
    answering that question is what releases them.
    """
    audit = _audit()
    diverge, _uncited, _agree = audit.scan()
    found = {d.key for d in diverge if d.is_permission_blocked}
    assert found == KNOWN_PERMISSION_BLOCKED, sorted(
        found ^ KNOWN_PERMISSION_BLOCKED
    )
    for d in diverge:
        if d.is_permission_blocked:
            assert d.zone_key in KNOWN_PERMISSION_SPLITS


def test_the_village_zone_mirrors_exactly() -> None:
    """Wilsonville V, added 2026-09-01, and the point of adding the audit.

    Every number the site plan will screen 2,508 Villebois lots with came out
    of the corpus reading rather than beside it, so there is nothing here for
    the divergence list to catch. That is what a zone written after the audit
    exists looks like.
    """
    audit = _audit()
    diverge, _uncited, _agree = audit.scan()
    assert not [d for d in diverge if d.jurisdiction == "wilsonville"
                and d.zone == "V"]

    v = _zone("wilsonville", "V")
    assert v["quadplex_allowed"] is True
    assert v["min_lot_sqft"] == 7000
    assert v["setback_front_ft"] == 20
    assert v["confidence"] == "needs_verification"


#: The fifteen dimensions the two files hold under different names, split by
#: whether the two names measure the same line on the ground. Frozen as keys so
#: a newly encoded city cannot join either list silently -- the whole point is
#: that the safe half and the unsafe half look identical until somebody reads
#: the table heading.
KNOWN_ALIAS_SAME_EDGE: frozenset[str] = frozenset({
    "west_linn/R-40.min_frontage_ft", "west_linn/R-20.min_frontage_ft",
    "west_linn/R-15.min_frontage_ft", "west_linn/R-10.min_frontage_ft",
    "west_linn/R-7.min_frontage_ft", "west_linn/R-5.min_frontage_ft",
    "west_linn/R-4.5.min_frontage_ft", "west_linn/R-3.min_frontage_ft",
    "west_linn/R-2.1.min_frontage_ft",
})

KNOWN_ALIAS_WRONG_EDGE: frozenset[str] = frozenset({
    "oregon_city/R-10.min_frontage_ft", "oregon_city/R-8.min_frontage_ft",
    "oregon_city/R-6.min_frontage_ft", "oregon_city/R-5.min_frontage_ft",
    "oregon_city/R-3.5.min_frontage_ft", "tualatin/RL.min_frontage_ft",
})


def test_the_frontage_numbers_are_quoted_after_all() -> None:
    """These fifteen read as uncited and were not.

    rules.yaml calls the standard `min_frontage_ft`; the corpus reads it off a
    row headed "Minimum lot width" and files it under that name. Every number
    matches a limb of the corpus value, which is the part that is fine. The
    part that is not fine is the next test.
    """
    audit = _audit()
    alias = audit.aliases()
    assert {a.key for a in alias} == (
        KNOWN_ALIAS_SAME_EDGE | KNOWN_ALIAS_WRONG_EDGE
    ), sorted({a.key for a in alias} ^ (KNOWN_ALIAS_SAME_EDGE | KNOWN_ALIAS_WRONG_EDGE))

    disagree = [str(a) for a in alias if not a.agrees]
    assert not disagree, (
        "a rules.yaml frontage number no longer matches the width standard it "
        f"was read from: {disagree}"
    )

    # And they are gone from the uncited list, which is what they were mistaken
    # for before anyone looked at the field names.
    _diverge, uncited, _agree = audit.scan()
    assert not [u for u in uncited if "min_frontage_ft" in u], uncited


def test_six_of_them_measure_the_wrong_line_on_the_lot() -> None:
    """The finding, frozen.

    s7 compares a lot's measured `frontage_ft` -- boundary that touches a
    street -- against `min_frontage_ft`. Oregon City 17.04.700 defines lot
    width "between the midpoints of the two principal opposite side lot lines";
    Tualatin TDC 31.060 measures it "at the center of the lot". Neither is the
    street edge. West Linn heads its row "Minimum lot width AT FRONT LOT LINE",
    which is, and that is the only reason its nine are safe.

    896 Oregon City lots and 92 Tualatin lots are excluded at
    `below_min_frontage` today, and 605 of them already fit the pod inside
    their own envelope -- drawn, clearing every setback, killed at a gate three
    steps before anything looked at the building. Closing this needs a
    lot-width measurement the pipeline does not take; deleting the gate instead
    would buy at most those 605 back at the price of an unknown number of false
    greens.
    """
    audit = _audit()
    alias = audit.aliases()
    same = {a.key for a in alias if a.same_edge}
    wrong = {a.key for a in alias if not a.same_edge}

    assert same == KNOWN_ALIAS_SAME_EDGE, sorted(same ^ KNOWN_ALIAS_SAME_EDGE)
    assert wrong == KNOWN_ALIAS_WRONG_EDGE, sorted(wrong ^ KNOWN_ALIAS_WRONG_EDGE)

    # A jurisdiction earns the safe list by a reason somebody wrote down, not
    # by being absent from the unsafe one.
    for a in alias:
        if a.same_edge:
            assert "FRONT LOT LINE" in a.why, a.key


def test_nothing_in_the_screen_is_unquoted() -> None:
    """The uncited list is empty, and it took two corrections to get there.

    Fifteen rows were a naming difference. The other eighteen were three zones
    that adopt another zone's standards by reference -- Fairview R/SFLD says the
    R-10 chapter applies, RM/TOZ says RM, Happy Valley R20CC says R20 -- which
    is how the corpus encodes an incorporation so it keeps tracking its source.
    An audit that reads a zone's own block and stops sees three unread zones and
    would send somebody off to read code that has already been read.

    Zero here means every dimension the pipeline screens with is quoted to a
    line of a stored document. It is the strongest claim this file makes, so it
    is pinned rather than printed.
    """
    audit = _audit()
    _diverge, uncited, agree = audit.scan()
    assert uncited == [], uncited
    assert agree > 460, agree


def test_an_adopted_zone_reports_the_standards_it_adopts() -> None:
    """The mechanism behind the row above, tested where it is load-bearing.

    R/SFLD is a Metro map label, not a chapter of the Fairview code. The layer
    holds it as a pointer at R-10 and nothing else; resolving it has to produce
    R-10's numbers or the audit is comparing rules.yaml against an empty zone
    and calling the silence agreement.
    """
    audit = _audit()
    from flats.rules.loader import load_rules

    layer = load_rules()["or/multnomah/fairview"]
    sfld = layer.zones["R/SFLD"]
    assert sfld.like is not None and sfld.like.zone == "R-10"
    assert "min_lot_sqft" not in sfld.values, "R/SFLD states its own lot size now"

    effective = audit._effective(layer, sfld)
    r10 = layer.zones["R-10"]
    assert effective["min_lot_sqft"].value == r10.values["min_lot_sqft"].value


#: Zones the corpus says permit a four-plex and rules.yaml has no entry for, so
#: `s3_filter` drops every lot in them at `zone_not_in_rules` before anything is
#: measured. Counted for the first time on 2026-09-02 and worth **76,752 lots**
#: -- 30% of the universe, and the largest recoverable pool measured to date.
#: Lake Oswego is listed and contributes none of them: the jurisdiction is
#: `eligible: false` by owner decision, so its rows are reference rather than
#: debt. Portland is 74,446 of the 76,752.
#:
#: It survived five weeks because the direction is safe: a lot the screen never
#: looks at cannot come back green by mistake. That is also why nothing reported
#: it. Every ledger in this project counts what it was pointed at, and the audit
#: that compares these two files compared them NUMBER BY NUMBER, for zones they
#: both hold. Neither had ever been read as a LIST.
#:
#: Frozen so the debt cannot grow while it is being paid down. A zone leaves
#: this list by being encoded in rules.yaml, never by being deleted from it.
UNSCREENED_ZONES: dict[str, tuple[str, ...]] = {
    "gresham": ("CMU", "HDR-PV", "MDR-PV", "OFR", "SC", "SC-RJ", "VLDR-SW"),
    "happy_valley": ("MURA", "SFA", "VTH"),
    "lake_oswego": ("R-10", "R-15", "R-2", "R-6", "R-DD", "R-W"),
    "multnomah_unincorporated": ("MR4", "R5"),
    "portland": ("CE", "CI2", "CM1", "CM2", "CM3", "CR", "CX", "EX", "IR",
                 "RM1", "RM2", "RM3", "RM4", "RX"),
    "troutdale": ("MU-2", "MU-3"),
    "wood_village": ("TC",),
}


def test_a_zone_missing_from_the_pipeline_is_a_debt_somebody_wrote_down() -> None:
    """The gap that comparing numbers could never find.

    Two files carry a zone's dimensions and they had been checked against each
    other figure by figure, for every zone they both hold. That is not the same
    as checking the LISTS. Doing that on 2026-09-02 found 35 zones the corpus
    says a four-plex is permitted in and rules.yaml has never heard of --
    Portland's RM1, RM2, EX, CM2 and CX among them, which is 74,446 of the
    76,752 lots involved.

    Every one of those lots is dropped at `zone_not_in_rules` before it is
    measured, so nothing about it can ever be wrong in the dangerous direction.
    That is precisely why it lasted: safety made it silent.

    This list may SHRINK, by encoding the zone. It may not grow, and a zone may
    not leave it by being removed from the corpus.
    """
    audit = _audit()
    found = {j: tuple(z) for j, z in audit.unscreened_zones().items()}
    assert found == UNSCREENED_ZONES, (
        "zone coverage moved: "
        f"{sorted(set(found) ^ set(UNSCREENED_ZONES))} differ by jurisdiction, "
        f"and per-jurisdiction "
        f"{ {j: sorted(set(found.get(j, ())) ^ set(UNSCREENED_ZONES.get(j, ()))) for j in set(found) | set(UNSCREENED_ZONES)} }"
    )
