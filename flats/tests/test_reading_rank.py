"""Which of a lot's readings the map shows (FOLLOWUPS 44).

A lot can be read more than one way: a corner's two fronts, a through
lot's two ends, a part-alley's two rear cuts, a line that is a street or
only a private drive. Where the owner chooses, the better reading is kept;
where nothing says which is true, the worse. "Better" and "worse" were the
triage: a fit the building MISSES read yellow there -- the variance path
round it -- and a reading that fits but waits on an open fact read
unknown, worse than yellow. Steph's flag plan (2026-10-02) shows every miss
RED, so the triage kept the wrong one both ways: an owner's corner was
shown on the front the building misses on (a false red), and a lot kept at
its worse reading was shown on the one it fits on (a false GREEN wherever
the open fact flags below the yellow line).

What must hold: the colour the map shows decides first, the triage only
breaks a tie on it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from flats.ingest.quadfit import _better, _front_rank, _shown, _worse
from flats.score.flags import Colour
from flats.score.screen import Triage

pytestmark = pytest.mark.unit


def reading(colour: Colour, triage: Triage, slack: float | None = 0.0, band: str | None = "target"):
    """The parts of a screened reading the ranking reads."""
    return SimpleNamespace(
        signed=SimpleNamespace(colour=colour, triage=triage),
        screening=SimpleNamespace(triage=triage, parking_band=band, fit_slack_ft=slack),
        envelope=None,
    )


#: The building misses by 3 ft: a bind, RED, whose variance path the triage
#: still reads yellow.
MISS = reading(Colour.red, Triage.yellow, slack=-3.0, band=None)
#: The building fits with 5 ft to spare, and waits on an open fact.
QUESTION = reading(Colour.yellow, Triage.unknown, slack=5.0)
#: Fits, and the open fact flags below the yellow line: GREEN on the map.
LOW_QUESTION = reading(Colour.green, Triage.unknown, slack=5.0)


def test_an_owner_keeps_the_front_the_building_fits_on() -> None:
    # 2026-10-05 bound, Beaverton 1S123AB02236: shown on the front it missed.
    for fronts in ((MISS, QUESTION), (QUESTION, MISS)):
        assert min(fronts, key=_front_rank) is QUESTION


def test_a_lot_kept_at_its_worse_reading_shows_the_miss() -> None:
    # A through lot nothing says the far end of (THROUGH_WORST) takes the
    # max: on the triage that was the reading it fits on, GREEN where the
    # open fact flags low.
    for question in (QUESTION, LOW_QUESTION):
        for ends in ((MISS, question), (question, MISS)):
            assert max(ends, key=_front_rank) is MISS


def test_the_worse_of_two_readings_is_the_miss() -> None:
    # Oregon City 32E06DD00603 pod80x25: shown fitting, the reading it is
    # kept at misses by 22 ft.
    for question in (QUESTION, LOW_QUESTION):
        assert _worse(question, MISS) is MISS
        assert _worse(MISS, question) is MISS


def test_the_better_of_two_readings_is_the_one_that_fits() -> None:
    for question in (QUESTION, LOW_QUESTION):
        assert _better(question, MISS) is question
        assert _better(MISS, question) is question


def test_the_triage_breaks_a_tie_on_the_colour() -> None:
    passes = reading(Colour.yellow, Triage.green)
    # Same colour: a question over a pass, as before.
    assert _worse(passes, QUESTION) is QUESTION
    assert _better(QUESTION, passes) is passes
    assert min((QUESTION, passes), key=_front_rank) is passes
    # Same colour and triage: the stall band, then the room to spare.
    roomy = reading(Colour.yellow, Triage.unknown, slack=9.0)
    assert min((QUESTION, roomy), key=_front_rank) is roomy


def test_the_colour_outranks_every_triage() -> None:
    order = [
        reading(Colour.green, Triage.unknown),
        reading(Colour.yellow, Triage.green),
        reading(Colour.yellow, Triage.unknown),
        reading(Colour.red, Triage.green),
        reading(Colour.red, Triage.red),
    ]
    assert sorted(order, key=_shown) == order
    assert sorted(reversed(order), key=_front_rank) == order
