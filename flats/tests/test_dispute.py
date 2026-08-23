"""A rejection that stops applying by itself when the number is fixed.

The failure this exists to prevent is the mirror of the one verification
prevents. There, a stale `verified` certifies a number nobody read. Here, a
stale rejection goes on marking a value as doubtful long after somebody
answered the doubt -- and a queue full of complaints that were already dealt
with is one nobody reads.

Both are solved the same way: the record is a signature over the value, its
citation and its quote. Change any of them and the record stops matching.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from flats.encode.dispute import (
    FIELD_GONE,
    VALUE_CHANGED,
    Dispute,
    DisputeError,
    DisputeLog,
    apply_disputes,
)
from flats.encode.verify import (
    Verification,
    VerificationLog,
    apply_verifications,
    fingerprint,
)
from flats.rules.model import Layer, Provenance, Status, Value, Zone

pytestmark = pytest.mark.unit

LAYER = "or/multnomah/portland"
WHEN = date(2026, 8, 23)
QUOTE = "pdx/33.110.txt#L42-L48"


def prov(cite: str = "PCC 33.110.220", quote: str | None = QUOTE) -> Provenance:
    return Provenance(
        cite=cite,
        url="https://www.portland.gov/code/33/100s/110",
        retrieved=WHEN,
        quote=quote,
    )


def value(name: str, val: object, *, cite: str = "PCC 33.110.220", quote: str = QUOTE) -> Value:
    return Value(name=name, value=val, prov=prov(cite, quote))


def layers(**values: Value) -> dict[str, Layer]:
    return {
        LAYER: Layer(
            layer=LAYER,
            kind="city",
            label="Portland",
            zones={"R5": Zone(zone="R5", values=values)},
        )
    }


def r5(out: dict[str, Layer], field: str = "setback_front_ft") -> Value:
    return out[LAYER].zones["R5"].values[field]


def raise_on(field: str, v: Value, *, zone: str = "R5", verdict: str = "rejected") -> Dispute:
    return Dispute(
        layer=LAYER,
        zone=zone,
        field=field,
        fingerprint=fingerprint(
            LAYER, zone, field, v.value, cite=v.prov.cite, quote=v.prov.quote
        ),
        reviewer="sjk",
        raised=WHEN,
        verdict=verdict,
        note="the table row is the corner-lot column, not the interior one",
    )


# --- what a dispute does to a value -----------------------------------


def test_a_rejected_value_stops_being_trusted() -> None:
    v = value("setback_front_ft", 10)
    out, answered = apply_disputes(layers(setback_front_ft=v), DisputeLog([raise_on("setback_front_ft", v)]))

    assert r5(out).status is Status.disputed
    assert not r5(out).status.trusted
    assert not answered


def test_a_dispute_outranks_a_signature() -> None:
    """Somebody signed it, somebody else read it and disagreed.

    The disagreement wins until it is settled. A screen that kept trusting the
    number while a reviewer's rejection sat in a queue would be reporting a
    confidence nobody currently holds.
    """
    v = value("setback_front_ft", 10)
    signed = VerificationLog(
        [
            Verification(
                layer=LAYER,
                zone="R5",
                field="setback_front_ft",
                fingerprint=fingerprint(
                    LAYER, "R5", "setback_front_ft", v.value, cite=v.prov.cite, quote=v.prov.quote
                ),
                reviewer="someone-else",
                reviewed=WHEN,
            )
        ]
    )

    promoted, _ = apply_verifications(layers(setback_front_ft=v), signed)
    assert r5(promoted).status is Status.verified

    out, _ = apply_disputes(promoted, DisputeLog([raise_on("setback_front_ft", v)]))
    assert r5(out).status is Status.disputed


def test_the_confirmer_is_not_overwritten_by_the_doubter() -> None:
    """``reviewer`` answers "who confirmed this". A rejection must not put a
    name there, or a reader looking for a confirmation finds a complaint
    wearing its clothes."""
    v = value("setback_front_ft", 10).model_copy(
        update={"status": Status.verified, "reviewer": "someone-else", "reviewed": WHEN}
    )
    out, _ = apply_disputes(layers(setback_front_ft=v), DisputeLog([raise_on("setback_front_ft", v)]))

    assert r5(out).status is Status.disputed
    assert r5(out).reviewer == "someone-else"


def test_unclear_disqualifies_as_firmly_as_rejected() -> None:
    """"The page does not answer the question" is a finding about the
    encoding, not indecision, and a number whose source does not state it is
    not one this screen may use."""
    v = value("setback_front_ft", 10)
    out, _ = apply_disputes(
        layers(setback_front_ft=v),
        DisputeLog([raise_on("setback_front_ft", v, verdict="unclear")]),
    )

    assert r5(out).status is Status.disputed


def test_a_dispute_on_another_value_leaves_this_one_alone() -> None:
    v = value("setback_front_ft", 10)
    other = value("setback_rear_ft", 20)
    out, answered = apply_disputes(
        layers(setback_front_ft=v, setback_rear_ft=other),
        DisputeLog([raise_on("setback_rear_ft", other)]),
    )

    assert r5(out, "setback_front_ft").status is Status.draft
    assert r5(out, "setback_rear_ft").status is Status.disputed
    assert not answered


# --- lifting, which nobody has to remember to do ----------------------


@pytest.mark.parametrize(
    "fixed",
    [
        pytest.param(value("setback_front_ft", 15), id="the number was changed"),
        pytest.param(value("setback_front_ft", 10, cite="PCC 33.120.220"), id="recited"),
        pytest.param(value("setback_front_ft", 10, quote="pdx/33.110.txt#L60-L64"), id="requoted"),
    ],
)
def test_answering_a_dispute_lifts_it_without_anybody_withdrawing_it(fixed: Value) -> None:
    """The property the whole design turns on.

    Somebody rejects a number. An encoder fixes it. Nothing runs a sweep, and
    nobody has to remember the rejection existed -- the signature stops
    matching what is written and the demotion stops applying on its own.
    """
    stood = value("setback_front_ft", 10)
    out, answered = apply_disputes(
        layers(setback_front_ft=fixed), DisputeLog([raise_on("setback_front_ft", stood)])
    )

    assert r5(out).status is not Status.disputed
    assert [a.reason for a in answered] == [VALUE_CHANGED]
    # And the complaint travels with it, because whether the edit actually
    # addressed it is a question for a person.
    assert "corner-lot" in answered[0].note


def test_a_dispute_on_a_field_that_is_gone_says_so() -> None:
    stood = value("setback_front_ft", 10)
    out, answered = apply_disputes(
        layers(setback_rear_ft=value("setback_rear_ft", 20)),
        DisputeLog([raise_on("setback_front_ft", stood)]),
    )

    assert [a.reason for a in answered] == [FIELD_GONE]
    assert answered[0].label == "setback_front_ft"


def test_a_withdrawal_is_appended_not_edited() -> None:
    """The argument stays on the record. That a number was once doubted is
    worth as much to the next reader as the doubt being lifted."""
    v = value("setback_front_ft", 10)
    raised = raise_on("setback_front_ft", v)
    log = DisputeLog([raised, replace(raised, withdrawn=True)])

    assert len(log) == 2, "both entries survive"
    assert not log.active()
    assert log.current(), "and the withdrawal is still visible"

    out, answered = apply_disputes(layers(setback_front_ft=v), log)
    assert r5(out).status is Status.draft
    assert not answered, "a withdrawn dispute is not an answered one"


# --- the log ----------------------------------------------------------


def test_the_log_round_trips(tmp_path: Path) -> None:
    v = value("setback_front_ft", 10)
    path = tmp_path / "disputes.jsonl"
    DisputeLog().append(raise_on("setback_front_ft", v), path=path)

    back = DisputeLog.load(path)

    assert len(back) == 1
    assert back.entries[0] == raise_on("setback_front_ft", v)


def test_no_log_is_a_state_not_an_error(tmp_path: Path) -> None:
    assert len(DisputeLog.load(tmp_path / "nothing-here.jsonl")) == 0


def test_a_verdict_outside_the_vocabulary_is_refused() -> None:
    with pytest.raises(DisputeError, match="not one of"):
        Dispute.from_dict(
            {
                "layer": LAYER,
                "zone": "R5",
                "field": "setback_front_ft",
                "fingerprint": "x",
                "reviewer": "sjk",
                "raised": WHEN.isoformat(),
                "verdict": "meh",
            }
        )


def test_a_malformed_entry_names_the_line(tmp_path: Path) -> None:
    path = tmp_path / "disputes.jsonl"
    path.write_text(json.dumps({"layer": LAYER}) + "\n", encoding="utf-8")

    with pytest.raises(DisputeError, match=r":1:"):
        DisputeLog.load(path)


# --- and it may not be typed into a rule file -------------------------


def test_a_file_may_not_declare_itself_disputed(tmp_path: Path) -> None:
    """Same reason a file may not declare itself verified. Trust and the
    absence of it are both signatures over a specific value, and a status
    typed into YAML outlives an edit to the number underneath it."""
    from flats.rules.loader import load_layer

    root = tmp_path / "jurisdictions"
    where = root / "or" / "multnomah"
    where.mkdir(parents=True)
    (where / "portland.yaml").write_text(
        "\n".join(
            [
                "kind: city",
                "label: Portland",
                "zones:",
                "  R5:",
                "    setback_front_ft:",
                "      value: 10",
                "      status: disputed",
                "      cite: PCC 33.110.220",
                "      url: https://www.portland.gov/code",
                "      retrieved: '2026-08-23'",
                "      quote: or/multnomah/portland/33.110.txt#L42-L48",
            ]
        ),
        encoding="utf-8",
    )

    problems: list[str] = []
    load_layer(where / "portland.yaml", root, problems)

    assert any("may not declare status" in p for p in problems), problems
