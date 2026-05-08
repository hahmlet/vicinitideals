"""Add map_polygons table and seed from market_polygons.json.

Revision ID: 0074
Revises: 0073
Create Date: 2026-05-07
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_polygons",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("purpose", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("points", JSONB(), nullable=False),
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
    )

    # Seed from the existing market_polygons.json
    data_path = Path(__file__).parent.parent.parent / "app" / "data" / "market_polygons.json"
    try:
        with data_path.open(encoding="utf-8") as f:
            polygons = json.load(f)
    except Exception:
        return

    conn = op.get_bind()
    for poly in polygons:
        slug = poly.get("name", "")
        if not slug:
            continue
        name = slug.replace("_", " ").title()
        conn.execute(
            sa.text(
                """
                INSERT INTO map_polygons
                    (id, name, slug, is_active, purpose, description, points)
                VALUES
                    (:id, :name, :slug, :is_active, :purpose, :description, :points::jsonb)
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "name": name,
                "slug": slug,
                "is_active": bool(poly.get("is_active", True)),
                "purpose": poly.get("purpose"),
                "description": poly.get("description"),
                "points": json.dumps(poly.get("points", [])),
            },
        )


def downgrade() -> None:
    op.drop_table("map_polygons")
