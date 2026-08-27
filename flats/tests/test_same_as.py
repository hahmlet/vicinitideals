"""A standard the code states by pointing at another standard.

Happy Valley LDC 16.43.030.E.4: "Parking areas shall be set back from a lot
line adjoining a street the same distance as the required building setbacks.
Regardless of other provisions, a minimum setback of ten feet shall be provided
along the property fronting on a public street."

There is one number in that sentence and it is the wrong one to encode. Ten is
the FLOOR; the standard is twenty-two feet in six Happy Valley districts and
twenty in two more, and a file holding the ten alone would be half the rule and
loose by twelve feet -- the one direction this corpus does not err in. So the
rule went unencoded for as long as no carrier could say "the same as that", and
the refusal was written into the layer in those words.

`same_as` is that carrier, and it strikes the same bargain `per_height_ft`
does: the file states only what the code prints -- the field the sentence
points at, and the floor -- and the loader resolves the pair. The difference is
where the other half comes from. A height ratio multiplies by a property of the
BUILDING. This one reads another standard in the same block, which is why the
lender has to be there in the file, three lines up, with its own citation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Provenance, Value
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

HV = "or/clackamas/happy-valley"
POD = ("multi_story", "attached_wall")
PROV = Provenance(
    cite="HV LDC 16.43.030.E.4",
    url="https://ecode360.com/print/HA4934?guid=43529966",
    retrieved="2026-08-27",
    quote="or/clackamas/happy-valley/16.43.parking.txt#L511,L527",
)


def _somewhere(root: Path, body: str) -> Path:
    d = root / "or" / "clackamas"
    d.mkdir(parents=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/clackamas/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  R-6:\n"
        "    cite_default:\n"
        "      cite: LDC 16.43.030\n"
        "      url: https://example.invalid/1643\n"
        "      retrieved: '2026-08-27'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


def _hv():
    return load_rules()[HV]


def test_the_same_distance_as_the_building_setback_is_twenty_two_feet() -> None:
    held = _hv().zones["R40"].values["parking_street_setback_ft"]

    assert held.same_as == "setback_front_ft"
    assert held.floor_ft == 10
    assert held.value == _hv().zones["R40"].values["setback_front_ft"].value == 22


def test_the_printed_ten_is_a_floor_and_binds_only_where_the_yard_is_shallow() -> None:
    """Three answers from one sentence, and the ten is the answer in three
    districts rather than in none.

    R-40 through R-7 set a building back twenty-two feet, R-5 and MUR-S twenty,
    and the three attached districts ten -- so the floor is doing nothing in
    eight zones and is exactly the standard in the other three. Encoding the
    printed figure alone would have been right in three districts out of eleven
    and twelve feet loose in six of them.
    """
    zones = _hv().zones
    got = {z: zones[z].values["parking_street_setback_ft"].value
           for z in ("R40", "R5", "MURS", "SFA", "MURA", "VTH")}

    assert got == {"R40": 22, "R5": 20, "MURS": 20,
                   "SFA": 10, "MURA": 10, "VTH": 10}
    for zone, value in got.items():
        assert value == max(zones[zone].values["setback_front_ft"].value, 10)


def test_a_zone_with_no_setback_to_lend_states_no_parking_setback() -> None:
    """MUR-M and MUR-X print "Variable" for every dimension in Table
    16.22.060-2 -- "determined through the master plan process or design review
    application" -- so there is nothing for the sentence to point at, and the
    file says nothing rather than reaching for another zone's number.
    """
    zones = _hv().zones
    for zone in ("MURM", "MURX"):
        assert "setback_front_ft" not in zones[zone].values
        assert "parking_street_setback_ft" not in zones[zone].values


def test_the_zone_that_adopts_another_adopts_this_too() -> None:
    """R20CC is `like: R20` -- a zoning-layer code with no chapter of its own.

    It holds no local setback for `same_as` to read, and needs none: adoption
    by reference is resolved a layer up, so the borrowed standard arrives with
    everything else R-20 states. The alternative was a hand copy of 22 into a
    zone whose base is an unconfirmed inference, which is the thing `like:`
    exists to avoid.
    """
    rules = RuleSet(load_rules())
    assert rules.resolve(HV, "R20CC", POD).get("parking_street_setback_ft") == 22
    assert rules.resolve(HV, "R20", POD).get("parking_street_setback_ft") == 22


def test_the_citation_carries_the_only_figure_the_sentence_prints() -> None:
    """22 is not in 16.43, and it does not have to be: the sentence prints the
    ten and points at the row that prints the rest, and that row is quoted
    where it is stated.
    """
    from flats.encode.readiness import readiness_for
    from flats.provenance.store import ProvenanceStore

    store = ProvenanceStore()
    zone = _hv().zones["R40"]
    text = store.quote(zone.values["parking_street_setback_ft"].prov.quote)

    assert "same distance as the required building setbacks" in text
    assert "minimum setback of ten feet" in text
    assert "22" not in text

    # And the check that would have caught it. Left to itself the citation
    # ladder looks for the resolved number, finds no 22 anywhere in 16.43 and
    # calls eight zones misquoted -- which it did, before `_printed` learned
    # that a borrowing prints its floor.
    ready = readiness_for(_hv(), store=store)
    assert not [row for row in ready.misquoted
                if row[1] == "parking_street_setback_ft"]
    assert not [row for row in ready.no_evidence
                if row[1] == "parking_street_setback_ft"]


def test_the_lender_lives_in_the_same_block(tmp_path: Path) -> None:
    """Not an implementation limit. A borrowed standard is only as readable as
    the row it borrows from, and a reviewer holding one screen should see both
    numbers and both citations without walking the layer hierarchy.
    """
    with pytest.raises(RuleLoadError, match="no number for it here"):
        load_rules(
            _somewhere(
                tmp_path,
                "    parking_street_setback_ft:\n"
                "      same_as: setback_front_ft\n"
                "      quote: 'or/clackamas/somewhere/16.43.txt#L1'\n",
            ),
            strict=True,
        )


def test_a_standard_may_not_borrow_one_measured_in_another_unit() -> None:
    """What makes a borrowing sound is not which fields are on a list -- it is
    that the two answer in the same unit and bind in the same direction.
    """
    with pytest.raises(ValueError, match="measured in its unit"):
        Value(name="parking_street_setback_ft", value=10,
              same_as="max_coverage_pct", prov=PROV)


def test_a_minimum_may_not_borrow_a_maximum() -> None:
    """Both are lengths, and a floor set to a ceiling is two rules wearing one
    number.
    """
    with pytest.raises(ValueError, match="binds in the other direction"):
        Value(name="parking_street_setback_ft", value=10,
              same_as="setback_front_max_ft", prov=PROV)


def test_a_value_states_its_own_number_or_borrows_one(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="not both"):
        load_rules(
            _somewhere(
                tmp_path,
                "    setback_front_ft:\n"
                "      value: 20\n"
                "      quote: 'or/clackamas/somewhere/16.43.txt#L1'\n"
                "    parking_street_setback_ft:\n"
                "      value: 10\n"
                "      same_as: setback_front_ft\n"
                "      quote: 'or/clackamas/somewhere/16.43.txt#L2'\n",
            ),
            strict=True,
        )


def test_a_floor_with_nothing_to_floor_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="no 'per_height_ft' and no 'same_as'"):
        load_rules(
            _somewhere(
                tmp_path,
                "    setback_front_ft:\n"
                "      value: 20\n"
                "      floor_ft: 10\n"
                "      quote: 'or/clackamas/somewhere/16.43.txt#L1'\n",
            ),
            strict=True,
        )
