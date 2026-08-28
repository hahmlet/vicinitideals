"""The notes list that announces itself with nothing but a weld.

`GLUED_NOTE` -- the superscript that lost its raised baseline in extraction and
welded itself to the first word of its own note -- was only ever read inside a
block somebody else had opened. Clackamas prints its bonus density notes with
no heading at all::

    1Does not apply in the VA, VR-4/5, VR-5/7, or VTH Districts
    2For the purposes of this provision, mixed-use development means ...
    3May only be applied in the C-3, CC, OC, and RTL Districts

so ZDO 1012 carried four markers, no block, and nothing to answer them. The
block is the first in the document, which means its region reaches back over
the general density paragraph that all nine of the layer's maximum densities
quote -- so opening it put nine values behind an unread note, and every one of
those notes turned out to qualify a bonus nobody has elected.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes as dispositions
from flats.encode.footnotes import _glued_run, census
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _lines(store: ProvenanceStore, doc: str) -> list[str]:
    return store.load(doc).text.split("\n")


# --- what opens a run --------------------------------------------------------


def test_the_second_note_has_to_follow_immediately() -> None:
    """Stricter than its headless sibling, which lets prose come between the
    first note and the second. A column gap says "table" on its own; a weld
    says nothing, and the only thing keeping "1Does" apart from a seam in the
    extraction is that a second one arrives directly under it."""
    run = ["1Does not apply in the VA District", "2For the purposes of this"]
    assert _glued_run(run, 0)
    assert not _glued_run(["1Does not apply", "A sentence in between", "2For the"], 0)


def test_and_the_run_has_to_start_at_one() -> None:
    assert not _glued_run(["2For the purposes", "3May only be applied"], 0)
    assert not _glued_run(["1Does not apply", "3May only be applied"], 0)


def test_a_measurement_or_a_citation_is_not_a_note() -> None:
    """`GLUED_NOTE` wants a capital and then a lowercase letter, which is what
    keeps a welded figure and a welded code out."""
    assert not _glued_run(["10 feet in between structures", "2For the purposes"], 0)
    assert not _glued_run(["1ORS 456.270 applies", "2For the purposes"], 0)


# --- what it opens in the corpus ---------------------------------------------


def test_exactly_one_document_opens_a_block_this_way(store: ProvenanceStore) -> None:
    """Eight lines in the corpus wear the welded shape, across three documents,
    and every one is a real note -- but only Clackamas needs the opener. Lake
    Oswego's pair sits under a "Notes:" heading that has already opened a
    block, and Wilsonville's is a note 2 inside an open one."""
    doc = "or/clackamas/lake-oswego/50.04.dimensional.txt"
    lines = _lines(store, doc)
    assert [i + 1 for i in range(len(lines)) if _glued_run(lines, i)] == [2412]
    inside = next(b for b in census("\n".join(lines), doc=doc).blocks if b.head == 2411)
    assert [(b.line, b.mark) for b in inside.bodies] == [(2412, "1"), (2413, "2")]

    doc = "or/clackamas/wilsonville/4.planning.txt"
    lines = _lines(store, doc)
    assert [i + 1 for i in range(len(lines)) if _glued_run(lines, i)] == []
    got = census("\n".join(lines), doc=doc)
    assert [(b.line, b.mark) for b in got.bodies if 5285 <= b.line <= 5295] == [
        (5290, "1"),
        (5291, "2"),
    ]


def test_the_bonus_density_table_has_its_notes(store: ProvenanceStore) -> None:
    doc = f"{CLACKAMAS}/zdo.1012.txt"
    got = census(store.load(doc).text, layer=CLACKAMAS, doc=doc)
    assert [b.head for b in got.blocks] == [186]
    block = got.blocks[0]
    assert [(b.line, b.mark) for b in block.bodies] == [
        (186, "1"),
        (187, "2"),
        (188, "3"),
        (189, "4"),
        (190, "5"),
    ]
    assert got.unbodied == ()


def test_but_two_of_them_are_marked_in_capitals_and_stay_unmarked(
    store: ProvenanceStore,
) -> None:
    """One of them, now. "MAXIMUM TOTAL INCREASE5" carries its mark welded to
    a capital, and `LABEL_MARKER` wants a lowercase letter or a bracket in
    front of the digit. Widening it to accept capitals reads 138 lines across
    21 documents, almost all of them permission codes -- ZDO 315 alone prints
    "CPUD23" forty-four times, which is a use code and two markers, not a
    marker numbered twenty-three. So that body is left reported as unmarked,
    which is the honest direction to fail: the census says a note exists that
    nothing was seen to point at.

    "Mixed-Use Development2" was the other, and it was never welded by the
    county -- the weld was the extractor's, closing up a `<sup>` it had no
    rule for. Since `flats-html-text/7` the line reads "Mixed-Use
    Development[2]" and the bracket is read anywhere, so the body is pointed
    at and this ledger is one shorter."""
    doc = f"{CLACKAMAS}/zdo.1012.txt"
    got = census(store.load(doc).text, layer=CLACKAMAS, doc=doc)
    assert [(b.line, b.mark) for b in got.unmarked] == [(190, "5")]


def test_every_bonus_note_is_ruled_and_nine_densities_come_unblocked() -> None:
    """The block's region is everything above it, which is the whole of the
    general density provisions -- so all nine of this layer's maximum densities
    quote a line the block governs. Each note qualifies Table 1012-1, Bonus
    Density: an election an applicant makes to exceed base density, priced in
    affordability covenants, mixed use, park dedication or habitat protection.
    A bonus can only add, so a pod that fits without one still fits."""
    ruled = {row.quote: row for row in dispositions(CLACKAMAS)}
    for line in (186, 187, 188, 189, 190):
        row = ruled[f"{CLACKAMAS}/zdo.1012.txt#L{line}"]
        assert row.state == "dismissed"
        assert "Bonus Density" in row.reason
    assert not [row for row in qualified() if row.blocking]
