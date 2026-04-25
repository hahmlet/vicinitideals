"""Broker Oregon eLicense enrichment + disciplinary actions + firm scrape status.

Adds columns and a new table to support enriching brokers from the Oregon Real
Estate Agency public license lookup (https://orea.elicense.micropact.com/Lookup/),
plus the framework for per-firm contact-info scrapers.

brokers — new columns:
  - license_number_locked    (bool) — when True, listing scrapers must not
    overwrite license_number; the user has manually set it to align with the
    Oregon database. Oregon enrichment still runs against the locked value.
  - license_personal_*       — the broker's personal/home address as listed
    on their Oregon license record (street/street2/city/state/zip)
  - license_type             — Oregon license type string (e.g. "Principal Broker")
  - license_status           — 'active' | 'inactive' | 'not_found' | 'unknown'
  - oregon_last_pulled_at    — last successful enrichment time
  - oregon_lookup_status     — 'success' | 'failed' | 'not_found' | 'pending'
  - oregon_failure_count     — consecutive failures; capped at 3 retries per sweep
  - oregon_detail_url        — direct link to the Oregon detail page for audit

brokerages — new columns:
  - oregon_company_*         — the "Affiliated with" company address pulled
    from the Oregon record (street/street2/city/state/zip)
  - oregon_company_name      — the company name as it appears on Oregon
  - firm_scrape_status       — 'supported' | 'unsupported' | 'unknown'
    drives the firm-name color in UI (green/red/grey)
  - firm_scrape_domain       — canonical domain key into the firm-scraper
    registry (e.g. 'smire.com')

broker_disciplinary_actions — new table:
  one row per disciplinary case found on a broker's Oregon record.

Revision ID: 0057
Revises: 0056
Create Date: 2026-04-24
"""

import sqlalchemy as sa
from alembic import op


revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- brokers: license enrichment columns ------------------------------
    op.add_column(
        "brokers",
        sa.Column(
            "license_number_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("brokers", sa.Column("license_personal_street", sa.Text(), nullable=True))
    op.add_column("brokers", sa.Column("license_personal_street2", sa.Text(), nullable=True))
    op.add_column("brokers", sa.Column("license_personal_city", sa.Text(), nullable=True))
    op.add_column("brokers", sa.Column("license_personal_state", sa.String(20), nullable=True))
    op.add_column("brokers", sa.Column("license_personal_zip", sa.String(20), nullable=True))
    op.add_column("brokers", sa.Column("license_type", sa.String(120), nullable=True))
    op.add_column("brokers", sa.Column("license_status", sa.String(40), nullable=True))
    op.add_column(
        "brokers",
        sa.Column("oregon_last_pulled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("brokers", sa.Column("oregon_lookup_status", sa.String(40), nullable=True))
    op.add_column(
        "brokers",
        sa.Column(
            "oregon_failure_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column("brokers", sa.Column("oregon_detail_url", sa.Text(), nullable=True))

    # ---- brokerages: oregon affiliation + firm scrape registry ------------
    op.add_column("brokerages", sa.Column("oregon_company_name", sa.Text(), nullable=True))
    op.add_column("brokerages", sa.Column("oregon_company_street", sa.Text(), nullable=True))
    op.add_column("brokerages", sa.Column("oregon_company_street2", sa.Text(), nullable=True))
    op.add_column("brokerages", sa.Column("oregon_company_city", sa.Text(), nullable=True))
    op.add_column("brokerages", sa.Column("oregon_company_state", sa.String(20), nullable=True))
    op.add_column("brokerages", sa.Column("oregon_company_zip", sa.String(20), nullable=True))
    op.add_column(
        "brokerages",
        sa.Column(
            "firm_scrape_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )
    op.add_column("brokerages", sa.Column("firm_scrape_domain", sa.String(255), nullable=True))
    op.create_index(
        "ix_brokerages_firm_scrape_domain",
        "brokerages",
        ["firm_scrape_domain"],
    )

    # ---- broker_disciplinary_actions: new table ---------------------------
    op.create_table(
        "broker_disciplinary_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("broker_id", sa.Uuid(), nullable=False),
        sa.Column("case_number", sa.String(120), nullable=True),
        sa.Column("order_signed_date", sa.Date(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("found_issues", sa.Text(), nullable=True),
        sa.Column(
            "source_pulled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["broker_id"], ["brokers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "broker_id",
            "case_number",
            name="uq_broker_disciplinary_actions_broker_case",
        ),
    )
    op.create_index(
        "ix_broker_disciplinary_actions_broker_id",
        "broker_disciplinary_actions",
        ["broker_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_broker_disciplinary_actions_broker_id",
        table_name="broker_disciplinary_actions",
    )
    op.drop_table("broker_disciplinary_actions")

    op.drop_index("ix_brokerages_firm_scrape_domain", table_name="brokerages")
    op.drop_column("brokerages", "firm_scrape_domain")
    op.drop_column("brokerages", "firm_scrape_status")
    op.drop_column("brokerages", "oregon_company_zip")
    op.drop_column("brokerages", "oregon_company_state")
    op.drop_column("brokerages", "oregon_company_city")
    op.drop_column("brokerages", "oregon_company_street2")
    op.drop_column("brokerages", "oregon_company_street")
    op.drop_column("brokerages", "oregon_company_name")

    op.drop_column("brokers", "oregon_detail_url")
    op.drop_column("brokers", "oregon_failure_count")
    op.drop_column("brokers", "oregon_lookup_status")
    op.drop_column("brokers", "oregon_last_pulled_at")
    op.drop_column("brokers", "license_status")
    op.drop_column("brokers", "license_type")
    op.drop_column("brokers", "license_personal_zip")
    op.drop_column("brokers", "license_personal_state")
    op.drop_column("brokers", "license_personal_city")
    op.drop_column("brokers", "license_personal_street2")
    op.drop_column("brokers", "license_personal_street")
    op.drop_column("brokers", "license_number_locked")
