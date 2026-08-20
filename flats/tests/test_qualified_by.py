"""A standard that is not the whole rule, and cannot say what the rest is.

Fairview's Table 19.30.030.A prints 35 ft of building height for R-6. Four
lines further down the same section, 19.30.030(E) makes a taller building
"step-down" to any existing single-storey building of 20 ft or less standing
within 20 ft of it. At 26 ft the pod is always the taller building, so on an
established street the height standard can refuse it outright rather than push
it around -- and whether it does turns on the neighbour's roof and the gap
between two walls, neither of which this project holds.

Every existing shape in the rule model wants a number. A variant states what
the standard BECOMES under a condition; an exemption states that there is no
standard; a step-back states a rate. This rule states none of the three in a
form anything here can evaluate, and the two ways of forcing it into the
existing shapes are wrong in the same direction: writing a number invents one,
and leaving it out lets an unqualified 35 certify a lot the code would not.

So `qualified_by` states only the two true things -- that a rule elsewhere
moves this standard, and which unanswerable fact it turns on -- and hands the
fact to the machinery that already exists for "read, and waiting on data". A
site fact registered with no assumption resolves as unknown; a standard that
leans on an unknown may not be certified. The lot comes back UNKNOWN with the
fact named, which is the true answer.

The rest of this file is the guard rail. A field that can say "there is more to
this rule" without saying what would be the most attractive place in the corpus
to put work nobody wants to do, so it is refused wherever the rule could have
been encoded properly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.designs.model import load_catalog
from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import CONDITIONS
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Layer, Provenance, Value
from flats.rules.resolver import RuleSet
from flats.score.configure import configure
from flats.score.screen import LotFacts

pytestmark = pytest.mark.unit

FAIRVIEW = "or/multnomah/fairview"
POD = ("multi_story", "attached_wall")
FACT = "adjacent_single_story_building"
#: Every zone reading row 17 of Table 19.30.030.A, and the height it reads.
TRANSITIONED = {"R-6": 35, "R-7.5": 35, "R-10": 35, "RM/TOZ": 35, "RM": 45}
PROV = Provenance(
    cite="FMC Table 19.30.030.A, row 17",
    url="https://www.codepublishing.com/OR/Fairview/html/Fairview19/Fairview1930.html",
    retrieved="2026-08-20",
    quote=f"{FAIRVIEW}/19.30.txt#L439,L440",
)


@pytest.fixture(scope="module")
def fairview() -> Layer:
    return load_rules()[FAIRVIEW]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


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
        "      cite: FMC 19.30.030\n"
        "      url: https://example.invalid/1930\n"
        "      retrieved: '2026-08-20'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


# -- what it does in Fairview ----------------------------------------------


def test_the_height_still_reads_what_the_table_prints(fairview: Layer) -> None:
    """A qualifier does not touch the number. It is not arithmetic, and the
    encoding stays checkable against the cell it was read from."""
    for zone, printed in TRANSITIONED.items():
        held = fairview.zones[zone].values["max_height_ft"]
        assert held.value == printed, zone
        assert held.qualified_by == FACT, zone


def test_the_qualifier_becomes_a_lever_on_the_standard(rules: RuleSet) -> None:
    for zone in TRANSITIONED:
        res = rules.resolve(FAIRVIEW, zone, POD)
        assert FACT in res.values["max_height_ft"].levers, zone


def test_a_lot_here_cannot_be_certified_on_the_unqualified_number(
    rules: RuleSet,
) -> None:
    """The whole point, in one assertion.

    `configure` lists every unanswered site fact the registry refuses to guess,
    `leans_on` narrows that to the ones some standard here actually turns on,
    and `flats.score.screen` turns a non-empty intersection into
    FACT_UNOBSERVED. Nothing in that chain needed changing: the qualifier's
    only job was to put the fact where the chain could see it.
    """
    design = max(load_catalog(), key=lambda d: d.height_ft)
    config = configure(LotFacts(lot_sqft=9000), design)

    assert FACT in config.unknown
    assert FACT in config.leans_on(rules.resolve(FAIRVIEW, "R-6", POD).levers)


def test_the_zone_that_borrows_the_table_borrows_the_qualifier(
    rules: RuleSet,
) -> None:
    """R/SFLD is a Metro label with no ordinance behind it, read as R-10.

    An incorporation that carried the number and dropped the sentence
    qualifying it would be the exact provenance failure this field exists for,
    one layer of indirection further from anyone who could spot it.
    """
    assert FACT in rules.resolve(FAIRVIEW, "R/SFLD", POD).levers


def test_the_sentence_is_quoted_and_says_what_the_encoding_says(
    fairview: Layer, store: ProvenanceStore
) -> None:
    text = store.quote(fairview.zones["R-6"].values["max_height_ft"].qualified_quote)

    assert "step-down" in text
    assert "within 20 feet" in text
    assert "single-story building with a height of 20 feet or less" in text


def test_the_qualifier_is_checked_for_evidence_and_not_for_a_number(
    fairview: Layer, store: ProvenanceStore
) -> None:
    """There is no figure in it -- what is verified is that the sentence is
    still where the file says it is, the bargain `measured_on` takes."""
    ready = readiness_for(fairview, store=store)

    assert not [row for row in ready.no_evidence if row[0] in TRANSITIONED]
    assert not [row for row in ready.misquoted if row[0] in TRANSITIONED]


def test_the_scope_this_encoding_chose_is_written_down(fairview: Layer) -> None:
    """The table hangs (E) off row 12, "Special Yards (distance between primary
    buildings on the same lot)", which would put it out of reach of one pod on
    its own lot. The subsection's own text says "between developments". The
    wider reading costs a review and the narrow one costs a false GREEN, and
    which was taken is not something a reader should have to reconstruct.
    """
    for zone in TRANSITIONED:
        notes = fairview.zones[zone].notes or ""
        assert "19.30.030(E)" in notes, zone
        assert "Special Yards" in notes, zone


def test_the_fact_is_one_nothing_measures_and_says_what_it_would_take() -> None:
    fact = CONDITIONS[FACT]

    assert fact.kind == "site_fact"
    assert fact.assume is None
    assert "footprints" in fact.evidence


# -- the floor area ratio the same table prints, and nobody had read ---------


def test_the_ratio_row_that_was_never_encoded(fairview: Layer) -> None:
    """Row 14 gives every column "0.7 to 1" and this corpus held none of it.

    It is the standard that decides a small lot in Fairview: the pod is 2,016
    sq ft on the ground over two storeys, so 0.7 asks for 5,760 sq ft, which
    R-6's own 6,000 sq ft minimum clears by 240. A lot platted before that
    minimum does not.
    """
    for zone in TRANSITIONED:
        assert fairview.zones[zone].values["max_far"].value == 0.7, zone


def test_the_carve_out_under_each_cell_is_a_different_housing_type(
    fairview: Layer, store: ProvenanceStore
) -> None:
    """"Cottage clusters none" in four columns and "Multi-unit none" in the
    fifth. Row 1 of the same table lists Quadplex, Townhouse, Cottage Cluster
    and Multi-Unit as four separate types with four separate lot minimums, so
    neither carve-out reaches this building on either platting path.
    """
    text = store.quote(fairview.zones["R-6"].values["max_far"].prov.quote)
    assert "Cottage clusters none" in text
    assert "0.7 to 1" in text

    rm = store.quote(fairview.zones["RM"].values["max_far"].prov.quote)
    assert "Multi-unit none" in rm


def test_the_ratio_is_read_across_the_row_it_belongs_to(
    fairview: Layer, store: ProvenanceStore
) -> None:
    """The table prints one cell per line and position names the column, so
    every citation carries the row label with the cell."""
    for zone in TRANSITIONED:
        text = store.quote(fairview.zones[zone].values["max_far"].prov.quote)
        assert "Maximum Floor Area Ratio" in text, zone


# -- the guard rails --------------------------------------------------------


def test_a_qualifier_names_a_fact_nothing_can_answer() -> None:
    """`unit_lots` is a design fact the caller states. A rule turning on it is
    a rule that can be encoded, and citing it as unanswerable would be a way of
    not encoding it with a citation attached."""
    with pytest.raises(ValueError, match="encode the rule as a variant"):
        Value(
            name="max_height_ft",
            value=35,
            qualified_by="unit_lots",
            qualified_cite="FMC 19.30.030(E)",
            qualified_quote=f"{FAIRVIEW}/19.30.txt#L481-L486",
            prov=PROV,
        )


def test_a_qualifier_carries_its_own_citation() -> None:
    with pytest.raises(ValueError, match="second rule in a second section"):
        Value(name="max_height_ft", value=35, qualified_by=FACT, prov=PROV)


def test_a_citation_with_no_fact_under_it_is_refused() -> None:
    with pytest.raises(ValueError, match="no 'qualified_by' fact"):
        Value(
            name="max_height_ft",
            value=35,
            qualified_cite="FMC 19.30.030(E)",
            prov=PROV,
        )


def test_a_standard_does_not_both_state_a_condition_and_disclaim_it(
    tmp_path: Path,
) -> None:
    """A variant says what the number becomes when the fact holds. Saying that
    and "nobody can answer this" at once is two answers to one question."""
    with pytest.raises(RuleLoadError, match="also calls it unanswerable"):
        load_rules(
            _somewhere(
                tmp_path,
                "    max_height_ft:\n"
                "      value: 35\n"
                "      quote: 'or/multnomah/somewhere/19.txt#L1'\n"
                "      qualified_by:\n"
                f"        fact: {FACT}\n"
                "        cite: FMC 19.30.030(E)\n"
                "        quote: 'or/multnomah/somewhere/19.txt#L2'\n"
                "      variants:\n"
                "        - value: 20\n"
                f"          when: [{FACT}]\n"
                "          quote: 'or/multnomah/somewhere/19.txt#L3'\n",
            ),
            strict=True,
        )


def test_a_qualifier_states_the_fact_it_turns_on(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="the qualifying rule turns on it"):
        load_rules(
            _somewhere(
                tmp_path,
                "    max_height_ft:\n"
                "      value: 35\n"
                "      quote: 'or/multnomah/somewhere/19.txt#L1'\n"
                "      qualified_by:\n"
                "        cite: FMC 19.30.030(E)\n"
                "        quote: 'or/multnomah/somewhere/19.txt#L2'\n",
            ),
            strict=True,
        )


def test_the_bare_string_form_parses_and_is_refused_for_its_citation(
    tmp_path: Path,
) -> None:
    """The arrangement `measured_on` uses: the shorthand loads, so the error
    names the missing half rather than the YAML shape."""
    with pytest.raises(RuleLoadError, match="second rule in a second section"):
        load_rules(
            _somewhere(
                tmp_path,
                "    max_height_ft:\n"
                "      value: 35\n"
                "      quote: 'or/multnomah/somewhere/19.txt#L1'\n"
                f"      qualified_by: {FACT}\n",
            ),
            strict=True,
        )
