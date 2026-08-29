"""What blocks a jurisdiction, and what unblocks it.

The failure this replaces is a status line reading "0.0% verified" across 603
values. True, and useless: it cannot tell a city nobody has found a code URL for
from one where every number is written, quoted, and waiting on a signature. Those
are hours apart, and they belong in different places in a queue.

The ladder is ordered by what blocks what rather than by how bad it is, and these
tests defend that ordering — because the moment it reports a rung somebody cannot
act on yet, the queue starts sending work to people who cannot do it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flats.encode.load import load_trusted
from flats.encode.readiness import by_stage, readiness, readiness_for
from flats.encode.verify import VerificationLog
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
DOC = f"{PORTLAND}/33.110.txt"
TEXT = (
    "33.110.220 Development Standards\n"
    "The minimum front building setback is 10 feet.\n"
    "The minimum side building setback is 5 feet.\n"
)

CODE = f'code:\n  - id: "33.110"\n    url: https://www.portland.gov/code/33.110.pdf\n'
CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
)
QUOTED = f'  quote: "{DOC}#L2"\n'


@pytest.fixture()
def bench(tmp_path: Path) -> dict:
    return {
        "root": tmp_path / "jurisdictions",
        "docs": tmp_path / "docs",
        "log": tmp_path / "verifications.jsonl",
    }


def city(bench: dict, body: str) -> None:
    p = bench["root"] / f"{PORTLAND}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("label: Portland\n" + body, encoding="utf-8")


def evidence(bench: dict) -> None:
    ProvenanceStore(bench["docs"]).save(
        DOC, url="https://www.portland.gov/code/33.110.pdf", text=TEXT, retrieved=date(2026, 8, 12)
    )


def report(bench: dict, *, signed: bool = False):
    store = ProvenanceStore(bench["docs"])
    log = VerificationLog.load(bench["log"])
    if signed:
        from flats.tests.signing import sign_encoded

        layers = sign_encoded(load_rules(bench["root"]))
        return readiness_for(layers[PORTLAND], store=store)
    trusted = load_trusted(bench["root"], log=log, store=store, strict=False)
    # The bench is its own corpus. Reading the real store's footnotes into it
    # would make these tests depend on which jurisdiction was encoded today.
    return readiness(trusted, store, footnoted={})[0]


#: Everything present and quoted, awaiting a signature. Each test below breaks
#: exactly one thing about it.
WHOLE = (
    CODE
    + CITE
    + "zones:\n  R5:\n    setback_front_ft:\n      value: 10\n"
    + f'      quote: "{DOC}#L2"\n'
)


# --- the ladder, rung by rung -----------------------------------------


def test_a_jurisdiction_with_nothing_encoded_says_so(bench: dict) -> None:
    city(bench, "kind: city\n")

    assert report(bench).stage == "no_zones"


def test_zones_with_no_declared_source_cannot_be_read(bench: dict) -> None:
    # 16 of 19 real jurisdictions sit here. Not "0% verified" — nobody has found
    # the URL, and no amount of reviewing will happen until somebody does.
    city(bench, CITE + "zones:\n  R5:\n    setback_front_ft: 10\n")

    r = report(bench)

    assert r.stage == "no_source"
    assert "declare it under `code:`" in r.action


def test_a_declared_document_nobody_fetched_blocks_everything_below(bench: dict) -> None:
    city(bench, WHOLE)

    r = report(bench)

    assert r.stage == "unfetched"
    assert r.unfetched == (DOC,)
    assert r.action == f"python -m flats.provenance.fetch --layer {PORTLAND}"


def test_a_value_with_no_quote_cannot_be_reviewed(bench: dict) -> None:
    city(bench, CODE + CITE + "zones:\n  R5:\n    setback_front_ft: 10\n")
    evidence(bench)

    r = report(bench)

    assert r.stage == "unquoted"
    assert r.unquoted == (("R5", "setback_front_ft"),)


def test_a_quote_that_resolves_to_nothing_is_its_own_rung(bench: dict) -> None:
    # Distinct from unquoted on purpose: one is an encoding omission, the other
    # is a fetch that did not happen or a line range that moved. Different fix.
    city(bench, CODE + CITE + f'zones:\n  R5:\n    setback_front_ft:\n      value: 10\n      quote: "{DOC}#L900"\n')
    evidence(bench)

    r = report(bench)

    assert r.stage == "no_evidence"
    assert r.no_evidence == (("R5", "setback_front_ft"),)


def test_everything_present_and_unread_is_waiting_on_a_reviewer(bench: dict) -> None:
    city(bench, WHOLE)
    evidence(bench)

    r = report(bench)

    assert r.stage == "unsigned"
    assert "sign" in r.action


def test_a_fully_signed_jurisdiction_is_ready(bench: dict) -> None:
    city(bench, WHOLE.replace("value: 10\n", "value: 10\n      status: encoded\n"))
    evidence(bench)

    r = report(bench, signed=True)

    assert r.stage == "ready"
    assert r.ready
    assert r.pct_verified == 100.0


# --- the ordering is the product --------------------------------------


def test_an_unfetched_document_outranks_an_unsigned_value(bench: dict) -> None:
    # However few documents are missing. Signing a value whose evidence was
    # never fetched is not possible, so reporting "unsigned" would put the work
    # in front of somebody who cannot do it.
    city(bench, WHOLE)

    assert report(bench).stage == "unfetched"


def test_the_worst_rung_sorts_first(bench: dict) -> None:
    city(bench, WHOLE)
    evidence(bench)
    other = bench["root"] / "or/multnomah/fairview.yaml"
    other.write_text("label: Fairview\n" + CITE + "zones:\n  VSF:\n    setback_front_ft: 5\n", encoding="utf-8")

    store = ProvenanceStore(bench["docs"])
    trusted = load_trusted(bench["root"], log=VerificationLog(), store=store, strict=False)
    order = [r.stage for r in readiness(trusted, store, footnoted={})]

    assert order == ["no_source", "unsigned"]


def test_among_equals_the_one_closest_to_done_comes_first(bench: dict) -> None:
    # Finishing one jurisdiction beats advancing three: a half-encoded city
    # screens no lots at all, so the cheapest completion is worth the most.
    from flats.rules.model import Layer, Provenance, Status, Value, Zone

    prov = Provenance(cite="PCC 33.110.220", url="https://x.gov/y", retrieved=date(2026, 8, 12))

    def layer(name: str, verified: int, total: int) -> Layer:
        values = {
            f"f{i}": Value(
                name="setback_front_ft",
                value=5,
                prov=prov,
                status=Status.verified if i < verified else Status.draft,
                reviewer="sjk" if i < verified else None,
                reviewed=date(2026, 8, 12) if i < verified else None,
            )
            for i in range(total)
        }
        return Layer(layer=name, kind="city", label=name, zones={"R5": Zone(zone="R5", values=values)})

    store = ProvenanceStore(bench["docs"])
    reports = sorted(
        (readiness_for(layer("a", 1, 4), store=store), readiness_for(layer("b", 3, 4), store=store)),
        key=lambda r: (r.rung, -r.pct_verified, r.layer),
    )

    assert [r.layer for r in reports] == ["b", "a"]


# --- what gets counted -------------------------------------------------


def test_an_unquoted_exception_blocks_the_jurisdiction(bench: dict) -> None:
    # A footnote is a number somebody has to read. Counting only base values
    # would report a jurisdiction as finished with unread rules in it.
    city(
        bench,
        CODE + CITE + "zones:\n"
        "  R5:\n"
        "    setback_front_ft:\n"
        "      value: 10\n"
        f'      quote: "{DOC}#L2"\n'
        "      variants:\n"
        "        - value: 5\n"
        "          when: [affordable]\n"
        "          quote: null\n",
    )
    evidence(bench)

    r = report(bench)

    assert r.stage == "unquoted"
    assert r.unquoted == (("R5", "setback_front_ft [affordable]"),)


def test_an_unquoted_incorporation_blocks_the_jurisdiction(bench: dict) -> None:
    city(
        bench,
        CODE + CITE + "zones:\n"
        "  R-6:\n"
        "    setback_front_ft:\n      value: 20\n" + f'      quote: "{DOC}#L2"\n'
        "  VSF:\n    like:\n      zone: R-6\n      quote: null\n",
    )
    evidence(bench)

    assert report(bench).unquoted == (("VSF", "like"),)


def test_a_variant_counts_toward_the_verified_share(bench: dict) -> None:
    city(
        bench,
        CODE + CITE + "zones:\n"
        "  R5:\n"
        "    setback_front_ft:\n"
        "      value: 10\n"
        f'      quote: "{DOC}#L2"\n'
        "      variants:\n"
        "        - value: 5\n"
        "          when: [affordable]\n",
    )
    evidence(bench)

    assert report(bench).values == 2


def test_the_summary_counts_jurisdictions_per_rung(bench: dict) -> None:
    city(bench, WHOLE)
    evidence(bench)
    (bench["root"] / "or/multnomah/fairview.yaml").write_text(
        "label: Fairview\n" + CITE + "zones:\n  VSF:\n    setback_front_ft: 5\n", encoding="utf-8"
    )

    store = ProvenanceStore(bench["docs"])
    trusted = load_trusted(bench["root"], log=VerificationLog(), store=store, strict=False)

    assert by_stage(readiness(trusted, store, footnoted={})) == {"no_source": 1, "unsigned": 1}


def test_the_line_names_the_command_that_unblocks_it(bench: dict) -> None:
    city(bench, WHOLE)

    line = report(bench).line()

    assert PORTLAND in line
    assert "flats.provenance.fetch --layer" in line


def test_the_unquoted_action_routes_by_cause_rather_than_naming_a_tool(bench: dict) -> None:
    # It used to name attach and one document. Across the corpus that was
    # wrong far more often than right: most uncited values are footnoted,
    # doubled, unreadable or absent from every stored chapter, and attach
    # refuses all four. Sending them there reads as citation work remaining
    # when the real work is finding a chapter. `gaps` sorts them by cause and
    # names attach only for the ones attach can act on.
    city(bench, CODE + CITE + "zones:\n  R5:\n    setback_front_ft: 10\n")
    evidence(bench)

    r = report(bench)

    assert r.stage == "unquoted"
    assert "flats.encode.review gaps" in r.action
    assert r.layer in r.action


def test_a_jurisdiction_with_no_document_still_renders_an_action(bench: dict) -> None:
    city(bench, CITE + "zones:\n  R5:\n    setback_front_ft: 10\n")

    # no_source names no document, and formatting must not blow up reaching for
    # one that does not exist.
    assert "code:" in report(bench).action


# --- misquoted: the citation that resolves and says nothing ------------------


def test_a_layer_whose_quotes_drifted_stops_at_misquoted(bench: dict) -> None:
    # Every value quoted and resolvable, and every citation pointing at the
    # wrong line — the state a re-extraction leaves behind. The ladder has to
    # name it, or the next rung says "waiting on a signature" over evidence
    # nobody can sign.
    evidence(bench)
    city(
        bench,
        CODE
        + CITE
        + "zones:\n  R5:\n    setback_front_ft:\n      value: 10\n"
        + f'      quote: "{DOC}#L3"\n',
    )

    got = report(bench)

    assert got.stage == "misquoted"
    assert got.misquoted == (("R5", "setback_front_ft"),)
    assert "attach" in got.action


def test_a_quote_that_states_its_number_is_not_misquoted(bench: dict) -> None:
    evidence(bench)
    city(
        bench,
        CODE
        + CITE
        + "zones:\n  R5:\n    setback_front_ft:\n      value: 10\n"
        + f'      quote: "{DOC}#L2"\n',
    )

    got = report(bench)

    assert got.misquoted == ()
    assert got.stage == "unsigned"


def test_a_quote_that_does_not_state_its_number_is_misquoted(tmp_path: Path) -> None:
    # Re-extracting a document moves every line in it, so a citation keeps
    # pointing at line 3 while line 3 becomes something else. Nothing else in
    # the ladder can see that: the value has a quote, and the quote resolves.
    from flats.encode.readiness import quotes_the_number

    assert quotes_the_number("Minimum lot area: 7,500 sq ft", 7500)
    assert quotes_the_number("The front setback is 7.5 feet", 7.5)
    assert quotes_the_number("Maximum floor area ratio 0.60", 0.6)
    assert not quotes_the_number("Maximum lot coverage", 30)
    assert not quotes_the_number("13.090 OTHER APPLICABLE DEVELOPMENT STANDARDS", 20)


def test_a_code_that_waives_a_standard_in_prose_states_zero() -> None:
    """Table codes print an em dash for a standard they do not impose, and the
    check already knew that spelling. Prose codes write the sentence instead --
    "No setback is required along property lines where townhouses are
    attached" -- and fourteen correctly-cited Wilsonville values read as
    misquoted because the passage supporting them contains no digit."""
    from flats.encode.readiness import quotes_the_number

    assert quotes_the_number(
        "8. Townhouse Setbacks: No setback is required along property lines "
        "where townhouses are attached.",
        0,
    )
    assert quotes_the_number("Interior side setbacks may be reduced to zero.", 0)
    assert quotes_the_number("There is no minimum lot size in this zone.", 0)
    assert quotes_the_number("Off-street parking is not required.", 0)


def test_a_borrowing_with_no_floor_is_checked_for_words_and_not_for_a_figure() -> None:
    """`same_as` where the sentence carries no number at all.

    Happy Valley 16.43.030.E.4 prints a ten-foot floor beside its borrowing, so
    there is one figure on the page and `_printed` looks for it. Troutdale
    9.095(D) prints none for this building: "Parking areas shall be set back
    from a lot line adjoining a street the same distance as required building
    setbacks", and the ten feet in the next sentence is an industrial-district
    standard that reaches no zone permitting a quadplex.

    Falling through to the RESOLVED number -- 15 in MU-2, 10 in the low-density
    districts -- would ask a reader to find a figure the cited sentence does
    not contain, which is the thing this check exists to stop. So a floorless
    borrowing prints nothing, its citation is opened and staleness-checked like
    `measured_on` and `qualified_by`, and the number is verified on the
    lender's own row where it is printed.
    """
    from flats.encode.readiness import _printed
    from flats.rules.model import Provenance, Value

    def borrowed(**extra: object) -> Value:
        return Value(
            name="parking_street_setback_ft",
            value=15,
            same_as="setback_front_ft",
            prov=Provenance(
                cite="TDC 9.095(D)",
                url="https://api.municode.com/PublicationPdfDownload/1813",
                retrieved="2026-08-29",
                quote="or/multnomah/troutdale/9.parking.txt#L540",
            ),
            **extra,
        )

    assert _printed(borrowed()) is None
    # And the floored form is unchanged: Happy Valley's ten is still the figure
    # its own sentence carries, and still the one checked.
    assert _printed(borrowed(floor_ft=10)) == 10


def test_a_standard_a_city_repealed_states_zero_without_printing_one() -> None:
    """The strongest way to impose nothing, and the only one that is invisible.

    Every other spelling this check knows is something a reader can find: an em
    dash, the word "None", "there is no minimum". A repeal leaves none of them.
    West Linn deleted CDC 46.080, Computation of Required Parking Spaces, and
    CDC 46.100, Parking Requirements for Unlisted Uses, by Ord. 1754 in 2024,
    and what stands under OFF-STREET PARKING SPACE REQUIREMENTS now is a
    subsection headed "Maximum parking". The city requires no off-street
    parking at all and nowhere says so; the sentence that used to require it is
    simply gone.

    Encoding that as zero is not optional -- leaving the field out inherits
    whatever a broader layer states, which is the one outcome that would put a
    parking requirement on 6,791 lots that carry none.
    """
    from flats.encode.readiness import quotes_the_number

    assert quotes_the_number(
        "46.080 COMPUTATION OF REQUIRED PARKING SPACES AND LOADING AREA "
        "Repealed by Ord. 1754.",
        0,
    )
    # And held to zero like every other waiver: a repealed section is not
    # evidence for a number, only for the absence of one.
    assert not quotes_the_number("Repealed by Ord. 1754.", 2)


def test_waiving_language_does_not_excuse_a_number_that_is_absent() -> None:
    """The rule runs in the permissive direction, so it is held to zero only.
    A passage that waives one standard is not evidence for a different one it
    never states."""
    from flats.encode.readiness import quotes_the_number

    waiver = "No setback is required where townhouses are attached."
    assert not quotes_the_number(waiver, 15)
    assert not quotes_the_number("Maximum lot coverage", 0)


def test_a_non_numeric_value_is_never_misquoted() -> None:
    # Permission flags and enums have no number to look for, and flagging
    # them would bury the citations that really did drift.
    from flats.encode.readiness import quotes_the_number

    assert quotes_the_number("Quadplexes are permitted outright.", True)
    assert quotes_the_number("Buildings shall face the street.", "axis_required")
    assert quotes_the_number("anything", None)


# --- a check that disagrees with the rest of the system -----------------


def test_a_letter_spaced_scan_is_repaired_before_the_number_is_looked_for() -> None:
    # Oregon City's Title 17 is a scan. Ten thousand square feet is stored as
    # "1 0 , 000 squ are f eet", which the readers repair and this check did
    # not, so fifteen correctly-quoted values read as citations pointing at
    # the wrong text. The same `spaced:` flag now governs both.
    from flats.encode.readiness import quotes_the_number

    cited = "Quad pl ex a nd co t tage 1 0 , 000 squ are 8 , 000 squ are"

    assert not quotes_the_number(cited, 10000)
    assert quotes_the_number(cited, 10000, spaced=True)


def test_a_standard_the_table_states_as_none_supports_a_zero() -> None:
    # Gresham's townhouse minimum lot size and Tualatin's townhouse lot width
    # are printed "None". Zero is how this system says the code imposes no
    # minimum, and the alternative — leaving the field out — inherits the
    # standard written for a different housing type, which is worse than
    # wrong because it looks encoded.
    from flats.encode.readiness import quotes_the_number

    assert quotes_the_number("T ownhouse None", 0)
    assert quotes_the_number("Townhouse N/A", 0)
    assert not quotes_the_number("T ownhouse None", 16), "only zero reads this way"


def test_a_number_the_cited_line_does_not_state_is_still_caught() -> None:
    from flats.encode.readiness import quotes_the_number

    assert not quotes_the_number("Minimum lot width 20 feet", 35)
    assert not quotes_the_number("Minimum lot width 20 feet", 0)


def test_a_number_printed_as_a_fraction_still_counts() -> None:
    """Clackamas ZDO 315 states the VR-5/7 garage setback as "19½ feet to the
    garage door". One character, and the digit scan reads the 19 beside it."""
    from flats.encode.readiness import quotes_the_number

    assert quotes_the_number("19½ feet to the garage door", 19.5)
    assert quotes_the_number("a half-foot: ½ ft", 0.5)
    assert not quotes_the_number("19½ feet to the garage door", 19.25)


