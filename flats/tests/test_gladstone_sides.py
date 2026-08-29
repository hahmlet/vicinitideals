"""Two side-setback rows, a minimum stated per dwelling, and a loud red herring.

Gladstone's R-7.2 dimensional table prints three side rows — "Side setback |
7.5 ft or 5 ft due to irregular shaped lots", "Street side setback | 20 ft",
and "Interior side setback | 5 ft" — with no housing type against any of them.
R-5's table prints one, at 5. The file carried 5 for R-7.2, cited against the
interior row, with nothing anywhere saying the other row existed. Five feet of
side yard either side is five feet of lot width against a pod 56 ft across, so
which row governs decides whether a 66 ft lot passes.

It is not resolvable from the page, so it is encoded the conservative way and
written down as the open question it is. That is the whole point of the note:
a value that quietly picked the looser of two rows reads exactly like a value
somebody checked.

The same table's third column spans all five setback rows and one of its five
sentences is a zero — "townhouse projects are allowed a zero-foot side setback
for lot lines where townhouse units are attached" — which is the party wall
this building is made of, and was not encoded either.

And R-5 states the townhouse minimum lot area twice: 5,000 sq ft for the
project, then "the average minimum lot area for a townhouse dwelling shall be
1,500 sf". Four dwellings want 6,000 of that. 6,000 is the larger figure, it is
the one that binds, and 17.12.050 prints it nowhere — so `per_dwelling` had to
grow onto a variant, which is what the last block here checks.

The loudest thing in the chapter is none of the above. GMC 17.62.070(4) is
referenced ten times across the two documents, every one of them beside a
number this screen uses, which made it the top of the cross-reference queue for
the whole county. It is one sentence about manufactured homes in a mobile home
park, printed once and spanned by rowspan over ten table cells.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flats.encode.crossrefs import dangling
from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import DWELLINGS
from flats.rules.loader import RuleLoadError, load_rules
from flats.rules.model import Layer, Provenance, Variant

pytestmark = pytest.mark.unit

GLADSTONE = "or/clackamas/gladstone"
#: R-10 has no chapter in Title 17 and mirrors R-7.2, so it inherits the
#: question along with the numbers.
MIRRORED = ("R7.2", "R10")
PROV = Provenance(
    cite="GMC 17.12.050",
    url="https://www.codepublishing.com/OR/Gladstone/html/Gladstone17/Gladstone1712.html",
    retrieved="2026-08-20",
    quote=f"{GLADSTONE}/17.12.r-5.txt#L171-L173",
)


@pytest.fixture(scope="module")
def gladstone() -> Layer:
    return load_rules()[GLADSTONE]


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
        "  R-5:\n"
        "    cite_default:\n"
        "      cite: GMC 17.12.050\n"
        "      url: https://example.invalid/17\n"
        "      retrieved: '2026-08-20'\n" + body,
        encoding="utf-8",
    )
    (root / "or" / "or.yaml").write_text(
        "layer: or\nkind: state\nlabel: Oregon\nzones: {}\n", encoding="utf-8"
    )
    return root


# -- the two rows -----------------------------------------------------------


def test_the_larger_of_two_rows_that_both_reach_this_building(
    gladstone: Layer, store: ProvenanceStore
) -> None:
    for zone in MIRRORED:
        held = gladstone.zones[zone].values["setback_side_ft"]
        assert held.value == 7.5, zone
        assert "7.5 ft" in store.quote(held.prov.quote), zone


def test_the_row_it_was_reading_before_is_still_on_the_page(
    store: ProvenanceStore
) -> None:
    """Which is the reason this needs a note rather than a correction.

    Both rows are real, both are in the same table, and neither carries a
    housing type. The encoding is a choice about how to be wrong safely, not a
    transcription anybody got right.
    """
    assert store.quote(f"{GLADSTONE}/17.10.r-7.2.txt#L189-L190").split() == [
        "Interior",
        "side",
        "setback",
        "5",
        "ft",
    ]


def test_the_zone_with_one_row_keeps_its_number(gladstone: Layer) -> None:
    """R-5 prints a single side row and it is the smaller figure. Reading
    R-7.2's answer across would be the same error pointing the other way."""
    assert gladstone.zones["R5"].values["setback_side_ft"].value == 5


def test_the_open_question_is_written_where_a_signer_will_see_it(
    gladstone: Layer,
) -> None:
    for zone in MIRRORED:
        notes = gladstone.zones[zone].notes or ""
        assert "side" in notes.lower(), zone
    assert "7.5" in (gladstone.zones["R7.2"].notes or "")


# -- the party wall ---------------------------------------------------------


def test_the_footnote_column_reaches_every_setback_row(
    gladstone: Layer, store: ProvenanceStore
) -> None:
    """One sentence, printed once, spanned by rowspan over five cells. It is a
    zero and it is the wall four units share."""
    for zone in ("R7.2", "R5", "R10"):
        held = gladstone.zones[zone].values["setback_side_ft"]
        zeroes = [v for v in held.variants if v.value == 0]

        assert len(zeroes) == 1, zone
        assert set(zeroes[0].when) == {"attached_wall", "unit_lots"}, zone
        assert "zero-foot side setback" in store.quote(zeroes[0].prov.quote), zone


