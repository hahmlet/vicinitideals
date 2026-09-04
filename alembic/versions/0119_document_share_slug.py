"""Add short random slug to document_shares (replaces signed-token URLs).

Guests now reach a shared room via /share/{slug} where slug is a 10-char
base58 code (no ambiguous 0/O/I/l). Existing rows are backfilled with a
freshly generated unique slug.

Revision ID: 0119
Revises: 0118
"""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from alembic import op

revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None

_SLUG_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_SLUG_LEN = 10


def _slug(used: set[str]) -> str:
    while True:
        s = "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(_SLUG_LEN))
        if s not in used:
            used.add(s)
            return s


def upgrade() -> None:
    op.add_column(
        "document_shares",
        sa.Column("slug", sa.String(length=32), nullable=True),
    )
    # Backfill only in online mode; --sql offline mode cannot run SELECT/UPDATE
    # -- op.get_bind() hands back a mock whose execute() returns None, so the
    # .fetchall() below raises AttributeError and takes the whole render with
    # it. Same guard as 0043. This one was missed, and because
    # `alembic upgrade head --sql` is the migration_dry_run promotion gate, and
    # that gate is the FIRST step of CI's light gate, the miss skipped Ruff,
    # the FLATS firewall and every test underneath it on every push. A slug is
    # random per row, so there is no set-based statement to emit in its place:
    # the rendered script therefore does NOT backfill, and must not be applied
    # by hand to a database that already has document_shares rows. Production
    # never takes that path -- deploy-vicinitideals.sh runs `alembic upgrade
    # head` online.
    if not op.get_context().as_sql:
        bind = op.get_bind()
        rows = bind.execute(sa.text("SELECT id FROM document_shares")).fetchall()
        used: set[str] = set()
        for (row_id,) in rows:
            bind.execute(
                sa.text("UPDATE document_shares SET slug = :slug WHERE id = :id"),
                {"slug": _slug(used), "id": row_id},
            )
    op.alter_column("document_shares", "slug", nullable=False)
    op.create_index(
        "ix_document_shares_slug", "document_shares", ["slug"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_document_shares_slug", table_name="document_shares")
    op.drop_column("document_shares", "slug")