def test_a_dimension_printed_in_feet_and_inches_still_counts() -> None:
    """Portland's Table 266-4 prints its stall width as "8 ft. 6 in.".

    The corpus stores feet, so 8.5 is the encoding, and neither an 8.5 nor a
    spelling of it appears on the line. Every row of that table is written this
    way -- 22 ft. 6 in., 9 ft. 9 in. -- so a reader that cannot add the inches
    calls a correctly cited table row a misquote, and the encoder's way out is
    to cite a line that does not say it.

    Both halves still count on their own: the feet and the inches are numbers
    the page really prints, and a row elsewhere may be cited for one of them.
    """
    from flats.encode.readiness import quotes_the_number

    assert quotes_the_number("90 8 ft. 6 in. 8 ft. 6 in. 20 ft. 16 ft.", 8.5)
    assert quotes_the_number("Curb length 22 ft. 6 in.", 22.5)
    assert quotes_the_number("9 feet 9 inches", 9.75)
    assert quotes_the_number("8'6\"", 8.5)
    assert quotes_the_number("90 8 ft. 6 in. 20 ft. 16 ft.", 16)
    assert not quotes_the_number("Curb length 22 ft. 6 in.", 22.75)
    # Twelve or more inches is two adjacent numbers, not one dimension.
    assert not quotes_the_number("aisle 20 ft. 20 in. clear", 21.667)


