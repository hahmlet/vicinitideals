"""The stale-reason check has to survive its own success.

Every other ledger in this project can pin a count, because the thing it counts
is a property of Oregon's codes and moves slowly. This one counts *our own
mistakes*, and the intended end state is zero -- so a test that pins today's
eleven would go red the day somebody fixes the eleventh, which is the worst
possible time for a test to fail.

So the corpus tests here assert only that whatever the check reports is
internally true, and everything about the mechanism is tested on text written
in this file.
"""

from __future__ import annotations

import pytest

from flats.encode.dispositions import Ruling
from flats.encode.stale import Stale, _named, audit, render

pytestmark = pytest.mark.unit


class _Layer:
    def __init__(self, *zones: str) -> None:
        self.zones = {z: object() for z in zones}


def _ruling(reason: str, state: str = "dismissed") -> Ruling:
    return Ruling(
        layer="or/x/y",
        digest="d",
        state=state,
        reason=reason,
        encoded_as="",
        fact="",
        quote="or/x/y/doc.txt#L1",
        zones=(),
    )


def _run(reason: str, *zones: str, state: str = "dismissed") -> list[Stale]:
    return audit({"or/x/y": [_ruling(reason, state)]}, {"or/x/y": _Layer(*zones)})


# --- which reasons are even in scope ---------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        "a district this layer does not encode",
        "two districts this layer does not hold",
        "neither of which is encoded here",
        "no commercial zone is encoded here",
        "the MDR column, which is not encoded here",
    ],
)
def test_a_claim_about_our_files_is_picked_up(reason) -> None:
    assert _run(reason)


@pytest.mark.parametrize(
    "reason",
    [
        "the code does not state a setback for this yard",
        "a relaxation we hold at its strict end already",
        "the note is about a detached dwelling, which the pod is not",
        "this is a land division procedure and not a dimensional standard",
    ],
)
def test_an_argument_about_the_code_is_left_alone(reason) -> None:
    """These are as durable as the page. Only claims about *us* decay."""
    assert not _run(reason)


def test_only_dismissals_are_asked(monkeypatch) -> None:
    """An 'encoded' ruling names the figure it became; `applied` checks that."""
    assert not _run("a district this layer does not encode", state="encoded")
    assert not _run("a district this layer does not encode", state="unmeasured")


# --- naming a zone ----------------------------------------------------------


def test_a_reason_that_names_a_live_zone_is_contradicted() -> None:
    rows = _run("scoped to SFA, which this layer does not encode", "SFA", "VTH")
    assert rows[0].contradicted == ("SFA",)
    assert rows[0].verdict == "contradicted"


def test_a_reason_that_names_nothing_is_unverifiable_not_clean() -> None:
    """Gresham's Rockwood note is this shape, and it was a real miss."""
    rows = _run("it marks a cell in a district this layer does not encode", "SC", "CMF")
    assert rows[0].contradicted == ()
    assert rows[0].verdict == "unverifiable"


def test_a_zone_the_layer_lost_stays_silent() -> None:
    rows = _run("MR-1 and MR-2, two districts this layer does not hold", "R5", "R7")
    assert rows[0].verdict == "unverifiable"


# --- the two ways a zone code lies ------------------------------------------


def test_a_longer_zone_code_is_not_the_zone_it_starts_with() -> None:
    assert _named("note 1 gives NC-SW the standards", ("NC",)) == ()
    assert _named("in R-50 the minimum is larger", ("R-5",)) == ()


def test_a_parenthesised_qualifier_names_a_different_column() -> None:
    """Troutdale prints "MDR (TC)" for Town Center, which is not our MDR.

    Four reasons said so correctly and were being called contradicted for it.
    """
    assert _named("attaches to the MDR (TC) column", ("MDR",)) == ()
    assert _named("attaches to the MDR column", ("MDR",)) == ("MDR",)


def test_a_one_letter_zone_is_never_matched() -> None:
    """Wilsonville really has zones called R and V."""
    assert _named("a relaxation this layer does not encode", ("R", "V")) == ()


# --- the report -------------------------------------------------------------


def test_the_report_leads_with_the_ones_a_person_can_act_on() -> None:
    text = render(
        [
            Stale("or/x/y", "d#L1", "not encoded here", ("SFA",)),
            Stale("or/x/y", "d#L2", "this layer does not encode it", ()),
        ]
    )
    assert "contradicted by the layer as it stands: 1" in text
    assert "naming nothing this can re-ask:         1" in text
    assert "d#L1" in text
    assert "d#L2" not in text


# --- against the real corpus, without pinning a number ----------------------


def test_every_zone_this_reports_really_is_in_that_layer() -> None:
    """The one claim the check makes about the corpus, checked both ways.

    No count is asserted: the intended end state of this ledger is zero, and a
    pinned number would fail on the day the last one is fixed.
    """
    from flats.rules.loader import load_rules

    layers = load_rules(strict=False)
    for row in audit():
        assert row.contradicted or row.verdict == "unverifiable"
        for zone in row.contradicted:
            assert zone in layers[row.layer].zones, f"{row.quote} named {zone}"


def test_the_check_reaches_the_whole_register() -> None:
    rows = audit()
    assert rows, "no dismissal reads as a claim about our own files -- suspicious"
    assert len({r.layer for r in rows}) > 1
