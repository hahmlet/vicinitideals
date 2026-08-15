"""Rule-value signatures captured in the browser.

A value is verified when a person has compared it to the line of code it was
read from. That comparison is now possible on a web page, but the record of it
belongs in the repository — ``flats/config/verifications.jsonl``, hashed over
the value and its citation so editing either breaks the signature.

This table is the inbox between the two. A reviewer's decision lands here the
moment they make it, and a later command drains unexported rows into the log for
commit. Nothing loads rules from this table: the repository stays canonical, and
a signature that never gets drained shows up as one that never took effect.

Revision ID: 0126
Revises: 0125
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "rule_signatures",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # What was signed. `when_key` is the sorted condition/band tokens that
        # address one variant, joined by '+', empty for the base value — the
        # same address the signing log uses, so draining is a copy rather than
        # a translation.
        sa.Column("layer", sa.String(length=120), nullable=False),
        sa.Column("zone", sa.String(length=40), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("when_key", sa.String(length=200), nullable=False, server_default=""),
        # The value as it stood when the reviewer looked at it. A signature is
        # over the number, not over the field: if the YAML changes afterwards
        # the drained entry stops matching, which is the intended failure.
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cite", sa.Text(), nullable=False, server_default=""),
        sa.Column("quote", sa.Text(), nullable=False, server_default=""),
        # verified | rejected. A rejection is not a signature — it is a note to
        # the encoder that the number does not match its quote — but it is the
        # other half of what a reviewer can say, and losing it would mean the
        # only recorded outcome of a review is agreement.
        sa.Column("verdict", sa.String(length=10), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("reviewer", sa.String(length=80), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        #: When a drain wrote this row into the repository log. NULL is the
        #: queue.
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    # The drain reads this: oldest undrained first.
    op.create_index(
        "ix_flats_rule_signatures_pending",
        "rule_signatures",
        ["decided_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("exported_at IS NULL"),
    )
    # One live opinion per address per reviewer; changing your mind supersedes
    # rather than duplicates, and the page reads the latest by decided_at.
    op.create_index(
        "ix_flats_rule_signatures_value",
        "rule_signatures",
        ["layer", "zone", "field", "when_key"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_flats_rule_signatures_value", "rule_signatures", schema=SCHEMA)
    op.drop_index("ix_flats_rule_signatures_pending", "rule_signatures", schema=SCHEMA)
    op.drop_table("rule_signatures", schema=SCHEMA)
