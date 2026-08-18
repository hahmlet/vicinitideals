"""One lot, four cities, four answers — and none of them is a bug.

The point of holding definitions per jurisdiction is that a borrowed default is
a wrong answer rather than a safe one. These tests are the evidence: the same
geometry goes into four encoded readings of "corner lot" and comes out
different, because the four codes say different things.
"""

from __future__ import annotations

import math

import pytest

from flats.rules.definitions import (
    TERMS,
    Abuts,
    Definition,
    Side,
    decide,
    interior_angle_deg,
    parse,
)

pytestmark = pytest.mark.unit


# --- the four readings, as encoded -------------------------------------

PORTLAND = Definition(
    term="corner_lot",
    test="intersecting_frontages",
    quote="or/multnomah/portland/33.910.definitions.txt#L701-L705",
    cite="PCC 33.910 Lot-Related Definitions, Corner Lot",
    curve_at_or_below_deg=120.0,
)
GRESHAM = Definition(
    term="corner_lot",
    test="frontage_count",
    quote="or/multnomah/gresham/3.0100.definitions.txt#L1304-L1305",
    cite="Gresham Development Code 3.0100, Lot, Corner Lot",
    curve_at_or_below_deg=120.0,
)
OREGON_CITY = Definition(
    term="corner_lot",
    test="intersecting_frontages",
    quote="or/clackamas/oregon-city/17.zoning.txt#L2081-L2083",
    cite="OCMC 17.04.665 Lot, corner",
)
RIVERGROVE = Definition(
    term="corner_lot",
    test="adjacent_frontages",
    quote="or/clackamas/rivergrove/rldo.composite.txt#L326-L328",
    cite="RLDO Corner Lot",
    max_intersection_angle_deg=135.0,
)

ALL_FOUR = {
    "portland": PORTLAND,
    "gresham": GRESHAM,
    "oregon-city": OREGON_CITY,
    "rivergrove": RIVERGROVE,
}


# --- lots, built from bearings rather than coordinates -----------------


def lot(*sides: tuple[float, float, Abuts]) -> list[Side]:
    """A boundary in ring order: (length, bearing, what it abuts)."""
    return [Side(length_ft=ln, bearing_deg=b % 180.0, abuts=a) for ln, b, a in sides]


def named(boundary: list[Side], *ids: str) -> list[Side]:
    """Put a street name on each frontage, in order. What the centreline layer
    gives us when it gives us anything, and the only thing that can tell a
    shallow fork of two streets from one road bending through the frontage."""
    it = iter(ids)
    return [
        Side(s.length_ft, s.bearing_deg, s.abuts, next(it))
        if s.abuts is Abuts.street
        else s
        for s in boundary
    ]


S, N = Abuts.street, Abuts.none


def interior() -> list[Side]:
    """A plain rectangle with one street across the front."""
    return lot((50, 0, S), (100, 90, N), (50, 0, N), (100, 90, N))


def corner() -> list[Side]:
    """Two streets meeting at a right angle."""
    return lot((50, 0, S), (100, 90, S), (50, 0, N), (100, 90, N))


def through() -> list[Side]:
    """Street across the front and another across the back. They never meet."""
    return lot((50, 0, S), (100, 90, N), (50, 0, S), (100, 90, N))


def fork(angle: float) -> list[Side]:
    """Two named streets meeting at a stated interior angle."""
    return named(
        lot((50, 0, S), (100, 180 - angle, S), (50, 0, N), (100, 90, N)),
        "SE Main",
        "SE Oak",
    )


# --- the answers -------------------------------------------------------


def test_an_interior_lot_is_nobodys_corner() -> None:
    for name, defn in ALL_FOUR.items():
        assert defn.holds(interior()) is False, name


def test_a_right_angle_corner_is_everybodys_corner() -> None:
    for name, defn in ALL_FOUR.items():
        assert defn.holds(corner()) is True, name


def test_a_through_lot_is_a_corner_in_gresham_and_nowhere_else() -> None:
    """The finding that started this. Gresham's definition asks for "frontage
    on two or more streets" and stops; Portland and Oregon City require the
    frontages to intersect, and Rivergrove requires adjacent sides. A street
    front and back satisfies exactly one of the four."""
    assert GRESHAM.holds(through()) is True
    assert PORTLAND.holds(through()) is False
    assert OREGON_CITY.holds(through()) is False
    assert RIVERGROVE.holds(through()) is False


def test_rivergroves_ceiling_is_the_one_nobody_else_has() -> None:
    """A shallow fork. "Provided the angle of the intersection of the adjacent
    streets does not exceed 135 degrees" is a real constraint and the only one
    of its kind in the corpus."""
    shallow = fork(150.0)
    assert RIVERGROVE.holds(shallow) is False
    assert PORTLAND.holds(shallow) is True
    assert OREGON_CITY.holds(shallow) is True
    assert GRESHAM.holds(shallow) is True

    assert RIVERGROVE.holds(fork(120.0)) is True


