"""Startup schema migration.

On every application start, `run_migrations()` brings the database schema to
the latest Alembic revision (`upgrade head`). This replaces the previous
`Base.metadata.create_all`, which silently ignored new columns on existing
tables (e.g. clusters.site).

Databases created by older versions with create_all (no alembic_version
table) are adopted automatically at the revision matching their actual
schema (0001 without clusters.site, otherwise 0002 — the last create_all
release), then upgraded to head.
"""
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASELINE_REVISION = "0001"
# create_all was removed at revision 0002; a legacy database can never be
# newer than that, so adoption must stamp at most 0002 and then upgrade.
LEGACY_LATEST_REVISION = "0002"


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def _inspect_schema(connection: Connection) -> tuple[bool, bool, bool]:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    has_version_table = "alembic_version" in tables
    has_clusters = "clusters" in tables
    has_site = has_clusters and any(
        column["name"] == "site" for column in inspector.get_columns("clusters")
    )
    return has_version_table, has_clusters, has_site


async def run_migrations() -> None:
    """Bring the schema to the latest revision (idempotent)."""
    # Dedicated NullPool engine: inspection must not leave pooled connections
    # (and their driver worker threads) behind.
    inspect_engine = create_async_engine(
        get_settings().database_url, poolclass=pool.NullPool
    )
    try:
        async with inspect_engine.connect() as connection:
            has_version_table, has_clusters, has_site = await connection.run_sync(
                _inspect_schema
            )
    finally:
        await inspect_engine.dispose()

    config = _alembic_config()

    if not has_version_table and has_clusters:
        # Legacy database created via create_all: register it with Alembic
        # at the revision matching its actual schema, then upgrade normally.
        stamp_revision = LEGACY_LATEST_REVISION if has_site else BASELINE_REVISION
        logger.info(
            "Adopting legacy (create_all) database into Alembic at revision %s",
            stamp_revision,
        )
        await asyncio.to_thread(command.stamp, config, stamp_revision)

    logger.info("Applying database migrations (alembic upgrade head)")
    # command.upgrade is synchronous and env.py starts its own event loop,
    # so it must run in a worker thread.
    await asyncio.to_thread(command.upgrade, config, "head")
    logger.info("Database schema is up to date")
