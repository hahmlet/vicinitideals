"""flats.lot_foundation: the foundation model's measured record per lot

FOLLOWUPS 209 (FD6 build step 10). One row per (county, tlid): what the record
was measured on, the model and geometry version, and the whole measured record
as JSONB. No price is stored: the lot report prices the record at read time
from flats/config/foundation.yaml. A note, never a colour: nothing that screens
reads this table. Filled by ``scripts/flats_foundation.py load``.

Follows 0152 (hazard notes). origin/flats/rel11 may add migrations before this
merges; re-point ``down_revision`` at merge if it does.

Revision ID: 0153
Revises: 0152
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0153"
down_revision = "0152"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "lot_foundation",
        sa.Column("county", sa.String(40), primary_key=True),
        sa.Column("tlid", sa.String(40), primary_key=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("geometry_hash", sa.String(16), nullable=False),
        sa.Column("drawing", sa.String(240), nullable=False),
        sa.Column("ground_source", sa.String(40), nullable=False),
        sa.Column("cell_m", sa.Numeric(6, 2)),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("record", JSONB(), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("lot_foundation", schema=SCHEMA)
