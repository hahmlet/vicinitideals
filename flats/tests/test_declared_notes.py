"""The chapter that answers its table in prose, and how it hid.

Portland prints no notes block under a use table. Table 120-1 says whether a
four-unit building is allowed in the multi-dwelling zones, and the
qualifications on that table are numbered subsections of section 33.120.100 --
ordinary paragraphs, ordinary layout, nothing on the page that says
"footnote". What makes them notes is a sentence inside each one: "This
regulation applies to all parts of Table 120-1 that have a [4]."

Six chapters are written that way -- open space, single-dwelling,
multi-dwelling, commercial, industrial, campus institutional; between them
Portland's entire non-residential half. They carried a hundred and
seventy-three markers no block could answer, and the census reported the
documents unreconciled and left it there.

Two things had to be true before the shape could be read safely. The note has
to name the table, because Portland prints Table 100-1 above its limitations
and Table 120-1 below them -- so a region rule that runs backwards from a
heading answers one and misses the other. And the block has to be allowed to
straddle its own table: chapter 33.140 prints limitations 1 through 9, then
Table 140-1, then limitations 10 through 16, and a block read as one
continuous span swallows the table it is about. A table inside a block is a
table whose markers are never counted, which turns sixteen captured notes into
sixteen notes nobody points at and reports the document reconciled backwards.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes as dispositions
from flats.encode.footnotes import census
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _chapter(store: ProvenanceStore, stem: str):
    doc = f"{PORTLAND}/{stem}.txt"
    return census(store.load(doc).text, layer=PORTLAND, doc=doc)


# --- a body that names its own marker -------------------------------------


TABLE = [
    "Table 99-1",
    "Zone Primary Uses",
    "Use Categories",
    "Household Living                          Y",
    "Retail Sales And Service                  CU [1]",
    "Agriculture                               L [2]",
    "99.100.100 Primary Uses",
]

LIMITS = [
    "B.  Limited uses. The paragraphs below correspond with the footnote",
    "numbers from Table 99-1.",
    "1.  Retail Sales And Service. This regulation applies to all parts of",
    "Table 99-1 that have a [1]. Retail uses are conditional uses only when",
    "they are associated with a Park And Open Areas use.",
    "2.  Agriculture. This regulation applies to all parts of Table 99-1 that",
    "have a [2]. Agriculture is an allowed use.",
    "C.  Conditional uses.",
]


def test_a_paragraph_that_names_its_marker_is_a_note() -> None:
    seen = census("\n".join(TABLE + LIMITS), doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2"]
    assert "conditional uses only when" in seen.bodies[0].text
    assert seen.reconciled


def test_and_it_is_read_the_same_where_the_table_is_printed_after_it() -> None:
    """Portland does it both ways in the same title. A rule that reads the
    lines around the notes gets one of the two orders right; a rule that reads
    the table the note names gets both."""
    seen = census("\n".join(LIMITS + TABLE), doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2"]
    assert seen.reconciled


def test_one_paragraph_alone_is_not_a_run() -> None:
    """Same standard of proof the gapped and glued shapes buy their reading
    with. A single sentence mentioning a table and a bracketed number is a
    cross-reference about as often as it is a limitation."""
    alone = TABLE + LIMITS[:5] + ["C.  Conditional uses."]
    seen = census("\n".join(alone), doc="d.txt")
    assert seen.bodies == ()


def test_the_paragraph_number_has_to_be_the_mark_it_declares() -> None:
    """Across the corpus it is, in all ninety-one cases. Demanding it keeps a
    paragraph that merely refers to another table's footnote out -- the shape
    has no layout to fall back on, so agreement is the whole discriminator."""
    mismatched = list(LIMITS)
    mismatched[5] = "9.  Agriculture. This regulation applies to all parts of Table 99-1 that"
    seen = census("\n".join(TABLE + mismatched), doc="d.txt")
    assert seen.bodies == ()


def test_a_table_the_document_does_not_caption_governs_nothing() -> None:
    """The note claims a table; if the table is not here the claim cannot be
    checked, and the markers stay orphans. Failing towards "unreconciled" is
    the direction that reports a problem rather than hiding one."""
    elsewhere = [line.replace("Table 99-1", "Table 88-4") for line in LIMITS]
    seen = census("\n".join(TABLE + elsewhere), doc="d.txt")
    assert seen.bodies == ()
    # Four orphans, not two: with no block to sit inside, the declarations are
    # read as references to themselves. Noisy and correct -- a document that
    # points at a table it does not print is a document to go and look at.
    assert len(seen.unbodied) == 4


# --- what the six chapters say now ----------------------------------------


def test_the_open_space_chapter_reconciles(store: ProvenanceStore) -> None:
    """Fourteen markers and no bodies at all, before. Seven markers on Table
    100-1 and the seven limitations that answer them, after -- and the drop in
    the marker count is the seven declarations no longer being read as
    references to themselves."""
    got = _chapter(store, "33.100")
    assert [b.mark for b in got.bodies] == [str(n) for n in range(1, 8)]
    assert got.reconciled


def test_the_industrial_chapter_does_not_swallow_its_own_table(
    store: ProvenanceStore,
) -> None:
    """Limitations 1 to 9, then Table 140-1, then limitations 10 to 16. The
    block covers both runs of prose and not the table between them."""
    got = _chapter(store, "33.140")
    block = next(b for b in got.blocks if b.head == 181)
    assert [b.mark for b in block.bodies] == [str(n) for n in range(1, 17)]
    assert block.region == (318, 384)
    assert not any(low <= 350 < high for low, high in block.covered)
    assert all(b.mark not in block.marks or b.line > 384 for b in got.unmarked)
    # The chapter's other unmarked body is a screening note a thousand lines
    # down -- "when the F2 + L2 option is used, the fence must be placed along
    # the interior side of the landscaped area" -- and the only thing that
    # ever pointed at it was the "L3" in "25 ft. / L3 or", which is a
    # landscaping standard and not a marker at all. Losing the false pointer
    # is what makes the report true; the real superscript did not survive
    # extraction.
    assert [b.line for b in got.unmarked] == [1200]


def test_the_multi_dwelling_chapter_leaves_the_other_table_its_own_notes(
    store: ProvenanceStore,
) -> None:
    """Table 120-1's limitations and Table 120-2's notes both reach the lines
    between them, because a headed block's region runs back to the previous
    block. The tighter region wins, so the housing-types table keeps the two
    notes that are actually printed under it."""
    got = _chapter(store, "33.120")
    declared = next(b for b in got.blocks if b.head == 197)
    headed = next(b for b in got.blocks if b.head == 416)
    assert declared.region == (331, 385)
    assert headed.region == (0, 415)
    assert declared.region[1] - declared.region[0] < headed.region[1] - headed.region[0]


def test_the_use_table_limitation_that_decides_two_zones(
    store: ProvenanceStore,
) -> None:
    """Note [1] of Table 140-1 is the reason a pod cannot be built in EG1 or
    EG2, and it was read when those zones were encoded -- the value's quote
    already spans its lines. What changed is that the note is now a note: it
    is in the ledger, ruled `encoded`, and a future edit that widened the
    zones would have to answer it."""
    got = _chapter(store, "33.140")
    first = next(b for b in got.bodies if b.line == 181)
    assert "hotel or motel is converted to dwelling units" in first.text
    assert "are prohibited" in first.text

    ruled = {(n.doc, n.line): n for n in dispositions(PORTLAND)}
    ruling = ruled[(f"{PORTLAND}/33.140.txt", 181)]
    assert ruling.state == "encoded"
    assert "EG1 and EG2" in ruling.encoded_as


def test_every_portland_use_table_limitation_is_ruled_and_none_blocks() -> None:
    """A hundred and eighteen notes, a hundred and four ruled, none blocking.
    The fourteen left unread are Chapter 33.266's parking tables, which govern
    no value this layer encodes and were unread before any of this."""
    ruled = list(dispositions(PORTLAND))
    assert len(ruled) == 118
    unread = {row.doc.rsplit("/", 1)[-1] for row in ruled if row.state == "unread"}
    assert unread == {"33.266.txt", "33.120.txt"}
    assert not [row for row in qualified() if row.blocking]


def test_and_not_one_encoded_number_moved() -> None:
    """Seventy-eight notes read that nobody had read, and every one of them is
    about retail floor area, industrial size, agriculture, utilities,
    transmission towers, commercial parking, waste or fuel storage. Portland
    gives Household Living a bare letter in every zone this layer holds, and
    the two limitations that do reach it were already in the values."""
    from flats.rules.loader import load_rules
    from flats.rules.resolver import RuleSet

    rules = RuleSet(load_rules())
    for zone in ("EG1", "EG2", "IG1", "IG2", "IH", "OS", "CI1"):
        assert rules.resolve(PORTLAND, zone).values["quadplex_allowed"].value is False
    for zone in ("CM1", "CM2", "CM3", "CX", "CE", "CR", "CI2", "IR"):
        assert rules.resolve(PORTLAND, zone).values["quadplex_allowed"].value is True


# --- the same shape in another city's words --------------------------------


WV_TABLE = [
    "Table 240-1. Uses in Manufacturing Zones",
    "LM                        GM",
    "Household Living                          N     N",
    "Retail Sales and Service                  L(1)  L(1)",
    "Office                                    L(2)  L(2)",
]

WV_LIMITS = [
    "D. Limited Uses. Uses shown in Table 240-1 with the letter L are allowed",
    "subject to the following limitations.",
    "(1) This regulation applies to all parts of Table 240-1 marked with a (1).",
    "Retail uses are limited to 35% of the footprint of all buildings.",
    "(2) This regulation applies to all parts of Table 240-1 marked with a (2).",
    "Office uses are limited to 35% of the footprint of all buildings.",
]


def test_the_declaring_sentence_reads_in_wood_village_s_words() -> None:
    """Same shape, different verb and different bracket. Portland writes "that
    have a [4]" and Wood Village writes "marked with a (1)", and the marks in
    its tables are parenthesised to match -- so widening the verb without
    widening the bracket would read the sentence and then look for a mark the
    city does not print."""
    seen = census("\n".join(WV_LIMITS + WV_TABLE), doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1", "2"]
    assert seen.reconciled


def test_a_titled_caption_is_still_a_caption() -> None:
    """Portland captions a table "Table 120-1" and nothing else; Wood Village
    writes "Table 240-1. Uses in Manufacturing Zones". The punctuation is what
    keeps the declaring sentence itself out of the caption rule -- "Table 240-1
    marked with a (1)" also starts a line and also names the table, and reading
    it as the caption opens the region at the note instead of the table."""
    from flats.encode.footnotes import TABLE_CAPTION

    assert TABLE_CAPTION.match("Table 240-1. Uses in Manufacturing Zones")
    assert TABLE_CAPTION.match("Table 120-1")
    assert not TABLE_CAPTION.match(
        "Table 240-1 marked with a (1). Retail uses are limited"
    )


def test_the_two_manufacturing_tables_reconcile(store: ProvenanceStore) -> None:
    """Ten orphan markers between them, before. Section 250.200 needed a third
    verb on top: its second note declares itself as "Uses shown in Table 250-1
    with the number (2)", quoting its own marker."""
    for stem, marks in (("240.200", ["1", "2", "3"]), ("250.200", ["1", "2"])):
        doc = f"or/multnomah/wood-village/{stem}.txt"
        got = census(store.load(doc).text, layer="or/multnomah/wood-village", doc=doc)
        assert [b.mark for b in got.bodies] == marks, stem
        assert got.reconciled, stem
