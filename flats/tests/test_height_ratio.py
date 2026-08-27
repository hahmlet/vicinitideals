"""A setback measured off the building instead of off the lot.

Every other standard in this corpus is a fact about the parcel: so many feet
from the line, so many square feet of area, so many dwellings to the acre. You
can read it without knowing what is going to be built. Portland's IR zone is
the exception. Its column of Table 150-2's three minimum-setback rows is one
merged cell -- "1 ft. for every 2 ft. of building height but not less than 10
ft." -- and until the building is named there is no number at all.

For a 26 ft pod there is: 13 ft, on every lot line, whatever is across it. But
13 appears nowhere in Chapter 33.150, so writing it into the rule file would
have been exactly the invented figure the readiness ladder exists to catch, and
writing the printed 10 instead would have stated a floor as if it were the
standard -- three feet looser on every side of the building.

So the file states the two figures a reader will find, the product is made at
load, and the citation is checked against the ratio. The same bargain `acres`,
`per_dwelling` and `sqft_per_unit` strike; the difference is what the missing
half comes from. Those three multiply by a property of the standard. This one
multiplies by a property of the building, which is why the constant it reads is
the tallest design in the catalog rather than a typical one -- a taller
building owes a larger setback, and the conservative answer is the strict one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.designs.model import load_catalog
from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS
from flats.rules.fields import DESIGN_HEIGHT_FT, HEIGHT_RATIO_FIELDS
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Provenance, Value
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
POD = ("multi_story", "attached_wall")
YARDS = ("setback_front_ft", "setback_side_ft", "setback_rear_ft")
PROV = Provenance(
    cite="PCC 33.150 Table 150-2",
    url="https://www.portland.gov/sites/default/files/code/150-campus-inst-zones_1.pdf",
    retrieved="2026-08-20",
    quote=f"{PORTLAND}/33.150.txt#L531,L538-L545",
)


def _somewhere(root: Path, body: str) -> Path:
    d = root / "or" / "multnomah"
    d.mkdir(parents=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/multnomah/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  R-6:\n"
        "    cite_default:\n"
        "      cite: PCC 33.150\n"
        "      url: https://example.invalid/150\n"
        "      retrieved: '2026-08-20'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def test_one_foot_for_every_two_of_a_twenty_six_foot_pod_is_thirteen() -> None:
    held = load_rules()[PORTLAND].zones["IR"].values["setback_side_ft"]

    assert held.per_height_ft == 2
    assert held.floor_ft == 10
    assert held.value == DESIGN_HEIGHT_FT / 2 == 13


def test_the_floor_is_a_maximum_against_the_ratio_not_a_substitute() -> None:
    """"but not less than 10 ft." — below the floor the ratio governs, above it
    the floor does, and which of the two binds is a fact about the building.

    A 16 ft building would owe 8 by the ratio and 10 by the floor, and the code
    would ask for 10. Nothing in this corpus is 16 ft, which is the point:
    encoding the answer rather than the rule would be right until it was not.
    """
    held = load_rules()[PORTLAND].zones["IR"].values["setback_side_ft"]
    assert held.value == 13
    assert held.value > held.floor_ft
    assert DESIGN_HEIGHT_FT / held.per_height_ft > held.floor_ft


def test_the_merged_cell_makes_all_three_yards_one_standard() -> None:
    """CI1 and CI2 read 15/10/0 down the three rows and IR reads one cell.

    So the neighbour's zoning -- unmeasured everywhere else in this chapter --
    changes nothing here, and the front lot line owes what the side does,
    because each row is headed "Lot line abutting or ACROSS THE STREET FROM".
    """
    rules = RuleSet(load_rules())
    res = rules.resolve(PORTLAND, "IR", POD)

    assert {res.values[f].value for f in YARDS} == {13}
    assert res.missing_required == ()

    ci2 = rules.resolve(PORTLAND, "CI2", POD)
    assert {ci2.values[f].value for f in YARDS} == {10}


def test_the_citation_is_checked_against_the_ratio_not_the_product() -> None:
    """Chapter 33.150 prints 2, prints 10, and prints 13 nowhere."""
    ready = readiness_for(load_rules()[PORTLAND], store=ProvenanceStore())

    assert not [row for row in ready.misquoted if row[0] == "IR"]
    assert not [row for row in ready.no_evidence if row[0] == "IR"]


def test_the_cell_quoted_carries_both_printed_figures() -> None:
    store = ProvenanceStore()
    text = store.quote(load_rules()[PORTLAND].zones["IR"].values["setback_side_ft"].prov.quote)

    assert "every 2 ft." in text
    assert "than 10 ft." in text
    assert "13" not in text


def test_the_frontage_that_must_be_built_up_to_the_street_owes_no_setback() -> None:
    """Note [5]: "for frontages where the maximum building setback applies,
    there is no minimum setback."

    Encoded as an exemption rather than a zero, because that is what the
    sentence says -- the standard is not there, rather than being one every lot
    passes. It waits on a transit street classification and a Pedestrian
    District map, neither of which this screen reads, so the 13 binds.
    """
    assert CONDITIONS["on_transit_street"].kind == "site_fact"
    assert CONDITIONS["on_transit_street"].assume is None

    rules = RuleSet(load_rules())
    assert rules.resolve(PORTLAND, "IR", POD).values["setback_front_ft"].value == 13

    on_a_transit_street = rules.resolve(PORTLAND, "IR", (*POD, "on_transit_street"))
    assert "setback_front_ft" not in on_a_transit_street.values


def test_the_same_note_reaches_the_campus_zone_next_to_it() -> None:
    """CI2 read `setback_front_ft: 0` on the reading that Table 150-2 states no
    minimum street setback at all. It does: each of the three minimum rows is
    headed "Lot line abutting or across the street from", 33.150.215.B names no
    other source, and note [5] only means something if a minimum otherwise
    reaches a frontage. The zone is 245 lots and the correction tightens it.
    """
    rules = RuleSet(load_rules())
    assert rules.resolve(PORTLAND, "CI2", POD).values["setback_front_ft"].value == 10

    on_a_transit_street = rules.resolve(PORTLAND, "CI2", (*POD, "on_transit_street"))
    assert "setback_front_ft" not in on_a_transit_street.values

    across_from_industry = rules.resolve(
        PORTLAND, "CI2", (*POD, "abuts_nonresidential_zone")
    )
    assert across_from_industry.values["setback_front_ft"].value == 0


def test_the_constant_is_the_tallest_thing_in_the_catalog() -> None:
    """The guard this form is owed.

    `DESIGN_HEIGHT_FT` is a design dimension living in the rules registry, and
    the honest defence of that is that both catalog pods are 26 ft two-storey
    townhomes and the screen answers for one building. The moment a third
    design is taller, every height-proportional setback in the corpus is
    understated and nothing else would say so.
    """
    tallest = max(d.height_ft for d in load_catalog())
    assert tallest == DESIGN_HEIGHT_FT, (
        f"catalog now holds a {tallest} ft design; DESIGN_HEIGHT_FT is "
        f"{DESIGN_HEIGHT_FT} and every per_height_ft setback is understated"
    )


def test_only_a_distance_may_be_stated_off_the_building() -> None:
    """A minimum lot AREA per foot of height is not a rule any code writes."""
    assert "min_lot_sqft" not in HEIGHT_RATIO_FIELDS

    with pytest.raises(ValueError, match="ratio of building height"):
        Value(name="min_lot_sqft", value=5000, per_height_ft=2, prov=PROV)


def test_a_ratio_of_zero_is_not_a_ratio(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="is not a ratio"):
        load_rules(
            _somewhere(
                tmp_path,
                "    setback_side_ft:\n"
                "      per_height_ft: 0\n"
                "      quote: 'or/multnomah/somewhere/33.txt#L1'\n",
            ),
            strict=True,
        )


def test_a_value_states_a_distance_or_a_ratio_and_not_both(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="a distance or a ratio"):
        load_rules(
            _somewhere(
                tmp_path,
                "    setback_side_ft:\n"
                "      per_height_ft: 2\n"
                "      value: 13\n"
                "      quote: 'or/multnomah/somewhere/33.txt#L1'\n",
            ),
            strict=True,
        )


def test_a_floor_with_no_ratio_under_it_is_refused(tmp_path: Path) -> None:
    """`floor_ft` is the least a DERIVED standard may come to.

    On its own it is a plain minimum written in the wrong key, and a file that
    accepted it would read as encoding a rule while stating half of one. The
    key is shared with `same_as` -- "the same distance as the required building
    setbacks... not less than ten feet" is one sentence with a ratio's shape
    and a field where the ratio would be -- so a floor is refused only when
    there is neither of the two under it.
    """
    with pytest.raises(RuleLoadError,
                       match="no 'per_height_ft' and no 'same_as' here"):
        load_rules(
            _somewhere(
                tmp_path,
                "    setback_side_ft:\n"
                "      floor_ft: 10\n"
                "      quote: 'or/multnomah/somewhere/33.txt#L1'\n",
            ),
            strict=True,
        )
