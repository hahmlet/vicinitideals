"""Moving a reading-queue decision into the rule file without losing it.

Same boundary as the signatures drain: it reads a production database and
writes a repository file, and the database row is the only copy until the file
is committed. So the invariant these tests hold to is the order -- nothing is
stamped ``exported_at`` until the YAML is on disk and has been read back by the
loader.

Every test runs against a temp copy of one jurisdiction file; the real
``flats/config`` tree is never written.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import scripts.flats_drain_reading_rulings as script
from app.models.flats import FlatsReadingRuling
from flats.encode import triage, worklist
from flats.rules import loader
from flats.rules.loader import load_rules

pytestmark = pytest.mark.asyncio

LAYER = "or/multnomah/gresham"
PATH = "or/multnomah/gresham/4.0100.residential.txt"
SECTION = "4.0140"
KEY = worklist.card_key(PATH, SECTION)
FIRST = "First thoughts: our reader missed this and it repeats a number we already hold."
SECOND = "Second thoughts: this section does not apply to a four-unit pod in this district."
T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def rules_root(tmp_path, monkeypatch) -> Path:
    """One real jurisdiction file, copied; the drain is pointed at the copy."""
    root = tmp_path / "jurisdictions"
    target = root / f"{LAYER}.yaml"
    target.parent.mkdir(parents=True)
    shutil.copyfile(loader.CONFIG_ROOT / f"{LAYER}.yaml", target)
    monkeypatch.setattr(loader, "CONFIG_ROOT", root)
    monkeypatch.setattr(triage, "CONFIG", root)
    return root


def _yaml(root: Path) -> Path:
    return root / f"{LAYER}.yaml"


def _row(outcome: str, note: str, decided_at: datetime, *, queue: str = "missed") -> FlatsReadingRuling:
    return FlatsReadingRuling(
        layer=LAYER,
        path=PATH,
        section=SECTION,
        queue=queue,
        outcome=outcome,
        note=note,
        fingerprint="0123456789abcdef",
        decided_by="reviewer@example.com",
        decided_at=decided_at,
    )


async def _rows(session: AsyncSession) -> list[FlatsReadingRuling]:
    result = await session.execute(
        select(FlatsReadingRuling)
        .order_by(FlatsReadingRuling.id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def test_the_latest_row_per_card_wins_and_the_superseded_one_is_not_drained(
    session: AsyncSession, rules_root
):
    session.add_all(
        [
            _row("duplicate", FIRST, T0),
            _row("not_here", SECOND, T0 + timedelta(hours=1)),
        ]
    )
    await session.commit()

    assert [r.note for r in await script.pending(session, LAYER)] == [SECOND]

    await script.drain(LAYER, write=True)

    text = _yaml(rules_root).read_text(encoding="utf-8")
    assert SECOND in " ".join(text.split())
    assert "First thoughts" not in text
    # The superseded row was never written, but it is closed so the queue is honest.
    assert all(r.exported_at is not None for r in await _rows(session))


async def test_write_puts_the_yaml_on_disk_and_readable_before_any_row_is_stamped(
    session: AsyncSession, rules_root, monkeypatch
):
    session.add(_row("duplicate", FIRST, T0))
    await session.commit()
    seen: dict[str, object] = {}
    real_rule = script.rule

    def spy(*args, **kwargs):
        path = real_rule(*args, **kwargs)
        # The row is only stamped after this returns, so the file must already hold it.
        seen["on_disk"] = FIRST in " ".join(path.read_text(encoding="utf-8").split())
        seen["path"] = path
        return path

    monkeypatch.setattr(script, "rule", spy)
    await script.drain(LAYER, write=True)

    assert seen["on_disk"] is True
    assert seen["path"] == _yaml(rules_root)
    got = load_rules(rules_root)[LAYER].readings[KEY]
    assert got.outcome == "duplicate"
    assert [r.exported_at is not None for r in await _rows(session)] == [True]


async def test_a_failed_write_leaves_exported_at_null(
    session: AsyncSession, rules_root, monkeypatch
):
    session.add(_row("duplicate", FIRST, T0))
    await session.commit()
    real_write = Path.write_text

    def failing(self, *args, **kwargs):
        if self == _yaml(rules_root):
            raise OSError("the volume is gone")
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing)

    with pytest.raises(OSError):
        await script.drain(LAYER, write=True)

    assert [r.exported_at for r in await _rows(session)] == [None]


async def test_a_ruling_the_loader_refuses_is_not_stamped_and_the_file_is_restored(
    session: AsyncSession, rules_root
):
    before = _yaml(rules_root).read_bytes()
    session.add(_row("no_such_outcome", SECOND, T0))
    await session.commit()

    await script.drain(LAYER, write=True)

    assert _yaml(rules_root).read_bytes() == before
    assert [r.exported_at for r in await _rows(session)] == [None]


async def test_a_dry_run_writes_nothing_and_stamps_nothing(
    session: AsyncSession, rules_root
):
    before = _yaml(rules_root).read_bytes()
    session.add_all(
        [
            _row("duplicate", FIRST, T0),
            _row("not_here", SECOND, T0 + timedelta(hours=1)),
        ]
    )
    await session.commit()

    assert await script.drain(LAYER, write=False) == 0

    assert _yaml(rules_root).read_bytes() == before
    assert [r.exported_at for r in await _rows(session)] == [None, None]
