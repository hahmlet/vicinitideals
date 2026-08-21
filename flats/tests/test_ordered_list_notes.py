"""Two readers were blind in series, and a county's footnotes fell through both.

ZDO Section 315 is the only document behind every value in Clackamas
unincorporated, and the census reported 305 footnote markers and zero bodies --
the worst document in the corpus by a factor of four. The gate that holds a
value back when an unread note governs it therefore governed nothing in that
layer at all. It did not report a problem; it reported the layer clean, because
a gate with nothing to hold looks exactly like a gate with nothing to hold back.

Two causes, one behind the other.

*The extractor.* The county writes each table's notes as an HTML ordered list.
An ``<ol>``'s numbers are drawn by the browser and never appear in the text, so
the stored document held ten note bodies stripped of the one thing tying them
to a marker. Fixed by numbering the items, written as a PREFIX on the line the
item already occupies -- every citation in this system is a line number, and a
line of its own would have lifted every quote below it.

*The census.* The notes that did keep their numbers -- Table 315-3 prints them
as superscripts -- arrived as "9 Except for middle housing", one space and no
heading, which is the one run shape the reader declined. It declined it for a
good reason: at one space that pattern also matches every numbered paragraph in
a code, and it matches an ordered list of ordinary provisions even better once
the extractor above starts numbering them. So the shape earns its reading
twice, by the run and by the markers.

What it cost to have missed it: 41 notes over 64 values. What it did not cost:
a single encoded number. Everything the notes say is about another housing
type, another application path, a split plat, or a relief this layer declines
to take.

The one that nearly did move a number is the reason to read notes at all. Table
315-3 note 12 ends "do not apply to cottage clusters developed pursuant to
Section 845, Triplexes, Quadplexes, Townhouses, and Cottage Clusters" -- four
building types, one of them ours, and the 18 foot maximum front setback on both
village zones would have come off. Those four are the TITLE of Section 845. The
relief runs to cottage clusters and the maximum binds.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes as dispositions
from flats.encode.footnotes import census
from flats.encode.qualified import qualified
from flats.provenance.fetch import html_to_text
from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import condition
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"
ZDO = f"{CLACKAMAS}/zdo.315.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# --- the extractor: an ordered list keeps its numbers -------------------


def test_an_ordered_list_arrives_numbered() -> None:
    got = html_to_text(
        "<p>Table 315-2</p><ol><li>The minimum lot size standards apply.</li>"
        "<li>In a planned unit development, there is no minimum lot size.</li></ol>"
    )
    assert "1 The minimum lot size standards apply." in got
    assert "2 In a planned unit development, there is no minimum lot size." in got


def test_and_an_unordered_one_does_not() -> None:
    """A bullet has no number to lose. Numbering it would invent one."""
    got = html_to_text("<ul><li>Freight shipping containers.</li><li>Metal buildings.</li></ul>")
    assert "1 Freight" not in got
    assert "Freight shipping containers." in got


def test_the_number_is_a_prefix_and_never_a_line_of_its_own() -> None:
    """The load-bearing constraint. Every citation in this system is a line
    number, so an extractor change that adds a line silently re-points every
    quote below it in the document. Same items, same line count."""
    markup = "<p>a</p><ol><li>one</li><li>two</li><li>three</li></ol><p>b</p>"
    numbered = html_to_text(markup).splitlines()
    plain = html_to_text(markup.replace("ol>", "ul>")).splitlines()
    assert len(numbered) == len(plain)
    assert [line for line in numbered if line] == ["a", "1 one", "2 two", "3 three", "b"]


def test_a_nested_list_restarts_and_the_parent_resumes() -> None:
    got = html_to_text(
        "<ol><li>one</li><li>two<ol><li>inner</li><li>inner two</li></ol></li>"
        "<li>three</li></ol>"
    )
    kept = [line for line in got.splitlines() if line]
    assert kept == ["1 one", "2 two", "1 inner", "2 inner two", "3 three"]


def test_a_list_inside_a_table_is_left_alone() -> None:
    """A cell holding a list collapses to one grid line, so numbering there
    would inject "1 2 3" into a row. The omission costs less than the repair."""
    got = html_to_text("<table><tr><td><ol><li>one</li><li>two</li></ol></td></tr></table>")
    assert "1 one" not in got
    assert "one" in got and "two" in got


# --- the census: what a one-space run has to prove ----------------------


def test_a_one_space_run_is_read_when_a_marker_points_into_it() -> None:
    text = "\n".join(
        [
            "Maximum Building Height",
            "35 feet3",
            "",
            "1 The minimum lot size standards apply as established by Section 1012.",
            "",
            "2 In a planned unit development, there is no minimum lot size.",
            "",
            "3 Except for middle housing developed pursuant to Section 845.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2", "3"]
    assert seen.unbodied == ()


def test_but_not_when_nothing_in_the_document_bears_a_marker() -> None:
    """ZDO 845 in one test: sixteen numbered lists, not one footnote marker.
    Read as notes blocks they become seventy bodies nobody references, and
    ``unmarked`` is how this census reports a marker lost in extraction --
    filling it with ordinary prose lists destroys the signal it exists for."""
    text = "\n".join(
        [
            "845.01 General standards.",
            "",
            "1 The minimum lot size is 7,000 square feet for a quadplex.",
            "",
            "2 A quadplex shall have four dwelling units.",
            "",
            "3 Off-street parking shall comply with Section 1015.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert seen.blocks == ()
    assert seen.bodies == ()
    assert seen.reconciled


def test_and_not_when_a_sentence_interrupts_the_run() -> None:
    """A code's numbered subsections are separated by the prose they govern.
    One interposed line is enough to decline the whole run."""
    text = "\n".join(
        [
            "Height 35 feet3",
            "",
            "1 The applicant shall submit a site plan.",
            "The plan shall be drawn to scale.",
            "2 The director shall review it.",
            "",
            "3 A decision shall issue within 30 days.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert seen.blocks == ()


def test_a_headed_block_needs_no_marker_to_be_believed() -> None:
    """The marker test is scoped to the weakest shape on purpose. A "NOTES:"
    heading says what it is without help, and a block that says what it is
    should still be read when its markers are the thing that went missing --
    which is precisely the case ``unmarked`` was built to report."""
    text = "\n".join(
        [
            "Standard          R-5",
            "Building height   45 feet",
            "",
            "NOTES:",
            "1 Density is calculated under Section 16.63.020.",
            "2 The maximum is 45 feet at the front elevation.",
        ]
    )
    seen = census(text, doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2"]
    assert [b.mark for b in seen.unmarked] == ["1", "2"]


# --- what it recovers in the document that prompted it ------------------


def test_the_worst_document_in_the_corpus_now_has_bodies(store: ProvenanceStore) -> None:
    """Four blocks where there were none, and the unbodied count down from
    every marker in the document to a fraction of them. Still unreconciled, and
    that is the ledger doing its job rather than a claim of completeness."""
    got = census(store.load(ZDO).text, layer=CLACKAMAS, doc=ZDO)
    assert len(got.markers) > 400
    assert len(got.blocks) == 4
    assert len(got.bodies) == 77
    assert len(got.unbodied) < len(got.markers) / 4


def test_each_table_answers_its_own_markers(store: ProvenanceStore) -> None:
    """The regions have to partition or table B's note 1 answers table A's
    marker 1. Before the extractor fix, Table 315-2's block was invisible and
    Table 315-3's notes reached back over the low-density districts."""
    got = census(store.load(ZDO).text, layer=CLACKAMAS, doc=ZDO)
    heads = [b.head for b in got.blocks]
    assert heads == [1040, 1249, 1398, 1535]
    # Table 315-2's grid sits inside the second block's region, so the R zones
    # read the ten notes printed under their own table.
    second = got.blocks[1]
    assert second.region[0] < 1169 < second.region[1]
    assert len(second.bodies) == 11


