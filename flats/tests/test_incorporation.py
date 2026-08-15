"""A zone with no standards of its own.

Fairview's VSF zone states no dimensional standards. It says the R-6 standards
apply — in a different chapter — and carries a conflict clause naming which text
governs where the two disagree. Roughly one Oregon city in three does something
like this somewhere in its code, and it cannot be encoded by copying the numbers
across: the copies stop tracking their source the first time R-6 is amended,
silently, and nobody reviewing VSF has any way to notice.

So the reference is the encoding. What these tests defend is that following it
behaves like reading the code does — the borrowed number still cites the section
it lives in, the borrowing zone's own statements interact with it the way the
conflict clause says, and the claim to borrow is itself a rule somebody has to
have read.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flats.encode.verify import VerificationLog, apply_verifications, sign_like
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Status
from flats.rules.resolver import RuleSet, Verdict
from flats.tests.signing import sign_encoded

pytestmark = pytest.mark.unit

FAIRVIEW = "or/41051-multnomah/4124150-fairview"
COUNTY = "or/41051-multnomah"
REVIEWED = date(2026, 8, 12)

CITE = (
    "cite_default:\n"
    '  cite: "FMC 19.115.030"\n'
    '  url: "https://fairvieworegon.gov/code/19.115"\n'
    "  retrieved: 2026-08-12\n"
    "  quote: \"or/multnomah/fairview/19.115.txt#L2\"\n"
)
#: Ready for review. The signing helper promotes exactly these.
READY = "      status: encoded\n"


def write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def fairview(root: Path, zones: str) -> None:
    write(root, f"{FAIRVIEW}.yaml", "label: Fairview\n" + CITE + "zones:\n" + zones)


def rules(root: Path, encoded: bool = False) -> RuleSet:
    layers = load_rules(root)
    return RuleSet(sign_encoded(layers) if encoded else layers)


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "jurisdictions"


#: R-6 states the standards; VSF adopts them. The shape this module is about.
BORROWED = (
    "  R-6:\n"
    "    setback_front_ft: 20\n"
    "    min_lot_sqft: 6000\n"
    "  VSF:\n"
    "    like: R-6\n"
)


# --- reading through the reference ------------------------------------


def test_a_borrowing_zone_gets_the_standards_it_adopted(root: Path) -> None:
    fairview(root, BORROWED)

    r = rules(root).resolve(FAIRVIEW, "VSF")

    assert r.get("setback_front_ft") == 20
    assert r.get("min_lot_sqft") == 6000


def test_a_borrowed_value_cites_the_section_it_lives_in(root: Path) -> None:
    # The reason not to copy. A detail page that cited VSF's own section would
    # send a reviewer to a page the number is not printed on.
    fairview(
        root,
        "  R-6:\n"
        "    setback_front_ft:\n"
        "      value: 20\n"
        '      cite: "FMC 19.105.040, Table 1"\n'
        "  VSF:\n"
        "    like: R-6\n",
    )

    r = rules(root).resolve(FAIRVIEW, "VSF")

    assert r.values["setback_front_ft"].prov.cite == "FMC 19.105.040, Table 1"
    assert r.values["setback_front_ft"].via == "R-6"


def test_a_resolution_says_which_zones_it_read_through(root: Path) -> None:
    fairview(root, BORROWED)

    assert rules(root).resolve(FAIRVIEW, "VSF").borrowed_from == ("R-6",)
    assert rules(root).resolve(FAIRVIEW, "R-6").borrowed_from == ()


def test_a_zone_that_states_its_own_number_keeps_it(root: Path) -> None:
    # The common conflict rule: the zone's own text governs. Adopting a table
    # and then restating one row of it is how codes write exceptions.
    fairview(root, BORROWED + "    setback_front_ft: 10\n")

    r = rules(root).resolve(FAIRVIEW, "VSF")

    assert r.get("setback_front_ft") == 10
    assert r.get("min_lot_sqft") == 6000, "the rest still comes from R-6"


def test_the_conflict_clause_can_run_the_other_way(root: Path) -> None:
    # Some codes say the adopted chapter governs. Assuming either direction
    # would silently pick the wrong number for every zone written the other way.
    fairview(
        root,
        "  R-6:\n"
        "    setback_front_ft: 20\n"
        "  VSF:\n"
        "    like:\n"
        "      zone: R-6\n"
        "      wins: referenced\n"
        "    setback_front_ft: 10\n",
    )

    assert rules(root).resolve(FAIRVIEW, "VSF").get("setback_front_ft") == 20


def test_a_reference_chain_is_followed_all_the_way(root: Path) -> None:
    fairview(
        root,
        "  R-6:\n    setback_front_ft: 20\n  R-7:\n    like: R-6\n  VSF:\n    like: R-7\n",
    )

    r = rules(root).resolve(FAIRVIEW, "VSF")

    assert r.get("setback_front_ft") == 20
    assert r.borrowed_from == ("R-6", "R-7")


def test_a_city_may_adopt_a_zone_from_up_the_hierarchy(root: Path) -> None:
    # A city adopting the county's zone is the same shape as adopting one of
    # its own, and it is how unincorporated-adjacent cities usually write it.
    write(
        root,
        f"{COUNTY}/_county.yaml",
        "label: Multnomah County\n" + CITE + "zones:\n  R-6:\n    setback_front_ft: 25\n",
    )
    fairview(root, "  VSF:\n    like: R-6\n")

    assert rules(root).resolve(FAIRVIEW, "VSF").get("setback_front_ft") == 25


def test_state_preemption_still_beats_a_borrowed_number(root: Path) -> None:
    # Borrowing changes where a number was read, not who outranks whom.
    write(
        root,
        "or/_state.yaml",
        "label: Oregon\n"
        'cite_default:\n  cite: "OAR 660-046-0220"\n'
        '  url: "https://oregon.gov/oar/660-046"\n  retrieved: 2026-08-12\n  quote: "or/oar.660-046-0220.txt#L79"\n'
        "defaults:\n"
        "  parking_min_per_unit:\n    value: 1.0\n    preempts: true\n",
    )
    fairview(root, "  R-6:\n    parking_min_per_unit: 2.0\n  VSF:\n    like: R-6\n")

    r = rules(root).resolve(FAIRVIEW, "VSF")

    assert r.get("parking_min_per_unit") == 1.0
    assert r.values["parking_min_per_unit"].preempted


# --- when the reference does not resolve -------------------------------


def test_adopting_a_zone_nobody_encoded_is_a_coverage_gap(root: Path) -> None:
    # Not an error and not a RED: the fix is to encode R-6, and until somebody
    # does, no lot in VSF may be answered either way.
    fairview(root, "  VSF:\n    like: R-6\n")

    r = rules(root).resolve(FAIRVIEW, "VSF")

    assert r.verdict is Verdict.zone_reference_missing
    assert r.reason == "ZONE_REFERENCE_MISSING"
    assert not r.trusted


def test_two_zones_that_adopt_each_other_are_refused(root: Path) -> None:
    # No set of standards exists to resolve, and following the reference would
    # not terminate. An encoding bug, reported as one.
    fairview(root, "  VSF:\n    like: R-6\n  R-6:\n    like: VSF\n")

    r = rules(root).resolve(FAIRVIEW, "VSF")

    assert r.verdict is Verdict.zone_reference_cycle
    assert r.reason == "ZONE_REFERENCE_CYCLE"


def test_a_zone_that_adopts_itself_is_refused(root: Path) -> None:
    fairview(root, "  VSF:\n    like: VSF\n")

    assert rules(root).resolve(FAIRVIEW, "VSF").verdict is Verdict.zone_reference_cycle


# --- what a file may say ----------------------------------------------


def test_the_shorthand_is_a_bare_zone_code(root: Path) -> None:
    fairview(root, BORROWED)

    like = load_rules(root)[FAIRVIEW].zones["VSF"].like

    assert like is not None
    assert (like.zone, like.wins) == ("R-6", "local")
    assert like.prov.cite == "FMC 19.115.030", "inherited from the zone's cite_default"


def test_an_incorporation_needs_provenance_like_any_other_rule(root: Path) -> None:
    # Unsourced, it is a guess about which numbers govern an entire zone.
    write(root, f"{FAIRVIEW}.yaml", "label: Fairview\nzones:\n  VSF:\n    like: R-6\n")

    with pytest.raises(RuleLoadError, match="an incorporation is a rule too"):
        load_rules(root)


def test_a_reference_with_no_zone_is_refused(root: Path) -> None:
    fairview(root, "  VSF:\n    like:\n      wins: local\n")

    with pytest.raises(RuleLoadError, match="name the zone"):
        load_rules(root)


def test_an_unknown_conflict_rule_is_refused(root: Path) -> None:
    fairview(root, "  VSF:\n    like:\n      zone: R-6\n      wins: whichever\n")

    with pytest.raises(RuleLoadError, match="like"):
        load_rules(root)


def test_a_file_may_not_declare_a_reference_verified(root: Path) -> None:
    fairview(
        root,
        "  VSF:\n"
        "    like:\n"
        "      zone: R-6\n"
        "      status: verified\n"
        "      reviewer: sjk\n"
        "      reviewed: 2026-08-14\n",
    )

    with pytest.raises(RuleLoadError, match="may not declare status"):
        load_rules(root)


# --- reviewing the claim ----------------------------------------------


def test_an_unread_reference_blocks_trust(root: Path) -> None:
    # A draft reference could be pointing at the wrong zone entirely, which
    # would hand a whole zone the wrong numbers with nothing on screen to
    # suggest it. Every borrowed value is verified here and it is still not
    # enough.
    fairview(root, "  R-6:\n    setback_front_ft:\n      value: 20\n" + READY + "  VSF:\n    like: R-6\n")

    r = rules(root, encoded=True).resolve(FAIRVIEW, "VSF")

    assert not r.trusted
    assert "R-6.like" not in r.untrusted, "R-6 borrows nothing"
    assert "VSF.like" in r.untrusted


def test_a_signed_reference_lets_the_borrowed_standards_stand(root: Path) -> None:
    fairview(
        root,
        "  R-6:\n"
        "    setback_front_ft:\n      value: 20\n" + READY +
        "    min_lot_sqft:\n      value: 6000\n" + READY +
        "    quadplex_allowed:\n      value: true\n" + READY +
        "  VSF:\n"
        "    like:\n      zone: R-6\n      status: encoded\n"
        "      reviewer: sjk\n      reviewed: 2026-08-14\n",
    )

    r = rules(root, encoded=True).resolve(FAIRVIEW, "VSF")

    assert r.values["setback_front_ft"].trusted
    assert "VSF.like" not in r.untrusted


def test_repointing_a_reference_withdraws_its_signature(root: Path) -> None:
    # The same property the value signatures have, and it matters more here:
    # editing one line moves every standard in the zone at once.
    fairview(root, BORROWED)
    layers = load_rules(root)
    like = layers[FAIRVIEW].zones["VSF"].like
    log = VerificationLog([sign_like(FAIRVIEW, "VSF", like, reviewer="sjk", reviewed=REVIEWED)])

    fairview(root, BORROWED.replace("like: R-6", "like: R-7") + "  R-7:\n    setback_front_ft: 15\n")
    out, orphans = apply_verifications(load_rules(root), log)

    assert out[FAIRVIEW].zones["VSF"].like.status is Status.draft
    assert [(o.zone, o.field) for o in orphans] == [("VSF", "like")]


def test_flipping_the_conflict_rule_withdraws_its_signature(root: Path) -> None:
    # Easier to edit unnoticed than the zone code, and it changes exactly which
    # numbers govern wherever the two texts disagree.
    fairview(root, BORROWED + "    setback_front_ft: 10\n")
    like = load_rules(root)[FAIRVIEW].zones["VSF"].like
    log = VerificationLog([sign_like(FAIRVIEW, "VSF", like, reviewer="sjk", reviewed=REVIEWED)])

    fairview(
        root,
        "  R-6:\n    setback_front_ft: 20\n    min_lot_sqft: 6000\n"
        "  VSF:\n    like:\n      zone: R-6\n      wins: referenced\n"
        "    setback_front_ft: 10\n",
    )
    out, orphans = apply_verifications(load_rules(root), log)

    assert out[FAIRVIEW].zones["VSF"].like.status is Status.draft
    assert orphans[0].reason == "value_changed"
