"""A note list is not too long, it just has not stopped being one.

A block was capped at eighty lines from its heading. Clackamas County's Table
315-1 runs thirty notes, several of which carry their own lettered criteria --
note 23 alone has five -- and the reading stopped mid-list at 23. Notes 24
through 30 were left as forty-four orphan markers on the table above, and ZDO
Section 315 is the only document behind every value in Clackamas
unincorporated.

Length was never the danger. A long run of numbered notes is a long run of
evidence. What the cap was put there to stop is a block that stopped being one
and is quietly swallowing prose under the rule that an unrecognised line
continues the previous note -- and that shows as a stretch of lines with no
note in it. So the eighty is measured from the last note taken.

The same cap was truncating a rule mid-sentence: Gresham's CMF townhouse height
note ended at "CMU and CMF districts: 1 Story" three lines short of the maximum
it was setting.
"""

from __future__ import annotations

import pytest

from flats.encode.footnotes import BLOCK_LIMIT, census
from flats.encode.dispositions import notes as dispositions
from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore

pytestmark = pytest.mark.unit

CLACKAMAS = "or/clackamas/_unincorporated"
ZDO = f"{CLACKAMAS}/zdo.315.txt"
GRESHAM = "or/multnomah/gresham"
CORRIDOR = f"{GRESHAM}/4.0400.corridor.txt"


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


@pytest.fixture(scope="module")
def zdo315(store: ProvenanceStore):
    return census(store.load(ZDO).text, layer=CLACKAMAS, doc=ZDO)


# --- what the eighty is counted from ----------------------------------------


def test_a_run_of_notes_may_be_longer_than_the_limit() -> None:
    """Thirty notes, each with a wrapped line under it, is sixty lines of
    block plus the criteria the codifier hangs off them. Counted from the
    head it stops at note 23; counted from the last note it does not stop at
    all."""
    lines = ["Notes:"]
    for n in range(1, 31):
        lines.append(f"{n} The use is subject to standard number {n}.")
        lines.append(f"   which continues onto a second line for note {n}.")
    seen = census("\n".join(lines), doc="d.txt")
    assert [b.mark for b in seen.bodies] == [str(n) for n in range(1, 31)]


def test_but_a_stretch_with_no_note_in_it_still_ends_the_block() -> None:
    """What the cap is for. Past this many lines with nothing numbered in
    them, the rule that an unrecognised line continues the previous note is
    doing more harm than good."""
    lines = ["Notes:", "1 The use is subject to the following standards."]
    lines += [f"prose line {n} that is not a note at all." for n in range(BLOCK_LIMIT + 5)]
    lines.append("2 This note is past the cap and is not reached.")
    seen = census("\n".join(lines), doc="d.txt")
    assert [b.mark for b in seen.bodies] == ["1"]


# --- what the corpus says now -----------------------------------------------


def test_the_county_use_table_answers_all_thirty(zdo315) -> None:
    block = next(b for b in zdo315.blocks if b.head == 1040)
    assert [b.mark for b in block.bodies] == [str(n) for n in range(1, 31)]


def test_the_orphans_the_cap_was_making(zdo315) -> None:
    """Forty-five markers with no body in their region, forty-four of them
    notes 24 to 30 on Table 315-1. One is left, and it is a different
    question: a label marker on Table 315-2 whose note the census has not
    found."""
    assert [m.line for m in zdo315.unbodied] == [1222]


def test_a_height_rule_that_used_to_stop_mid_sentence(store) -> None:
    """Gresham's CMF townhouse height note is the eighteenth under its
    heading, and the cap cut it three lines short of the maximum it sets."""
    seen = census(store.load(CORRIDOR).text, layer=GRESHAM, doc=CORRIDOR)
    note = next(b for b in seen.bodies if b.line == 492)
    assert "Minimum Building Height" in note.text
    assert "Maximum Building Height: 45 feet" in note.text


def test_every_new_note_is_ruled_and_none_blocks() -> None:
    ruled = {row.quote: row for row in dispositions(CLACKAMAS)}
    for line in (1120, 1122, 1124, 1126, 1134, 1136, 1138):
        assert ruled[f"{ZDO}#L{line}"].state == "dismissed"
    assert not [row for row in qualified() if row.blocking]
