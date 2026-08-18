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


def on_a_private_drive() -> list[Side]:
    return lot(
        (50, 0, S), (100, 90, Abuts.private_drive), (50, 0, N), (100, 90, N)
    )


# --- the corpus, as encoded --------------------------------------------


def test_the_five_cities_that_have_been_read(rules: RuleSet) -> None:
    """Changing this list is a real change and should be seen in review."""
    read = sorted(
        layer_id
        for layer_id, layer in rules.layers.items()
        if "corner_lot" in layer.definitions
    )
    assert read == [
        "or/clackamas/oregon-city",
        "or/clackamas/rivergrove",
        "or/clackamas/wilsonville",
        "or/multnomah/gresham",
        "or/multnomah/portland",
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


def test_a_city_with_no_definition_gets_no_definition(rules: RuleSet) -> None:
    """Milwaukie sits under Clackamas County in the file layout and takes
    nothing from it. Hierarchy is where our YAML lives, not who wrote
    Milwaukie's code."""
    assert rules.definitions_for("or/clackamas/milwaukie") == {}
    assert rules.defines("or/clackamas/milwaukie", "corner_lot", corner()) is None
    assert rules.undefined("or/clackamas/milwaukie") == TERMS


def test_a_sibling_is_never_a_source(rules: RuleSet) -> None:
    """Oregon City and Milwaukie are both Clackamas cities and one of them has
    been read. That is not a route between them."""
    assert "corner_lot" in rules.definitions_for("or/clackamas/oregon-city")
    assert "corner_lot" not in rules.definitions_for("or/clackamas/milwaukie")


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
    rules = RuleSet(load_rules())
    borrower = rules.layers["or/clackamas/milwaukie"]
    lender = rules.layers["or/clackamas/oregon-city"]
    rules.layers[borrower.layer] = borrower.model_copy(
        update={"definitions_from": [lender.layer]}
    )
    resolved = rules.definitions_for(borrower.layer)
    assert resolved["corner_lot"].cite == "OCMC 17.04.665, Lot, corner"
    assert rules.defines(borrower.layer, "corner_lot", corner()) is True


def test_a_layer_defining_a_term_outranks_the_one_it_adopts_from() -> None:
    rules = RuleSet(load_rules())
    gresham = rules.layers["or/multnomah/gresham"]
    rules.layers[gresham.layer] = gresham.model_copy(
        update={"definitions_from": ["or/multnomah/portland"]}
    )
    resolved = rules.definitions_for(gresham.layer)
    assert resolved["corner_lot"].cite.startswith("Gresham")
    # And the borrowed reading is genuinely different, so this is a real test.
    assert rules.defines(gresham.layer, "corner_lot", through()) is True


def test_an_adoption_cycle_terminates() -> None:
    rules = RuleSet(load_rules())
    for a, b in (
        ("or/clackamas/milwaukie", "or/clackamas/tualatin"),
        ("or/clackamas/tualatin", "or/clackamas/milwaukie"),
    ):
        layer = rules.layers[a]
        rules.layers[a] = layer.model_copy(update={"definitions_from": [b]})
    assert rules.definitions_for("or/clackamas/milwaukie") == {}


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
    -- because ``silent`` is a claim about the code and we have not earned it."""
    rows = coverage_for(rules, "or/clackamas/milwaukie")
    assert [r.status for r in rows] == ["unsourced"]
    assert all(r.blocking for r in rows)


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
    troutdale = coverage_for(rules, "or/multnomah/troutdale")
    assert [r.status for r in troutdale] == ["unsourced"]
    # And it is a real gap rather than an absent one: the code uses the word.
    assert troutdale[0].uses >= 5


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
