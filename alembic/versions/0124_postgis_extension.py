"""Enable PostGIS. Nothing else — this migration is deliberately alone.

FLATS stores lot polygons, buildable envelopes and generated site plans, and the
map view serves them as vector tiles. Without PostGIS that means WKB in bytea
with no spatial index and GeoJSON over the wire, which is unpleasant at 300k
lots. With it, viewport queries and ``ST_AsMVT`` are one query.

The image swap that accompanies this (``postgres:16`` -> ``postgis/postgis:16-3.5``
in docker-compose.yml) keeps the same PostgreSQL major version, so the existing
data directory is used as-is — the PostGIS image is the official postgres image
with the extension binaries added. The container is recreated against the same
named volume; no dump/restore.

Ordering matters for the deploy that first applies this: the postgres container
must be recreated on the new image *before* alembic runs, or the extension
binaries will not be on disk when ``CREATE EXTENSION`` executes. Subsequent
deploys are unaffected — the statement is idempotent.

Reversible on purpose: this ships before any geometry column exists, so the
downgrade is a clean ``DROP EXTENSION``. Once a table holds a geometry column
that stops being true, and the downgrade will refuse rather than cascade.

Revision ID: 0124
Revises: 0123
"""

from alembic import op

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    # No CASCADE. If something depends on the extension, dropping it silently
    # would take that dependent object with it; failing loudly is correct.
    op.execute("DROP EXTENSION IF EXISTS postgis")
