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
from flats.score.paper import BY_COVERAGE, BY_ENVELOPE, BY_MIN_LOT, paper_fit
from flats.tests.signing import sign_encoded

pytestmark = pytest.mark.unit

GRESHAM = "or/41051-multnomah/4131250-gresham"

CITE = (
    "cite_default:\n"
    '  cite: "GRC 9.0100, Table 9.0100"\n'
    '  url: "https://example.gov/9.0100"\n'
    "  retrieved: 2026-08-14\n"
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
    """Resolve R5 with these standards. ``draft`` names one left unsigned."""
    body = ["  R5:\n"]
    for name, value in {**BASE, **fields}.items():
        status = "" if name == draft else "      status: encoded\n"
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


def test_a_number_nobody_has_signed_is_not_a_requirement(tmp_path: Path) -> None:
    # A draft side setback is a number somebody typed. Quoting it as the lot
    # a market demands is the same mistake as screening a parcel on it.
    got = fit(tmp_path, draft="setback_side_ft")

    assert got.unknown == ("setback_side_ft",)
    assert got.min_width_ft is None
    assert not got.complete
    # Depth is unaffected — one missing standard does not void the others.
    assert got.min_depth_ft == 76


def test_an_orientation_that_could_not_be_costed_never_wins(tmp_path: Path) -> None:
    # With no envelope, both orientations tie on the area floor the code
    # states, and the answer is that floor rather than nothing.
    got = fit(tmp_path, draft="setback_side_ft", min_lot_sqft=7000)

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


def test_four_lots_need_four_of_every_per_lot_standard(tmp_path: Path) -> None:
    # 1,500 sq ft is a townhouse lot. Four of them is the project, and reading
    # that number once would say this pod fits on a 4,416 sq ft parcel.
    assert fit(tmp_path, design=SPLIT, min_lot_sqft=1500).min_area_sqft == 6000
    assert fit(tmp_path, min_lot_sqft=1500).min_area_sqft == 4416


def test_shared_walls_do_not_multiply_the_side_yards(tmp_path: Path) -> None:
    # Only the two ends of the row see a side yard, whichever way it is
    # platted. Scaling setbacks with the lots would invent six yards.
    assert fit(tmp_path, design=SPLIT).min_depth_ft == fit(tmp_path).min_depth_ft
    assert fit(tmp_path, design=SPLIT).min_width_ft == 46


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
