"""Answering page-check problems: one append-only ``replied`` row per problem.

``replies`` builds the rows; ``main`` is what writes them, and only with
``--write``. A reply never edits or deletes the row it answers.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_flats_check as check
from app.models.flats import FlatsPageCheck
from scripts import flats_page_check_reply as reply

pytestmark = pytest.mark.asyncio


def _row(answer: str, field: str = "max_height_ft", question: str = "value") -> FlatsPageCheck:
    return FlatsPageCheck(
        layer="test-layer",
        zone="TEST-1",
        field=field,
        when_key="",
        value=35,
        fingerprint="f" * 64,
        question=question,
        answer=answer,
        says="",
        note="",
        quote="a quoted line",
        page=12,
        placed="table",
        book_sha256="b" * 64,
        reviewer="first reviewer",
    )


async def _all(session) -> list[FlatsPageCheck]:
    return list((await session.execute(select(FlatsPageCheck).order_by(FlatsPageCheck.id))).scalars())


async def _seed(session: AsyncSession, *rows: FlatsPageCheck) -> list[int]:
    session.add_all(rows)
    await session.commit()
    return [r.id for r in rows]


class _Keep:
    """An async-session stand-in whose ``async with`` does not close the test session."""

    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *exc):
        return False


def _run_main(monkeypatch, session, tmp_path, words, *extra):
    f = tmp_path / "replies.json"
    f.write_text(json.dumps({str(k): v for k, v in words.items()}), encoding="utf-8")
    monkeypatch.setattr(reply, "AsyncSessionLocal", lambda: _Keep(session))
    monkeypatch.setattr("sys.argv", ["flats_page_check_reply.py", "--file", str(f), *extra])
    return reply.main()


async def test_one_replied_row_per_problem(session: AsyncSession):
    problems = sorted(check.PROBLEMS)
    ids = await _seed(session, *(_row(a, field=f"f_{a}") for a in problems))

    rows = await reply.replies(session, {i: f"  traced {i}  " for i in ids}, "triage")

    assert len(rows) == len(problems)
    for target_id, r in zip(ids, rows, strict=True):
        assert r.answer == check.REPLIED
        assert r.question == f"reply:{target_id}"
        assert r.note == f"traced {target_id}"
        assert r.reviewer == "triage"


async def test_a_non_problem_or_unknown_id_is_refused(session: AsyncSession):
    ok, fine = await _seed(session, _row("differs"), _row("matches"))

    with pytest.raises(SystemExit):
        await reply.replies(session, {fine: "no"}, "triage")
    with pytest.raises(SystemExit):
        await reply.replies(session, {ok + fine + 1000: "no"}, "triage")
    # One bad id refuses the whole batch.
    with pytest.raises(SystemExit):
        await reply.replies(session, {ok: "yes", fine: "no"}, "triage")


async def test_a_dry_run_writes_nothing(session: AsyncSession, monkeypatch, tmp_path):
    (target,) = await _seed(session, _row("differs"))

    await _run_main(monkeypatch, session, tmp_path, {target: "explained"})

    assert [r.answer for r in await _all(session)] == ["differs"]


async def test_a_second_reply_is_appended_and_the_first_stays(
    session: AsyncSession, monkeypatch, tmp_path
):
    (target,) = await _seed(session, _row("differs"))

    await _run_main(monkeypatch, session, tmp_path, {target: "first"}, "--write")
    await _run_main(monkeypatch, session, tmp_path, {target: "second"}, "--write")

    rows = await _all(session)
    assert [r.answer for r in rows] == ["differs", check.REPLIED, check.REPLIED]
    assert [r.note for r in rows[1:]] == ["first", "second"]
    assert rows[0].id == target
    assert all(r.question == f"reply:{target}" for r in rows[1:])
