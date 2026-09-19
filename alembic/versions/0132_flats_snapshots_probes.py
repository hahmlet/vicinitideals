"""flats.snapshots, flats.probes -- the county copy has a name, and a warning

Steph's decision on HUMAN_TODO 20 (2026-09-19): the screen's copy of the
county map lives in this database, on three conditions -- a written process
for updating it, a failure-state warning that does not depend on any live
connection, and a way to correct for lots splitting and merging. This is the
first of those: every copy is a ``snapshots`` row carrying the acquire
manifest (what was fetched, refused, failed), exactly one row is ``current``,
and the monthly source check writes a ``probes`` row the Lots pages read.

Each snapshot owns its own lot rows: ``lots.snapshot_id`` replaces the
``(county, tlid)`` uniqueness with ``(snapshot_id, county, tlid)``, so a
refresh lands beside the copy in use rather than on top of it, and a lot the
county deleted is simply absent from the next copy. The one run already in
production (run 2, 289,845 lots, read from quadfit's July raw file rather
than a dated snapshot) is backfilled onto a synthetic ``current`` snapshot
dated 2026-07-28 so the column can be NOT NULL and the banner has a copy to
name. ``runs.snapshot_id`` says which copy a run read.

Revision ID: 0132
Revises: 0131
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None

SCHEMA = "flats"

#: Run 2's lots came from ``data/quadfit/raw/taxlots.geojson`` on LXC 137,
#: fetched 2026-07-28 from Metro's Taxlots (Public) FeatureServer.
BACKFILL_NOTES = (
    "quadfit raw (Metro Taxlots (Public) FeatureServer, fetched 2026-07-28); "
    "the bridge county run loaded 2026-09-18 as flats.runs id 2. Registered by "
    "migration 0132 so every lot row names the copy it came from."
)


def upgrade() -> None:
    op.create_table(
        "snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("host", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rlis_release", sa.String(length=16), nullable=True),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_by", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_date", "host", name="uq_flats_snapshots_date_host"),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_flats_snapshots_current",
        "snapshots",
        ["status"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'current'"),
    )

    op.create_table(
        "probes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("seconds", sa.Numeric(8, 1), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], [f"{SCHEMA}.snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index("ix_flats_probes_ran_at", "probes", ["ran_at"], unique=False, schema=SCHEMA)

    # Runs and lots name the copy they read.
    op.add_column("runs", sa.Column("snapshot_id", sa.BigInteger(), nullable=True), schema=SCHEMA)
    op.create_foreign_key(
        "fk_flats_runs_snapshot_id",
        "runs",
        "snapshots",
        ["snapshot_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.add_column("lots", sa.Column("snapshot_id", sa.BigInteger(), nullable=True), schema=SCHEMA)

    # The copy already in production, given a name so nothing is orphaned.
    op.execute(
        sa.text(
            f"""
            INSERT INTO {SCHEMA}.snapshots
                (snapshot_date, host, status, rlis_release, manifest, counts, acquired_at, notes)
            SELECT DATE '2026-07-28', '137', 'current', NULL, '{{}}'::jsonb,
                   jsonb_build_object('lots', (SELECT count(*) FROM {SCHEMA}.lots)),
                   TIMESTAMPTZ '2026-07-28 00:00:00+00', :notes
            WHERE EXISTS (SELECT 1 FROM {SCHEMA}.lots)
            """
        ).bindparams(notes=BACKFILL_NOTES)
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.lots SET snapshot_id = s.id
        FROM {SCHEMA}.snapshots s
        WHERE s.status = 'current' AND {SCHEMA}.lots.snapshot_id IS NULL
        """
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.runs SET snapshot_id = s.id
        FROM {SCHEMA}.snapshots s
        WHERE s.status = 'current' AND {SCHEMA}.runs.snapshot_id IS NULL
          AND EXISTS (SELECT 1 FROM {SCHEMA}.lot_results r WHERE r.run_id = {SCHEMA}.runs.id)
        """
    )
    op.alter_column("lots", "snapshot_id", nullable=False, schema=SCHEMA)
    op.create_foreign_key(
        "fk_flats_lots_snapshot_id",
        "lots",
        "snapshots",
        ["snapshot_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )

    # Uniqueness is now within a snapshot; (county, tlid) stays indexed for
    # the lot page and the review decisions that key on it.
    op.drop_constraint("uq_flats_lots_county_tlid", "lots", schema=SCHEMA, type_="unique")
    op.create_unique_constraint(
        "uq_flats_lots_snapshot_county_tlid", "lots", ["snapshot_id", "county", "tlid"], schema=SCHEMA
    )
    op.create_index("ix_flats_lots_county_tlid", "lots", ["county", "tlid"], unique=False, schema=SCHEMA)


def downgrade() -> None:
    # Only one snapshot's lots can go back under a (county, tlid) uniqueness;
    # keep the current copy's rows and drop the rest.
    op.execute(
        f"""
        DELETE FROM {SCHEMA}.lots
        WHERE snapshot_id NOT IN (SELECT id FROM {SCHEMA}.snapshots WHERE status = 'current')
        """
    )
    op.drop_index("ix_flats_lots_county_tlid", table_name="lots", schema=SCHEMA)
    op.drop_constraint("uq_flats_lots_snapshot_county_tlid", "lots", schema=SCHEMA, type_="unique")
    op.create_unique_constraint("uq_flats_lots_county_tlid", "lots", ["county", "tlid"], schema=SCHEMA)
    op.drop_constraint("fk_flats_lots_snapshot_id", "lots", schema=SCHEMA, type_="foreignkey")
    op.drop_column("lots", "snapshot_id", schema=SCHEMA)
    op.drop_constraint("fk_flats_runs_snapshot_id", "runs", schema=SCHEMA, type_="foreignkey")
    op.drop_column("runs", "snapshot_id", schema=SCHEMA)
    op.drop_index("ix_flats_probes_ran_at", table_name="probes", schema=SCHEMA)
    op.drop_table("probes", schema=SCHEMA)
    op.drop_index("uq_flats_snapshots_current", table_name="snapshots", schema=SCHEMA)
    op.drop_table("snapshots", schema=SCHEMA)
