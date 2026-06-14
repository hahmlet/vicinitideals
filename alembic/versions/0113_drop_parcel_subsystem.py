"""Drop the parcel-intelligence subsystem (DC-5c-drop).

Removes the now-detached parcel data layer:
  * ``parcels`` (446K county-GIS rows — backed up to /root/backups before drop)
  * ``parcel_transformations`` (lot merger/split log — 0 rows)
  * ``opportunities.parcel_id`` + FK ``fk_scraped_listings_parcel_id_parcels``
  * ``opportunities.parcel_conflicts_ack`` (dead reconciliation ack column)
  * ``projects.parcel_id`` + FK ``projects_parcel_id_fkey``

All parcel-derived property data (apn, address, lot/building sqft, year built,
property type) was previously moved onto ``opportunities`` own columns, so the
JSON export/import and KNN comps no longer read from these tables. ``project_parcels``
was already dropped in migration 0067.

KEPT intentionally: ``opportunities.apn`` / ``apn_normalized`` and any manual
jurisdiction fields (the jurisdiction stub). LoopNet/HelloData cleanups are
deferred (entangled with historical rows + live comps).

``downgrade()`` recreates the table/column *schema* only — the 446K parcel rows
are NOT restored (restore from the pre-drop pg_dump at /root/backups if needed).

Revision ID: 0113
Revises: 0112
Create Date: 2026-06-14
"""

from __future__ import annotations

from alembic import op


revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop FK-bearing columns first so ``parcels`` has no inbound references.
    # In PostgreSQL, dropping a column drops its FK constraint automatically.
    op.drop_column("opportunities", "parcel_conflicts_ack")
    op.drop_column("opportunities", "parcel_id")  # drops fk_scraped_listings_parcel_id_parcels
    op.drop_column("projects", "parcel_id")  # drops projects_parcel_id_fkey

    # parcel_transformations FK targets opportunities (not parcels); drop the
    # leaf table, then the now-unreferenced parcels table.
    op.drop_table("parcel_transformations")
    op.drop_table("parcels")


def downgrade() -> None:
    # Schema-only restore (no data). Recreate parcels with its full column set,
    # constraints, and indexes exactly as captured from production pre-drop.
    op.execute(
        """
        CREATE TABLE public.parcels (
            id uuid NOT NULL,
            apn character varying(100) NOT NULL,
            address_normalized text,
            address_raw text,
            owner_name character varying(255),
            owner_mailing_address text,
            lot_sqft numeric(18,6),
            zoning_code character varying(50),
            zoning_description text,
            current_use character varying(255),
            assessed_value_land numeric(18,6),
            assessed_value_improvements numeric(18,6),
            year_built integer,
            building_sqft numeric(18,6),
            unit_count integer,
            geometry json,
            scraped_at timestamp with time zone,
            last_updated timestamp with time zone DEFAULT now(),
            state_id character varying(100),
            owner_street text,
            owner_city character varying(120),
            owner_state character varying(20),
            owner_zip character varying(20),
            gis_acres numeric(18,8),
            total_assessed_value numeric(18,6),
            tax_code character varying(50),
            legal_description text,
            county character varying(120),
            jurisdiction character varying(120),
            priority_bucket character varying(30),
            latitude numeric(10,7),
            longitude numeric(10,7),
            postal_city character varying(120),
            zip_code character varying(20),
            unincorporated_community character varying(120),
            neighborhood character varying(120),
            address_unit character varying(100),
            building_id character varying(100),
            street_full_name character varying(255),
            street_number integer,
            is_residential boolean,
            is_mailable boolean,
            address_stage character varying(50),
            place_type character varying(100),
            landmark_name character varying(255),
            address_placement character varying(50),
            elevation_ft integer,
            address_source_updated_at timestamp with time zone,
            address_effective_at timestamp with time zone,
            address_expires_at timestamp with time zone,
            nguid character varying(200),
            discrepancy_agency_id character varying(200),
            esn character varying(50),
            msag_community character varying(120),
            sale_price integer,
            sale_date character varying(6),
            state_class character varying(10),
            ortaxlot character varying(50),
            primary_account_num character varying(20),
            alt_account_num character varying(20),
            rlis_land_use character varying(10),
            rlis_taxcode character varying(20),
            zoning_lookup_url character varying(500),
            enterprise_zone_name character varying(120),
            cultural_sensitivity character varying(120),
            apn_normalized character varying(100)
        )
        """
    )
    op.execute(
        "ALTER TABLE ONLY public.parcels ADD CONSTRAINT parcels_pkey PRIMARY KEY (id)"
    )
    op.execute(
        "ALTER TABLE ONLY public.parcels ADD CONSTRAINT parcels_apn_key UNIQUE (apn)"
    )
    for idx, col in [
        ("ix_parcels_apn_normalized", "apn_normalized"),
        ("ix_parcels_enterprise_zone_name", "enterprise_zone_name"),
        ("ix_parcels_gis_acres", "gis_acres"),
        ("ix_parcels_jurisdiction", "jurisdiction"),
        ("ix_parcels_latitude", "latitude"),
        ("ix_parcels_longitude", "longitude"),
        ("ix_parcels_ortaxlot", "ortaxlot"),
        ("ix_parcels_postal_city", "postal_city"),
        ("ix_parcels_priority_bucket", "priority_bucket"),
        ("ix_parcels_state_class", "state_class"),
        ("ix_parcels_year_built", "year_built"),
        ("ix_parcels_zip_code", "zip_code"),
        ("ix_parcels_zoning_code", "zoning_code"),
    ]:
        op.execute(f"CREATE INDEX {idx} ON public.parcels USING btree ({col})")
    op.execute(
        "CREATE UNIQUE INDEX ix_parcels_nguid ON public.parcels "
        "USING btree (nguid) WHERE (nguid IS NOT NULL)"
    )

    op.execute(
        """
        CREATE TABLE public.parcel_transformations (
            id uuid NOT NULL,
            project_id uuid NOT NULL,
            transformation_type character varying(50) NOT NULL,
            input_apns text[] NOT NULL,
            output_apns text[],
            effective_lot_sqft numeric(18,6),
            notes text,
            effective_date date
        )
        """
    )
    op.execute(
        "ALTER TABLE ONLY public.parcel_transformations "
        "ADD CONSTRAINT parcel_transformations_pkey PRIMARY KEY (id)"
    )
    op.execute(
        "ALTER TABLE ONLY public.parcel_transformations "
        "ADD CONSTRAINT fk_parcel_transformations_project_id "
        "FOREIGN KEY (project_id) REFERENCES public.opportunities(id) ON DELETE CASCADE"
    )

    # Re-add the FK columns on opportunities / projects.
    op.execute("ALTER TABLE public.opportunities ADD COLUMN parcel_id uuid")
    op.execute(
        "ALTER TABLE ONLY public.opportunities "
        "ADD CONSTRAINT fk_scraped_listings_parcel_id_parcels "
        "FOREIGN KEY (parcel_id) REFERENCES public.parcels(id)"
    )
    op.execute("ALTER TABLE public.opportunities ADD COLUMN parcel_conflicts_ack jsonb")
    op.execute("ALTER TABLE public.projects ADD COLUMN parcel_id uuid")
    op.execute(
        "ALTER TABLE ONLY public.projects "
        "ADD CONSTRAINT projects_parcel_id_fkey "
        "FOREIGN KEY (parcel_id) REFERENCES public.parcels(id)"
    )
