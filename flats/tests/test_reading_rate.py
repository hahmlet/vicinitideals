"""The published blind-re-read rates.

A rate is a defence's denominator, and a wrong one is worse than none: it
argues *for* the corpus using a number nobody checked. These tests pin the
three ways this particular figure could be flattering -- counting cards nobody
answered as agreement, summing two different questions into one rate, and
counting the dismissal run's raw disagreements instead of the corner that can
actually buy a false GREEN.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from flats.encode.reading_rate import (
    READINGS,
    SPECS,
    Reading,
    readings,
    render,
)

pytestmark = pytest.mark.unit


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# --- the sheets exist ------------------------------------------------


def test_every_declared_run_has_its_answer_sheet() -> None:
    """A spec naming a file that is not there reports nothing and says
    nothing, so the run silently leaves the published rate. Renaming a CSV
    must break this, not quietly shrink the denominator."""
    missing = [s.stem for s in SPECS if not (READINGS / f"{s.stem}.csv").exists()]
    assert missing == []


def test_a_sheet_nobody_stored_is_skipped_not_counted_as_zero(tmp_path: Path) -> None:
    """The same distinction `read_coverage` draws between None and empty: a
    run that was never stored did not find nothing."""
    assert readings(tmp_path) == []


# --- the three ways it could flatter ---------------------------------


def test_a_card_nobody_answered_is_not_a_card_that_agreed() -> None:
    """`unread` and `unscored` leave the denominator.

    1,902 rows were dealt in the number re-read; 54 came back without an
    answer. Counting those as agreement would move the reported accuracy in
    the direction that flatters it, on cards nobody read.
    """
    run = next(r for r in readings() if r.stem == "second_reading_2026_09_07")
    dealt = sum(1 for _ in csv.DictReader((READINGS / f"{run.stem}.csv").open(encoding="utf-8")))

    assert dealt == 1902
    assert run.read == 1848, "54 unanswered cards must leave the denominator"
    assert run.flagged == 3


def test_the_dismissal_run_counts_the_corner_that_can_buy_a_false_green() -> None:
    """139 rows disagree; 71 are alarming; the published figure is 71.

    Waving away a *relaxation* costs lots and never correctness -- the trade
    this project makes everywhere. Only a note the reader says reaches us AND
    makes a standard stricter can call a lot GREEN when it is not, and
    `flats.encode.waved` already names exactly that corner `alarming`.
    Publishing 139 would nearly double the claim using rows that cannot
    produce the error the rate is about.
    """
    with (READINGS / "dismissal_reading_2026_09_07.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    disagree = sum(1 for r in rows if r["verdict"] == "disagree")
    alarming = sum(1 for r in rows if r["alarming"] == "True")

    run = next(r for r in readings() if r.stem == "dismissal_reading_2026_09_07")

    assert disagree == 139 and alarming == 71, "the two counts must stay distinct"
    assert run.flagged == alarming
    assert run.flagged != disagree


def test_a_flag_is_not_a_confirmed_error() -> None:
    """The dismissal run flags 71 and adjudication confirmed 3. Both print,
    and the confirmed count is attributed to the module that holds it."""
    run = next(r for r in readings() if r.stem == "dismissal_reading_2026_09_07")

    assert run.confirmed == (3, "flats.encode.stale")
    assert run.flagged > run.confirmed[0], "a ceiling, not the finding"

    out = "\n".join(render(readings()))
    assert "3 confirmed real (flats.encode.stale)" in out
    assert "not a confirmed error" in out


def test_accuracy_and_completeness_are_never_one_number() -> None:
    """They have different populations. A blended rate divides errors in our
    own encodings by a denominator that is mostly lines of somebody else's
    code, and means nothing."""
    runs = readings()
    kinds = {r.asks for r in runs}

    assert kinds == {"accuracy", "completeness"}
    out = render(runs)
    body = "\n".join(out)
    assert "ACCURACY" in body and "COMPLETENESS" in body

    # No line may carry a total over both groups.
    total_read = sum(r.read for r in runs)
    assert f"{total_read:,} read" not in body


# --- the arithmetic --------------------------------------------------


def test_the_rate_is_flagged_over_read() -> None:
    r = Reading("x_2026_09_07", "accuracy", "s", read=200, flagged=8, confirmed=None)
    assert r.rate == pytest.approx(0.04)
    assert r.date == "2026-09-07"


def test_a_run_that_read_nothing_has_no_rate_rather_than_a_crash() -> None:
    r = Reading("x_2026_09_07", "accuracy", "s", read=0, flagged=0, confirmed=None)
    assert r.rate == 0.0


def test_a_spec_counts_only_rows_its_own_scoring_answered(tmp_path: Path) -> None:
    """End to end over a sheet written here, so the predicate wiring is
    exercised without depending on the committed corpus."""
    _write(
        tmp_path / "second_reading_2026_09_07.csv",
        [
            {"verdict": "agree"},
            {"verdict": "agree_alt"},  # agreement under another spelling
            {"verdict": "disagree"},
            {"verdict": "unread"},  # never answered
            {"verdict": "unscored"},
        ],
    )

    run = next(r for r in readings(tmp_path) if r.stem == "second_reading_2026_09_07")

    assert run.read == 3
    assert run.flagged == 1
