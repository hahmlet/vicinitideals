"""Async investor-export jobs table.

Tracks one row per Excel export request so the UI can poll for status,
attach the rendered .xlsx bytes (Postgres BYTEA), and resend cached
exports without re-running the engine when the scenario hasn't been
recomputed since the last successful build.

Revision ID: 0062
Revises: 0061
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


export_job_status = sa.Enum(
    "queued",
    "calculating",
    "sending",
    "sent",
    "failed",
    name="export_job_status",
    create_type=False,
)


def upgrade() -> None:
    # Idempotent enum creation — a previous half-applied attempt may have
    # left the type behind. Raw DO-block makes re-running this migration
    # safe; the column-level Enum reference uses ``create_type=False`` so
    # ``op.create_table`` does not re-attempt creation either.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'export_job_status') THEN
                CREATE TYPE export_job_status AS ENUM ('queued', 'calculating', 'sending', 'sent', 'failed');
            END IF;
        END$$;
        """
    )

    op.create_table(
        "export_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("recipient_email", sa.String(320), nullable=False),
        sa.Column(
            "status",
            export_job_status,
            nullable=False,
            server_default="queued",
        ),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("xlsx_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Composite index for the "last sent export for this scenario" lookup
    # used by the resend-eligibility check on click.
    op.create_index(
        "ix_export_jobs_scenario_created",
        "export_jobs",
        ["scenario_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_export_jobs_scenario_created", table_name="export_jobs")
    op.drop_table("export_jobs")
    export_job_status.drop(op.get_bind(), checkfirst=True)
