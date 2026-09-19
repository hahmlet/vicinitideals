"""flats.lot_changes -- what each lot did between two copies of the county map

Steph's third condition on keeping the county copy in this database
(HUMAN_TODO 20): a method for delta correction, lots combining and lots
splitting. The delta (``flats/ingest/delta.py``) reads lineage from geometry
overlap between two snapshots -- the TLID is a hint, since a split parent
sometimes keeps its number and shrinks -- and this table holds one row per
lot per change: attr_change, reshape, split (parent / child), merge (parent /
survivor), renumbered (parent / child), added, deleted, vacated. Metro's own
quarterly change list is recorded beside each row as the cross-check.

Nothing here changes a lot row; promotion (plan phase 4) reads these rows to
flag review decisions that were made about different ground.

Revision ID: 0133
Revises: 0132
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "lot_changes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("snapshot_from", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_to", sa.BigInteger(), nullable=False),
        sa.Column("county", sa.String(length=40), nullable=False),
        sa.Column("tlid", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=True),
        sa.Column(
            "related_tlids",
            postgresql.ARRAY(sa.String(length=40)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("area_before", sa.Numeric(14, 2), nullable=True),
        sa.Column("area_after", sa.Numeric(14, 2), nullable=True),
        sa.Column("iou", sa.Numeric(6, 4), nullable=True),
        sa.Column("attr_diff", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("rlis_change", sa.String(length=8), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(
            "kind IN ('attr_change', 'reshape', 'split', 'merge', 'renumbered', 'added', 'deleted', 'vacated')",
            name="ck_flats_lot_changes_kind",
        ),
        sa.CheckConstraint(
            "role IS NULL OR role IN ('parent', 'child', 'survivor')",
            name="ck_flats_lot_changes_role",
        ),
        sa.ForeignKeyConstraint(["snapshot_from"], [f"{SCHEMA}.snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_to"], [f"{SCHEMA}.snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_lot_changes_to_county_tlid",
        "lot_changes",
        ["snapshot_to", "county", "tlid"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_lot_changes_to_kind", "lot_changes", ["snapshot_to", "kind"], unique=False, schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_flats_lot_changes_to_kind", table_name="lot_changes", schema=SCHEMA)
    op.drop_index("ix_flats_lot_changes_to_county_tlid", table_name="lot_changes", schema=SCHEMA)
    op.drop_table("lot_changes", schema=SCHEMA)
