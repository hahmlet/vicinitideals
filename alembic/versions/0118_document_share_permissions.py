"""Add per-link permissions + expiry to document_shares (Phase 3 follow-up).

Restores the originally-planned share controls: per-link upload/download
toggles and an optional auto-expiry. View remains always-on.

Revision ID: 0118
Revises: 0117
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_shares",
        sa.Column("can_upload", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "document_shares",
        sa.Column("can_download", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "document_shares",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_shares", "expires_at")
    op.drop_column("document_shares", "can_download")
    op.drop_column("document_shares", "can_upload")
