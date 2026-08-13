"""Verification as a signature over a value.

The failure this design exists to prevent: a `verified` flag sitting in a file
next to a number somebody edited afterwards, certifying a value nobody ever
read. A signature cannot do that. Change the number, the citation, or the
quote, and the promotion stops applying on its own — no invalidation step to
remember, and nothing that can be forgotten.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from flats.encode.verify import (
    FIELD_GONE,
    VALUE_CHANGED,
    Verification,
    VerificationError,
    VerificationLog,
    apply_verifications,
    fingerprint,
    sign,
)
from flats.rules.model import Layer, Provenance, Status, Value, Zone

pytestmark = pytest.mark.unit

LAYER = "or/multnomah/portland"
REVIEWED = date(2026, 8, 12)


def prov(cite: str = "PCC 33.110.220", quote: str | None = "pdx/33.110.txt#L42-L48") -> Provenance:
    return Provenance(
        cite=cite,
        url="https://www.portland.gov/code/33/100s/110",
        retrieved=REVIEWED,
        quote=quote,
    )


def value(name: str, val: object, *, cite: str = "PCC 33.110.220", quote=...) -> Value:
    return Value(
        name=name,
        value=val,
        prov=prov(cite, quote if quote is not ... else "pdx/33.110.txt#L42-L48"),
    )


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


def log_for(field: str, v: Value, *, zone: str = "R5", reviewer: str = "sjk") -> VerificationLog:
    return VerificationLog([sign(LAYER, zone, field, v, reviewer=reviewer, reviewed=REVIEWED)])


# --- the signature ----------------------------------------------------


def test_the_same_value_signs_the_same_way() -> None:
    a = fingerprint(LAYER, "R5", "setback_front_ft", 10, cite="PCC 33.110", quote="a.txt#L1")
    b = fingerprint(LAYER, "R5", "setback_front_ft", 10, cite="PCC 33.110", quote="a.txt#L1")

    assert a == b


@pytest.mark.parametrize(
    "changed",
    [
        {"value": 15},
        {"cite": "PCC 33.120.220"},
        {"quote": "a.txt#L60-L64"},
        {"field": "setback_rear_ft"},
        {"zone": "R2.5"},
        {"layer": "or/multnomah/gresham"},
    ],
)
def test_changing_anything_the_reviewer_saw_changes_the_signature(changed: dict) -> None:
    base = dict(
        layer=LAYER, zone="R5", field="setback_front_ft", value=10, cite="PCC 33.110", quote="a.txt#L1"
    )
    original = fingerprint(**base)

    assert fingerprint(**{**base, **changed}) != original


# --- promotion --------------------------------------------------------


def test_a_matching_signature_promotes_the_value() -> None:
    v = value("setback_front_ft", 10)
    out, orphans = apply_verifications(layers(setback_front_ft=v), log_for("setback_front_ft", v))

    assert r5(out).status is Status.verified
    assert r5(out).reviewer == "sjk"
    assert r5(out).reviewed == REVIEWED
    assert orphans == []


def test_an_unsigned_value_stays_draft() -> None:
    out, orphans = apply_verifications(
        layers(setback_front_ft=value("setback_front_ft", 10)), VerificationLog()
    )

    assert r5(out).status is Status.draft
    assert orphans == []


def test_editing_the_number_withdraws_the_verification_by_itself() -> None:
    # The whole design in one test. Somebody signed off on 10 feet; the file
    # now says 15. Nothing ran an invalidation step — the signature simply
    # stops matching, and the field is draft again.
    signed = log_for("setback_front_ft", value("setback_front_ft", 10))

    out, orphans = apply_verifications(
        layers(setback_front_ft=value("setback_front_ft", 15)), signed
    )

    assert r5(out).status is Status.draft
    assert [(o.field, o.reason) for o in orphans] == [("setback_front_ft", VALUE_CHANGED)]


def test_repointing_the_quote_withdraws_it_too() -> None:
    # Same number, different evidence. What was reviewed is no longer what is
    # cited, so the review no longer applies.
    signed = log_for("setback_front_ft", value("setback_front_ft", 10))

    out, orphans = apply_verifications(
        layers(setback_front_ft=value("setback_front_ft", 10, quote="pdx/33.110.txt#L90")), signed
    )

    assert r5(out).status is Status.draft
    assert orphans[0].reason == VALUE_CHANGED


def test_a_verification_for_a_field_nobody_kept_is_reported() -> None:
    signed = log_for("setback_front_ft", value("setback_front_ft", 10))

    _, orphans = apply_verifications(layers(setback_rear_ft=value("setback_rear_ft", 5)), signed)

    assert [(o.field, o.reason) for o in orphans] == [("setback_front_ft", FIELD_GONE)]


def test_a_verification_for_a_zone_that_vanished_is_reported() -> None:
    signed = log_for("setback_front_ft", value("setback_front_ft", 10), zone="RM1")

    _, orphans = apply_verifications(
        layers(setback_front_ft=value("setback_front_ft", 10)), signed
    )

    assert orphans[0].zone == "RM1"
    assert orphans[0].reason == FIELD_GONE


def test_layer_defaults_can_be_verified() -> None:
    # State preemption lives in defaults, and an unverified preemption is the
    # last thing that should be trusted quietly.
    v = Value(name="parking_min_per_unit", value=1.0, prov=prov(), preempts=True)
    state = {
        "or": Layer(layer="or", kind="state", label="Oregon", defaults={"parking_min_per_unit": v})
    }
    signed = VerificationLog(
        [sign("or", "defaults", "parking_min_per_unit", v, reviewer="sjk", reviewed=REVIEWED)]
    )

    out, orphans = apply_verifications(state, signed)

    assert out["or"].defaults["parking_min_per_unit"].status is Status.verified
    assert orphans == []


def test_the_input_layers_are_never_mutated() -> None:
    v = value("setback_front_ft", 10)
    original = layers(setback_front_ft=v)

    apply_verifications(original, log_for("setback_front_ft", v))

    assert r5(original).status is Status.draft


# --- the log ----------------------------------------------------------


def test_a_later_entry_supersedes_an_earlier_one() -> None:
    old = Verification(LAYER, "R5", "setback_front_ft", "aaa", "sjk", date(2026, 1, 1))
    new = Verification(LAYER, "R5", "setback_front_ft", "bbb", "pat", REVIEWED)

    log = VerificationLog([old, new])

    assert log.active()[(LAYER, "R5", "setback_front_ft", ())].reviewer == "pat"
    assert len(log) == 2, "history is kept, not overwritten"


def test_a_withdrawal_stops_applying_without_erasing_the_record() -> None:
    v = value("setback_front_ft", 10)
    entry = sign(LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED)
    log = VerificationLog([entry, replace(entry, revoked=True)])

    out, orphans = apply_verifications(layers(setback_front_ft=v), log)

    assert r5(out).status is Status.draft
    assert orphans == [], "a withdrawn verification is not an orphan; it was withdrawn on purpose"
    assert len(log.current()) == 1


def test_the_log_round_trips_through_disk(tmp_path: Path) -> None:
    path = tmp_path / "verifications.jsonl"
    v = value("setback_front_ft", 10)
    entry = sign(LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED, note="Table 110-4")

    VerificationLog().append(entry, path)
    reloaded = VerificationLog.load(path)

    assert list(reloaded) == [entry]
    assert reloaded.active()[entry.key].note == "Table 110-4"


def test_appending_never_rewrites_what_is_already_there(tmp_path: Path) -> None:
    path = tmp_path / "verifications.jsonl"
    v = value("setback_front_ft", 10)
    log = VerificationLog()
    log.append(sign(LAYER, "R5", "setback_front_ft", v, reviewer="sjk", reviewed=REVIEWED), path)
    log.append(sign(LAYER, "R5", "setback_rear_ft", v, reviewer="pat", reviewed=REVIEWED), path)

    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_no_log_yet_is_a_state_not_an_error(tmp_path: Path) -> None:
    # The correct state for a jurisdiction nobody has reviewed.
    assert len(VerificationLog.load(tmp_path / "nothing.jsonl")) == 0


def test_a_corrupt_line_names_its_line_number(tmp_path: Path) -> None:
    # Hand-appending to the log is expected — a truncated entry has to say
    # which line to look at, not just that something somewhere is wrong.
    path = tmp_path / "verifications.jsonl"
    path.write_text("# header\nnot json\n", encoding="utf-8")

    with pytest.raises(VerificationError, match=":2:"):
        VerificationLog.load(path)


def test_a_line_missing_a_field_also_names_its_line_number(tmp_path: Path) -> None:
    # Valid JSON, wrong shape. Same failure to the person fixing it, so it
    # gets the same line context.
    path = tmp_path / "verifications.jsonl"
    path.write_text('{"layer": "a", "zone": "R5"}\n', encoding="utf-8")

    with pytest.raises(VerificationError, match=r":1:.*malformed"):
        VerificationLog.load(path)


def test_comments_and_blank_lines_are_tolerated(tmp_path: Path) -> None:
    path = tmp_path / "verifications.jsonl"
    entry = sign(LAYER, "R5", "setback_front_ft", value("setback_front_ft", 10), reviewer="sjk", reviewed=REVIEWED)
    path.write_text(f"# Portland R5 pass\n\n{entry.to_json()}\n", encoding="utf-8")

    assert len(VerificationLog.load(path)) == 1