def test_a_spelled_number_restated_in_brackets_still_finds_its_unit() -> None:
    """Troutdale writes "Minimum of seven and one-half (7" and breaks the line
    before the fraction, so the digits land too far apart for the fraction
    repair to join them and the words in front are all that is left.

    The unit test is what those words have to clear -- "one" and "two" are
    ordinary English and a bare match on them would let a citation about
    anything corroborate a setback. Here the unit is behind a bracketed
    restatement of the same number, which is how nearly every ordinance in
    this corpus is drafted, so the check steps over it rather than stopping.
    """
    from flats.encode.readiness import quotes_the_number

    broken = (
        "Minimum of seven and one-half (7\n"
        "                                  ½) feet from an adjoining side yard"
    )
    assert quotes_the_number(broken, 7.5)
    assert quotes_the_number("a setback of five (5) feet", 5)
    # The bracket is stepped over, not treated as a unit: a spelled number
    # with nothing dimensional behind it still fails.
    assert not quotes_the_number("Two (2) story or greater construction", 2.5)
    assert not quotes_the_number("seven and one-half (7 1/2) reasons", 7.5)


def test_a_footnote_marker_stuck_to_a_number_is_only_read_where_declared() -> None:
    """Milwaukie prints "Street side yard 154" for fifteen feet with note 4.
    Read as 154 the encoding looks wrong; read as 15 everywhere, a table that
    really says 154 would corroborate an encoding of 15."""
    from flats.encode.readiness import quotes_the_number

    assert not quotes_the_number("Street side yard 154", 15)
    assert quotes_the_number("Street side yard 154", 15, glued=True)
    assert quotes_the_number("Street side yard 154", 154, glued=True)
    # One digit, and only off a bare number -- 1,500 is not 150.
    assert not quotes_the_number("Minimum lot area 1,500", 150, glued=True)