# --- the gate, awake --------------------------------------------------


def test_the_gate_governs_this_layer_and_holds_nothing_back() -> None:
    rows = [r for r in qualified() if r.layer == CLACKAMAS]
    assert len(rows) == 64
    assert not any(r.blocking for r in rows)
    assert not any(n.state == "unread" for r in rows for n in r.governing)


def test_and_not_one_encoded_number_moved() -> None:
    """The claim the whole change rests on. Forty-one notes read, sixty-four
    values governed, and every figure in the layer is what it was: the relief
    in this chapter is for other housing types, other application paths, or a
    split plat, and the one piece that does reach this building is declined."""
    rules = RuleSet(load_rules())
    assert {
        zone: rules.resolve(CLACKAMAS, zone).values["max_height_ft"].value
        for zone in ("R5", "R7", "R8.5", "R10", "R15", "R20", "R30", "VR57", "VR45")
    } == dict.fromkeys(("R5", "R7", "R8.5", "R10", "R15", "R20", "R30", "VR57", "VR45"), 35)
    vr = rules.resolve(CLACKAMAS, "VR57").values
    assert (vr["setback_front_ft"].value, vr["setback_front_max_ft"].value) == (10, 18)
    assert vr["max_coverage_pct"].value == 50


def test_the_note_that_reads_as_a_relief_and_is_a_section_title(
    store: ProvenanceStore,
) -> None:
    """Table 315-3 note 12 ends "The maximum setback standards do not apply to
    cottage clusters developed pursuant to Section 845, Triplexes, Quadplexes,
    Townhouses, and Cottage Clusters." Read as a list of four building types it
    lifts the 18 foot maximum front setback off this pod entirely.

    It is not a list. It is the title of Section 845, and the document settles
    it: nine sentences print the same trailing four, eight of them nowhere near
    a setback, and two cannot be read any other way -- "subject to Section 845, Triplexes, Quadplexes,
    Townhouses, and Cottage Clusters", and a townhouse rule whose scope would
    contradict itself if the four were its scope. The relief runs to cottage
    clusters, a quadplex is not one, and the maximum binds.

    This is the test for a misreading that costs nothing to make and would have
    silently deleted a standard: the safe direction on a maximum is to hold it.
    """
    lines = store.load(ZDO).text.splitlines()
    title = "Section 845, Triplexes, Quadplexes, Townhouses, and Cottage Clusters"
    printed = [i + 1 for i, line in enumerate(lines) if title in line]
    assert printed == [1078, 1080, 1082, 1253, 1255, 1400, 1414, 1420, 1442]
    # The two that can only be a title: one names the section as a thing you
    # are subject to, the other states a rule for townhouses alone.
    assert lines[1077].endswith(f"is subject to {title}.")
    assert lines[1252].startswith(f"3 For townhouses developed pursuant to {title},")

    ruled = {n.line: n for n in dispositions(CLACKAMAS) if n.doc == ZDO}
    note = ruled[1420]
    assert "maximum setback standards do not apply to cottage clusters" in note.text
    assert note.state == "dismissed"
    assert "TITLE of Section 845" in note.reason
    assert "not a cottage cluster" in note.reason


