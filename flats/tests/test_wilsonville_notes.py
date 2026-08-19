"""Wilsonville's Table 8A, which is mostly footnotes.

Every RN dimension in the corpus is read off one table in Section 4.127, and
that table hands its townhouse standards to notes B, C, G, I, J and M. Until
the census could read a lettered note, none of them was visible: the values
sat clear of footnotes that plainly qualify them, which is the exact shape of
a false GREEN.

What these hold is the encoding that came out of ruling on them — the combined
side yard the per-side numbers cannot carry, the two notes that move a
measuring line onto an easement nobody holds, and the fact that ruling did not
quietly certify anything.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import notes
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

WV = "or/clackamas/wilsonville"


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_pair_of_side_yards_is_carried_where_the_code_states_it(rules: RuleSet) -> None:
    """Note M is three standards in one sentence.

    "the minimum combined side yard setbacks shall total 20 ft. with a minimum
    of 10 ft." — the pair takes width off the lot, the floor says where the
    building may sit on what is left, and half of 20 is a number the document
    never prints.
    """
    big = rules.resolve(WV, "RN", lot={"lot_sqft": 12000})

    assert big.values["setback_side_ft"].value == 10
    assert big.values["setback_side_total_ft"].value == 20


def test_below_the_band_the_code_states_no_combined_standard(rules: RuleSet) -> None:
    """An ordinary lot gets the 5 ft floor and no pair at all.

    Exempt, not zero: the note asks nothing about the pair there, which is a
    different answer from asking that it total nothing.
    """
    small = rules.resolve(WV, "RN", lot={"lot_sqft": 8000})

    assert small.values["setback_side_ft"].value == 5
    assert "setback_side_total_ft" in small.exempted
    assert "setback_side_total_ft" not in small.values


def test_the_townhouse_lot_is_the_one_the_notes_state(rules: RuleSet) -> None:
    """Notes B and I, the two that make a split-plat townhouse lot possible."""
    split = rules.resolve(WV, "RN", ("unit_lots",))

    assert split.values["min_lot_sqft"].value == 1500
    assert split.values["min_lot_width_ft"].value == 20
    assert split.values["min_frontage_ft"].value == 20


def test_every_note_over_an_encoded_value_has_been_ruled_on() -> None:
    """The point of the pass: nothing governing is left unread.

    The twenty-four notes still unread belong to Table 8B, Table 8C, the Town
    Center sub-districts and the parking maximums — none of which this layer
    encodes a value from.
    """
    unread = [n for n in notes(WV) if n.state == "unread"]

    assert all(n.line > 7400 for n in unread), [f"L{n.line} [{n.mark}]" for n in unread]


def test_the_two_easement_notes_cap_the_verdict_rather_than_clearing_it() -> None:
    """Notes K and P move the line a setback is measured from onto an easement.

    Read, and unanswerable: the envelope starts somewhere inside the lot and
    nothing here holds recorded easements. Ruling them `unmeasured` stops them
    blocking the encoding and keeps them stopping a GREEN.
    """
    capping = {n.mark: n.fact for n in notes(WV) if n.state == "unmeasured"}

    assert capping == {"K": "access_easement", "P": "sidewalk_easement"}
