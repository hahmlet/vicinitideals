"""flats.flag_instances + flats.flag_questions: flag history and the review queue

Steph's flag plan (FOLLOWUPS 37 item 4): a flag instance per lot with the
run that opened it and the run that cleared it -- "cleared flags are kept,
not deleted" -- and a queue of questions an agent could not answer alone,
each on one flag's resolution key, for the next review session. The run's
own ``lot_results.checks -> 'flags'`` stay the screen's answer; these
outlive the run, keyed on the durable taxlot id.

Revision ID: 0141
Revises: 0140
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def _run_fk(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.BigInteger(),
        sa.ForeignKey(f"{SCHEMA}.runs.id", ondelete="SET NULL"),
        nullable=True,
    )


def upgrade() -> None:
    op.create_table(
        "flag_instances",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("county", sa.String(40), nullable=False),
        sa.Column("tlid", sa.String(40), nullable=False),
        sa.Column("design_key", sa.String(80), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("raised_by", sa.String(80), nullable=False),
        sa.Column("bounds_low", sa.Numeric(14, 3), nullable=True),
        sa.Column("bounds_high", sa.Numeric(14, 3), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.Integer(), nullable=True),
        sa.Column("colour", sa.String(10), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        _run_fk("opened_run_id"),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        _run_fk("last_seen_run_id"),
        _run_fk("cleared_run_id"),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint("status IN ('open', 'cleared')", name="ck_flats_flag_instances_status"),
        sa.CheckConstraint(
            "(status = 'cleared') = (cleared_run_id IS NOT NULL AND cleared_at IS NOT NULL)",
            name="ck_flats_flag_instances_cleared",
        ),
        sa.CheckConstraint(
            "(bounds_low IS NULL) = (bounds_high IS NULL) AND (bounds_low IS NULL OR bounds_low <= bounds_high)",
            name="ck_flats_flag_instances_bounds",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity BETWEEN 0 AND 10", name="ck_flats_flag_instances_severity"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_flats_flag_instances_open",
        "flag_instances",
        ["county", "tlid", "design_key", "code", "key"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_flats_flag_instances_open_code_key",
        "flag_instances",
        ["code", "key"],
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "flag_questions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("asked_by", sa.String(200), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered_by", sa.String(200), nullable=True),
        sa.Column(
            "answered_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(answer IS NULL) = (answered_at IS NULL) AND (answer IS NULL) = (answered_by IS NULL)",
            name="ck_flats_flag_questions_answered",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_flats_flag_questions_code_key", "flag_questions", ["code", "key"], schema=SCHEMA)
    op.create_index(
        "ix_flats_flag_questions_waiting",
        "flag_questions",
        ["asked_at"],
        schema=SCHEMA,
        postgresql_where=sa.text("answered_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_flats_flag_questions_waiting", table_name="flag_questions", schema=SCHEMA)
    op.drop_index("ix_flats_flag_questions_code_key", table_name="flag_questions", schema=SCHEMA)
    op.drop_table("flag_questions", schema=SCHEMA)
    op.drop_index("ix_flats_flag_instances_open_code_key", table_name="flag_instances", schema=SCHEMA)
    op.drop_index("uq_flats_flag_instances_open", table_name="flag_instances", schema=SCHEMA)
    op.drop_table("flag_instances", schema=SCHEMA)
