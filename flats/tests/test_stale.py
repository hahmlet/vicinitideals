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


class _Value:
    def __init__(self, value) -> None:
        self.value = value


class _Zone:
    def __init__(self, quadplex: bool | None = None) -> None:
        self.values = {} if quadplex is None else {"quadplex_allowed": _Value(quadplex)}


class _Layer:
    def __init__(self, *zones: str) -> None:
        self.zones = {z: _Zone() for z in zones}


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


def _run(
    reason: str,
    *zones: str,
    state: str = "dismissed",
    over: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> list[Stale]:
    layer = _Layer(*zones)
    for zone in forbidden:
        layer.zones[zone] = _Zone(quadplex=False)
    return audit(
        {"or/x/y": [_ruling(reason, state)]},
        {"or/x/y": layer},
        {("or/x/y/doc.txt", 1): set(over)},
    )


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
    assert "naming nothing this can re-ask:          1" in text
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


# --- does getting it wrong cost anything? -----------------------------------


def test_a_false_reason_over_permitted_land_is_the_one_that_bites() -> None:
    rows = _run("scoped to SFA, which this layer does not encode", "SFA", over=("SFA",))
    assert rows[0].bites
    assert rows[0].permitting == ("SFA",)


def test_a_false_reason_over_a_prohibited_district_is_a_wrong_sentence_only() -> None:
    """Gresham's CC and MC hold quadplex_allowed False.

    The reason on that note is wrong about the corpus and the answer is still
    right, because the lot is red on use before any footnote is reached.
    """
    rows = _run(
        "in the CC district, which is not encoded here",
        "CC",
        over=("CC",),
        forbidden=("CC",),
    )
    assert rows[0].verdict == "contradicted"
    assert rows[0].permitting == ()
    assert not rows[0].bites


def test_a_note_standing_over_nothing_cannot_bite() -> None:
    rows = _run("scoped to SFA, which this layer does not encode", "SFA")
    assert rows[0].over == ()
    assert not rows[0].bites


def test_a_district_we_have_never_recorded_a_use_for_counts_as_open() -> None:
    """Absent is permitted. Only a recorded False closes a district."""
    rows = _run("the MU zone, not encoded here", "MU", over=("MU",))
    assert rows[0].permitting == ("MU",)


# --- work already done ------------------------------------------------------


def test_a_reason_that_records_its_own_repair_is_not_asked_again() -> None:
    """The first run of this check flagged the one note somebody had fixed.

    Its reason quotes the false claim in order to record killing it, and a
    queue that keeps returning finished work stops being read.
    """
    rows = _run(
        "this used to be dismissed on the grounds that CC and MC were not "
        "encoded here, which stopped being true when both were encoded",
        "CC",
        "MC",
        over=("CC",),
    )
    assert rows[0].verdict == "repaired"
    assert not rows[0].bites


def test_repair_language_is_narrow_enough_to_mean_something() -> None:
    rows = _run("a district this layer does not encode, and was true once", "SFA")
    assert rows[0].verdict != "repaired"


def test_the_report_separates_a_wrong_sentence_from_a_wrong_answer() -> None:
    text = render(
        [
            Stale("or/x/y", "d#L1", "not encoded here", ("SFA",), ("SFA",), ("SFA",)),
            Stale("or/x/y", "d#L2", "not encoded here", ("CC",), ("CC",), ()),
        ]
    )
    assert "COULD STILL BE A WRONG GREEN: 1" in text
    assert "wrong sentence, right answer (no permitted zone behind it): 1" in text


def test_the_corpus_run_carries_scope_for_every_row() -> None:
    """`over` comes from the same value -> note map the whole register uses.

    A row with no scope is not an error -- plenty of notes stand over nothing
    we hold -- but every permitting zone must be one of them.
    """
    for row in audit():
        assert set(row.permitting) <= set(row.over)