def test_a_marker_glued_to_a_decimal_is_read_the_same_way() -> None:
    """Gresham's Downtown table states a density to a tenth and marks it.

    "8.71" is 8.7 units per acre with note 1, and "12.458" is 12.45 with note
    8 -- a whole column of rates the earlier reader skipped, because it only
    tried tokens with no decimal point in them. Skipping them made a correct
    citation read as a misquote, which is the check disagreeing with the flag
    that was set to tell it about this document.
    """
    from flats.encode.readiness import quotes_the_number

    assert not quotes_the_number("Minimum Residential Net Density 8.71", 8.7)
    assert quotes_the_number("Minimum Residential Net Density 8.71", 8.7, glued=True)
    assert quotes_the_number("Maximum 12.458", 12.45, glued=True)
    # Still one digit, and still the number as printed reads too.
    assert quotes_the_number("Minimum Residential Net Density 8.71", 8.71, glued=True)
    assert not quotes_the_number("Maximum 12.458", 12.4, glued=True)
    # Cutting a digit must leave a figure behind: 7.1 does not read as 7.
    assert not quotes_the_number("Setback 7.1 feet", 7, glued=True)
    # And a comma still keeps the whole token out of it, so 7,500 is not 750.
    assert not quotes_the_number("Minimum lot area 7,500", 750, glued=True)