def test_and_the_three_reliefs_that_hang_off_that_maximum_stand_on_their_own() -> None:
    """Notes 18, 19 and 20 each relax the maximum front setback. While note 12
    was misread they were dismissed as relaxations of a standard already gone,
    which is a reason that evaporates with the misreading. Each has to decline
    on its own merit -- a relief this screen does not take can refuse a lot the
    county would pass and can never pass one it would refuse."""
    ruled = {n.line: n for n in dispositions(CLACKAMAS) if n.doc == ZDO}
    for line in (1432, 1434, 1436):
        assert ruled[line].state == "dismissed", line
        assert "relief" in ruled[line].reason.lower(), line


def test_and_the_one_that_rests_on_a_lot_fact_nobody_holds_is_not_dismissed() -> None:
    """Note 15 makes frontage on an accessway a front lot line, which turns a
    5 ft side into a 10 ft front on whichever face it lands. It tightens, and
    an accessway is not a street, so no layer here answers it. That is
    ``unmeasured``, against a condition registered for it -- the alternative is
    a dismissal that quietly assumes the lot has no accessway."""
    ruled = {n.line: n for n in dispositions(CLACKAMAS) if n.doc == ZDO}
    note = ruled[1426]
    assert note.text.startswith("Frontage on an accessway shall be considered a front lot line")
    assert note.state == "unmeasured"
    assert note.fact == "abuts_accessway"
    registered = condition("abuts_accessway")
    assert registered.kind == "site_fact"
    assert registered.assume is None


