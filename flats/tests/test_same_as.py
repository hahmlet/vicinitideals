"""A standard the code states by pointing at another standard.

Happy Valley LDC 16.43.030.E.4, until Ord. 603 (8/18/2026): "Parking areas
shall be set back from a lot line adjoining a street the same distance as the
required building setbacks. Regardless of other provisions, a minimum setback
of ten feet shall be provided along the property fronting on a public street."

There was one number in that sentence and it was the wrong one to encode. Ten
was the FLOOR; the standard was twenty-two feet in six Happy Valley districts
and twenty in two more, and a file holding the ten alone would have been half
the rule and loose by twelve feet -- the one direction this corpus does not err
in. So the rule went unencoded for as long as no carrier could say "the same as
that", and the refusal was written into the layer in those words.

`same_as` is that carrier, and it strikes the same bargain `per_height_ft`
does: the file states only what the code prints -- the field the sentence
points at, and the floor -- and the loader resolves the pair. The difference is
where the other half comes from. A height ratio multiplies by a property of the
BUILDING. This one reads another standard in the same block, which is why the
lender has to be there in the file, three lines up, with its own citation.

Ord. 603 replaced the sentence with a flat "minimum of 10 feet from the public
right-of-way and abutting properties" (16.43.030.D.2, re-fetched 2026-11-09,
FOLLOWUPS 166), so Happy Valley now prints its number and borrows nothing. The
carrier is exercised here on Canby, whose zones send parking to "the street
yard", and on a synthetic layer for the floor.
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


CANBY = "or/clackamas/canby"


def test_the_same_distance_as_the_building_setback_is_the_street_yard() -> None:
    held = load_rules()[CANBY].zones["R-1.5"].values["parking_street_setback_ft"]

    assert held.same_as == "setback_front_ft"
    assert held.floor_ft is None
    assert held.value == load_rules()[CANBY].zones["R-1.5"].values["setback_front_ft"].value == 20


def test_the_floor_binds_only_where_the_lender_is_shallower(tmp_path: Path) -> None:
    """The bargain Happy Valley's old E.4 struck: the borrowed setback, never
    less than the printed ten. Two zones, one deeper than the floor and one
    shallower, give one answer each.
    """
    root = _somewhere(
        tmp_path,
        "    setback_front_ft:\n"
        "      value: 22\n"
        "      quote: 'or/clackamas/somewhere/16.22.txt#L1'\n"
        "    parking_street_setback_ft:\n"
        "      same_as: setback_front_ft\n"
        "      floor_ft: 10\n"
        "      quote: 'or/clackamas/somewhere/16.43.txt#L1'\n"
        "  SFA:\n"
        "    cite_default:\n"
        "      cite: LDC 16.43.030\n"
        "      url: https://example.invalid/1643\n"
        "      retrieved: '2026-08-27'\n"
        "    setback_front_ft:\n"
        "      value: 5\n"
        "      quote: 'or/clackamas/somewhere/16.22.txt#L2'\n"
        "    parking_street_setback_ft:\n"
        "      same_as: setback_front_ft\n"
        "      floor_ft: 10\n"
        "      quote: 'or/clackamas/somewhere/16.43.txt#L1'\n",
    )
    zones = load_rules(root)["or/clackamas/somewhere"].zones
    assert zones["R-6"].values["parking_street_setback_ft"].value == 22
    assert zones["SFA"].values["parking_street_setback_ft"].value == 10


def test_happy_valley_now_prints_its_number() -> None:
    """Ord. 603 (8/18/2026): "Parking areas shall be setback a minimum of 10
    feet from the public right-of-way and abutting properties." Held as
    printed in every zone that held the borrowing, and 16.43.030.H exempts
    middle housing from the subsection, so it binds nothing for the pod.
    """
    zones = _hv().zones
    got = {z: zones[z].values["parking_street_setback_ft"]
           for z in ("R40", "R5", "MURS", "SFA", "MURA", "VTH")}
    for zone, held in got.items():
        assert held.same_as is None, zone
        assert held.value == 10, zone
        assert zones[zone].values["setback_front_ft"].value >= 10, zone


def test_a_zone_with_no_setback_to_lend_states_no_parking_setback() -> None:
    """MUR-M and MUR-X print "Variable" for every dimension in Table
    16.22.060-2 -- "determined through the master plan process or design review
    application" -- so there was nothing for the old sentence to point at, and
    the file said nothing rather than reaching for another zone's number. The
    new D.2 states its own ten, but 16.43.030.H exempts the pod from it, so
    these two still hold nothing: a held ten would bind nothing either.
    """
    zones = _hv().zones
    for zone in ("MURM", "MURX"):
        assert "setback_front_ft" not in zones[zone].values
        assert "parking_street_setback_ft" not in zones[zone].values


def test_the_zone_that_adopts_another_adopts_this_too() -> None:
    """R20CC is `like: R20` -- a zoning-layer code with no chapter of its own.

    It holds no local parking setback, and needs none: adoption by reference
    is resolved a layer up, so the standard arrives with everything else R-20
    states.
    """
    rules = RuleSet(load_rules())
    assert rules.resolve(HV, "R20CC", POD).get("parking_street_setback_ft") == 10
    assert rules.resolve(HV, "R20", POD).get("parking_street_setback_ft") == 10


def test_the_citation_of_a_borrowing_quotes_the_lender() -> None:
    """Canby's parking setback borrows the street yard, and its quote is the
    street-yard line itself, so the citation ladder finds the number where it
    is printed and calls nothing misquoted.
    """
    from flats.encode.readiness import readiness_for
    from flats.provenance.store import ProvenanceStore

    store = ProvenanceStore()
    layer = load_rules()[CANBY]
    text = store.quote(layer.zones["R-1.5"].values["parking_street_setback_ft"].prov.quote)

    assert "Street yard: twenty feet" in text

    ready = readiness_for(layer, store=store)
    assert not [row for row in ready.misquoted
                if row[1] == "parking_street_setback_ft"]
    assert not [row for row in ready.no_evidence
                if row[1] == "parking_street_setback_ft"]


def test_happy_valleys_ten_is_quoted_where_it_is_printed() -> None:
    from flats.provenance.store import ProvenanceStore

    text = ProvenanceStore().quote(
        _hv().zones["R40"].values["parking_street_setback_ft"].prov.quote)
    assert "Parking Location" in text
    assert "minimum of 10 feet from the public right-of-way" in text


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
