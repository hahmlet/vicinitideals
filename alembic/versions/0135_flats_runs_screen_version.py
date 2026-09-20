"""flats.runs -- the screen's own version beside the repo HEAD

The drift report puts a verdict move that neither the ground nor a measured
fact explains to the rules version, else to the code version -- and
``code_version`` is the repo HEAD, which differs whenever any commit landed
between two runs, a docs edit included. ``screen_version`` is a content
hash of the screen's own files (``flats/`` less the tests, the jurisdictions
and the provenance store, plus quadfit), stamped by the exporter
(``scripts/flats_load_bridge.py``), so a move is put to "code" only when the
screen changed. Nullable: runs loaded before this carry none and the
report falls back to the HEAD for them.

Revision ID: 0135
Revises: 0134
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.add_column("runs", sa.Column("screen_version", sa.String(length=64), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("runs", "screen_version", schema=SCHEMA)
