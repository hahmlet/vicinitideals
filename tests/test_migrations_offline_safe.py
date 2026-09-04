"""A migration that reads rows must say what it does when there are none to read.

``alembic upgrade head --sql`` renders every migration to a static script
without a database. In that mode ``op.get_bind()`` returns a mock whose
``execute()`` returns ``None``, so any ``.fetchall()``, ``.fetchone()`` or
``.scalar()`` on the result raises ``AttributeError`` and takes the whole
render down with it.

That render is the ``migration_dry_run`` promotion gate, and that gate is a
step of CI's light gate -- so one unguarded data migration does not fail one
check, it fails the *first* check and skips Ruff, the FLATS firewall, the unit
tests and the FLATS tests underneath it. 0119 and 0121 were both missing the
guard; ten other data migrations in this directory have had it since 0043, so
the convention was already the house style and these two simply escaped it.

The test is deliberately textual rather than behavioural. Running the real
dry-run here would need alembic and a config, take seconds, and fail with a
traceback pointing at a library frame; this points at the file and the line
that needs the guard. It over-reports in one direction only -- a migration that
mentions ``as_sql`` anywhere passes -- which is the safe direction for a
convention check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

#: Calls that need a real result object. ``execute()`` alone is fine offline --
#: it renders as a statement in the script, which is the point of --sql.
_READS = re.compile(r"\.(?:fetchall|fetchone|fetchmany|scalar|scalars|first)\s*\(")

#: How this repo spells the guard, in both of its forms:
#: ``if not op.get_context().as_sql:`` and ``if op.get_context().as_sql: return``.
_GUARD = re.compile(r"\bas_sql\b")


def _migrations() -> list[Path]:
    return sorted(p for p in VERSIONS.glob("*.py") if p.name != "__init__.py")


def test_there_are_migrations_to_check() -> None:
    """Guards the guard: an empty glob would make the test below vacuous."""
    assert len(_migrations()) > 100


def test_every_row_reading_migration_guards_offline_mode() -> None:
    unguarded = []
    for path in _migrations():
        source = path.read_text(encoding="utf-8")
        if not _READS.search(source):
            continue
        if _GUARD.search(source):
            continue
        line = next(
            (
                n
                for n, text in enumerate(source.splitlines(), start=1)
                if _READS.search(text)
            ),
            0,
        )
        unguarded.append(f"{path.name}:{line}")

    assert not unguarded, (
        "these migrations read rows with no offline guard, so "
        "`alembic upgrade head --sql` will raise and take CI's first gate step "
        f"with it: {unguarded}. Wrap the read in "
        "`if not op.get_context().as_sql:` the way 0043 does."
    )
