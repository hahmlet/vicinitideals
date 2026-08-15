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
    return readiness(trusted, store)[0]


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
    order = [r.stage for r in readiness(trusted, store)]

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

    assert by_stage(readiness(trusted, store)) == {"no_source": 1, "unsigned": 1}


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
