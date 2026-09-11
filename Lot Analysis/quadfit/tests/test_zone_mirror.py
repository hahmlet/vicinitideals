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
from datetime import date

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


def test_neither_disputed_permission_can_reach_a_green() -> None:
    """The assertion the list above cannot make, and the one that matters.

    Both rows claim a permission the corpus denies, which is the direction that
    manufactures greens -- and neither can, because both carry
    `confidence: needs_verification` and s7 caps such a lot at REVIEW however
    much else it clears. That is the whole reason the rows are allowed to stand
    while the legal question waits for a person: the looser permission buys the
    zone a measurement, not a verdict.

    So this is not a restatement of the count. If somebody promotes either row
    to `verified` without settling the preemption argument behind it, the count
    above does not move and 664 lots become eligible for a green list on a
    reading the corpus rejects. This test is what goes red instead.
    """
    audit = _audit()

    assert audit.live_permission_splits() == []
    for s in audit.permission_splits():
        assert "[capped at review by needs_verification]" in s


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


#: The dimensions the two files hold under different names, split by whether
#: the two names measure the same line on the ground. Frozen as keys so a
#: newly encoded city cannot join either list silently -- the whole point is
#: that the safe half and the unsafe half look identical until somebody reads
#: the table heading.
KNOWN_ALIAS_SAME_EDGE: frozenset[str] = frozenset({
    "west_linn/R-40.min_frontage_ft", "west_linn/R-20.min_frontage_ft",
    "west_linn/R-15.min_frontage_ft", "west_linn/R-10.min_frontage_ft",
    "west_linn/R-7.min_frontage_ft", "west_linn/R-5.min_frontage_ft",
    "west_linn/R-4.5.min_frontage_ft", "west_linn/R-3.min_frontage_ft",
    "west_linn/R-2.1.min_frontage_ft",
})

#: EMPTY since 2026-09-11, and it held seven rows for a year before that: six
#: Oregon City zones and Tualatin's RL, every one a mid-lot WIDTH -- OCMC
#: 17.04.700 "between the midpoints of the two principal opposite side lot
#: lines", TDC 31.060 "at the center of the lot" -- carried in a street
#: frontage column because there was no other, and judged against the street
#: edge because that is what the column is judged against. They left by a
#: column: `ZoneRule.min_lot_width_ft` exists, the seven numbers moved into
#: it, and MIRRORED compares them under their own name. The list stays because
#: the way onto it is still open -- port a city's "lot width" into
#: `min_frontage_ft` and it lands here -- and the way off is the same as it
#: was: move the number, name the measure.
KNOWN_ALIAS_WRONG_EDGE: frozenset[str] = frozenset()


def test_the_frontage_numbers_are_quoted_after_all() -> None:
    """These nine read as uncited and were not.

    rules.yaml calls the standard `min_frontage_ft`; the corpus reads it off a
    row headed "Minimum lot width" and files it under that name. Every number
    matches a limb of the corpus value, which is the part that is fine. The
    part that has to stay fine is the next test.
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


def test_none_of_them_measure_the_wrong_line_on_the_lot() -> None:
    """The finding, frozen -- at zero, which is where it took a column to get.

    s7 compares a lot's measured `frontage_ft` -- boundary that touches a
    street -- against `min_frontage_ft`. Oregon City 17.04.700 defines lot
    width "between the midpoints of the two principal opposite side lot lines";
    Tualatin TDC 31.060 measures it "at the center of the lot". Neither is the
    street edge, and for a year both sat in the frontage column and were
    judged against it: 896 Oregon City lots and 92 Tualatin lots excluded at
    `below_min_frontage` on a line the code never measured, 605 of them
    already fitting the pod inside their own envelope.

    Since 2026-09-11 those numbers live in `min_lot_width_ft`, s4 takes the
    measurement each city's glossary describes, and the alias fires only in
    West Linn, whose tables head the row "Minimum lot width AT FRONT LOT
    LINE". That is the only reason its nine are safe, and it is asserted
    below rather than assumed.
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
    # All that is left of the 35. The other 29 were ported on 2026-09-02 and
    # every one arrived `needs_verification`, so their lots reach REVIEW rather
    # than GREEN -- work to do, not lots to buy.
    #
    # Lake Oswego's six stay, and they are not debt: the jurisdiction is
    # `eligible: false` by owner decision, so nothing screens there at all and
    # a zone the screen never reaches costs nothing. They are listed because a
    # decision that can be reversed should leave its consequences visible.
    "lake_oswego": ("R-10", "R-15", "R-2", "R-6", "R-DD", "R-W"),
}


