"""Add email_verified columns to users table.

Backfills all existing users as verified=True so nobody gets locked out
of the soft-gate banner.  New users created after this migration default
to verified=False until they click their verification link.

Revision ID: 0041
Revises: 0040
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add with server_default=false so new rows start unverified.
    # Existing rows are backfilled to true in the separate UPDATE below.
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Backfill: mark all existing users as verified (grandfather clause).
    # Using CURRENT_TIMESTAMP so we have an audit trail for the backfill.
    op.execute(
        "UPDATE users "
        "SET email_verified = true, "
        "    email_verified_at = CURRENT_TIMESTAMP "
        "WHERE email_verified = false"
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
