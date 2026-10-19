"""CLI dispatch for flag synchronization, checks, questions, and asks."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import flats_flags


class _Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["sync", "--help"], ["--run"]),
        (["check", "--help"], ["check"]),
        (["ask", "--help"], ["--code", "--key", "--question", "--by"]),
        (["questions", "--help"], ["questions"]),
    ],
)
async def test_subcommand_help_exposes_expected_arguments(args, expected, capsys):
    with pytest.raises(SystemExit) as exited:
        await flats_flags.main(args)

    assert exited.value.code == 0
    output = capsys.readouterr().out
    assert all(option in output for option in expected)


async def test_ask_requires_by_before_opening_a_database(capsys):
    with pytest.raises(SystemExit) as exited:
        await flats_flags.main(["ask", "--code", "CODE", "--key", "key", "--question", "Question?"])

    assert exited.value.code == 2
    assert "--by" in capsys.readouterr().err


async def test_sync_dispatches_and_commits(monkeypatch, capsys):
    session = _Session()
    seen = []

    async def _sync(got_session, run_id):
        seen.append((got_session, run_id))
        return SimpleNamespace(skipped="", run_id=64, opened=2, updated=3, cleared=4)

    monkeypatch.setattr(flats_flags.flats_flags, "sync_instances", _sync)

    assert await flats_flags.run(session, SimpleNamespace(command="sync", run=64)) == 0
    assert seen == [(session, 64)]
    assert session.commits == 1
    assert "run 64: 2 opened, 3 updated, 4 cleared" in capsys.readouterr().out


async def test_check_dispatches_and_returns_failure_status(monkeypatch, capsys):
    session = _Session()

    async def _check(_session):
        return SimpleNamespace(run_id=64, ok=False, report={"rows": 3, "moved": 1})

    monkeypatch.setattr(flats_flags.flats_flags, "nightly_check", _check)

    assert await flats_flags.run(session, SimpleNamespace(command="check")) == 1
    assert session.commits == 1
    output = capsys.readouterr().out
    assert "run 64: needs a look -- 3 rows" in output
    assert "moved: 1" in output


async def test_ask_dispatches_with_actor_and_commits(monkeypatch, capsys):
    session = _Session()
    seen = {}

    async def _ask(got_session, **kwargs):
        seen.update(session=got_session, **kwargs)
        return SimpleNamespace(id=12)

    monkeypatch.setattr(flats_flags.flats_flags, "ask", _ask)

    assert await flats_flags.run(
        session,
        SimpleNamespace(
            command="ask",
            code="FACT-CORNER-LOT",
            key="or/multnomah/portland|corner_lot",
            question="Does this qualify?",
            by="test actor",
        ),
    ) == 0
    assert seen["by"] == "test actor"
    assert session.commits == 1
    assert "question 12 waiting" in capsys.readouterr().out


async def test_questions_prints_waiting_and_answered_items(monkeypatch, capsys):
    session = _Session()
    calls = []
    waiting = SimpleNamespace(
        id=12,
        code="FACT-CORNER-LOT",
        key="or/multnomah/portland|corner_lot",
        question="Does this qualify?",
        answer=None,
        answered_by=None,
    )
    answered_item = SimpleNamespace(
        id=13,
        code="FACT-CORNER-LOT",
        key="or/multnomah/portland|corner_lot",
        question="Which rule applies?",
        answer="The adopted standard.",
        answered_by="reviewer",
    )

    async def _questions(_session, *, answered):
        calls.append(answered)
        row = waiting if not answered else answered_item
        return [{"row": row, "lots": {"R5": 2}}]

    monkeypatch.setattr(flats_flags.flats_flags, "questions", _questions)

    assert await flats_flags.run(session, SimpleNamespace(command="questions")) == 0
    assert calls == [False, True]
    output = capsys.readouterr().out
    assert "Waiting (1)" in output
    assert "Answered (1)" in output
    assert "The adopted standard." in output
    assert session.commits == 0
