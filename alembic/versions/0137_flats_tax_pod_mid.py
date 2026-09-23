"""flats.tax_impact_lots: the pod at a middle unit value (c_mid_*)

The pod was priced at the two ends of a per-unit band ($275k / $450k) with no
middle. The county roll answers what the middle is: the assessor's own value
on the jurisdiction's new single-family houses on small lots -- the nearest
thing on the roll to a new townhome. ``c_mid_*`` holds the pod at that value;
the snapshot's ``params.band.mid`` records the figure and how it was read.

Revision ID: 0137
Revises: 0136
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0137"
down_revision = "0136"
branch_labels = None
depends_on = None

SCHEMA = "flats"
FIGURES = ("av", "total", "local_option", "city", "city_local_option", "ten_year")


def upgrade() -> None:
    for f in FIGURES:
        op.add_column("tax_impact_lots", sa.Column(f"c_mid_{f}", sa.Numeric(14, 2), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    for f in FIGURES:
        op.drop_column("tax_impact_lots", f"c_mid_{f}", schema=SCHEMA)
