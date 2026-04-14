"""Refactor entity renames — Phase 1c

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-04

Creates the milestones table.

Pre-close milestones (offer → contract → close) belong to an Opportunity.
Post-close milestones (pre-dev → construction → lease-up → stabilized → divestment)
belong to a Project.

Exactly one of opportunity_id or project_id must be set per row (enforced via
a CHECK constraint — not both, not neither).

Milestone ordering is duration-based: each milestone's start = sum of all
predecessor durations. An optional target_date can override for calendar pinning.

Preloaded milestone_type values per deal_type:
  Minor Reno:       construction, operation_lease_up, operation_stabilized
  Major Reno:       pre_development, construction, operation_lease_up, operation_stabilized
  New Construction: pre_development, construction, operation_lease_up, operation_stabilized
  All:              + divestment (optional, user-added)

Pre-close types (opportunity-level):
  offer_made, under_contract, close
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# Valid milestone_type values
# Pre-close (opportunity-level):
#   offer_made | under_contract | close
# Post-close (project-level):
#   pre_development | construction | operation_lease_up | operation_stabilized | divestment


def upgrade() -> None:
    op.create_table(
        "milestones",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        # Exactly one of these must be set
        sa.Column(
            "opportunity_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        # Milestone type — drives UI label and default duration
        sa.Column("milestone_type", sa.String(60), nullable=False),
        # Duration from previous milestone (day-count). Default durations
        # are populated by the application layer based on deal_type presets.
        sa.Column("duration_days", sa.Integer(), nullable=False, server_default="0"),
        # Optional calendar pin — overrides duration-based positioning when set
        sa.Column("target_date", sa.Date(), nullable=True),
        # Ordering within the sequence (1-based, contiguous per opportunity/project)
        sa.Column("sequence_order", sa.Integer(), nullable=False, server_default="1"),
        # Human-readable override (e.g., "Phase 2 Construction")
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Enforce: exactly one parent must be set
        sa.CheckConstraint(
            "(opportunity_id IS NOT NULL AND project_id IS NULL) OR "
            "(opportunity_id IS NULL AND project_id IS NOT NULL)",
            name="ck_milestones_single_parent",
        ),
    )
    op.create_index("ix_milestones_opportunity_id", "milestones", ["opportunity_id"])
    op.create_index("ix_milestones_project_id", "milestones", ["project_id"])
    op.create_index(
        "ix_milestones_sequence",
        "milestones",
        ["opportunity_id", "project_id", "sequence_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_milestones_sequence", "milestones")
    op.drop_index("ix_milestones_project_id", "milestones")
    op.drop_index("ix_milestones_opportunity_id", "milestones")
    op.drop_table("milestones")
