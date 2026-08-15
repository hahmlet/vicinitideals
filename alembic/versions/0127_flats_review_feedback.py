"""Feedback as a record of what was on screen, not just a verdict.

A reviewer who finds a problem has something to say about it, and a bare
``rejected`` throws that away. These columns make a decision self-contained:
the code text that was displayed, the citation it was displayed under, and a
fingerprint of the exact value it was about.

The fingerprint is what closes the loop. It hashes the address, the number, its
citation and its quote — so when the encoding changes in response to the note,
the fingerprint no longer matches and the item resurfaces as "changed since you
wrote this" rather than sitting in a list nobody can tell is stale.

``bundled_at`` is separate from ``exported_at`` on purpose. Exporting is the
drain that writes confirmations into the repository's verification log;
bundling is a reviewer handing a batch of problems to whoever will fix them.
A row can be one, the other, both or neither.

Revision ID: 0127
Revises: 0126
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0127"
down_revision = "0126"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.add_column(
        "rule_signatures",
        sa.Column("shown", sa.Text(), nullable=False, server_default=""),
        schema=SCHEMA,
    )
    op.add_column(
        "rule_signatures",
        sa.Column("shown_ref", sa.Text(), nullable=False, server_default=""),
        schema=SCHEMA,
    )
    op.add_column(
        "rule_signatures",
        sa.Column("fingerprint", sa.String(length=64), nullable=False, server_default=""),
        schema=SCHEMA,
    )
    op.add_column(
        "rule_signatures",
        sa.Column("bundled_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    # The bundle page reads this: everything a reviewer has not yet handed on,
    # oldest first.
    op.create_index(
        "ix_flats_rule_signatures_unbundled",
        "rule_signatures",
        ["decided_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("bundled_at IS NULL"),
    )
    # "Has what I reviewed changed since?" is a lookup by fingerprint.
    op.create_index(
        "ix_flats_rule_signatures_fingerprint",
        "rule_signatures",
        ["fingerprint"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_flats_rule_signatures_fingerprint", "rule_signatures", schema=SCHEMA)
    op.drop_index("ix_flats_rule_signatures_unbundled", "rule_signatures", schema=SCHEMA)
    op.drop_column("rule_signatures", "bundled_at", schema=SCHEMA)
    op.drop_column("rule_signatures", "fingerprint", schema=SCHEMA)
    op.drop_column("rule_signatures", "shown_ref", schema=SCHEMA)
    op.drop_column("rule_signatures", "shown", schema=SCHEMA)
