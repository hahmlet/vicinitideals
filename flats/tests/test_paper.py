"""Paper fit — the lot a design needs before any lot is looked at.

Two things are being pinned. That the answer is the *less demanding* of the
orientations, because a requirement stated for the worse one is a requirement
nobody has to meet. And that the plat path changes the answer: the same
building on the same zone needs a different lot depending on whether it is
permitted as one quadplex or as four townhouse lots, which is why that choice
belongs to the design rather than to whoever wrote the rule file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.designs.model import Design, Plat
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet
from flats.score.paper import BY_COVERAGE, BY_ENVELOPE, BY_MIN_LOT, _pair, paper_fit
from flats.tests.signing import sign_encoded

pytestmark = pytest.mark.unit

GRESHAM = "or/41051-multnomah/4131250-gresham"

CITE = (
    "cite_default:\n"
    '  cite: "GRC 9.0100, Table 9.0100"\n'
    '  url: "https://example.gov/9.0100"\n'
    "  retrieved: 2026-08-14\n"
    "  quote: \"or/multnomah/gresham/9.0100.txt#L2\"\n"
)

#: Front 20, rear 20, side 5. Broadside the pod wants 66 x 76; end-on 46 x 96,
#: which is the smaller lot and the one the answer should be about.
BASE: dict[str, object] = {
    "setback_front_ft": 20,
    "setback_rear_ft": 20,
    "setback_side_ft": 5,
}

POD = Design(
    id="pod56x36",
    version=1,
    label="56 x 36 quad",
    typology="townhome_rear_court",
    footprint={"width_ft": 56, "depth_ft": 36},
    units=4,
    stories=2,
    height_ft=26,
    parking={"stalls_per_unit": 1.5, "config": "rear_court"},
    delivery={"method": "panelized"},
)
SPLIT = POD.model_copy(update={"plat": Plat.unit_lots})


def rules(root: Path, draft: str, fields: dict[str, object]) -> RuleSet:
    """Resolve R5 with these standards. ``draft`` names one left unsigned.

    A value written as ``(base, per_unit)`` states the whole-building number
    and, as a variant keyed on ``unit_lots``, the number the code states for a
    townhouse lot — which is how a real encoding carries both.
    """
    body = ["  R5:\n"]
    for name, value in {**BASE, **fields}.items():
        if value is None:
            continue
        status = "" if name == draft else "      status: encoded\n"
        if isinstance(value, tuple):
            base, split = value
            body.append(
                f"    {name}:\n      value: {base}\n{status}"
                "      variants:\n"
                f"        - value: {split}\n"
                "          when: [unit_lots]\n"
                f"{'' if name == draft else '          status: encoded'}\n"
            )
            continue
        body.append(f"    {name}:\n      value: {value}\n{status}")
    path = root / f"{GRESHAM}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("label: Gresham\n" + CITE + "zones:\n" + "".join(body), encoding="utf-8")
    return RuleSet(sign_encoded(load_rules(root)))


def fit(root: Path, design: Design = POD, draft: str = "", **fields: object):
    zone = rules(root, draft, fields).resolve(GRESHAM, "R5", design.conditions)
    return paper_fit(design, zone)


# --- the shape of the lot --------------------------------------------


def test_the_cheaper_orientation_is_the_one_reported(tmp_path: Path) -> None:
    # Broadside is 66 x 76 = 5,016; end-on is 46 x 96 = 4,416. Reporting the
    # first would tell somebody a lot they can build on is too small.
    got = fit(tmp_path)

    assert (got.min_width_ft, got.min_depth_ft) == (46, 96)
    assert got.orientation == "depth_facing"
    assert got.min_area_sqft == 4416
    assert got.binding == BY_ENVELOPE
    assert got.complete


def test_a_minimum_lot_area_above_the_envelope_is_what_binds(tmp_path: Path) -> None:
    # The envelope says 4,416 and the code says 7,000. The lot has to clear
    # both, and the page should say which one is the thing to argue with.
    got = fit(tmp_path, min_lot_sqft=7000)

    assert got.min_area_sqft == 7000
    assert got.binding == BY_MIN_LOT


def test_a_coverage_cap_states_a_lot_size_without_naming_one(tmp_path: Path) -> None:
    # 2,016 sq ft of building at 20% of the lot needs 10,080 sq ft of lot, and
    # no line in the code says 10,080.
    got = fit(tmp_path, min_lot_sqft=7000, max_coverage_pct=20)

    assert got.min_area_sqft == pytest.approx(10080)
    assert got.binding == BY_COVERAGE


def test_a_lot_width_minimum_widens_a_narrower_envelope(tmp_path: Path) -> None:
    # End-on, the building plus its side yards is 46 ft. Where the code sets a
    # 100 ft minimum lot width, 100 is the requirement and 46 is not.
    assert fit(tmp_path, min_lot_width_ft=100).min_width_ft == 100


def test_a_width_minimum_can_flip_which_orientation_is_cheaper(tmp_path: Path) -> None:
    # A 60 ft minimum buys nothing end-on — that lot still has to be 96 deep,
    # so 60 x 96 loses to 66 x 76 and the building turns to face the street.
    assert fit(tmp_path).orientation == "depth_facing"
    assert fit(tmp_path, min_lot_width_ft=60).orientation == "width_facing"


# --- what may be used ------------------------------------------------


def test_a_number_nobody_has_read_yet_is_used_and_named(tmp_path: Path) -> None:
    # A draft side setback is a number somebody typed and nobody has checked.
    # Refusing to use it would blank the page; using it silently would dress a
    # draft as a requirement. It is used, and the answer says it rests on it.
    got = fit(tmp_path, draft="setback_side_ft")

    assert got.min_width_ft == 46
    assert got.unsigned == ("setback_side_ft",)
    assert got.complete, "stated but unread is not missing"
    assert not got.signed
    assert not got.certain


def test_only_a_signed_and_complete_answer_is_certain(tmp_path: Path) -> None:
    got = fit(tmp_path)

    assert got.certain
    assert got.signed


def test_a_standard_the_zone_never_states_is_missing_not_unsigned(tmp_path: Path) -> None:
    # The whole point of the split: "the code has no such rule" and "nobody has
    # verified this rule" are different problems with different fixes.
    got = fit(tmp_path, setback_side_ft=None)

    assert got.unknown == ("setback_side_ft",)
    assert got.unsigned == ()
    assert got.min_width_ft is None
    assert not got.complete
    # Depth is unaffected — one missing standard does not void the others.
    assert got.min_depth_ft == 76


def test_an_orientation_that_could_not_be_costed_never_wins(tmp_path: Path) -> None:
    # With no envelope, both orientations tie on the area floor the code
    # states, and the answer is that floor rather than nothing.
    got = fit(tmp_path, setback_side_ft=None, min_lot_sqft=7000)

    assert got.min_area_sqft == 7000
    assert got.binding == BY_MIN_LOT


def test_the_standards_left_out_are_named_and_why(tmp_path: Path) -> None:
    # A street-side setback binds corner lots. Folding it into every answer
    # would overstate the frontage this design needs everywhere.
    got = fit(tmp_path)

    assert any("street_side" in x for x in got.excluded)
    assert any("frontage" in x for x in got.excluded)


# --- height ----------------------------------------------------------


def test_height_is_checked_only_where_the_zone_states_a_limit(tmp_path: Path) -> None:
    assert fit(tmp_path).height_ok is None
    assert fit(tmp_path).fits_height, "no stated limit is not a failed one"


def test_a_two_storey_pod_fails_a_limit_it_exceeds(tmp_path: Path) -> None:
    got = fit(tmp_path, max_height_ft=25)

    assert got.height_ok is False
    assert not got.fits_height
    assert fit(tmp_path, max_height_ft=35).height_ok is True


# --- the plat path ---------------------------------------------------


def test_four_lots_need_four_of_the_codes_townhouse_minimum(tmp_path: Path) -> None:
    # The zone says 7,000 for a fourplex and 1,500 for a townhouse lot. Split,
    # the project needs four of the 1,500s; whole, it needs the 7,000.
    banded = {"min_lot_sqft": (7000, 1500)}

    assert fit(tmp_path, design=SPLIT, **banded).min_area_sqft == 6000
    assert fit(tmp_path, **banded).min_area_sqft == 7000


def test_the_fourplex_minimum_is_not_multiplied_into_a_townhouse_one(tmp_path: Path) -> None:
    # 7,000 sq ft is the lot a fourplex needs. On four lots it is not the
    # standard at all, and x4 would invent a 28,000 sq ft requirement out of
    # it. Where the code's townhouse row is not encoded, the honest answer is
    # that we do not have that standard — which is an encoding job, not a
    # number to guess.
    got = fit(tmp_path, design=SPLIT, min_lot_sqft=7000)

    assert "min_lot_sqft" in got.unknown
    assert got.min_area_sqft == 4416, "the envelope still answers"
    assert not got.complete


def test_shared_walls_do_not_multiply_the_side_yards(tmp_path: Path) -> None:
    # Only the two ends of the row see a side yard, whichever way it is
    # platted. Scaling setbacks with the lots would invent six yards.
    assert fit(tmp_path, design=SPLIT).min_depth_ft == fit(tmp_path).min_depth_ft
    assert fit(tmp_path, design=SPLIT).min_width_ft == 46


def test_the_coverage_cap_does_not_care_how_the_ground_is_divided(tmp_path: Path) -> None:
    # The same building over the same ground is the same share of it whether
    # that ground is one lot or four.
    whole = fit(tmp_path, max_coverage_pct=20)
    split = fit(tmp_path, design=SPLIT, max_coverage_pct=20)

    assert whole.min_area_sqft == split.min_area_sqft == pytest.approx(10080)


def test_the_plat_path_is_carried_on_the_answer(tmp_path: Path) -> None:
    # Two plat paths are two answers, and a page showing both must be able to
    # say which is which without asking the catalog again.
    assert fit(tmp_path).plat == "one_lot"
    assert fit(tmp_path, design=SPLIT).plat == "unit_lots"


def test_the_split_is_a_condition_the_rule_layer_can_read(tmp_path: Path) -> None:
    # A code that states a townhouse lot width separately needs to be told
    # which product this is. The design says so; nothing on the parcel can.
    assert "unit_lots" in SPLIT.conditions
    assert "unit_lots" not in POD.conditions


# --- the statute behind the plat path ---------------------------------
#
# Left to itself, the split path reported a hole in 76 of the 86 zones that
# allow a fourplex: no townhouse lot standard encoded, so no answer. The hole
# was never in the codes. Oregon answers it once, for all of them.


def test_the_parent_lots_minimum_governs_a_middle_housing_land_division(
    tmp_path: Path,
) -> None:
    # ORS 92.031(2)(b): the plan must comply with the regulations "applicable
    # to the original lot or parcel". One 7,000 sq ft lot meets the zone and
    # the four lots inside it inherit nothing further to meet.
    got = fit(
        tmp_path,
        design=SPLIT,
        min_lot_sqft=7000,
        land_division_parent_standards=True,
    )

    assert got.min_area_sqft == 7000
    assert got.complete, "the standard is stated; the statute says which one applies"


def test_the_parent_lot_rule_is_not_four_parent_lots(tmp_path: Path) -> None:
    # The failure this exists to prevent: reading "the original lot's standard
    # applies" as "and once per resulting lot". A city may not charge four
    # minimum lot sizes for splitting one building.
    whole = fit(tmp_path, min_lot_sqft=7000)
    split = fit(
        tmp_path, design=SPLIT, min_lot_sqft=7000, land_division_parent_standards=True
    )

    assert split.min_area_sqft == whole.min_area_sqft


def test_a_citys_own_townhouse_row_still_wins(tmp_path: Path) -> None:
    # The statute says which lot the zone's standards attach to. It does not
    # erase a townhouse lot standard a city states for a conventional
    # subdivision — a different path to the same building. Where the encoding
    # carries one, it is the one asked, four times.
    got = fit(
        tmp_path,
        design=SPLIT,
        min_lot_sqft=(7000, 1500),
        land_division_parent_standards=True,
    )

    assert got.min_area_sqft == 6000


def test_without_the_statute_the_split_path_still_admits_it_does_not_know(
    tmp_path: Path,
) -> None:
    # Not every jurisdiction is inside the middle-housing regime — outside a
    # UGB, under 1,000 people, unincorporated without urban services. Where no
    # layer states the rule, the answer stays "we do not have that standard".
    assert "min_lot_sqft" in fit(tmp_path, design=SPLIT, min_lot_sqft=7000).unknown


def test_the_one_lot_path_is_untouched_by_the_statute(tmp_path: Path) -> None:
    # It is a rule about land division. A quadplex on one lot divides nothing,
    # and its answer must not move because the flag is present.
    assert fit(tmp_path, min_lot_sqft=7000).min_area_sqft == fit(
        tmp_path, min_lot_sqft=7000, land_division_parent_standards=True
    ).min_area_sqft


# --- a code that regulates the pair, not either yard ---------------------


def test_a_combined_side_yard_is_spent_once_not_twice() -> None:
    """Lake Oswego's R-7.5 cell reads "Total 15, 5 min." Doubling the 5 would
    ask 10 feet of a lot the code asks 15 of; halving the 15 -- which is what
    the encoding used to do -- puts a number in the file that the document
    does not print."""
    assert _pair(5.0, 15.0) == 15.0
    # A floor that would push the pair wider than the stated total governs.
    assert _pair(8.0, 15.0) == 16.0
    # Either alone is what there is.
    assert _pair(5.0, None) == 10.0
    assert _pair(None, 15.0) == 15.0
    # Neither is an unknown requirement, not a free one.
    assert _pair(None, None) is None
