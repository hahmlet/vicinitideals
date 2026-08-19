"""Nobody inherits a definition, and the register says so with evidence.

The tempting design is a fallback: a city with no definition of "corner lot"
takes its county's, the county takes the state's, and every lot gets an answer.
These tests exist to make that design fail loudly if anyone builds it, because
the encoded corpus already shows five cities saying five different things and a
sixth city's silence is not a vote for any of them.
"""

from __future__ import annotations

import pytest

from flats.encode.definitions import STATUSES, coverage, coverage_for
from flats.rules.definitions import TERMS, Abuts, Definition, Side
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


S, N = Abuts.street, Abuts.none


def lot(*sides: tuple[float, float, Abuts]) -> list[Side]:
    return [Side(length_ft=ln, bearing_deg=b % 180.0, abuts=a) for ln, b, a in sides]


def corner() -> list[Side]:
    return lot((50, 0, S), (100, 90, S), (50, 0, N), (100, 90, N))


def through() -> list[Side]:
    return lot((50, 0, S), (100, 90, N), (50, 0, S), (100, 90, N))


def named_fork(angle: float) -> list[Side]:
    """Two named streets meeting at a stated interior angle. Named, because
    without street identity a shallow fork and one bending road are the same
    boundary and the conservative reading is one road."""
    sides = lot((50, 0, S), (100, (180 - angle) % 180.0, S), (50, 0, N), (100, 90, N))
    ids = iter(("SE Main", "SE Oak"))
    return [
        Side(x.length_ft, x.bearing_deg, x.abuts, next(ids))
        if x.abuts is Abuts.street
        else x
        for x in sides
    ]


def on_a_private_drive() -> list[Side]:
    return lot(
        (50, 0, S), (100, 90, Abuts.private_drive), (50, 0, N), (100, 90, N)
    )


# --- the corpus, as encoded --------------------------------------------


def test_the_jurisdictions_that_have_been_read(rules: RuleSet) -> None:
    """Changing this list is a real change and should be seen in review."""
    read = sorted(
        layer_id
        for layer_id, layer in rules.layers.items()
        if "corner_lot" in layer.definitions
    )
    assert read == [
        "or/clackamas/_unincorporated",
        "or/clackamas/happy-valley",
        "or/clackamas/milwaukie",
        "or/clackamas/oregon-city",
        "or/clackamas/rivergrove",
        "or/clackamas/tualatin",
        "or/clackamas/west-linn",
        "or/clackamas/wilsonville",
        "or/multnomah/_unincorporated",
        "or/multnomah/gresham",
        "or/multnomah/portland",
        "or/multnomah/troutdale",
    ]


def test_one_lot_five_codes_and_the_answers_disagree(rules: RuleSet) -> None:
    """The whole argument for holding definitions per jurisdiction, run against
    the encoded corpus rather than test fixtures. A street front and back is a
    corner lot in Gresham alone."""
    answers = {
        layer_id: rules.defines(layer_id, "corner_lot", through())
        for layer_id in rules.layers
        if "corner_lot" in rules.layers[layer_id].definitions
    }
    assert answers["or/multnomah/gresham"] is True
    assert answers["or/multnomah/portland"] is False
    assert answers["or/clackamas/oregon-city"] is False
    assert answers["or/clackamas/rivergrove"] is False
    # Wilsonville cannot say no: its second clause is unmeasurable.
    assert answers["or/clackamas/wilsonville"] is None


def test_wilsonville_alone_counts_a_private_drive(rules: RuleSet) -> None:
    """"...each abut a street or private drive". A lot on an internal drive is
    a corner there and an interior lot in the other four."""
    drive = on_a_private_drive()
    assert rules.defines("or/clackamas/wilsonville", "corner_lot", drive) is True
    for elsewhere in (
        "or/multnomah/portland",
        "or/multnomah/gresham",
        "or/clackamas/oregon-city",
        "or/clackamas/rivergrove",
    ):
        assert rules.defines(elsewhere, "corner_lot", drive) is False, elsewhere


def test_an_unmeasurable_clause_makes_no_a_maybe() -> None:
    """A definition that cannot see half its own text may answer yes and may
    never answer no. The direction matters: a corner lot carries a second front
    setback in these codes, so a missed corner is a false GREEN."""
    partial = Definition(
        term="corner_lot",
        test="intersecting_frontages",
        quote="d#L1",
        incomplete="a clause we cannot measure",
    )
    assert partial.holds(corner()) is True
    assert partial.holds(through()) is None


# --- and nobody borrows ------------------------------------------------

