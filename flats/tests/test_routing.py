"""The redirect ledger, and the one row that proves it works.

This module exists because of a mistake no check in the system could see.
"Portland states no parking aisle width" was read from 33.266.120, encoded,
and shipped -- and 33.266.120.B.1, four lines above the quoted sentence, sends
parking in a parking tract to 33.266.130, which states one. The section was in
a document already fetched, so the cross-reference ledger had nothing to
report; the value had a citation that rendered, so the readiness ladder had
nothing to report; the refusal was counted, so the refusal ledger had nothing
to report. Everything was green and the number was wrong.

:func:`test_the_ledger_speaks_on_the_state_the_corpus_was_actually_in`
reconstructs that day and asserts this ledger would have spoken. It is the
reason the followed/open split is computed from citations rather than recorded
as a ruling: a ruling channel closes a row when somebody says they read the
section, and that is exactly the sentence that was false.
"""

from __future__ import annotations

import csv

import pytest

from flats.encode.crossrefs import dangling
from flats.encode.routing import (
    _ROUTE,
    Routing,
    _is_followed,
    _spans,
    _within,
    redirects,
    survey,
    write,
)
from flats.rules.loader import load_rules

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def rows() -> list[Routing]:
    return survey()


#: Every redirect the corpus makes, beside a number it uses, pointing at a
#: section nothing was read from -- as of 2026-08-25. Each was read when this
#: ledger was built and each is somebody else's building or a rule that can
#: only loosen. Grouped by the reason, because the reasons repeat:
#:
#: *A bonus we do not claim.* Gresham's 10.1700, six times over. Every one of
#: those sentences removes a MINIMUM density for affordable housing
#: development; the chapter was fetched and read on 2026-08-20 and that
#: layer's notes record it as "a bonus and nothing else".
#:
#: *Somebody else's building.* Multnomah's 39.4753 is UF-20 conditional uses,
#: reached from a farm-use exception in a zone whose minimum lot is twenty
#: acres. Gresham's 4.0330 is industrial development and 4.1414 is commercial
#: use limits. West Linn's 25.020 is the Willamette Historic District, an
#: overlay this screen does not place into.
#:
#: *A rule that can only loosen.* Lake Oswego's 50.04.003 is Exceptions,
#: Projections and Encroachments, reached from two minimum-density footnotes.
#: Wilsonville's 4.140(.10)C is nonconformity -- about a building that already
#: exists. Portland's 33.140.215 is reached from a footnote reading "Does not
#: apply to lot lines that abut lots in the RX zone", in the employment and
#: industrial chapter.
#:
#: *A rule with no field to hold it.* Clackamas County's ZDO 845.01 states the
#: quadplex minimum lot size this layer reads, and two lines under it hands
#: the rest of middle housing to 845.02 through 845.04. 845.02, Triplexes And
#: Quadplexes, is this building exactly, and it is not somebody else's and it
#: does not only loosen: street-facing windows at 15 percent, entry
#: orientation, driveway entries capped at 32 feet total, and garages and
#: off-street parking barred from between a building and a public street
#: unless a dwelling screens them or they stay under half the frontage. The
#: last two are geometry this screen places. Nothing in the field registry can
#: say where parking sits relative to the street -- Gresham's equivalent rule
#: lives in the site-plan generator as a hard-coded rear-court typology, not
#: as a standard -- so the row stays open on a modelling gap rather than a
#: reading. This one appeared the day `_doc_ids` learned to read a filename
#: that opens with the code's own abbreviation: `zdo.845.txt` claimed no
#: chapter before that, so its own sections read as unfetched and the redirect
#: could not be scored.
#:
#: A row that is not on this list is the thing to look at. It means a number
#: in use sits beside a sentence handing its standard to a section nobody
#: opened.
OPEN = {
    "or/clackamas/_unincorporated 845.01 -> 845.02",
    "or/clackamas/lake-oswego 50.04.001.3 -> 50.04.003",
    "or/clackamas/west-linn 25.070 -> 25.020",
    "or/clackamas/wilsonville 4.001 -> 4.140",
    "or/multnomah/_unincorporated 39.4751 -> 39.4753",
    "or/multnomah/gresham 4.0120 -> 10.1700",
    "or/multnomah/gresham 4.0130 -> 10.1700",
    "or/multnomah/gresham 4.0420 -> 4.0330",
    "or/multnomah/gresham 4.0434 -> 10.1700",
    "or/multnomah/gresham 4.1130 -> 10.1700",
    "or/multnomah/gresham 4.1413 -> 4.1414",
    "or/multnomah/gresham 4.1415 -> 10.1700",
    "or/multnomah/gresham 4.1508 -> 10.1700",
    "or/multnomah/portland 33.140.210 -> 33.140.215",
}

#: The redirects the corpus can show somebody followed. Small, and worth
#: reading as a list: six sentences in the whole store hand a standard to a
#: section this corpus then went and read.
#:
#: The Clackamas County row is the pair of the open one above. ZDO 315.04
#: reads "The development of a triplex, quadplex, townhouse, or cottage
#: cluster is subject to Section 845", and the layer's quadplex minimum lot
#: size is cited to 845.01 -- so the pointer out of the district chapter was
#: followed and the pointer inside 845 was not. Both rows arrived together
#: when `_doc_ids` learned to read `zdo.845.txt`.
FOLLOWED = {
    "or/clackamas/_unincorporated 315.04 -> 845",
    "or/multnomah/_unincorporated 39.4245 -> 39.3070",
    "or/multnomah/fairview 19.115.020 -> 19.30",
    "or/multnomah/fairview 19.115.040 -> 19.30.030",
    "or/multnomah/gresham 9.0802 -> 9.0822",
    "or/multnomah/portland 33.266.120 -> 33.266.130",
}


