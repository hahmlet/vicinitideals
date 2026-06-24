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
