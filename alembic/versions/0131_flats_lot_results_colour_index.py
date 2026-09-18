"""flats.lot_results — index the signed colour

The county run (289,845 lots, 579,690 results) is in ``flats.lot_results``
and the first page that reads it counts lots by colour and filters on one.
The colour is not a column: the verdict is ``tier`` (``unknown`` everywhere
until the rules are signed) and the colour the lot would take once they are
lives beside it at ``checks->>'if_signed'`` -- kept there on purpose, never in
the verdict's place. Counting it therefore read every row's JSON, 665 MB a
page. This index makes the per-run, per-lot best colour an index-only read.

Revision ID: 0131
Revises: 0130
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0131"
down_revision = "0130"
branch_labels = None
depends_on = None

SCHEMA = "flats"
NAME = "ix_flats_lot_results_run_colour"


def upgrade() -> None:
    op.create_index(
        NAME,
        "lot_results",
        ["run_id", sa.text("(checks ->> 'if_signed')"), "lot_id", "design_key"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(NAME, table_name="lot_results", schema=SCHEMA)
