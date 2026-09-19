"""flats.review_decisions -- a decision about ground that has since moved is marked "look again"

Steph's third condition on keeping the county copy in this database
(HUMAN_TODO 20): lots combine and lots split, and a decision a person made
about one lot must not be carried silently onto different ground. Promotion
(``app.services.flats_refresh.promote``) reads ``flats.lot_changes`` for the
copy being promoted and stamps every active decision whose lot split,
merged, was renumbered, deleted or vacated -- or whose zone changed between
the two copies -- with the snapshot that put it in doubt and the reason.
The decision stays in force (superseding is a person's act); the mark is
what the review page shows and what the runbook asks to be cleared.

Revision ID: 0134
Revises: 0133
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.add_column(
        "review_decisions",
        sa.Column("needs_rereview_snapshot_id", sa.BigInteger(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "review_decisions",
        sa.Column("needs_rereview_reason", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_flats_review_decisions_rereview_snapshot",
        "review_decisions",
        "snapshots",
        ["needs_rereview_snapshot_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_flats_review_decisions_rereview",
        "review_decisions",
        ["needs_rereview_snapshot_id"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("needs_rereview_snapshot_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_flats_review_decisions_rereview", table_name="review_decisions", schema=SCHEMA)
    op.drop_constraint(
        "fk_flats_review_decisions_rereview_snapshot", "review_decisions", schema=SCHEMA, type_="foreignkey"
    )
    op.drop_column("review_decisions", "needs_rereview_reason", schema=SCHEMA)
    op.drop_column("review_decisions", "needs_rereview_snapshot_id", schema=SCHEMA)
