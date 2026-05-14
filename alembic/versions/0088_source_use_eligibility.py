"""Add source-use eligibility routing columns.

eligible_module_ids on use_lines: explicit whitelist of capital module UUIDs
that may fund this use. Empty array = permissive (any source may fund it).

eligible_use_tags on capital_modules: optional whitelist of use cost_category
strings this source is restricted to. Empty array = permissive (funds any use).

Revision ID: 0088
Revises: 0087
Create Date: 2026-05-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "use_lines",
        sa.Column(
            "eligible_module_ids",
            ARRAY(PGUUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "capital_modules",
        sa.Column(
            "eligible_use_tags",
            ARRAY(sa.String(100)),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("use_lines", "eligible_module_ids")
    op.drop_column("capital_modules", "eligible_use_tags")
