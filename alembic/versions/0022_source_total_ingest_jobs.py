"""Add source_total to ingest_jobs

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingest_jobs", sa.Column("source_total", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("ingest_jobs", "source_total")
