"""Moving an approval from the Unknowns page into flags.yaml / colour.yaml.

The order is the thing: nothing is stamped until the file is on disk and has
been read back, only the latest decision per kind is written, and a decision
the file refuses stays in the queue. Run against copies of the real files.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flats import RULES_SUBJECT, FlatsFlagDecision
from flats.score import flags as fp
from scripts import flats_drain_flag_decisions as dr

pytestmark = pytest.mark.asyncio

T0 = datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)


@pytest.fixture
def files(tmp_path):
    reg = tmp_path / "flags.yaml"
    col = tmp_path / "colour.yaml"
    shutil.copy(fp.REGISTRY_PATH, reg)
    shutil.copy(fp.COLOUR_PATH, col)
    return reg, col


def _code() -> str:
    return next(iter(fp.load_registry())).code


def _row(subject: str, values: dict, *, at: datetime = T0) -> FlatsFlagDecision:
    return FlatsFlagDecision(
        subject=subject, values=values, note="", decided_by="Stephen Ketch", decided_at=at
    )


async def _drain(session, files, *, write=True):
    reg, col = files
    return await dr.drain(session, write=write, registry_path=reg, colour_path=col)


async def _rows(session) -> list[FlatsFlagDecision]:
    return list(
        (await session.execute(select(FlatsFlagDecision).order_by(FlatsFlagDecision.id))).scalars()
    )


async def test_an_approval_lands_in_the_file_and_the_row_is_stamped(
    session: AsyncSession, files
):
    code = _code()
    session.add(_row(code, {"severity": 8, "priority": "now"}))
    await session.commit()

    await _drain(session, files)

    got = fp.load_registry(files[0])[code]
    assert got.severity == 8
    assert got.priority.value == "now"
    assert got.status is fp.TypeStatus.approved
    assert got.approved_by == "Stephen Ketch"
    assert got.approved_on == T0.date()
    assert all(r.exported_at is not None for r in await _rows(session))
    # The colour file was not part of this batch and is untouched.
    assert files[1].read_text(encoding="utf-8") == fp.COLOUR_PATH.read_text(encoding="utf-8")


async def test_a_dry_run_writes_and_stamps_nothing(session: AsyncSession, files):
    session.add(_row(_code(), {"severity": 8}))
    await session.commit()

    await _drain(session, files, write=False)

    assert files[0].read_text(encoding="utf-8") == fp.REGISTRY_PATH.read_text(encoding="utf-8")
    assert all(r.exported_at is None for r in await _rows(session))


async def test_only_the_latest_decision_is_written_and_the_earlier_is_closed(
    session: AsyncSession, files
):
    code = _code()
    session.add(_row(code, {"severity": 9}, at=T0))
    session.add(_row(code, {"severity": 4}, at=T0 + timedelta(minutes=5)))
    await session.commit()

    await _drain(session, files)

    assert fp.load_registry(files[0])[code].severity == 4
    assert all(r.exported_at is not None for r in await _rows(session))


async def test_a_refused_decision_stays_in_the_queue(session: AsyncSession, files):
    code = _code()
    session.add(_row("NO-SUCH-KIND", {"severity": 5}))
    session.add(_row(code, {"severity": 6}))
    await session.commit()

    await _drain(session, files)

    by_subject = {r.subject: r for r in await _rows(session)}
    assert by_subject["NO-SUCH-KIND"].exported_at is None
    assert by_subject[code].exported_at is not None
    assert fp.load_registry(files[0])[code].severity == 6


async def test_the_colour_rule_lands_in_its_own_file(session: AsyncSession, files):
    session.add(
        _row(RULES_SUBJECT, {"yellow_at_severity": 4, "risk_bands": {"possible": 0.35}})
    )
    await session.commit()

    await _drain(session, files)

    got = fp.load_rules(files[1])
    assert got.yellow_at_severity == 4
    assert {getattr(k, "value", k): v for k, v in got.risk_bands.items()}["possible"] == 0.35
    assert got.status is fp.TypeStatus.approved
    assert files[0].read_text(encoding="utf-8") == fp.REGISTRY_PATH.read_text(encoding="utf-8")


async def test_nothing_is_stamped_when_the_write_does_not_land(
    session: AsyncSession, files, monkeypatch
):
    session.add(_row(_code(), {"severity": 8}))
    await session.commit()

    def _lost(path, text):
        raise RuntimeError("disk full")

    monkeypatch.setattr(dr, "_land", _lost)
    with pytest.raises(RuntimeError):
        await _drain(session, files)

    await session.rollback()
    assert all(r.exported_at is None for r in await _rows(session))