#: The same silence, arrived at the other way round, and it needs its own name
#: because the ratchet above cannot hold it.
#:
#: :data:`UNSCREENED_ZONES` was frozen on the assumption that the list could
#: only grow through neglect -- somebody encoding a zone in the corpus and not
#: carrying it across. On 2026-09-08 it grew twice in one evening for the
#: opposite reason: the corpus is being extended faster than ``rules.yaml``, on
#: purpose, because FLATS replaces this pipeline rather than feeding it.
#:
#: WHY THESE ARE NOT SIMPLY PORTED, which is the question the frozen list
#: answers with "they should be". Nine of the ten hang on a condition
#: ``rules.yaml`` has no way to write down:
#:
#:   * Oregon City's five state their setbacks twice -- "Minimum required
#:     setbacks if not abutting a residential zone: None", and twenty feet
#:     where it does abut one. The corpus holds that as a base value with a
#:     variant keyed on `abuts_residential_zone`, an unmeasured site fact, so
#:     the screen returns UNKNOWN rather than GREEN. ``rules.yaml`` holds one
#:     number per field. Porting the zero produces a measurement that is wrong
#:     on exactly the lots where the standard bites; porting the twenty
#:     disagrees with the corpus, and the number-by-number half of this same
#:     audit would then report it as drift. Neither is the truth.
#:   * MR-1 and MR-2 in unincorporated Clackamas are the same shape through
#:     Table 315-4's note 14, ruled `unmeasured` against
#:     `abuts_lower_density_zone`.
#:
#: The tenth, PMD, could be ported and is held with the other three so the
#: reason for the group stays one reason.
#:
#: This list is not frozen the way the one above is. It may grow, because the
#: corpus is meant to; what it may not do is grow SILENTLY, which is the whole
#: property this test defends. Every entry names the zone, and the assertion
#: below fails the moment one appears that nobody has written a line for.
AHEAD_OF_QUADFIT: dict[str, tuple[str, ...]] = {
    # Encoded 2026-09-08 off the top of the rebuilt two-county coverage
    # ledger. R-2.5 was encoded in the same pass and is absent here because it
    # is a prohibition -- `unscreened_zones` counts only zones that permit the
    # pod, and a zone that forbids it costs the pipeline nothing to not know.
    "clackamas_unincorporated": ("MR1", "MR2", "PMD", "VA"),
    # Oregon City's commercial and mixed-use side, encoded 2026-09-08. The
    # five that permit a quadplex; MUE, I, GI, CI, HC and NC were encoded in
    # the same pass as refusals and so are not here.
    "oregon_city": ("C", "MUC-1", "MUC-2", "MUD", "WFDD"),
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

    It grew anyway on 2026-09-08, and the growth was correct: the corpus is
    now being extended faster than ``rules.yaml``, deliberately, because FLATS
    replaces this pipeline rather than feeds it. So the assertion is against
    :data:`UNSCREENED_ZONES` and :data:`AHEAD_OF_QUADFIT` together -- the first
    still frozen as debt, the second an open list that may grow and may not
    grow silently. Whichever side a zone is on, appearing on neither is what
    fails.
    """
    audit = _audit()
    found = {j: tuple(z) for j, z in audit.unscreened_zones().items()}
    expected = {
        j: tuple(sorted(set(UNSCREENED_ZONES.get(j, ())) | set(AHEAD_OF_QUADFIT.get(j, ()))))
        for j in set(UNSCREENED_ZONES) | set(AHEAD_OF_QUADFIT)
    }
    assert found == expected, (
        "zone coverage moved: "
        f"{sorted(set(found) ^ set(expected))} differ by jurisdiction, "
        f"and per-jurisdiction "
        f"{ {j: sorted(set(found.get(j, ())) ^ set(expected.get(j, ()))) for j in set(found) | set(expected)} }"
    )


#: Standards the corpus reads, cites and holds on a zone BOTH files carry, that
#: rules.yaml has no column for and that reach the pipeline no other way. The
#: step-back was one of these and it took a feature to close; this is the rest
#: of the list, with the number of zones each one is silent on.
#:
#: Most of them would not move a verdict. A minimum lot WIDTH is largely said
#: again by area and frontage; a garage entrance setback means nothing to a pod
#: with no garage; a minimum number of STORIES is not a constraint on a
#: two-storey building.
#:
#: `max_density_du_per_acre` looks like the dangerous one and is not: OAR
#: 660-046-0220(2)(b) forbids a Large City applying a density maximum to a
#: quadplex, and the state layer strikes it out with `exempt: true, preempts:
#: always`. West Linn's R-5 prints 8.7 units per acre against a 5,000 sq ft
#: minimum lot -- four units is four times that -- and the zone still is not a
#: wall, because the state says the row does not apply. A column here would
#: have to carry the exemption too, and not having one carries it by accident.
#:
#: Two are live, and both were measured on 2026-09-02 against the pre-overlay
#: run rather than argued about.
#:
#: A MAXIMUM front setback pushes the building toward the street and the
#: placement search has never heard of it. 23 zones state one and 21 of them are
#: `needs_verification`, so their lots reach REVIEW anyway; the two that are
#: verified -- unincorporated Clackamas VR57 and Gresham CMF -- hold **zero
#: greens between them**. So the gap moves no verdict as the corpus stands,
#: which is a fact about the corpus and not about the rule. (Portland IR used to
#: be the 24th and the reason to keep looking: 13 ft minimum against a 10 ft
#: maximum, no legal front setback at all. Resolved 2026-09-02 -- see the note
#: below the list.)
#:
#: The other live one was minimum density, and it left this list the same day
#: it arrived: 2026-09-02, count 14 -> 13. (2)(b) is about maximums and no part
#: of -0220 relieves a quadplex of a floor, so a lot can be too BIG for four
#: units to be enough -- 110 of 10,106 greens, every one in Oregon City, sat
#: above their zone's. `flats.score.screen` already applied it and this pipeline
#: had no column, so it was a gap between two screens rather than an unread
#: rule, and the cheapest close was the column. It is now mirrored on all 40
#: zones that state a floor, checked by the mirror audit like any other
#: dimension, and s7 routes a lot over its floor to REVIEW rather than RED --
#: the code divides by NET developable area and nothing here surveys that, so
#: clearing the floor on gross area settles it and failing on gross area does
#: not.
#:
#: THE OTHER SIX, WALKED 2026-09-02. Six entries had a place on this list and
#: no reason on it, which is the same shape of silence the list was built to
#: end. Two kinds of answer came back, and the difference between them is the
#: only part worth remembering.
#:
#: INERT BY ARITHMETIC -- these cannot bite whatever the corpus does next,
#: because the pod's own numbers clear them:
#:   * `max_units`: both Gladstone zones state FOUR. The pod is four units. A
#:     cap met exactly is not a cap, and it would still be met if Gladstone
#:     were the greenest city in the screen.
#:   * `min_units_at_trigger` / `min_density_trigger_lot_sqft`: the floor is
#:     TWO units on every one of the five zones -- Portland R2.5/R5/R7 above
#:     5,000/10,000/14,000 sq ft, and unincorporated Multnomah's two copies of
#:     the same Portland sections. Four clears two on any lot.
#:   * `min_building_separation_ft`: 10 ft between buildings, Fairview and
#:     Happy Valley. The pod is ONE building. There is nothing to separate it
#:     from.
#:
#: ZERO GREENS TODAY -- a fact about the corpus, not about the rule, and it can
#: change the moment one of those zones is verified:
#:   * `min_landscaped_pct` is the biggest of the thirteen after lot width, and
#:     the only one that would plainly compete with the pod for ground: 20% in
#:     Fairview and Happy Valley, 30% in Portland's RM zones. Its 33 zones hold
#:     50,132 lots on the 2026-09-02 run and **not one of them is green** --
#:     46,205 red and 3,927 in review. Every Portland zone on the list is one
#:     of the 29 recovered ones, which are `needs_verification` and capped at
#:     review; Fairview and Happy Valley have no greens at all.
#:   * `min_lot_depth_ft` WAS the sharpest of these and is now CLOSED -- see
#:     the 2026-09-11 entry below. The argument recorded here for leaving it
#:     alone was that no green-producing zone's greens were anywhere near their
#:     depth floor, so a column would be "for a lot that does not exist yet".
#:     That reasoning was sound about GREENS and silently wrong about the
#:     screen: it measured the risk of the column changing an answer instead of
#:     the risk of never asking the question, and the second is the one a
#:     screen is judged on. It is kept here rather than deleted because it is a
#:     shape worth recognising again -- "this would move nothing" is an
#:     argument for cheapness, never for correctness.
#:   * `max_lot_depth_ratio` (3:1, four Fairview zones) and
#:     `setback_side_total_ft` (Lake Oswego R-7.5) sit behind cities with no
#:     greens -- Lake Oswego is `eligible: false` and its side yard already has
#:     its own entry in KNOWN_SIDE_TOTAL_COLLAPSE.
#:
#: A THIRD WAY OFF THE LIST, found 2026-09-02: `setback_front_max_ft` 24 -> 23.
#: Portland's IR left it, and not by getting a column. Its maximum front
#: setback had been stated flat at 10 ft while its minimum -- the corpus's only
#: standard measured off the BUILDING, 1 ft per 2 ft of height -- comes to 13 ft
#: for the pod. Table 150-2's note [5] says "for frontages where the maximum
#: building setback applies, there is no minimum setback", and the maximum's own
#: row is headed "Street Lot Line, Transit Street or Pedestrian District". So
#: the ceiling reaches only the frontage where the floor lifts: 13 and no
#: ceiling off a transit street, no floor and 10 on one. Held flat, the two
#: described a zone no building fits in. The maximum is now exempt at the base
#: with the 10 as a transit-street variant, so the corpus no longer holds a
#: number there and this pipeline no longer needs a column for one.
#:
#: That is a reading, not a deletion, and it is the only kind of shrink allowed
#: besides a column: the standard has to stop applying, quoted, on the page.
#:
#: Frozen so the list cannot grow quietly. A standard leaves it by getting a
#: column or by being read as not applying, never by being dropped from the
#: corpus.
#: MOVED 2026-09-08, and two of the moves had been sitting red for days
#: because nothing runs this directory. `Lot Analysis/quadfit/tests` is in no
#: CI job -- the light gate runs `tests/` and `flats/tests` -- so the mirror
#: audit, the only thing comparing what the screen RUNS on against what was
#: READ, went stale the moment a corpus commit landed without somebody
#: remembering to run it by hand. Three moves, attributable to the line:
#:
#:   8a6924a5  -3 setback_garage_entrance_ft  (67 -> 64) three numbers quoted
#:             from an exception and held as the rule, withdrawn
#:   c9ed261f  +3 setback_front_max_ft        (23 -> 26) three dismissals that
#:             quoted a number and declined it anyway, encoded
#:   this one  +1 to five fields              Oregon City R-2
#:
#: A CI step now runs this directory, which is the actual fix; the numbers
#: below are the second fix.
#:
#: MOVED AGAIN 2026-09-10, and the CI step did exactly what it was put there to
#: do -- it went red and stayed red, which is how this was found. Four moves,
#: and only the last of them belongs to the commit that is writing this line:
#:
#:   01df7d29  +1 min_building_height_ft     (-- -> 1) the field did not exist
#:             before that commit; Troutdale MU-3 states a floor of 25 ft and
#:             this pipeline has no column for a MINIMUM height. It is the one
#:             shape where an unheld standard buys a false GREEN rather than a
#:             false RED, so it is the entry on this list to close first.
#:   e8c9dd11  +1 min_lot_width_ft           (66 -> 67)
#:             +6 min_lot_depth_ft           (29 -> 35) Milwaukie R-MD/R-HD and
#:             Gresham's low-density family. That commit is the only one in the
#:             range that encoded a lot width or depth, and `rules.yaml` has not
#:             been touched since the numbers below were last written -- so
#:             every move here came from the corpus side, which is the ordinary
#:             direction: reading a page creates the debt, it does not pay it.
#:   this one  +8 min_average_lot_width_ft   (-- -> 8) West Linn states an
#:             average lot width beside the width at the front lot line, and
#:             CDC 02.030 measures them on two different lines. `rules.yaml`
#:             has one width slot and `lot_width_measure` names one measure per
#:             city, so the second row has nowhere to go. Direction of the
#:             error is a possible false GREEN on a lot that tapers -- the
#:             audit's own docstring carries the long version.
#:
#: Three of the four had been red on `main` before anybody looked: SIX
#: consecutive CI runs failed on this step -- e8c9dd11, 048938f6, b32583bd,
#: 01df7d29, ffe4bf56, a3bbd72d -- each one pushed and deployed on top of the
#: red, and because the full gate is gated on the light gate, the integration,
#: E2E, Trivy and Semgrep steps were SKIPPED all six times. The list is a
#: ratchet, not a report: it is only worth what somebody does when it moves.
#:
#: SHRANK 2026-09-11, and by a column rather than a reading -- the first time
#: an entry has left this list that way:
#:
#:   this one  -35 min_lot_depth_ft          (35 -> gone) `ZoneRule` grew a
#:             `min_lot_depth_ft`, `s7.policy_gates` judges it, and s4 had
#:             already begun measuring the depth each city's own glossary
#:             defines. Nothing had to be read to close it; the standard was
#:             encoded, cited and mirrored all along, and what was missing was
#:             a column here and a measurement there. Both now exist.
#:
#:             `max_lot_depth_ratio` deliberately STAYS at 4. Fairview states
#:             depth as a multiple of width in four zones, and this pipeline
#:             measures Fairview's depth and not its width -- so the ratio has
#:             one of its two terms. Encoding it against a missing width would
#:             be a number divided by nothing, which is worse than the gap.
#:
#: SHRANK AGAIN 2026-09-11, later the same day, by the same route:
#:
#:   this one  -67 min_lot_width_ft          (67 -> gone) `ZoneRule` grew a
#:             `min_lot_width_ft`; s4 measures the width under each city's own
#:             definition -- six forms across eleven cities -- and s7 judges
#:             it at `below_min_lot_width`. The seven Oregon City and Tualatin
#:             numbers that had been sitting in the frontage column moved into
#:             it, and fifty-seven more were carried across from the corpus
#:             under their own name. Sixty-four filled, not sixty-seven: R-3 in
#:             West Linn states only the front-line width, which is the
#:             frontage alias; Lake Oswego's R-7.5 is switched off; and
#:             Tualatin's RML is left blank on purpose, because TDC 31.060's
#:             "average lot width" is front-plus-rear over two, a seventh form
#:             nothing measures. That blank is now pinned in UNFILLED below,
#:             which is the ledger this shrink created a need for.
#:            -8 min_average_lot_width_ft    (8 -> gone) West Linn's second
#:             width row, the one measured at the midpoints of opposite lot
#:             lines. It is Oregon City's form under another name, so it
#:             needed no new measurement -- only somewhere to go. It goes in
#:             `min_lot_width_ft`, and the audit's REMAPPED table sends that
#:             column to the corpus's `min_average_lot_width_ft` for West Linn
#:             alone, so R-10's 50 is compared against the 50 it came from
#:             rather than the 35 on the row above it.
#:
#:             `max_lot_depth_ratio` STILL stays at 4, and the reason has
#:             flipped: Fairview's width now exists, so the ratio has both its
#:             terms. It is a follow-on, not a rider -- a ratio of two
#:             measurements is a new comparison, and this commit is already
#:             moving verdicts in eleven cities.
UNEXPRESSIBLE: dict[str, int] = {
    "setback_garage_entrance_ft": 64,
    "min_landscaped_pct": 34,
    "setback_front_max_ft": 27,
    "max_density_du_per_acre": 21,
    "min_building_separation_ft": 9,
    "min_density_trigger_lot_sqft": 5,
    "min_units_at_trigger": 5,
    "max_lot_depth_ratio": 4,
    "max_units": 2,
    "max_height_stories": 2,
    "setback_side_total_ft": 1,
    "min_building_height_ft": 1,
}


def test_a_standard_with_no_column_is_a_standard_nobody_applies() -> None:
    """The step-back's siblings, counted.

    A number the corpus holds and rules.yaml cannot express is not a
    disagreement between the files -- it agrees perfectly, on nothing. It took
    building `StepBack` to see that this was a CATEGORY rather than one odd
    rule, and the honest thing is to say how big it is rather than close it
    quietly by hard-coding.

    Anything routed into the pipeline some other way is excluded by
    `ROUTED_ELSEWHERE`: the per-city parking and open-space figures live in
    `footprints.yaml` and `common.py`, not here, and are not missing.
    """
    audit = _audit()
    found = {k: len(v) for k, v in audit.unexpressible_standards().items()}
    assert found == UNEXPRESSIBLE, (
        "the set of standards this pipeline cannot express moved: "
        f"{ {k: (UNEXPRESSIBLE.get(k), found.get(k)) for k in set(found) ^ set(UNEXPRESSIBLE) | {k for k in found if found[k] != UNEXPRESSIBLE.get(k)}} }"
    )


#: The three entries on UNEXPRESSIBLE whose reason is the pod's own arithmetic
#: rather than the state of the corpus, and the value each has to keep for that
#: reason to hold. See the ledger note above.
INERT_BY_ARITHMETIC: dict[str, float] = {
    #: A cap of four on a four-unit building is met exactly, not breached.
    "max_units": 4,
    #: A floor of two units is cleared by four on any lot, at any trigger size.
    "min_units_at_trigger": 2,
    #: Ten feet between buildings, and the pod is one building.
    "min_building_separation_ft": 10,
}


def test_the_inert_standards_are_inert_because_of_their_values() -> None:
    """Three of the twelve can never bite, and this is why rather than that.

    The ledger note above says these are safe whatever the corpus does next,
    which is a claim about the NUMBERS: four units meet a cap of four and clear
    a floor of two, and one building has nothing to be separated from. Written
    only as prose, that claim survives a re-reading that changes the number
    underneath it -- Gladstone amending its cap to three, or a city raising a
    density floor to five, would leave the sentence standing and the reasoning
    false.

    So the values are asserted. If one moves, this goes red and the standard
    has to be argued again rather than inherited.
    """
    from flats.encode.port_quadfit import layer_id_for

    audit = _audit()
    unexpressible = audit.unexpressible_standards()
    _top, corpus = audit._load()

    for field, expected in INERT_BY_ARITHMETIC.items():
        zones = unexpressible.get(field, [])
        assert zones, f"{field} left the ledger; its note has to go with it"
        for key in zones:
            juris, _, zone = key.partition("/")
            layer = corpus[layer_id_for(juris)]
            # Through the audit's own resolution, not the zone's raw values:
            # Fairview's R/SFLD states almost nothing of its own and adopts
            # R-6's block, which is the encoding rather than a gap in it.
            effective = audit._effective(layer, layer.zones[zone])
            value = effective.get(field) or layer.defaults.get(field)
            assert value is not None and float(value.value) == expected, (
                f"{key}.{field} reads {value and value.value}, not {expected} "
                f"-- the reason it is inert no longer holds"
            )


#: Standards the corpus states in more than one column of LOT AREA where
#: rules.yaml still carries a single number. Each one needs a reason, and each
#: of these has the same reason: the column that would differ cannot be reached.
#:
#: Wilsonville's rear yard is 15 ft on a small lot for a ONE-STOREY building
#: and 20 ft for two or more; over 10,000 sq ft it is 20 either way. The pod is
#: two storeys at 26 ft, so it owes 20 ft in every column and the band would
#: only restate it. Milwaukie's rear yard drops to 15 ft in the 1,500-2,999
#: sq ft column, and R-MD's own minimum lot is 3,000 unless the plat is unit
#: lots -- which is not how this pod is built -- so no lot the screen looks at
#: is ever in that column.
#:
#: R-MD's STREET FRONTAGE, added 2026-09-10, has a different reason and it is
#: worth reading rather than inheriting. Table 19.301.4 row B.3.b prints
#: 35 / 30 / 35 / 35 across the four columns, so the only column that differs is
#: a RELAXATION: 30 ft where the rest of the table asks 35. A screen holding the
#: flat 35 there is stricter than the city, never looser, which is the safe
#: direction and the direction this project defaults to everywhere else.
#:
#: The larger fact is that `rules.yaml` holds no frontage figure for R-MD at all
#: -- not a band, not the flat 35 -- and the same is true of R-HD, whose row
#: prints a single 35 and so never reaches this test. Milwaukie's row is headed
#: "Minimum street frontage requirements", which is the edge s4 actually
#: measures, so this is not the lot-width alias problem; it is a standard the
#: corpus reads and the screen does not apply. Closing it would move lots from
#: green to red, so it is a change of its own rather than a rider on this one.
#: Since 2026-09-11 UNFILLED below is the list that carries it.
#:
#: R-MD's LOT DEPTH joined 2026-09-11, the day `min_lot_depth_ft` entered
#: MIRRORED and this check could see it. Table 19.301.4 row B.2 prints 70 ft
#: in the 1,500-2,999 column and 80 in the other three; rules.yaml holds 80.
#: Same reason as the rear yard two rows up: the zone's own minimum lot is
#: 3,000, so no lot that reaches the depth gate is in the column that differs,
#: and where the band would matter the flat figure is the stricter one.
#:
#: R-MD's LOT WIDTH is the counter-example, and it is deliberately NOT here:
#: 30 / 50 / 60 across the three reachable columns, where the higher columns
#: are STRICTER than the lowest. Held flat at 30 it would pass a 7,000 sq ft
#: lot the city asks 60 of, so it is carried as a band and reads `banded`.
FLAT_BUT_BANDED: frozenset[str] = frozenset({
    "milwaukie/R-MD.min_frontage_ft",
    "milwaukie/R-MD.min_lot_depth_ft",
    "milwaukie/R-MD.setback_rear_ft",
    "wilsonville/OTR.setback_rear_ft",
    "wilsonville/PDR1.setback_rear_ft",
    "wilsonville/PDR2.setback_rear_ft",
    "wilsonville/PDR3.setback_rear_ft",
    "wilsonville/PDR4.setback_rear_ft",
    "wilsonville/PDR5.setback_rear_ft",
    "wilsonville/PDR6.setback_rear_ft",
    "wilsonville/R.setback_rear_ft",
})


def test_a_table_with_two_columns_of_lot_area_is_held_as_two_columns() -> None:
    """The blind spot in the check above, and the largest one found so far.

    `scan()` accepts a shipped number when it matches ANY limb of the corpus
    value. A standard written as several columns of lot area therefore agrees
    with itself whichever column you ship, and Wilsonville shipped the small-lot
    single-storey column for every residential zone it has -- with the correct
    reading spelled out in its own `notes:` line, because rules.yaml had no way
    to hold a number that depends on the size of the lot.

    `lot_size_bands` is that way. This test says every banded standard in the
    corpus is either held as a band or listed above with a reason.
    """
    audit = _audit()
    flat = {
        row.split(" ")[1] for row in audit.banded_standards() if row.startswith("FLAT ")
    }
    assert flat == FLAT_BUT_BANDED, (
        "a banded standard is being screened as one number: "
        f"new {sorted(flat - FLAT_BUT_BANDED)}, closed {sorted(FLAT_BUT_BANDED - flat)}"
    )


def test_a_band_that_tightens_with_lot_size_is_carried_as_a_band() -> None:
    """The one banded standard where FLAT would be the wrong answer, pinned.

    Milwaukie R-MD's lot width climbs with the lot: 30 ft under 5,000 sq ft,
    50 to 7,000, 60 above. Every other FLAT row in this file is safe because
    the column that differs is a relaxation nothing reaches; this one is the
    other way round, and a flat 30 would wave through a 9,000 sq ft lot that
    is 40 ft wide against a code asking 60. So it is held as a band, the
    audit reads it as `banded`, and the band answers per lot.
    """
    from common import load_rules

    audit = _audit()
    rows = {r.split(" ")[1]: r.split(" ")[0] for r in audit.banded_standards()}
    assert rows.get("milwaukie/R-MD.min_lot_width_ft") == "banded", rows

    r = load_rules().jurisdictions["milwaukie"].rule_for("R-MD")
    assert [r.banded("min_lot_width_ft", a) for a in (3_000, 4_999, 5_000, 6_999, 7_000, 9_000)] == [
        30, 30, 50, 50, 60, 60,
    ]
    # And with no area in hand the scalar is the smallest reachable column,
    # so a caller that has not learned the band is lenient, never strict on a
    # lot it cannot place.
    assert r.banded("min_lot_width_ft", None) == 30


#: Zones where the corpus states a number, rules.yaml has a column for it, and
#: the row is blank. Found 2026-09-11 by the check built to pin one deliberate
#: blank -- Tualatin RML's lot width -- which turned up thirty-seven more that
#: nobody had deliberately anything. Each group below has its own reason, and
#: none of the reasons is "fixed here": every one of these moves a verdict in
#: the strict direction, so each is a commit that says so.
#:
#: STREET FRONTAGE, 24 zones in Gresham, Happy Valley, Milwaukie and Troutdale.
#: The corpus reads a "Minimum street frontage" row in each -- the edge s4
#: already measures, so no new measurement is needed -- and rules.yaml has
#: never held it. Before 2026-09-11 the frontage column was also carrying
#: Oregon City's mid-lot width, and filling it in a city with an
#: `applicant_choice` corner-lot rule would have needed care about which edge;
#: now it is one number with one meaning everywhere and the fill is a port.
#: A lot short of it goes RED. Follow-on.
#:
#: MINIMUM LOT, 12 zones. Nine are Clackamas County's urban residential
#: districts, and they are the sharp one: rules.yaml leaves the row blank on a
#: written reading that ZDO 845 WAIVES the minimum for a middle-housing land
#: division, while the corpus reads 845.01 as a 7,000 sq ft floor on the lot a
#: quadplex stands on, "the same number in every district". Two readings of
#: one section, and the direction of the disagreement is a possible false
#: GREEN on every lot under 7,000 sq ft in nine zones. Needs the county text
#: read once more with both readings in hand. Gresham TLDR (8,000), Happy
#: Valley MURS (7,000, 6,000 on a unit lot) and Tualatin RML (4,500) are plain
#: omissions.
#:
#: STREET-SIDE SETBACK, 2 zones: Milwaukie R-HD's 15 (5 on the mapped
#: properties) and Tualatin RL's 10. A corner lot in either is screened on
#: the interior side yard at the street. Omissions.
#:
#: MINIMUM DENSITY, Gresham SC and SC-RJ at 18 du/acre. Omissions, and the
#: dangerous direction: a lot can be too big for four units to be enough.
#:
#: LOT WIDTH, Tualatin RML, the one blank that is on purpose. TDC 41.220 heads
#: the row "Minimum AVERAGE lot width" and 31.060 defines it as front lot line
#: plus rear lot line over two -- a seventh form `lotdims.py` does not take,
#: on two lines `center_parallel` does not draw. RML has no mapped lots. Left
#: unmeasured rather than measured wrong; rules.yaml says so beside the row.
UNFILLED: frozenset[str] = frozenset({
    "clackamas_unincorporated/R10.min_lot_sqft",
    "clackamas_unincorporated/R15.min_lot_sqft",
    "clackamas_unincorporated/R20.min_lot_sqft",
    "clackamas_unincorporated/R30.min_lot_sqft",
    "clackamas_unincorporated/R5.min_lot_sqft",
    "clackamas_unincorporated/R7.min_lot_sqft",
    "clackamas_unincorporated/R8.5.min_lot_sqft",
    "clackamas_unincorporated/VR45.min_lot_sqft",
    "clackamas_unincorporated/VR57.min_lot_sqft",
    "gresham/DRL-1.min_frontage_ft",
    "gresham/DRL-2.min_frontage_ft",
    "gresham/HDR-PV.min_frontage_ft",
    "gresham/LDR-5.min_frontage_ft",
    "gresham/LDR-7.min_frontage_ft",
    "gresham/LDR-PV.min_frontage_ft",
    "gresham/LDR-SW.min_frontage_ft",
    "gresham/MDR-12.min_frontage_ft",
    "gresham/MDR-24.min_frontage_ft",
    "gresham/SC-RJ.min_density_du_per_acre",
    "gresham/SC.min_density_du_per_acre",
    "gresham/TLDR.min_frontage_ft",
    "gresham/TLDR.min_lot_sqft",
    "gresham/TR.min_frontage_ft",
    "happy_valley/MURS.min_lot_sqft",
    "happy_valley/R10.min_frontage_ft",
    "happy_valley/R15.min_frontage_ft",
    "happy_valley/R20.min_frontage_ft",
    "happy_valley/R20CC.min_frontage_ft",
    "happy_valley/R40.min_frontage_ft",
    "happy_valley/R5.min_frontage_ft",
    "happy_valley/R7.min_frontage_ft",
    "happy_valley/R8.5.min_frontage_ft",
    "milwaukie/R-HD.min_frontage_ft",
    "milwaukie/R-HD.setback_street_side_ft",
    "milwaukie/R-MD.min_frontage_ft",
    "tualatin/RL.setback_street_side_ft",
    "tualatin/RML.min_lot_sqft",
    "tualatin/RML.min_lot_width_ft",
})


def test_a_blank_row_under_an_existing_column_is_written_down() -> None:
    """The gap between `scan` and `unexpressible_standards`, closed.

    `scan` compares numbers both files state. `unexpressible_standards` asks
    whether rules.yaml has a column at all. A column that exists corpus-wide
    and is blank in one zone is invisible to both, and that is the shape of a
    deliberate omission and a forgotten one alike. Milwaukie's frontage lived
    in that gap as a paragraph of prose; this is the list instead.

    Every width-stating zone the corpus holds is filled but one, and the one
    is here with its reason. A zone that stops being blank leaves the list and
    this goes red until the entry is removed, which is the moment to say what
    moved. A zone that joins goes red the same way.
    """
    audit = _audit()
    found = {row.split(" ")[0] for row in audit.unfilled_standards()}
    assert found == UNFILLED, (
        f"new {sorted(found - UNFILLED)}, filled {sorted(UNFILLED - found)}"
    )

    # The one deliberate blank, and the reason it is deliberate has to be on
    # the row in rules.yaml, not only here.
    rml = _zone("tualatin", "RML")
    assert "min_lot_width_ft" not in rml
    src = io.open(_audit().RULES, encoding="utf-8").read()
    assert "AVERAGE lot width" in src and "seventh form" in src

    # And every OTHER width-stating zone both files hold is filled: the width
    # column did not arrive with holes in it.
    blank_widths = {k for k in found if k.endswith(".min_lot_width_ft")}
    assert blank_widths == {"tualatin/RML.min_lot_width_ft"}, blank_widths


def test_the_band_answers_per_lot_and_not_per_zone() -> None:
    """Wilsonville's two columns, read off a lot of each size.

    The numbers are WDC 4.113(.14): A for lots over 10,000 sq ft, B for lots
    not exceeding it, and inside B a storey branch the pod's own height settles.
    A 9,000 sq ft lot and a 12,000 sq ft lot in the same zone owe different
    yards, which is the whole point and exactly what a single column cannot say.
    """
    from common import load_rules

    r = load_rules().jurisdictions["wilsonville"].rule_for("R")
    assert (r.effective_setback_front_ft(9_000),
            r.effective_setback_side_ft(lot_area_sqft=9_000),
            r.effective_setback_rear_ft(lot_area_sqft=9_000)) == (15, 7, 20)
    assert (r.effective_setback_front_ft(12_000),
            r.effective_setback_side_ft(lot_area_sqft=12_000),
            r.effective_setback_rear_ft(lot_area_sqft=12_000)) == (20, 10, 20)

    # 4.122's coverage is a four-step table and the steps are steep: the same
    # zone allows half the lot at 6,000 sq ft and a quarter of it at 12,000.
    assert r.coverage_cap_sqft(6_000) == 3_000
    assert r.coverage_cap_sqft(12_000) == 3_000

    # And with no area in hand every one of them falls back to the scalar, so
    # a caller that has not been taught the band keeps the answer it had.
    assert r.effective_setback_side_ft() == 7


def test_a_floor_that_does_not_reach_a_small_lot_is_no_floor() -> None:
    """Gresham states 12.1 du/acre as a minimum and then confines it to sites
    of 11,000 sq ft and up. Carried flat it would ask a 9,000 sq ft lot to meet
    a floor its own code does not apply -- the band is what says "no floor
    here", which is not the same as a floor of zero."""
    from common import load_rules

    z = load_rules().jurisdictions["gresham"].rule_for("MDR-24")
    assert z.density_floor_lot_sqft(lot_area_sqft=9_000) is None
    assert z.density_floor_lot_sqft(lot_area_sqft=12_000) == pytest.approx(14_400, abs=1)


# --- the seam between a signature and the screen ---------------------------


def test_nothing_is_signed_and_still_capped_at_review() -> None:
    """The gap that opens the day signing starts, watched before it does.

    "Verified" means two unconnected things. In the corpus it means a person
    read the quoted sentence against the number and signed it. To the pipeline
    it means a `confidence:` field on the zone's rules.yaml row, and s7 sends
    every lot in a `needs_verification` zone to REVIEW whatever else it clears.
    No code carries the first to the second; flipping the flag and re-running
    s7 is a separate step somebody has to remember.

    So a zone can be fully read, fully signed, and still cap its lots -- with
    the corpus reporting it finished and the screen reporting it unverified,
    both truthfully about their own file. 710 lots in the current run are held
    by nothing but that flag.

    Zero today because nothing is signed anywhere, which is exactly why it is
    worth having now. A check written the first time it fires is written by
    somebody who has already lost the lots.
    """
    assert _audit().stalled_signatures() == []


def test_a_signed_zone_whose_flag_never_flipped_is_reported() -> None:
    """And the check actually fires, which zero cannot demonstrate.

    Built rather than found: one signed zone, one rules.yaml row still marked
    `needs_verification`, and the two names matched up the way the real files
    match them.
    """
    from flats.encode.port_quadfit import layer_id_for
    from flats.rules.model import Layer, Provenance, Status, Value, Zone

    audit = _audit()
    # A row the pipeline really does distrust, taken from the feed rather than
    # named, so the test does not go red the day that zone is verified.
    juris, zone_code = next(
        (j, z["zone"])
        for j, spec in _rules().items()
        if isinstance(spec, dict) and spec.get("zones")
        for z in spec["zones"]
        if str(z.get("confidence", "")) == "needs_verification"
    )
    layer_id = layer_id_for(juris)

    signed = Value(
        name="setback_front_ft",
        value=10,
        prov=Provenance(
            cite="somewhere",
            url="https://example.invalid/code",
            retrieved=date(2026, 9, 2),
            quote="doc.txt#L1",
        ),
        status=Status.verified,
        reviewer="sjk",
        reviewed=date(2026, 9, 2),
    )
    layer = Layer(
        layer=layer_id,
        kind="city",
        label="X",
        zones={zone_code: Zone(zone=zone_code, values={"setback_front_ft": signed})},
    )

    class _Trusted:
        layers = {layer_id: layer}

    import flats.encode.load as load

    original = load.load_trusted
    load.load_trusted = lambda *a, **k: _Trusted()
    try:
        rows = audit.stalled_signatures()
    finally:
        load.load_trusted = original

    hit = [r for r in rows if r.startswith(f"{juris}/{zone_code}:")]
    assert hit, f"a signed {juris}/{zone_code} was not reported: {rows}"
    assert "needs_verification" in hit[0]