#: A hierarchy nobody will ever encode, so these tests keep testing the rule
#: rather than the state of the queue. Reading a real city used to break six of
#: them at once, which measured our progress and not the resolver.
def synthetic() -> RuleSet:
    county = Layer(
        layer="zz/county",
        kind="county",
        label="Test County",
        definitions={
            "corner_lot": Definition(
                term="corner_lot",
                test="frontage_count",
                quote="zz/county/defs.txt#L1",
                cite="Test County 1.000",
            )
        },
    )
    city = Layer(layer="zz/county/city", kind="city", label="Test City")
    sibling = Layer(layer="zz/county/sibling", kind="city", label="Sibling City")
    return RuleSet({layer.layer: layer for layer in (county, city, sibling)})


def test_a_city_with_no_definition_gets_no_definition() -> None:
    """The city sits under the county in the file layout and takes nothing from
    it. Hierarchy is where our YAML lives, not who wrote the city's code."""
    rules = synthetic()
    assert rules.definitions_for("zz/county")
    assert rules.definitions_for("zz/county/city") == {}
    assert rules.defines("zz/county/city", "corner_lot", corner()) is None
    assert rules.undefined("zz/county/city") == TERMS


def test_a_sibling_is_never_a_source() -> None:
    """Two cities in one county, one of them read. That is not a route between
    them, and it is not a route up to the county and back down either."""
    rules = synthetic()
    rules.layers["zz/county/sibling"] = rules.layers["zz/county/sibling"].model_copy(
        update={"definitions": rules.layers["zz/county"].definitions}
    )
    assert rules.definitions_for("zz/county/city") == {}


def test_nothing_in_the_corpus_resolves_a_definition_it_did_not_write() -> None:
    """The corpus-level form of the same rule, written as an invariant so it
    survives every jurisdiction we encode next. A layer's resolved definitions
    are its own, unless it declares an adoption -- and none does."""
    rules = RuleSet(load_rules())
    for layer_id, layer in rules.layers.items():
        resolved = rules.definitions_for(layer_id)
        if layer.definitions_from:
            continue
        assert set(resolved) == set(layer.definitions), layer_id
        for term, defn in resolved.items():
            assert defn is layer.definitions[term], f"{layer_id}.{term}"


def test_no_layer_in_the_corpus_claims_to_adopt_anybody(rules: RuleSet) -> None:
    """Standing evidence for the answer to "who uses what": nobody adopts.

    Every incorporated Oregon city in the corpus writes its own development
    code. If a city is later found to adopt its county's definitions, this test
    is where that shows up, and it should carry the adopting clause as a quote.
    """
    adopting = {
        layer_id: layer.definitions_from
        for layer_id, layer in rules.layers.items()
        if layer.definitions_from
    }
    assert adopting == {}


def test_adoption_works_when_a_code_actually_says_so() -> None:
    """The mechanism exists and is deliberately unused. Wiring it needs one
    line of YAML and a citation, which is the price of borrowing a meaning."""
    rules = synthetic()
    rules.layers["zz/county/city"] = rules.layers["zz/county/city"].model_copy(
        update={"definitions_from": ["zz/county"]}
    )
    resolved = rules.definitions_for("zz/county/city")
    assert resolved["corner_lot"].cite == "Test County 1.000"
    assert rules.defines("zz/county/city", "corner_lot", corner()) is True


def test_a_layer_defining_a_term_outranks_the_one_it_adopts_from() -> None:
    rules = synthetic()
    own = Definition(
        term="corner_lot",
        test="adjacent_frontages",
        quote="zz/city/defs.txt#L9",
        cite="Test City 2.000",
        max_intersection_angle_deg=100.0,
    )
    rules.layers["zz/county/city"] = rules.layers["zz/county/city"].model_copy(
        update={"definitions": {"corner_lot": own}, "definitions_from": ["zz/county"]}
    )
    resolved = rules.definitions_for("zz/county/city")
    assert resolved["corner_lot"].cite == "Test City 2.000"
    # And the borrowed reading is genuinely different, so this is a real test.
    assert rules.defines("zz/county", "corner_lot", through()) is True
    assert rules.defines("zz/county/city", "corner_lot", through()) is False


def test_an_adoption_cycle_terminates() -> None:
    rules = synthetic()
    for a, b in (("zz/county/city", "zz/county/sibling"), ("zz/county/sibling", "zz/county/city")):
        rules.layers[a] = rules.layers[a].model_copy(update={"definitions_from": [b]})
    assert rules.definitions_for("zz/county/city") == {}


# --- the register ------------------------------------------------------


def test_the_register_covers_every_layer_and_term(rules: RuleSet) -> None:
    rows = coverage(rules)
    assert len(rows) == len(rules.layers) * len(TERMS)
    assert {r.status for r in rows} <= set(STATUSES)


def test_the_register_names_a_citation_for_every_encoded_definition(
    rules: RuleSet,
) -> None:
    for row in coverage(rules):
        if row.status == "own":
            assert row.where, f"{row.layer} cites nothing"


