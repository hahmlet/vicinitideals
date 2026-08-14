"""The reviewer's tool.

What is being tested is mostly what the tool refuses. A verification CLI that
is easy to use carelessly is worse than none — it produces a log full of names
attached to numbers nobody read, which is indistinguishable from real review
and scales silently to every lot in the county.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flats.encode.review import main
from flats.encode.verify import VerificationLog
from flats.provenance.store import ProvenanceStore
from flats.rules.model import Status

pytestmark = pytest.mark.unit

PORTLAND = "or/multnomah/portland"
DOC = "or/multnomah/portland/33.110.txt"
TEXT = (
    "33.110.220 Development Standards\n"
    "The minimum front building setback is 10 feet.\n"
    "The minimum side building setback is 5 feet.\n"
)
CITE = (
    "cite_default:\n"
    '  cite: "PCC 33.110.220, Table 110-4"\n'
    '  url: "https://www.portland.gov/code/33/100s/110"\n'
    "  retrieved: 2026-08-12\n"
    f'  quote: "{DOC}#L2"\n'
)


@pytest.fixture()
def bench(tmp_path: Path) -> dict:
    """A rule file, its evidence, and an empty log — one reviewer's desk."""
    root = tmp_path / "jurisdictions"
    rules = root / f"{PORTLAND}.yaml"
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text(
        "label: Portland\n"
        + CITE
        + "zones:\n  R5:\n    setback_front_ft: 10\n    setback_side_ft: 5\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    ProvenanceStore(docs).save(
        DOC,
        url="https://www.portland.gov/code/33/100s/110",
        text=TEXT,
        retrieved=date(2026, 8, 12),
    )
    return {
        "root": root,
        "docs": docs,
        "log": tmp_path / "verifications.jsonl",
        "rules": rules,
    }


def run(bench: dict, *argv: str) -> int:
    return main(
        [
            "--root",
            str(bench["root"]),
            "--docs",
            str(bench["docs"]),
            "--log",
            str(bench["log"]),
            *argv,
        ]
    )


def log(bench: dict) -> VerificationLog:
    return VerificationLog.load(bench["log"])


# --- reading before signing -------------------------------------------


def test_show_puts_the_number_next_to_the_text_it_claims(bench: dict, capsys) -> None:
    # The entire job, in one screen: 10 feet, and the sentence that says so.
    assert run(bench, "show", PORTLAND, "R5", "setback_front_ft") == 0

    out = capsys.readouterr().out
    assert "value     10" in out
    assert "minimum front building setback is 10 feet" in out


def test_show_reports_a_value_with_no_evidence_stored(bench: dict, capsys) -> None:
    bench["rules"].write_text(
        bench["rules"].read_text(encoding="utf-8").replace(f'  quote: "{DOC}#L2"\n', ""),
        encoding="utf-8",
    )

    assert run(bench, "show", PORTLAND, "R5", "setback_front_ft") == 1
    assert "NO EVIDENCE" in capsys.readouterr().out


def test_the_queue_lists_what_is_waiting(bench: dict, capsys) -> None:
    assert run(bench, "queue") == 0

    out = capsys.readouterr().out
    assert "setback_front_ft" in out and "setback_side_ft" in out
    assert "draft" in out


def test_the_queue_narrows_to_one_zone(bench: dict, capsys) -> None:
    assert run(bench, "queue", "--zone", "RM1") == 0
    assert "nothing pending" in capsys.readouterr().out


# --- signing ----------------------------------------------------------


