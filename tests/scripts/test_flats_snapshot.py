"""Command-line flows for registering, reporting, and listing FLATS snapshots."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from scripts import flats_snapshot


class _Engine:
    async def dispose(self) -> None:
        pass


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _Session:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        pass

    async def execute(self, _statement):
        return _Result([])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _db(monkeypatch):
    session = _Session()
    monkeypatch.setattr(flats_snapshot, "create_async_engine", lambda *a, **k: _Engine())
    monkeypatch.setattr(flats_snapshot, "async_sessionmaker", lambda *a, **k: lambda: session)
    return session


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["register", "--help"], ["--manifest", "--host", "--status", "--dry-run"]),
        (["report", "--help"], ["--snapshot", "--section", "--summary", "--dry-run"]),
        (["list", "--help"], ["list"]),
    ],
)
async def test_subcommand_help_exposes_expected_arguments(args, expected, capsys):
    with pytest.raises(SystemExit) as exited:
        await flats_snapshot.main(args)

    assert exited.value.code == 0
    output = capsys.readouterr().out
    assert all(option in output for option in expected)


async def test_register_dry_run_reads_manifest_and_rolls_back(tmp_path, monkeypatch, capsys):
    session = _db(monkeypatch)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"snapshot_date": "2026-01-02"}), encoding="utf-8")
    row = SimpleNamespace(
        id=3,
        snapshot_date=date(2026, 1, 2),
        host="137",
        status="candidate",
        rlis_release="2026",
        counts={"features": 11, "by_status": {"measured": 11}},
    )
    seen = {}

    async def _register(_session, got, **kwargs):
        seen.update(manifest=got, **kwargs)
        return row

    monkeypatch.setattr(flats_snapshot, "register_snapshot", _register)

    assert await flats_snapshot.main(
        ["register", "--manifest", str(manifest), "--host", "137", "--dry-run"]
    ) == 0

    assert seen["manifest"] == {"snapshot_date": "2026-01-02"}
    assert seen["host"] == "137"
    assert session.commits == 0
    assert session.rollbacks == 1
    assert "dry run, rolled back" in capsys.readouterr().out


async def test_report_dry_run_reads_summary_and_rolls_back(tmp_path, monkeypatch, capsys):
    session = _db(monkeypatch)
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"from": "old", "to": "new", "rows": 2}), encoding="utf-8")
    row = SimpleNamespace(
        id=3,
        snapshot_date=date(2026, 1, 2),
        host="137",
        status="candidate",
        report={"delta": {"rows": 2}},
    )
    seen = {}

    async def _attach(_session, snapshot, section, doc):
        seen.update(snapshot=snapshot, section=section, doc=doc)
        return row

    monkeypatch.setattr(flats_snapshot, "attach_report", _attach)

    assert await flats_snapshot.main(
        ["report", "--snapshot", "3", "--summary", str(summary), "--dry-run"]
    ) == 0

    assert seen == {
        "snapshot": 3,
        "section": "delta",
        "doc": {"from": "old", "to": "new", "rows": 2},
    }
    assert session.commits == 0
    assert session.rollbacks == 1
    assert "dry run, rolled back" in capsys.readouterr().out


async def test_list_prints_registered_snapshots(monkeypatch, capsys):
    session = _db(monkeypatch)
    row = SimpleNamespace(
        id=9,
        snapshot_date=date(2026, 1, 2),
        host="137",
        status="current",
        rlis_release="2026",
        counts={"features": 11},
        notes="registered",
    )

    async def _execute(_self, _statement):
        return _Result([row])

    monkeypatch.setattr(_Session, "execute", _execute)

    assert await flats_snapshot.main(["list"]) == 0
    assert "9  2026-01-02" in capsys.readouterr().out
