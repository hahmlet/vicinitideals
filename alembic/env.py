"""Alembic environment — async-compatible with asyncpg."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so Alembic autogenerate can detect them
from app.models import Base  # noqa: F401  (also imports all sub-models)
from app.config import settings

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Schema filtering
#
# FLATS lives in the `flats` schema, so autogenerate has to look outside
# `public` (include_schemas=True). That makes it see PostGIS's own objects too,
# and since they are not in Base.metadata it would helpfully propose dropping
# them — taking the extension's coordinate-system catalog with it. Filter them.
# ---------------------------------------------------------------------------
_POSTGIS_TABLES = {"spatial_ref_sys", "geometry_columns", "geography_columns"}
_POSTGIS_SCHEMAS = {"tiger", "tiger_data", "topology"}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    if type_ == "table":
        if name in _POSTGIS_TABLES:
            return False
        if getattr(obj, "schema", None) in _POSTGIS_SCHEMAS:
            return False
    return True

# Override sqlalchemy.url from application settings
config.set_main_option("sqlalchemy.url", settings.database_url)


# ---------------------------------------------------------------------------
# Offline migrations (generate SQL without live DB connection)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (async)
# ---------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create async engine, acquire connection, run migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