def test_both_halves_of_the_sentence_are_conditions(gladstone: Layer) -> None:
    """"Townhouse projects are allowed a zero-foot side setback for lot lines
    where townhouse units are attached" says two things. Encoding only the
    party wall would give the zero to a quadplex on one lot, which has no lot
    line to be attached along."""
    held = gladstone.zones["R5"].values["setback_side_ft"]

    assert "unit_lots" in held.variants[0].when
    assert "attached_wall" in held.variants[0].when


# -- the minimum stated per dwelling ----------------------------------------


def test_four_townhouses_want_the_average_four_times_over(gladstone: Layer) -> None:
    held = gladstone.zones["R5"].values["min_lot_sqft"]
    townhouse = {v.when: v for v in held.variants}[("unit_lots",)]

    assert held.value == 7000
    assert townhouse.per_dwelling == 1500
    assert townhouse.value == 1500 * DWELLINGS == 6000


def test_the_smaller_of_the_two_townhouse_figures_does_not_govern(
    store: ProvenanceStore,
) -> None:
    """5,000 is printed first and 1,500-per-dwelling below it, and a file that
    took the 5,000 would pass a 5,000 sq ft lot the code refuses."""
    cited = store.quote(f"{GLADSTONE}/17.12.r-5.txt#L171-L173")

    assert "5,000 sf" in cited
    assert "average minimum lot area for a townhouse dwelling shall be 1,500 sf" in cited


def test_the_citation_is_checked_against_the_average_not_the_product(
    gladstone: Layer,
) -> None:
    """17.12.050 prints 1,500 and prints 6,000 nowhere, so a check looking for
    the product would flag the one encoding that did not invent a number."""
    r = readiness_for(gladstone, store=ProvenanceStore())

    assert not r.misquoted
    assert not r.no_evidence
    assert not r.unquoted


def test_a_variant_states_a_number_or_an_area_per_dwelling(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="area per dwelling unit, not both"):
        load_rules(
            _somewhere(
                tmp_path,
                "    min_lot_sqft:\n"
                "      value: 7000\n"
                "      quote: 'or/clackamas/somewhere/17.txt#L1'\n"
                "      variants:\n"
                "        - per_dwelling: 1500\n"
                "          value: 6000\n"
                "          when: [unit_lots]\n"
                "          quote: 'or/clackamas/somewhere/17.txt#L2'\n",
            ),
            strict=True,
        )


def test_a_per_dwelling_area_has_to_be_an_area(tmp_path: Path) -> None:
    with pytest.raises(RuleLoadError, match="is not an area"):
        load_rules(
            _somewhere(
                tmp_path,
                "    min_lot_sqft:\n"
                "      value: 7000\n"
                "      quote: 'or/clackamas/somewhere/17.txt#L1'\n"
                "      variants:\n"
                "        - per_dwelling: 0\n"
                "          when: [unit_lots]\n"
                "          quote: 'or/clackamas/somewhere/17.txt#L2'\n",
            ),
            strict=True,
        )


def test_an_exemption_states_no_area_per_dwelling() -> None:
    """"No such standard" and "this much of it each" are different answers, and
    a variant carrying both leaves a reader to guess which half is honoured."""
    with pytest.raises(ValueError, match="area per dwelling"):
        Variant(exempt=True, per_dwelling=1500, when=("unit_lots",), prov=PROV)


# -- the reference that was loudest and meant least -------------------------


def test_the_reference_at_the_top_of_the_queue_was_a_use_we_do_not_place(
    gladstone: Layer,
) -> None:
    """Ten mentions, ten of them binding, and the whole of it is one sentence
    a table repeats: setbacks for manufactured homes in a mobile home park.
    The pod is factory-built and is neither of those things.

    Asserted as a presence in the notes rather than an absence in the ledger,
    because the honest outcome here was a ruling and not a fetch — 17.62 is
    not in the store and should not be.
    """
    assert "17.62.070" in (gladstone.notes or "")
    assert "17.62.070" in {d.ref for d in dangling(gladstone)}


def test_the_parking_chapter_was_read_and_the_reason_for_not_reading_it_is_gone(
    gladstone: Layer,
) -> None:
    """This test used to assert the opposite, and the opposite was wrong.

    Both dimensional tables send the reader to GMC 17.48 without stating a
    number, and the layer used to answer that with the state cap: OAR
    660-046-0220 lets no city ask more than one space per unit of middle
    housing, so the chapter "can only bind at or below the figure already
    screened against". True, and beside the point -- it settles how many
    spaces and says nothing about how big one is. The chapter was fetched on
    2026-08-29 and turned out to hold the widest stall in the corpus.

    Kept rather than deleted, and inverted: what it now pins is that the
    superseded reasoning stays legible in the notes and that the numbers it
    used to stand in for are really in the layer. A test that pins a corpus
    condition should go red when the condition is fixed, and then say so.
    """
    assert "17.48" in (gladstone.notes or "")
    assert "SUPERSEDED" in (gladstone.notes or "")

    for field in (
        "parking_min_per_unit",
        "parking_max_per_unit",
        "parking_stall_width_ft",
        "parking_stall_depth_ft",
        "parking_aisle_one_way_ft",
        "parking_aisle_two_way_ft",
        "parking_street_setback_ft",
    ):
        assert field in gladstone.defaults
