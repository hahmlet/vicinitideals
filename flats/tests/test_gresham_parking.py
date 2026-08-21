"""The two loudest unfetched references in the corpus, and what was behind them.

Thirty-four mentions sent a zone's affordable-housing sentence to Section
10.1700 and twenty-two sent its parking row to Table 9.0851. Between them they
were thirteen of the corpus's hundred and twenty-seven binding references --
references standing beside a number this screen actually uses -- and they had
sat at the top of the queue since the queue existed.

**10.1700** is a bonus and nothing else: density up 125 to 200 percent, height
up 12 to 36 feet, minimum density switched off, in exchange for every unit at 80
percent of area median income under a thirty-year recorded covenant. It loosens,
and it is elective. Ruled, not encoded.

**9.0851** turned out not to hold the answer either. The answer is one sentence
three hundred lines earlier: *"Vehicle parking minimums are not required for any
land use type."* Section 9.0802(A), whole city, every use.

That is the largest single correction this layer has taken. Four Gresham zones
had read their own Table 4.0430 row and encoded zero. The other thirty-four had
nothing, so they fell through to the state's cap of one stall per unit, and
every lot in them was screened as owing four stalls -- about 1,300 square feet
of a site that also has to hold the pod and its driveway. The state row is a
ceiling on what a city *may* require. Standing in for a reading of what Gresham
does require, it was wrong in the direction that refuses a lot.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
PARKING = f"{GRESHAM}/9.0800.parking.txt"
BONUS = f"{GRESHAM}/10.1700.affordable.txt"

#: The four that read Table 4.0430 row K for themselves before this. They keep
#: their own citation, because the same answer from the zone's own table is not
#: the same sentence.
CORRIDOR = ("CMF", "SC", "SC-RJ", "CMU")


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# -- the sentence ------------------------------------------------------------


def test_the_city_waives_the_minimum_in_one_sentence_for_every_use(
    gresham: Layer, store: ProvenanceStore
) -> None:
    held = gresham.defaults["parking_min_per_unit"]
    assert held.value == 0
    quoted = store.quote(held.prov.quote)
    assert "Vehicle parking minimums are not required for any land use type" in quoted


def test_and_the_table_the_zone_rows_point_at_has_no_minimum_column(
    store: ProvenanceStore,
) -> None:
    """Which is why reading only the table would not have settled it. Table
    9.0851 states auto parking as a MAXIMUM and prints no minimum at all."""
    lines = store.load(PARKING).text.splitlines()
    head = lines[lines.index(next(l for l in lines if "Table 9.0851: Auto and Bicycle" in l))]
    assert "Auto and Bicycle Parking Requirements" in head
    columns = next(l for l in lines if "AUTO PARKING" in l and "BICYCLE PARKING" in l)
    assert "MINIMUM" not in columns.upper().replace("MAXIMUM", "")


def test_the_two_plan_districts_that_restate_it_say_zero(store: ProvenanceStore) -> None:
    """Civic Neighborhood and Downtown write it out rather than relying on
    9.0802(A), and they agree with it."""
    text = store.load(PARKING).text
    assert text.count("street parking for all uses is zero") == 2


# -- what it was standing in for ---------------------------------------------


def test_every_zone_in_the_city_now_asks_for_nothing(rules: RuleSet, gresham: Layer) -> None:
    """All thirty-eight. Before this, four."""
    assert len(gresham.zones) == 38
    for zone in gresham.zones:
        held = rules.resolve(GRESHAM, zone).values["parking_min_per_unit"]
        assert held.value == 0, zone


def test_the_state_ceiling_is_no_longer_answering_for_the_city(
    rules: RuleSet, gresham: Layer
) -> None:
    """The failure this fixes, named so it cannot come back quietly. OAR
    660-046-0220 caps a city at one stall per unit; it is not a statement that
    a city asks for one. Every Gresham zone without its own value was resolving
    to the cap and being screened as owing four stalls -- which is the whole
    parking court, on a lot that has to hold a 56 by 36 building as well."""
    for zone in gresham.zones:
        cite = rules.resolve(GRESHAM, zone).values["parking_min_per_unit"].prov.cite
        assert "OAR" not in cite, f"{zone} is still answering from the state ceiling"
        assert "9.0802(A)" in cite or "4.0430" in cite or "Table 4.0430" in cite, zone


def test_the_four_that_read_their_own_table_keep_their_own_citation(
    rules: RuleSet, gresham: Layer
) -> None:
    """A layer default is what a zone falls back to, not what it is overwritten
    with. If the city ever restores a minimum in one district, the zone row is
    where it would appear, and a zone that had been quietly folded into the
    default would not notice."""
    for zone in CORRIDOR:
        assert "parking_min_per_unit" in gresham.zones[zone].values, zone
        cite = rules.resolve(GRESHAM, zone).values["parking_min_per_unit"].prov.cite
        assert "4.0430" in cite, zone

    stating = [z for z, zn in gresham.zones.items() if "parking_min_per_unit" in zn.values]
    assert sorted(stating) == sorted(CORRIDOR)


# -- the bicycle rows, read and not encoded ----------------------------------


def test_eleven_districts_state_none_for_a_quadplex_outright(
    store: ProvenanceStore,
) -> None:
    lines = store.load(PARKING).text.splitlines()
    at = next(i for i, l in enumerate(lines) if "Table 9.0851: Auto and Bicycle" in l)
    # The district list wraps three lines in the PDF's own layout.
    listed = " ".join(lines[at : at + 6])
    assert "LDR-7, LDR-5, LDRGB, LDR-PV, MDR-PV, VLDR-" in listed
    assert "MDR-12, and OFR districts" in listed
    row = next(l for l in lines[at : at + 20] if l.strip().startswith("(d)") and "Quadplexes" in l)
    assert row.count("None") == 3


def test_and_where_they_do_not_the_requirement_is_satisfiable_indoors(
    store: ProvenanceStore,
) -> None:
    """One long-term space per dwelling unit, which the code lets you keep in
    the dwelling: no rack, no locker, no ground. Read and not encoded on that
    basis rather than on the basis that four bicycles are small."""
    text = store.load(PARKING).text
    assert "Developments containing four or more dwelling units" in text
    assert (
        "if long-term bicycle parking is provided\n"
        "               in a dwelling unit, living unit, or dormitory unit, neither racks nor lockers is required"
        in text
    ) or "neither racks nor lockers is required" in text
    assert "Contained within a dwelling unit or living unit" in text
    # And the parking-lot design standards do not reach this building at all.
    assert "do not apply to single detached" in text


# -- the bonus ---------------------------------------------------------------


def test_the_affordable_housing_section_only_ever_loosens(
    store: ProvenanceStore,
) -> None:
    text = store.load(BONUS).text
    assert "AFFORDABLE HOUSING WITH HEIGHT AND DENSITY" in text
    assert "Table 10.1711(B): Affordable Housing Density and Height Bonus" in text
    assert "Minimum net density does not apply" in text


def test_and_is_elective_at_a_price_a_market_rate_building_does_not_pay(
    store: ProvenanceStore,
) -> None:
    """Which is the second and independent reason it is not encoded: a lot
    cannot fail a standard nobody has opted into."""
    text = store.load(BONUS).text
    assert "80\npercent or less of the area median income" in text or "percent or less of the area median income" in text
    assert "for\n       a duration of no less than 30 years" in text or "no less than 30 years" in text


# -- the queue, and the title that was in the wrong block --------------------


def test_both_references_are_ruled(gresham: Layer) -> None:
    for ref in ("10.1700", "9.0851"):
        assert ref in gresham.crossrefs, ref
        assert len(gresham.crossrefs[ref]) > 200, ref


def test_the_documents_are_declared_and_fetched(
    gresham: Layer, store: ProvenanceStore
) -> None:
    declared = {doc.id for doc in gresham.code}
    assert "9.0800.parking" in declared
    assert "10.1700.affordable" in declared
    for path in (PARKING, BONUS):
        assert store.exists(path), path


def test_every_declared_document_carries_its_own_title(gresham: Layer) -> None:
    """7.0400's title had been written inside 7.0500's mapping, under a key
    that block already had. YAML takes the last one silently, so Rockwood was
    carrying Middle Housing's name and 7.0400 was carrying none -- a duplicate
    key is not a parse error and nothing in the pipeline reads a title, which
    is exactly why it survived. The cheapest possible check that it did not."""
    titles = {doc.id: doc.title for doc in gresham.code}
    assert titles["7.0400.middle-housing-design"] == "Section 7.0400 - Middle Housing Design Standards"
    assert titles["7.0500.rockwood-design"] == "Section 7.0500 - Rockwood Design District"
    assert all(titles.values()), [k for k, v in titles.items() if not v]
    assert len(set(titles.values())) == len(titles)


def test_the_one_footnote_in_the_document_is_ruled(store: ProvenanceStore) -> None:
    """The gate governs by document, so the layer default picked up the only
    note 9.0800 carries: Table 9.0825A note 1, minimum aisle widths inside a
    parking lot. Dismissed twice over -- an aisle width qualifies how wide an
    aisle is in a lot somebody builds, not whether a lot must be built, and
    9.0802(F) puts Sections 9.0822 to 9.0840 out of reach of a quadplex
    anyway. The gate is right to have asked; the answer is on file."""
    from flats.encode.qualified import qualified

    rows = [
        r
        for r in qualified()
        if r.layer == GRESHAM and r.zone == "(defaults)" and r.field == "parking_min_per_unit"
    ]
    assert rows, "the default should still be governed by the note, and answered"
    assert not any(r.blocking for r in rows)
    assert all(n.state == "dismissed" for r in rows for n in r.governing)
    assert "minimum aisle width may vary" in store.quote(
        "or/multnomah/gresham/9.0800.parking.txt#L346"
    )