def test_a_decimal_printed_without_its_leading_zero_still_reads() -> None:
    """Wood Village's Table 210-3 gives its LR12 density floor as ".9 (25%)"
    and Table 220-3 gives a coverage as ".80". Both are how a table prints a
    figure below one, and the scan saw no number there at all -- so a value
    encoded 0.9 against the line that states it came back misquoted, which is
    the check disagreeing with the typography rather than with the encoding.
    """
    from flats.encode.readiness import quotes_the_number

    assert quotes_the_number("Minimum Number of Dwellings Per Net Acre  .9 (25%)", 0.9)
    assert quotes_the_number("Maximum lot coverage  .80", 0.8)
    # And it is still the number it prints, not one nearby.
    assert not quotes_the_number("Minimum Number of Dwellings Per Net Acre  .9", 9)
    assert not quotes_the_number("Maximum lot coverage  .80", 80)


def test_the_tail_of_a_citation_is_not_a_number_the_line_states() -> None:
    """The guard that says so had never run. `_NUMBER` was defined twice at
    module scope, three hundred lines apart, and the second definition -- which
    carried no guard -- silently won every lookup. So for as long as the check
    has existed, a value could have been evidenced by the section number of the
    sentence it was cited from: 33.110.220 reading as 220 feet.

    Nothing in the corpus was resting on that. Un-shadowing the guard moved no
    jurisdiction on the ladder, which is the answer to whether it mattered in
    practice and not the answer to whether it should have been live.
    """
    from flats.encode.readiness import quotes_the_number

    assert not quotes_the_number("PCC 33.110.220 Development standards", 220)
    assert not quotes_the_number("PCC 33.110.220 Development standards", 110)
    # A bare decimal is read, and the dot in a citation still is not.
    assert not quotes_the_number("See CDC 25.070 for the district", 70)
    assert quotes_the_number("a floor of .070", 0.07)


def test_no_value_anywhere_in_the_corpus_is_misquoted() -> None:
    """A ratchet, in the shape the footnote gate already uses.

    Eighteen jurisdictions assert this about themselves and the nineteenth does
    not, which is how a misquote reaches production: it arrives in the layer
    nobody wrote the assertion for. Stated once, over everything, so that a
    quote pointing at a line that does not carry its number fails the suite in
    the slice that introduced it rather than in the review it was meant to make
    possible.
    """
    store = ProvenanceStore()
    found = [
        (name, zone, field)
        for name, layer in sorted(load_rules().items())
        for zone, field in readiness_for(layer, store=store).misquoted
    ]
    assert found == []
