"""Shared set-up for the FLATS suite.

**The car is not asked about a court outside ``test_turns.py``.** Since
2026-10-02 a lane-fed rear court is given the room a car needs to use every
stall (:func:`flats.score.turns.fixes`: on the design's own court an aisle
4 ft deeper, or the 13 ft dead end). The suite's other tests pin their own
mechanism -- open space, the paving cap, the outdoor square, the floor of
stalls -- on lots drawn to the foot around the court as it stood before, and a shape only a test's stub
rules produce is one the ledger does not hold, which would leave every such
court unchecked. So here every court needs no room; ``test_turns.py``
charges the real room, from the real ledger.
"""

from __future__ import annotations

import pytest

from flats.score import paper
from flats.score.turns import AS_DRAWN


@pytest.fixture(autouse=True)
def _courts_as_drawn(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.module.__name__.endswith("test_turns"):
        return
    monkeypatch.setattr(paper, "fixes", lambda shape: (AS_DRAWN,))