def test_the_bend_that_makes_one_street_into_two() -> None:
    """Portland: "a street that curves with angles that are 120 degrees or less
    ... is considered two intersecting streets". Gresham writes the same bend
    as a delta angle of 60 degrees or more. Oregon City states no angle, so a
    curve is one street however tight."""
    bent = lot((50, 0, S), (50, 70, S), (60, 20, N), (80, 110, N))
    assert interior_angle_deg(bent[0], bent[1]) == pytest.approx(110.0)

    assert PORTLAND.holds(bent) is True
    assert GRESHAM.holds(bent) is True
    assert OREGON_CITY.holds(bent) is True  # not collinear, so it intersects

    gentle = lot((50, 0, S), (50, 25, S), (60, 20, N), (80, 110, N))
    assert interior_angle_deg(gentle[0], gentle[1]) == pytest.approx(155.0)
    assert PORTLAND.holds(gentle) is False
    assert GRESHAM.holds(gentle) is False


def test_without_a_street_name_a_shallow_fork_reads_as_one_bending_road() -> None:
    """The same geometry, and the answer turns on data we mostly do not have.

    Two streets meeting at 150 degrees and one road bending through 150 degrees
    are the same boundary. Portland's definition tells them apart by street
    identity -- "more than one intersecting street" -- and falls back on the
    curve clause only for a single street. Where the centreline layer names the
    streets we can follow that; where it does not, the bend reads as one road,
    which is the answer that cannot invent a corner that is not there.

    This is the argument for carrying street identity onto the lot rather than
    a distance check, stated as a test instead of a paragraph.
    """
    anonymous = lot((50, 0, S), (100, 30, S), (50, 0, N), (100, 90, N))
    assert PORTLAND.holds(anonymous) is False
    assert PORTLAND.holds(fork(150.0)) is True


def test_a_surveyors_split_is_not_a_second_street() -> None:
    """One straight frontage recorded as two collinear segments. Every reading
    has to see one street, or every long lot becomes a corner."""
    split = lot((25, 0, S), (25, 0.5, S), (100, 90, N), (50, 0, N), (100, 90, N))
    for name, defn in ALL_FOUR.items():
        assert defn.holds(split) is False, name


def test_frontage_that_wraps_index_zero_is_still_one_street() -> None:
    """The ring has no beginning. A lot whose frontage happens to straddle the
    first vertex must not read as two stretches meeting head-on."""
    wrapped = lot((25, 0, S), (100, 90, N), (50, 0, N), (100, 90, N), (25, 0, S))
    for name, defn in ALL_FOUR.items():
        assert defn.holds(wrapped) is False, name


def test_an_alley_is_not_frontage_and_every_code_says_so() -> None:
    """Portland's street lot line "does not include lot lines that abut an
    alley"; Gresham's "lot line abutting an alley is a rear lot line";
    Rivergrove's corner test says "streets other than alleys" outright. A lot
    with a street across the front and an alley down the side is not a corner,
    and `flats.geom.edges` calls it one today."""
    with_alley = lot((50, 0, Abuts.street), (100, 90, Abuts.alley), (50, 0, N), (100, 90, N))
    for name, defn in ALL_FOUR.items():
        assert defn.holds(with_alley) is False, name


# --- the registry keeps its promises -----------------------------------


def test_an_unread_jurisdiction_gets_an_unknown_not_a_borrowed_answer() -> None:
    """The whole reason the definitions are held per layer. A city nobody has
    read does not quietly inherit Portland's test."""
    assert decide({"corner_lot": PORTLAND}, "corner_lot", corner()) is True
    assert decide({}, "corner_lot", corner()) is None
    # And a city that defined some other term still has not defined this one.
    assert decide({"corner_lot": PORTLAND}, "front_lot_line", corner()) is None


def test_a_definition_cannot_be_invented_inline() -> None:
    with pytest.raises(ValueError, match="not a definable term"):
        Definition(term="vibes", test="frontage_count", quote="d#L1")
    with pytest.raises(ValueError, match="unknown test"):
        Definition(term="corner_lot", test="looks_cornery", quote="d#L1")
    with pytest.raises(ValueError, match="recollection"):
        Definition(term="corner_lot", test="frontage_count", quote="")
    with pytest.raises(ValueError, match="must be in"):
        Definition(
            term="corner_lot",
            test="adjacent_frontages",
            quote="d#L1",
            max_intersection_angle_deg=400.0,
        )


def test_the_loader_collects_every_error_rather_than_the_first() -> None:
    problems: list[str] = []
    got = parse(
        {
            "corner_lot": {"test": "nope", "quote": "d#L1"},
            "not_a_term": {"test": "frontage_count", "quote": "d#L1"},
        },
        where="or/somewhere",
        problems=problems,
    )
    assert got == {}
    assert len(problems) == 2
    assert all(p.startswith("or/somewhere.definitions.") for p in problems)


def test_every_term_has_at_least_one_test() -> None:
    from flats.rules.definitions import TESTS

    assert TERMS
    assert all(TESTS[term] for term in TERMS)


def test_the_angle_is_measured_the_way_the_codes_write_it() -> None:
    """Codes say "120 degrees or less" and "does not exceed 135 degrees" — the
    interior angle of the turn, where 180 is a straight run."""
    straight = Side(10, 0.0)
    assert interior_angle_deg(straight, Side(10, 0.0)) == pytest.approx(180.0)
    assert interior_angle_deg(straight, Side(10, 90.0)) == pytest.approx(90.0)
    assert interior_angle_deg(straight, Side(10, 60.0)) == pytest.approx(120.0)
    assert interior_angle_deg(straight, Side(10, 179.0)) == pytest.approx(179.0)
    assert not math.isnan(interior_angle_deg(straight, Side(10, 45.0)))
