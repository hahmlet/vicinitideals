"""Portland's table notes govern other tables, other buildings, or relief.

Twenty-five of the forty captured notes sit over a value this corpus encodes
and every one of them is dismissed, which is a finding rather than a shrug:
Portland writes its conditions into the regulation text and keeps its table
notes for the institutional standards, the FAR bonus table, the parking
maximums, and for grandfathering lots that a condemnation or a zone change
left undersized.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes
from flats.encode.qualified import qualified

pytestmark = pytest.mark.unit

LAYER = "or/multnomah/portland"


def test_no_encoded_value_waits_on_an_unread_note() -> None:
    """The rung this clears: a number read from lines a footnote governs
    cannot be signed until somebody rules on the footnote."""
    blocked = [q for q in qualified(LAYER) if q.blocking]

    assert not blocked


def test_exactly_one_note_caps_a_verdict() -> None:
    """For a long time none did, and that was the finding: Portland writes its
    conditions into the section text — the civic corridor coverage bonus is a
    variant, not a note — and keeps its table notes for other tables, other
    buildings and relief.

    Chapter 33.150 broke the run. Note [3] under Table 150-2 sets maximum FAR
    inside the PCC Sylvania campus boundary at .75 to 1 where the CI2 column
    says 3 to 1 — a quarter of the zone's own ceiling, on a line on Map 150-5
    that nothing here reads. It is the one Portland note that makes a standard
    tighter on a fact nobody measures, and 0.75 is low enough to decide a
    four-unit pod rather than sitting harmlessly above it."""
    capping = [n for n in notes() if n.layer == LAYER and n.state == "unmeasured"]

    assert [n.quote for n in capping] == ["or/multnomah/portland/33.150.txt#L571"]
    assert capping[0].fact == "site_specific_limitation"


def test_the_grandfathering_notes_are_dismissed_as_relief() -> None:
    """Table 110-3's five notes keep a primary structure allowed on lots that
    a condemnation, a zone change or an old lot confirmation shrank. Declining
    a widening can only cost a lot that would have qualified; reading one in
    would manufacture a GREEN."""
    ruled = {
        n.line: n
        for n in notes()
        if n.layer == LAYER and n.doc.endswith("33.110.txt") and 390 < n.line < 420
    }

    assert len(ruled) == 5
    assert all(n.state == "dismissed" and n.reason for n in ruled.values())