def test_silence_and_not_having_looked_are_different_rows(rules: RuleSet) -> None:
    """The distinction the whole module exists for. A jurisdiction whose
    definitions chapter nobody has found reads ``unsourced``, never ``silent``
    -- because ``silent`` is a claim about the code and we have not earned it.

    Stated over the whole corpus rather than one city, so it cannot be made
    true again by encoding whichever city it named.
    """
    for row in coverage(rules):
        if row.status == "silent":
            assert row.where, "silent has to name the chapter it searched"
        if row.status in ("unsourced", "unsearched"):
            assert not row.where
        assert row.blocking == (row.status not in ("own", "adopted"))


def test_an_encoded_definition_stops_blocking(rules: RuleSet) -> None:
    rows = coverage_for(rules, "or/multnomah/portland")
    assert [(r.status, r.blocking) for r in rows] == [("own", False)]


def test_the_matcher_does_not_read_prose_as_a_definition(rules: RuleSet) -> None:
    """Two shapes that fooled it and are now pinned.

    Troutdale's window standard wraps onto a line beginning "corner lots, this
    standard shall apply..." — a term, a comma, and forty characters of body,
    which is a definition to anything that only checks punctuation. And every
    code headlines the standard in the plural, "Corner Lots", while defining
    the singular, so counting uses has to see both and defining must not fire
    on a table heading with nothing after it.
    """
    gladstone = coverage_for(rules, "or/clackamas/gladstone")
    assert [r.status for r in gladstone] == ["unsourced"]
    # And it is a real gap rather than an absent one: the code uses the word.
    assert gladstone[0].uses >= 4


def test_usage_counts_drive_the_queue(rules: RuleSet) -> None:
    """A code that leans on a word it never defines is the expensive gap. An
    eligible jurisdiction with uses and no definition outranks everything, and
    an exempt one never enters the queue however often it says the word."""
    rows = coverage(rules)
    blocking = [r for r in rows if r.priority]
    assert blocking, "the queue is not empty and should not silently become so"
    assert blocking == sorted(blocking, key=lambda r: -r.uses)
    assert all(r.eligible and r.blocking for r in blocking)

    exempt = next(r for r in rows if r.layer == "or/clackamas/lake-oswego")
    assert exempt.uses > 0 and exempt.blocking and exempt.priority == 0


def test_the_two_codes_that_state_a_ceiling_state_it_differently(
    rules: RuleSet,
) -> None:
    """Rivergrove: "does not exceed 135 degrees". Multnomah County: "less than
    135 degrees". They agree everywhere except at exactly 135, and encoding
    both as one comparison would pick a side without anybody deciding to."""
    at_135 = named_fork(135.0)
    assert rules.defines("or/clackamas/rivergrove", "corner_lot", at_135) is True
    assert rules.defines("or/multnomah/_unincorporated", "corner_lot", at_135) is None

    inside = named_fork(120.0)
    assert rules.defines("or/clackamas/rivergrove", "corner_lot", inside) is True
    assert rules.defines("or/multnomah/_unincorporated", "corner_lot", inside) is True


def test_the_county_governs_its_own_land_and_nobody_elses(rules: RuleSet) -> None:
    """Multnomah County now has a definition, which is exactly the moment a
    chain-walking resolver would start handing it to Gresham, Fairview,
    Troutdale and Wood Village. It does not."""
    assert "corner_lot" in rules.definitions_for("or/multnomah/_unincorporated")
    for city in ("or/multnomah/fairview", "or/multnomah/wood-village"):
        assert rules.definitions_for(city) == {}, city
        assert rules.defines(city, "corner_lot", corner()) is None, city


def test_the_three_answers_a_bending_street_gets(rules: RuleSet) -> None:
    """One frontage, one road, bent at 110 degrees. Three codes, three rules,
    and none of them is a default:

    * Portland and Gresham turn a tight enough curve into two intersecting
      streets -- 120 degrees or less, or a 60-degree delta, the same bend.
    * Oregon City states no angle, so a non-collinear frontage is read as an
      intersection and the lot is a corner.
    * Clackamas County rules it out outright: "a lot within the radius curve
      of a single street is not a corner lot".
    """
    bent = lot((50, 0, S), (50, 70, S), (60, 20, N), (80, 110, N))
    assert rules.defines("or/multnomah/portland", "corner_lot", bent) is True
    assert rules.defines("or/multnomah/gresham", "corner_lot", bent) is True
    assert rules.defines("or/clackamas/oregon-city", "corner_lot", bent) is True
    assert rules.defines("or/clackamas/_unincorporated", "corner_lot", bent) is False

    # And a real intersection of two named streets is a corner everywhere.
    real = named_fork(90.0)
    for layer_id in (
        "or/multnomah/portland",
        "or/multnomah/gresham",
        "or/clackamas/oregon-city",
        "or/clackamas/_unincorporated",
    ):
        assert rules.defines(layer_id, "corner_lot", real) is True, layer_id


