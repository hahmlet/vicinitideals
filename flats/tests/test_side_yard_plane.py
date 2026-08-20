"""A side yard printed as five feet, on a table that also prints eleven.

Milwaukie's Table 19.301.4 gives R-MD a 5 ft side yard. Four rows below it, the
same table gives a "Side yard height plane limit": 20 ft of height allowed at
the minimum side yard depth, and a plane sloping up from there at 45 degrees. A
26 ft wall is six feet over that plane, and at 45 degrees it buys six feet of
height with six feet of distance. The side yard for this building is 11 ft.

Both numbers had been in the store since 13 August, four rows apart, and only
one of them was read. Nothing reported it, which is the part worth dwelling on:
the coverage ledger counts fields and there is no field for the slope of a
plane, the citation checker verifies the lines that *are* cited, and the
cross-reference ledger looks for chapters we cannot open. A rule printed on the
same page as one we encoded, in a document we hold, was invisible to all three.
:mod:`flats.encode.uncited` is the check that sees it, and this file is the
finding.

The form is Gresham's -- ``step_back`` already existed for a roof plane in
another chapter -- with one addition. Gresham writes its plane as a rate, "one
foot in height for every one foot of distance"; Milwaukie writes the same plane
as an angle, "Slope of plane (degrees) 45". Typing ``rise_per_ft: 1`` against a
cell that prints 45 would be an invented figure: exact, trivially derivable,
and still not the number a reviewer opening the page would find. So the file
states the angle and the loader takes the tangent, which is the bargain every
derived form here makes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import DESIGN_HEIGHT_FT
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

MILWAUKIE = "or/clackamas/milwaukie"
POD = ("multi_story", "attached_wall")
#: The plane each zone prints, and the side yard a 26 ft wall ends up with.
PLANED = {"R-MD": (20, 11), "R-HD": (25, 6)}


@pytest.fixture(scope="module")
def milwaukie() -> Layer:
    return load_rules()[MILWAUKIE]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _somewhere(root: Path, body: str) -> Path:
    d = root / "or" / "clackamas"
    d.mkdir(parents=True)
    (d / "somewhere.yaml").write_text(
        "layer: or/clackamas/somewhere\n"
        "kind: city\n"
        "label: Somewhere\n"
        "zones:\n"
        "  R-MD:\n"
        "    cite_default:\n"
        "      cite: MMC 19.301.4\n"
        "      url: https://example.invalid/19301\n"
        "      retrieved: '2026-08-20'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


# -- what the plane does to Milwaukie ---------------------------------------


def test_the_side_yard_this_building_actually_gets(rules: RuleSet) -> None:
    for zone, (_, stood_back) in PLANED.items():
        res = rules.resolve(MILWAUKIE, zone, POD)
        assert res.values["setback_side_ft"].value == stood_back, zone


def test_the_table_keeps_the_five_feet_it_prints(milwaukie: Layer) -> None:
    """`before_step_back` is what a reviewer finds in row C.1, and it has to
    survive: the citation check compares that figure against the table's own
    quote, and the table prints 5 in both zones."""
    for zone in PLANED:
        held = milwaukie.zones[zone].values["setback_side_ft"]
        assert held.before_step_back == 5, zone


def test_the_arithmetic_is_the_two_cells_and_nothing_else(
    milwaukie: Layer,
) -> None:
    for zone, (allowed, stood_back) in PLANED.items():
        held = milwaukie.zones[zone].values["setback_side_ft"]
        owed = (DESIGN_HEIGHT_FT - held.step_back_at_ft) / held.step_back_rise
        assert held.step_back_at_ft == allowed, zone
        assert held.before_step_back + owed == stood_back, zone


def test_the_angle_is_what_the_file_states(milwaukie: Layer) -> None:
    """45 degrees is printed; the 1:1 rate is not. A file holding the rate
    would hold a number nobody could find on the page."""
    for zone in PLANED:
        held = milwaukie.zones[zone].values["setback_side_ft"]
        assert held.step_back_degrees == 45, zone
        assert held.step_back_rise == 1.0, zone


def test_both_cells_are_quoted(milwaukie: Layer, store: ProvenanceStore) -> None:
    plane = store.quote(milwaukie.zones["R-MD"].values["setback_side_ft"].step_back_quote)

    assert "Side yard height plane limit" in plane
    assert "Height above ground at minimum required side yard depth (ft)" in plane
    assert "Slope of plane (degrees)" in plane
    assert "20" in plane and "45" in plane

    hd = store.quote(milwaukie.zones["R-HD"].values["setback_side_ft"].step_back_quote)
    assert "25" in hd


def test_neither_cell_prints_the_answer(
    milwaukie: Layer, store: ProvenanceStore
) -> None:
    """Which is why it is computed. The table prints 5, 20 and 45, and prints
    11 nowhere."""
    held = milwaukie.zones["R-MD"].values["setback_side_ft"]
    assert "11" not in store.quote(held.step_back_quote).replace("11.", "")

    ready = readiness_for(milwaukie, store=ProvenanceStore())
    assert not [row for row in ready.misquoted if row[0] in PLANED]
    assert not [row for row in ready.no_evidence if row[0] in PLANED]


def test_where_the_plane_starts_is_the_difference_between_eleven_and_six(
    store: ProvenanceStore,
) -> None:
    """The definition is load-bearing and lives in another document.

    Read as starting at the lot line, the plane would put the wall at 6 ft in
    R-MD instead of 11. MMC 19.200 settles it, and because a quote may not
    span two documents the sentence is cited in the encoding's comment rather
    than carried on the value -- so this asserts the sentence still says what
    the comment claims.
    """
    text = store.quote(f"{MILWAUKIE}/19.200.definitions.txt#L813-L814")

    assert "Side yard height plane" in text
    assert "horizontally offset from the side lot line by the required side yard depth" in text
    assert "slopes up at a specified angle" in text


def test_the_exceptions_section_does_not_reach_a_wall(store: ProvenanceStore) -> None:
    """19.501.3 is titled Exceptions, which is the reason it had to be fetched
    before any of this could be encoded. It grants two, and a solid wall is
    neither: objects not used for human occupancy, and eaves up to 30 in."""
    text = store.quote(f"{MILWAUKIE}/19.500.supplementary.txt#L89-L101")

    assert "not used for human occupancy" in text
    assert "Roof overhangs or eaves" in text
    assert "30 in horizontally beyond the side yard height plane" in text


def test_the_cumulative_yard_that_was_read_backwards(milwaukie: Layer) -> None:
    """19.301.5.A makes the side yards asymmetric above 7,000 sq ft -- 5 ft and
    10 ft, so 15 cumulative -- and the file's own note used to call encoding 5
    the cautious reading. Five either side reserves 10 where the code demands
    15, which passes a pod five feet too wide.

    It is still unencoded, and now for a reason that survives inspection: the
    plane puts both side yards at 11, so the pair is 22 and a cumulative 15
    cannot bind. The note has to say which of those two things is true.
    """
    notes = milwaukie.zones["R-MD"].notes or ""

    assert "19.301.5.A" in notes
    assert "setback_side_total_ft" in notes
    assert "five feet too wide" in notes


# -- the form ---------------------------------------------------------------


def test_a_plane_is_stated_as_a_rate_or_an_angle_and_not_both(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuleLoadError, match="write the one the code prints"):
        load_rules(
            _somewhere(
                tmp_path,
                "    setback_side_ft:\n"
                "      value: 5\n"
                "      quote: 'or/clackamas/somewhere/19.txt#L1'\n"
                "      step_back:\n"
                "        height_ft: 20\n"
                "        rise_per_ft: 1\n"
                "        slope_degrees: 45\n"
                "        cite: MMC Table 19.301.4 row C.3\n"
                "        quote: 'or/clackamas/somewhere/19.txt#L2'\n",
            ),
            strict=True,
        )


@pytest.mark.parametrize("angle", [0, 90, 120, -30])
def test_an_angle_has_to_be_one_a_plane_could_rise_at(
    tmp_path: Path, angle: int
) -> None:
    """A vertical plane rises forever and a flat one never does, and both fall
    out of the arithmetic as a division by zero or a negative distance rather
    than as an error anybody could read."""
    with pytest.raises(RuleLoadError, match="not a plane rising from the setback"):
        load_rules(
            _somewhere(
                tmp_path,
                "    setback_side_ft:\n"
                "      value: 5\n"
                "      quote: 'or/clackamas/somewhere/19.txt#L1'\n"
                "      step_back:\n"
                "        height_ft: 20\n"
                f"        slope_degrees: {angle}\n"
                "        cite: MMC Table 19.301.4 row C.3\n"
                "        quote: 'or/clackamas/somewhere/19.txt#L2'\n",
            ),
            strict=True,
        )


def test_a_shallower_plane_costs_more_distance(tmp_path: Path) -> None:
    """The angle is not decoration. At 45 degrees six feet of height costs six
    feet of yard; at 26.57 degrees -- a 1:2 plane -- it costs twelve."""
    layers = load_rules(
        _somewhere(
            tmp_path,
            "    setback_side_ft:\n"
            "      value: 5\n"
            "      quote: 'or/clackamas/somewhere/19.txt#L1'\n"
            "      step_back:\n"
            "        height_ft: 20\n"
            "        slope_degrees: 26.565\n"
            "        cite: MMC Table 19.301.4 row C.3\n"
            "        quote: 'or/clackamas/somewhere/19.txt#L2'\n",
        ),
        strict=False,
    )
    held = layers["or/clackamas/somewhere"].zones["R-MD"].values["setback_side_ft"]
    assert held.before_step_back == 5
    assert round(held.value) == 17