def test_signing_promotes_the_value_on_the_next_load(bench: dict) -> None:
    from flats.encode.load import load_trusted

    assert run(bench, "sign", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk") == 0

    trusted = load_trusted(
        bench["root"], log=log(bench), store=ProvenanceStore(bench["docs"])
    )
    value = trusted.layers[PORTLAND].zones["R5"].values["setback_front_ft"]
    assert value.status is Status.verified
    assert value.reviewer == "sjk"


def test_a_reviewer_may_sign_a_row_of_a_table_at_once(bench: dict) -> None:
    # One table read, several numbers confirmed — but every field typed out.
    assert (
        run(
            bench,
            "sign",
            PORTLAND,
            "R5",
            "setback_front_ft",
            "setback_side_ft",
            "--reviewer",
            "sjk",
        )
        == 0
    )

    assert len(log(bench)) == 2


def test_signing_refuses_a_value_it_cannot_show_you(bench: dict, capsys) -> None:
    # The rule that matters most. Without stored text there is nothing to
    # compare the number against, so a signature would certify a comparison
    # that never happened.
    bench["rules"].write_text(
        bench["rules"].read_text(encoding="utf-8").replace(DOC, "or/multnomah/portland/99.txt"),
        encoding="utf-8",
    )

    assert run(bench, "sign", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk") == 1
    assert "refusing" in capsys.readouterr().err
    assert not bench["log"].exists(), "a refused batch writes nothing at all"


def test_a_bad_field_in_a_batch_writes_nothing(bench: dict) -> None:
    with pytest.raises(SystemExit):
        run(bench, "sign", PORTLAND, "R5", "setback_front_ft", "max_height_ft", "--reviewer", "sjk")

    assert not bench["log"].exists()


def test_signing_the_same_value_twice_is_a_no_op(bench: dict, capsys) -> None:
    run(bench, "sign", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk")
    capsys.readouterr()

    # Second pass: nothing changed in the file, so there is nothing to re-sign.
    assert run(bench, "sign", PORTLAND, "R5", "setback_front_ft", "--reviewer", "pat") == 0
    assert len(log(bench)) == 1
    assert "already verified" in capsys.readouterr().out


def test_a_reviewer_must_name_themselves(bench: dict) -> None:
    # No default reviewer, ever. An unattributed verification is not one.
    with pytest.raises(SystemExit):
        run(bench, "sign", PORTLAND, "R5", "setback_front_ft")


def test_a_note_survives_into_the_log(bench: dict) -> None:
    run(
        bench,
        "sign",
        PORTLAND,
        "R5",
        "setback_front_ft",
        "--reviewer",
        "sjk",
        "--note",
        "Table 110-4 row 2",
    )

    assert list(log(bench))[0].note == "Table 110-4 row 2"


# --- withdrawal -------------------------------------------------------


def test_revoking_stops_the_promotion_without_erasing_the_record(bench: dict) -> None:
    from flats.encode.load import load_trusted

    run(bench, "sign", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk")

    assert run(bench, "revoke", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk") == 0

    trusted = load_trusted(
        bench["root"], log=log(bench), store=ProvenanceStore(bench["docs"])
    )
    assert trusted.layers[PORTLAND].zones["R5"].values["setback_front_ft"].status is Status.draft
    assert len(log(bench)) == 2, "the withdrawal is an append; the history stays"


def test_revoking_what_was_never_signed_is_an_error(bench: dict, capsys) -> None:
    assert run(bench, "revoke", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk") == 1
    assert "no active verification" in capsys.readouterr().err


# --- status -----------------------------------------------------------


def test_status_reports_nothing_verified_as_a_clean_but_untrusted_state(
    bench: dict, capsys
) -> None:
    assert run(bench, "status") == 0

    out = capsys.readouterr().out
    assert "verified: 0.0%" in out
    assert "draft=2" in out


def test_status_surfaces_evidence_that_was_edited(bench: dict, capsys) -> None:
    run(bench, "sign", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk")
    ProvenanceStore(bench["docs"]).text_path(DOC).write_text(
        TEXT.replace("10 feet", "20 feet"), encoding="utf-8", newline=""
    )
    capsys.readouterr()

    assert run(bench, "status") == 1, "a non-zero exit is what a CI gate reads"

    out = capsys.readouterr().out
    assert "TAMPERED" in out
    assert "STALE" in out


def test_status_names_a_broken_rule_file_instead_of_failing(bench: dict, capsys) -> None:
    bench["rules"].write_text(
        "label: Portland\n" + CITE + "zones:\n  R5:\n    setback_diagonal_ft: 10\n",
        encoding="utf-8",
    )

    assert run(bench, "status") == 1
    assert "unknown rule field" in capsys.readouterr().out


# --- exceptions at the desk -------------------------------------------

#: The same zone, with a footnote on the front setback. `--when` is how a
#: reviewer says which of the two sentences they read.
WITH_VARIANT = (
    "label: Portland\n"
    + CITE
    + "zones:\n"
    "  R5:\n"
    "    setback_front_ft:\n"
    "      value: 10\n"
    "      variants:\n"
    "        - value: 5\n"
    "          when: [affordable]\n"
)


@pytest.fixture()
def footnoted(bench: dict) -> dict:
    bench["rules"].write_text(WITH_VARIANT, encoding="utf-8")
    return bench


def test_show_lists_the_exceptions_hanging_off_a_value(footnoted: dict, capsys) -> None:
    # Reviewing the base without being told the exception exists is how a
    # signature ends up standing for more than the reviewer read.
    assert run(footnoted, "show", PORTLAND, "R5", "setback_front_ft") == 0

    out = capsys.readouterr().out
    assert "exceptions:" in out
    assert "--when affordable" in out


def test_show_can_be_pointed_at_the_exception(footnoted: dict, capsys) -> None:
    assert run(footnoted, "show", PORTLAND, "R5", "setback_front_ft", "--when", "affordable") == 0

    out = capsys.readouterr().out
    assert "setback_front_ft [affordable]" in out
    assert "value     5" in out


def test_signing_the_base_does_not_sign_the_exception(footnoted: dict) -> None:
    assert run(footnoted, "sign", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk") == 0

    entries = list(log(footnoted))
    assert [e.when for e in entries] == [()]


def test_the_exception_signs_on_its_own(footnoted: dict) -> None:
    assert (
        run(
            footnoted, "sign", PORTLAND, "R5", "setback_front_ft",
            "--reviewer", "sjk", "--when", "affordable",
        )
        == 0
    )

    assert [e.when for e in log(footnoted)] == [("affordable",)]


def test_signing_an_exception_nobody_encoded_is_refused(footnoted: dict) -> None:
    with pytest.raises(SystemExit, match="no variant"):
        run(
            footnoted, "sign", PORTLAND, "R5", "setback_front_ft",
            "--reviewer", "sjk", "--when", "corner_lot",
        )


def test_the_queue_lists_a_signed_base_and_its_unsigned_exception(
    footnoted: dict, capsys
) -> None:
    run(footnoted, "sign", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk")
    capsys.readouterr()

    assert run(footnoted, "queue") == 0

    lines = [ln for ln in capsys.readouterr().out.splitlines() if "setback_front_ft" in ln]
    assert len(lines) == 1, "the base is done; the footnote is not"
    assert "[affordable]" in lines[0]


def test_revoking_names_the_exception_it_withdraws(footnoted: dict, capsys) -> None:
    run(
        footnoted, "sign", PORTLAND, "R5", "setback_front_ft",
        "--reviewer", "sjk", "--when", "affordable",
    )
    capsys.readouterr()

    assert (
        run(
            footnoted, "revoke", PORTLAND, "R5", "setback_front_ft",
            "--reviewer", "sjk", "--when", "affordable",
        )
        == 0
    )
    assert "setback_front_ft [affordable]" in capsys.readouterr().out
    assert log(footnoted).active() == {}


def test_revoking_the_base_leaves_the_exception_signed(footnoted: dict) -> None:
    for extra in ([], ["--when", "affordable"]):
        run(footnoted, "sign", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk", *extra)

    run(footnoted, "revoke", PORTLAND, "R5", "setback_front_ft", "--reviewer", "sjk")

    assert [k[3] for k in log(footnoted).active()] == [("affordable",)]


# --- a zone that borrows ----------------------------------------------

#: R-6 states the standards; VSF adopts them and says so.
BORROWS = (
    "label: Portland\n"
    + CITE
    + "zones:\n"
    "  R-6:\n"
    "    setback_front_ft: 10\n"
    "  VSF:\n"
    "    like: R-6\n"
)


@pytest.fixture()
def borrowing(bench: dict) -> dict:
    bench["rules"].write_text(BORROWS, encoding="utf-8")
    return bench


def test_show_reads_the_reference_as_a_rule(borrowing: dict, capsys) -> None:
    assert run(borrowing, "show", PORTLAND, "VSF", "like") == 0

    out = capsys.readouterr().out
    assert "adopts    R-6" in out
    assert "this zone's own text governs" in out
    assert "| The minimum front building setback is 10 feet." in out, "the evidence is shown"


def test_a_borrowed_field_sends_the_reviewer_to_where_it_lives(borrowing: dict) -> None:
    # Not "no such field". The number exists; it is printed in another chapter,
    # and reviewing it here would mean reviewing a copy.
    with pytest.raises(SystemExit, match="comes from R-6"):
        run(borrowing, "show", PORTLAND, "VSF", "setback_front_ft")


def test_the_reference_signs_like_anything_else(borrowing: dict) -> None:
    assert run(borrowing, "sign", PORTLAND, "VSF", "like", "--reviewer", "sjk") == 0

    entries = list(log(borrowing))
    assert [(e.zone, e.field) for e in entries] == [("VSF", "like")]


def test_signing_the_reference_twice_is_a_no_op(borrowing: dict, capsys) -> None:
    run(borrowing, "sign", PORTLAND, "VSF", "like", "--reviewer", "sjk")
    capsys.readouterr()

    assert run(borrowing, "sign", PORTLAND, "VSF", "like", "--reviewer", "sjk") == 0
    assert "nothing to sign" in capsys.readouterr().out
    assert len(log(borrowing)) == 1


def test_an_unread_reference_is_queued(borrowing: dict, capsys) -> None:
    assert run(borrowing, "queue") == 0

    out = capsys.readouterr().out
    assert "VSF like = R-6" in out


def test_a_signed_reference_leaves_the_queue(borrowing: dict, capsys) -> None:
    run(borrowing, "sign", PORTLAND, "VSF", "like", "--reviewer", "sjk")
    capsys.readouterr()

    run(borrowing, "queue")

    assert "VSF like" not in capsys.readouterr().out


def test_a_zone_that_borrows_nothing_has_no_reference_to_show(bench: dict) -> None:
    with pytest.raises(SystemExit, match="adopts no other zone"):
        run(bench, "show", PORTLAND, "R5", "like")


def test_a_reference_has_no_exceptions_to_sign(borrowing: dict) -> None:
    with pytest.raises(SystemExit, match="no exceptions"):
        run(borrowing, "sign", PORTLAND, "VSF", "like", "--reviewer", "sjk", "--when", "affordable")


# --- gaps: why the uncited values are uncited ------------------------


UNCITED = (
    "label: Fairview\n"
    "cite_default:\n"
    '  cite: "FMC 19.100"\n'
    '  url: "https://www.cityoffairview-or.gov/code/19.30"\n'
    "  retrieved: 2026-08-12\n"
    "zones:\n"
    "  LDR:\n"
    "    min_lot_sqft: 7000\n"
    "    quadplex_allowed: true\n"
)


def test_gaps_separates_a_missing_chapter_from_an_unreadable_field(bench: dict, capsys) -> None:
    # Both values are uncited and the ladder calls both `unquoted`. One needs a
    # document nobody has fetched; the other needs a person, because no reader
    # has an opinion about booleans. Sending them to the same command is how a
    # jurisdiction looks 90% cited when it is barely sourced.
    (bench["root"] / "or" / "multnomah" / "fairview.yaml").write_text(UNCITED, encoding="utf-8")

    assert run(bench, "gaps", "--layer", "or/multnomah/fairview", "--verbose") == 0

    out = capsys.readouterr().out
    assert "undeclared" in out and "min_lot_sqft" in out
    assert "uncheckable" in out and "quadplex_allowed" in out


def test_gaps_reports_nothing_for_a_jurisdiction_whose_values_all_cite(bench: dict, capsys) -> None:
    assert run(bench, "gaps", "--layer", PORTLAND) == 0

    assert "0 unquoted value(s)" in capsys.readouterr().out


# --- no signing a restatement ----------------------------------------


RESTATED = (
    "label: West Linn\n"
    "cite_default:\n"
    '  cite: "West Linn CDC 13.070"\n'
    '  url: "https://www.zoneomics.com/code/west-linn-OR/chapter_9"\n'
    "  retrieved: 2026-08-12\n"
    f'  quote: "{DOC}#L2"\n'
    "zones:\n  R-5:\n    setback_front_ft: 10\n"
)


def test_a_citation_to_an_aggregator_cannot_be_signed(bench: dict, capsys) -> None:
    # The quote resolves, so the reviewer would read real text and sign in good
    # faith. What they cannot see from the number is that the text is somebody
    # else's transcription of the ordinance.
    (bench["root"] / "or" / "clackamas").mkdir(parents=True, exist_ok=True)
    (bench["root"] / "or" / "clackamas" / "west-linn.yaml").write_text(RESTATED, encoding="utf-8")

    code = run(
        bench, "sign", "or/clackamas/west-linn", "R-5", "setback_front_ft", "--reviewer", "sjk"
    )

    assert code == 1
    assert "zoneomics.com" in capsys.readouterr().err
    assert not bench["log"].exists()
