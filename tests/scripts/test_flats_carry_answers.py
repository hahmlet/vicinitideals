"""Carrying page-check answers and pending signatures onto a re-cut's moved quotes.

``carry`` appends a copy on the new fingerprint for every row on an old one;
the old rows stay. A reply is pointed at the copy of the row it answered, and
a signature already exported is not the inbox's to carry.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import FlatsPageCheck, FlatsRuleSignature
from scripts import flats_carry_answers as carry_answers

pytestmark = pytest.mark.asyncio

OLD, NEW = "a" * 64, "b" * 64
OLD_QUOTE = "or/test/town/40/40.300.txt#L12-L13"
NEW_QUOTE = "or/test/town/40/40.300.txt#L9"
MOVES = [{
    "layer": "or/test/town", "zone": "R-1", "field": "max_height_ft", "when_key": "",
    "old_fingerprint": OLD, "new_fingerprint": NEW, "old_quote": OLD_QUOTE, "new_quote": NEW_QUOTE,
}]
WHEN = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def _check(answer: str, *, question: str = "value", quote: str = OLD_QUOTE, fp: str = OLD) -> FlatsPageCheck:
    return FlatsPageCheck(
        layer="or/test/town", zone="R-1", field="max_height_ft", when_key="", value=35,
        fingerprint=fp, question=question, answer=answer, says="", note="", quote=quote,
        page=12, placed="table", book_sha256="c" * 64, reviewer="first reviewer", decided_at=WHEN,
    )


def _signature(*, exported: bool = False) -> FlatsRuleSignature:
    return FlatsRuleSignature(
        layer="or/test/town", zone="R-1", field="max_height_ft", when_key="", value=35,
        cite="TDC 40.300", quote=OLD_QUOTE, verdict="agree", note="", reviewer="first reviewer",
        decided_at=WHEN, fingerprint=OLD, exported_at=WHEN if exported else None,
    )


class _Keep:
    """An async-session stand-in whose ``async with`` does not close the test session."""

    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *exc):
        return False


async def test_each_answer_on_a_moved_quote_is_copied_onto_the_new_one(session: AsyncSession):
    answered = _check("matches")
    other = _check("matches", fp="d" * 64)
    session.add_all([answered, other])
    await session.commit()

    checks, signatures = await carry_answers.carry(session, MOVES)

    assert signatures == []
    assert len(checks) == 1
    copy = checks[0]
    assert (copy.fingerprint, copy.quote) == (NEW, NEW_QUOTE)
    assert (copy.answer, copy.reviewer, copy.decided_at, copy.page) == ("matches", "first reviewer", WHEN, 12)
    rows = list((await session.execute(select(FlatsPageCheck).order_by(FlatsPageCheck.id))).scalars())
    assert [r.fingerprint for r in rows] == [OLD, "d" * 64, NEW]  # append-only


async def test_a_reply_points_at_the_copy_of_the_row_it_answered(session: AsyncSession):
    problem = _check("differs")
    session.add(problem)
    await session.flush()
    session.add(_check("replied", question=f"reply:{problem.id}"))
    await session.commit()

    checks, _ = await carry_answers.carry(session, MOVES)

    problem_copy, reply_copy = checks
    assert reply_copy.question == f"reply:{problem_copy.id}"


async def test_a_row_shown_under_another_quote_is_not_carried(session: AsyncSession):
    session.add(_check("matches", quote="or/test/town/40/40.300.txt#L1"))
    await session.commit()
    assert await carry_answers.carry(session, MOVES) == ([], [])


async def test_only_pending_signatures_are_carried(session: AsyncSession):
    session.add_all([_signature(), _signature(exported=True)])
    await session.commit()

    _, signatures = await carry_answers.carry(session, MOVES)

    assert len(signatures) == 1
    assert (signatures[0].fingerprint, signatures[0].quote, signatures[0].exported_at) == (NEW, NEW_QUOTE, None)


async def test_a_dry_run_writes_nothing(session: AsyncSession, monkeypatch, tmp_path):
    session.add(_check("matches"))
    await session.commit()
    moves = tmp_path / "moves.json"
    moves.write_text(json.dumps(MOVES), encoding="utf-8")
    monkeypatch.setattr(carry_answers, "AsyncSessionLocal", lambda: _Keep(session))
    monkeypatch.setattr("sys.argv", ["flats_carry_answers.py", str(moves)])

    await carry_answers.main()

    rows = list((await session.execute(select(FlatsPageCheck))).scalars())
    assert [r.fingerprint for r in rows] == [OLD]