def test_a_definition_cannot_both_split_a_curve_and_refuse_to() -> None:
    with pytest.raises(ValueError, match="contradicts"):
        Definition(
            term="corner_lot",
            test="intersecting_frontages",
            quote="d#L1",
            curve_is_one_street=True,
            curve_at_or_below_deg=120.0,
        )


def test_identical_language_in_two_cities_is_still_two_definitions(
    rules: RuleSet,
) -> None:
    """Troutdale and Rivergrove state the corner lot test word for word, down
    to the 135-degree ceiling and the "streets other than alleys" exclusion.
    Model language spreading is not an argument for a shared default: each is
    quoted from its own code, so if one amends its ceiling only one moves."""
    a = rules.definitions_for("or/multnomah/troutdale")["corner_lot"]
    b = rules.definitions_for("or/clackamas/rivergrove")["corner_lot"]
    assert (a.test, a.max_intersection_angle_deg) == (b.test, b.max_intersection_angle_deg)
    assert a.quote != b.quote
    assert a.cite != b.cite


def test_a_city_does_not_take_the_county_that_surrounds_it(rules: RuleSet) -> None:
    """Tualatin states no angle, so a bending street reads as an intersection.
    Clackamas County, whose land surrounds it, says the opposite outright. The
    county rule does not reach inside the city."""
    bent = lot((50, 0, S), (50, 70, S), (60, 20, N), (80, 110, N))
    assert rules.defines("or/clackamas/tualatin", "corner_lot", bent) is True
    assert rules.defines("or/clackamas/_unincorporated", "corner_lot", bent) is False


def test_one_number_two_boundaries(rules: RuleSet) -> None:
    """Happy Valley and Multnomah County both state 135 degrees and mean
    different lots by it -- "135 degrees or less" against "less than 135".
    On the boundary lot they answer opposite ways, which is exactly the kind
    of difference a shared default would erase."""
    at_135 = named_fork(135.0)
    assert rules.defines("or/clackamas/happy-valley", "corner_lot", at_135) is True
    assert rules.defines("or/multnomah/_unincorporated", "corner_lot", at_135) is None

    over = named_fork(150.0)
    assert rules.defines("or/clackamas/happy-valley", "corner_lot", over) is False
    # ...while three codes that state no ceiling call the same lot a corner.
    for open_ended in ("or/multnomah/portland", "or/clackamas/oregon-city", "or/clackamas/milwaukie"):
        assert rules.defines(open_ended, "corner_lot", over) is True, open_ended


def test_fairview_is_the_first_code_that_is_actually_silent(rules: RuleSet) -> None:
    """The case the register was built to tell apart, and the strongest
    argument for refusing to inherit.

    Fairview declares Chapter 19.13 DEFINITIONS, we hold it, and it defines
    Lot, Lot area, Lot coverage, Lot depth, Lot line adjustment and Lot width
    -- and not corner lot. Its own entry for front yard orientation says the
    orientation "on corner lots" is determined by the zoning districts, so the
    code leans on a word it never defines, eight times.

    A resolver that fell back would hand Fairview Multnomah County's test,
    which Fairview never adopted. The honest answer is that we do not know,
    and it stays that way until somebody finds a definition or the city writes
    one.
    """
    rows = coverage_for(rules, "or/multnomah/fairview")
    assert [r.status for r in rows] == ["silent"]
    assert rows[0].where == "19.13.definitions"
    assert rows[0].uses >= 8
    assert rows[0].blocking
    assert rules.defines("or/multnomah/fairview", "corner_lot", corner()) is None


def test_four_wordings_of_one_number_and_they_do_not_all_agree(
    rules: RuleSet,
) -> None:
    """135 degrees is the most-written number in the corpus and it is written
    four ways:

      "does not exceed 135"                    Rivergrove, Troutdale
      "135 degrees or less"                    Happy Valley
      "excluding ... angles greater than 135"  West Linn
      "less than 135 degrees"                  Multnomah County

    The first three include 135 and the fourth does not, so on the boundary
    lot five jurisdictions split four to one. Nothing about that is visible
    unless each is encoded from its own sentence.
    """
    at_135 = named_fork(135.0)
    including = (
        "or/clackamas/rivergrove",
        "or/multnomah/troutdale",
        "or/clackamas/happy-valley",
        "or/clackamas/west-linn",
    )
    for layer_id in including:
        assert rules.defines(layer_id, "corner_lot", at_135) is True, layer_id
    assert rules.defines("or/multnomah/_unincorporated", "corner_lot", at_135) is None
