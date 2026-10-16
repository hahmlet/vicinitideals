"""Command-line surface and transaction boundaries for flats_promote."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from scripts import flats_promote


class _Engine:
    async def dispose(self) -> None:
        pass


class _Result:
    def scalars(self):
        return self

    def all(self):
        return []


class _Session:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        pass

    async def execute(self, _statement):
        return _Result()

    async def get(self, *_args):
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _db(monkeypatch: pytest.MonkeyPatch) -> _Session:
    session = _Session()
    monkeypatch.setattr(flats_promote, "create_async_engine", lambda *a, **k: _Engine())
    monkeypatch.setattr(flats_promote, "async_sessionmaker", lambda *a, **k: lambda: session)
    return session


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["status", "--help"], ["status"]),
        (["drift", "--help"], ["--from-run", "--to-run", "--dry-run"]),
        (["promote", "--help"], ["--snapshot", "--run", "--by", "--dry-run"]),
        (["rollback", "--help"], ["--by", "--reason", "--dry-run"]),
        (["prune", "--help"], ["--keep", "--dry-run"]),
        (["prune-runs", "--help"], ["--keep", "--dry-run"]),
    ],
)
async def test_subcommand_help_exposes_expected_arguments(args, expected, capsys):
    with pytest.raises(SystemExit) as exited:
        await flats_promote.main(args)

    assert exited.value.code == 0
    output = capsys.readouterr().out
    assert all(option in output for option in expected)


@pytest.mark.parametrize(
    "args",
    [
        ["promote", "--snapshot", "1"],
        ["rollback", "--reason", "because"],
    ],
)
async def test_required_actor_and_reason_fail_through_argparse(args, capsys):
    with pytest.raises(SystemExit) as exited:
        await flats_promote.main(args)

    assert exited.value.code == 2
    assert "required" in capsys.readouterr().err


def _promote_result():
    snapshot = SimpleNamespace(id=5, snapshot_date=date(2026, 1, 2))
    run = SimpleNamespace(id=8)
    return SimpleNamespace(
        snapshot=snapshot,
        run=run,
        previous=None,
        blocks=[],
        by="test actor",
        flagged=0,
    )


def _rollback_result():
    restored = SimpleNamespace(id=2, snapshot_date=date(2026, 1, 1))
    demoted = SimpleNamespace(id=5, snapshot_date=date(2026, 1, 2))
    run = SimpleNamespace(id=8)
    return SimpleNamespace(restored=restored, demoted=demoted, demoted_run=run)


@pytest.mark.parametrize(
    "args",
    [
        ["status"],
        ["drift", "--from-run", "1", "--to-run", "2", "--dry-run"],
        ["promote", "--snapshot", "5", "--by", "test actor", "--dry-run"],
        ["promote", "--run", "8", "--by", "test actor", "--dry-run"],
        ["rollback", "--by", "test actor", "--reason", "test", "--dry-run"],
        ["rollback", "--run", "8", "--by", "test actor", "--reason", "test", "--dry-run"],
        ["prune", "--dry-run"],
        ["prune-runs", "--dry-run"],
    ],
)
async def test_commands_dispatch_and_dry_runs_roll_back_without_committing(
    args, monkeypatch, capsys
):
    session = _db(monkeypatch)

    async def _empty(*_args, **_kwargs):
        return []

    async def _drift(*_args, **_kwargs):
        return {"to_snapshot": 5}

    async def _promote(*_args, **_kwargs):
        return _promote_result()

    async def _promote_run(*_args, **_kwargs):
        return _promote_result()

    async def _rollback(*_args, **_kwargs):
        return _rollback_result()

    async def _rollback_run(*_args, **_kwargs):
        return SimpleNamespace(demoted=SimpleNamespace(id=8), restored=SimpleNamespace(id=7), snapshot=SimpleNamespace(id=5, snapshot_date=date(2026, 1, 1)))

    monkeypatch.setattr(flats_promote, "drift", _drift)
    monkeypatch.setattr(flats_promote, "drift_markdown", lambda _doc: "drift report")
    monkeypatch.setattr(flats_promote, "promote", _promote)
    monkeypatch.setattr(flats_promote, "promote_run", _promote_run)
    monkeypatch.setattr(flats_promote, "rollback", _rollback)
    monkeypatch.setattr(flats_promote, "rollback_run", _rollback_run)
    monkeypatch.setattr(flats_promote, "prune", _empty)
    monkeypatch.setattr(flats_promote, "prune_runs", _empty)

    assert await flats_promote.main(args) == 0
    assert session.commits == 0
    if args[0] == "status":
        assert session.rollbacks == 0
    else:
        assert session.rollbacks == 1
    capsys.readouterr()