def test_the_two_that_only_ever_loosen_are_dismissed_as_such() -> None:
    """Notes 22 and 26 re-label a face as a SIDE lot line, and 26 prints the
    five feet that is already the encoded side setback. Neither can move a
    value, so neither is unmeasured -- capping a verdict on a fact that cannot
    change the answer is how an honest signal turns into noise."""
    ruled = {n.line: n for n in dispositions(CLACKAMAS) if n.doc == ZDO}
    for line in (1440, 1448):
        assert ruled[line].state == "dismissed", line
        assert "side lot line" in ruled[line].text, line


# --- and the lists that are not lists of provisions ---------------------


def test_a_breadcrumb_is_an_ordered_list_and_is_not_numbered() -> None:
    """The regression the fix above walked into. Both Oregon state sources --
    the Secretary of State's rules and the Legislature's statutes -- open every
    page with a breadcrumb trail marked up as an <ol>, so numbering ordered
    lists put "1 OAR", "2 Chap. 660", "3 Division 46" above the text of the law
    and pushed everything under it down by two lines.

    Two lines is the whole danger. Every citation in this system is a line
    number, and three state documents carry citations that other layers lean
    on -- the middle housing rules that bar a city from applying a density
    maximum to a quadplex among them."""
    got = html_to_text(
        '<nav><ol class="breadcrumb"><li><a href="/">OAR</a></li>'
        "<li>Chap. 660</li><li>Rule 660-046-0220</li></ol></nav>"
        "<p>(2)(b) A Large City shall not apply a density maximum.</p>"
    )
    kept = [line for line in got.splitlines() if line]
    assert kept == ["OAR", "Chap. 660", "Rule 660-046-0220",
                    "(2)(b) A Large City shall not apply a density maximum."]


def test_the_class_alone_is_enough_without_a_nav_wrapper() -> None:
    for markup in (
        '<ol class="breadcrumb"><li>OAR</li><li>Chap. 660</li></ol>',
        '<ol id="site-nav"><li>OAR</li><li>Chap. 660</li></ol>',
        '<ol role="navigation"><li>OAR</li><li>Chap. 660</li></ol>',
    ):
        assert "1 OAR" not in html_to_text(markup), markup


def test_a_list_nested_inside_navigation_stays_unnumbered() -> None:
    """A menu's submenu is still a menu."""
    got = html_to_text(
        '<nav><ol><li>Chapters<ol><li>Chapter 16</li><li>Chapter 17</li></ol></li></ol></nav>'
    )
    assert "1 Chapter 16" not in got
    assert "Chapter 16" in got


def test_but_an_ordinary_list_after_a_breadcrumb_is_still_numbered() -> None:
    """The guard is scoped to the nav element and to the list that declares
    itself one. A page is a breadcrumb followed by the law, and the law keeps
    its numbering."""
    got = html_to_text(
        '<nav><ol class="breadcrumb"><li>OAR</li></ol></nav>'
        "<ol><li>The minimum lot size standards apply.</li>"
        "<li>In a planned unit development, there is no minimum.</li></ol>"
    )
    assert "1 The minimum lot size standards apply." in got
    assert "2 In a planned unit development, there is no minimum." in got
    assert "1 OAR" not in got


def test_the_three_state_documents_that_caught_it_are_line_stable() -> None:
    """What the sweep is for. These are the only documents in the corpus that
    moved, they are the ones state law is quoted from, and a quote into them is
    a line number that has to mean today what it meant when it was written."""
    store = ProvenanceStore()
    assert len(store.load("or/oar.660-046-0020.txt").text.splitlines()) == 226
    assert len(store.load("or/oar.660-046-0220.txt").text.splitlines()) == 287
    assert (
        len(store.load("or/clackamas/johnson-city/ors.197a.420.txt").text.splitlines())
        == 343
    )
