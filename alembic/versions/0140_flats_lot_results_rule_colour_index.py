"""flats.lot_results — index the colour rule's colour

0131 indexed the signed colour (``checks->>'if_signed'``) so the lot list
could count and filter by it off the index alone. The flag plan (FOLLOWUPS
37) writes its own colour beside it, ``checks->>'colour'``: green / yellow /
red from binds and flags under the colour rule in ``flats/config/colour.yaml``.
The pages now show that colour where the run wrote one and the older signed
colour where it did not (a run screened before the rule, or a row the screen
never wrote), so the index carries the same COALESCE the query does and the
old one goes.

Revision ID: 0140
Revises: 0139
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0140"
down_revision = "0139"
branch_labels = None
depends_on = None

SCHEMA = "flats"
OLD = "ix_flats_lot_results_run_colour"
NEW = "ix_flats_lot_results_run_rule_colour"


def upgrade() -> None:
    op.create_index(
        NEW,
        "lot_results",
        [
            "run_id",
            sa.text("(COALESCE(checks ->> 'colour', checks ->> 'if_signed'))"),
            "lot_id",
            "design_key",
        ],
        unique=False,
        schema=SCHEMA,
    )
    op.drop_index(OLD, table_name="lot_results", schema=SCHEMA)


def downgrade() -> None:
    op.create_index(
        OLD,
        "lot_results",
        ["run_id", sa.text("(checks ->> 'if_signed')"), "lot_id", "design_key"],
        unique=False,
        schema=SCHEMA,
    )
    op.drop_index(NEW, table_name="lot_results", schema=SCHEMA)
