"""Add zoning_lookup_url to parcels table.

For jurisdictions with no queryable GIS zoning layer (e.g. Fairview), parcels
receive a URL pointing to the jurisdiction's authoritative PDF zoning map so the
UI can surface a link rather than showing an empty zoning field.

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parcels", sa.Column("zoning_lookup_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("parcels", "zoning_lookup_url")