def test_the_open_and_followed_rows_are_the_ones_that_have_been_read(
    rows: list[Routing],
) -> None:
    assert {r.label for r in rows if not r.followed} == OPEN
    assert {r.label for r in rows if r.followed} == FOLLOWED


def test_the_ledger_speaks_on_the_state_the_corpus_was_actually_in() -> None:
    """2026-08-24, reconstructed: the stall cited to 33.266.120.D.1.

    That is the whole state that mattered. One parking value, read from inside
    33.266.120, nothing read from inside 33.266.130, and a counted refusal
    saying Portland states no aisle. Every other check in the system was green
    on it.

    Rebuilt from the live layer rather than a fixture, because a fixture is a
    copy of a document and a copy cannot go stale in the same direction the
    original does -- if the extraction of 33.266 ever shifts, this test should
    move with it or fail, not quietly keep testing a file nobody ships.
    """
    layer = load_rules()["or/multnomah/portland"]
    stall = layer.defaults["parking_stall_width_ft"]
    for field in (
        "parking_stall_depth_ft",
        "parking_aisle_one_way_ft",
        "parking_aisle_two_way_ft",
    ):
        layer.defaults.pop(field)
    layer.defaults["parking_stall_width_ft"] = stall.model_copy(
        update={
            "prov": stall.prov.model_copy(
                update={"quote": "or/multnomah/portland/33.266.txt#L317-L318"}
            )
        }
    )

    row = next(r for r in redirects(layer) if r.ref == "33.266.130")

    assert row.section == "33.266.120"
    assert "subject to the standards of Section 33.266.130" in row.text
    assert not row.followed


def test_a_redirect_is_only_closed_by_a_citation_landing_inside_it() -> None:
    """One direction of containment, not both.

    A section read has to *be* the target or sit inside it. Reading a
    chapter's other sections is not evidence anybody opened this one --
    33.266 is where both the aisle and the refusal to state an aisle live, and
    a rule letting any 33.266.x citation answer for 33.266.130 would close the
    row this ledger exists to hold open.
    """
    assert _is_followed("33.266.130", {"33.266.130"})
    assert _is_followed("33.266", {"33.266.130"})

    assert not _is_followed("33.266.130", {"33.266"})
    assert not _is_followed("33.266.130", {"33.266.120"})
    assert not _is_followed("33.266.130", {"33.266.13"})
    assert not _is_followed("33.266.130", set())


def test_a_handed_off_block_is_answered_by_reading_anywhere_inside_it() -> None:
    """Gresham hands off "Sections 9.0822 to 9.0840" and the aisle is in 9.0825.

    Codes name a block, not each section in it. Matching only the number the
    reference starts with would hold that row open forever while the standard
    it points at sits encoded three sections in -- and a ledger with a
    permanent false alarm at the top of it is a ledger people learn to skip.
    """
    assert _spans("design standards (Sections 9.0822 to 9.0840) do not apply") == [
        ("9.0822", "9.0840")
    ]
    assert _spans("FMC 19.65.030 through 19.65.090") == [("19.65.030", "19.65.090")]

    assert _within("9.0825", "9.0822", "9.0840")
    assert _within("9.0822", "9.0822", "9.0840")
    assert not _within("9.0841", "9.0822", "9.0840")
    assert not _within("9.0821", "9.0822", "9.0840")


def test_a_pointer_that_only_adds_a_term_is_not_a_redirect() -> None:
    """The regex is the whole reason this ledger is a page.

    Codes cross-reference constantly and almost none of it replaces a
    standard. Admitting "see" or "in accordance with" would report every
    chapter in the store beside every number, which is a ledger nobody reads
    and therefore no ledger at all.
    """
    assert _ROUTE.search(
        "Parking that is in a parking tract is subject to the standards of "
        "Section 33.266.130 instead of the standards of this section."
    )
    assert _ROUTE.search("Minimum density does not apply to affordable housing.")
    assert _ROUTE.search("the requirements of this chapter supersede Chapter 19.30")

    assert not _ROUTE.search("See Section 10.1700.")
    assert not _ROUTE.search("as defined in FMC 19.162, Access and Circulation")
    assert not _ROUTE.search("in accordance with the standards of Chapter 52")
    assert not _ROUTE.search("intended to control the scale of those uses")


def test_a_layer_with_no_documents_reports_nothing() -> None:
    """The state layer holds no zones and no fetched code of its own.

    Worth pinning because the alternative is a crash on an empty document set,
    and a ledger that raises for one layer is a ledger that gets skipped in
    the run that would have caught something.
    """
    assert redirects(load_rules()["or"]) == []


def test_a_reference_we_cannot_open_belongs_to_the_other_ledger(
    rows: list[Routing],
) -> None:
    """No row here is also a row there.

    The two ledgers partition the same sentences: crossrefs takes the ones
    pointing at text the store does not hold, this takes the rest. An overlap
    would mean a reference counted twice and, worse, a chapter that looks
    fetched in one report and missing in the other.
    """
    layer = load_rules()["or/multnomah/gresham"]
    unfetched = {d.ref for d in dangling(layer)}
    here = {r.ref for r in rows if r.layer == "or/multnomah/gresham"}

    assert here
    assert here & unfetched == set()


def test_the_ledger_writes_one_row_per_redirect(tmp_path, rows: list[Routing]) -> None:
    out = write(rows, tmp_path / "routing.csv")
    with out.open(encoding="utf-8", newline="") as fh:
        got = list(csv.DictReader(fh))

    assert len(got) == len(rows)
    assert {r["followed"] for r in got} <= {"yes", ""}
    portland = next(r for r in got if r["ref"] == "33.266.130")
    assert portland["followed"] == "yes"
    assert portland["section"] == "33.266.120"
