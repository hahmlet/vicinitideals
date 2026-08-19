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


def test_nothing_here_caps_a_verdict() -> None:
    """No Portland note rests on a lot fact nothing measures. Where a mapped
    condition does decide a number — the civic corridor coverage bonus — it is
    in the section text and is encoded as a variant."""
    capping = [n for n in notes() if n.layer == LAYER and n.state == "unmeasured"]

    assert not capping


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
