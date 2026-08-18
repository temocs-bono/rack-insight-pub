"""Guard: SQLAlchemy models and Alembic migrations must stay in sync.

If this test fails, a model was changed without creating a migration.
Fix it with:

    cd backend
    alembic revision --autogenerate -m "describe the change"
    alembic upgrade head
"""
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import config as app_config
import models  # noqa: F401  (register every model on the metadata)
from database.session import Base

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Structural drift we refuse to ship without a migration. Constraint/index
# tweaks are excluded to avoid dialect-specific noise on SQLite.
SIGNIFICANT_DIFFS = {"add_table", "remove_table", "add_column", "remove_column"}


def _diff_kind(diff: object) -> str:
    entry = diff[0] if isinstance(diff, list) else diff
    return str(entry[0])


@pytest.fixture()
def migrated_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = tmp_path / "migration_check.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    app_config.get_settings.cache_clear()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")

    yield f"sqlite:///{db_path}"

    app_config.get_settings.cache_clear()


def test_migrations_match_models(migrated_db_url: str) -> None:
    engine = create_engine(migrated_db_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": False}
            )
            diffs = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    drift = [d for d in diffs if _diff_kind(d) in SIGNIFICANT_DIFFS]
    assert not drift, (
        "Models and Alembic migrations are out of sync. "
        "Create a migration: alembic revision --autogenerate -m '...' "
        f"Drift detected: {drift}"
    )


def test_migrations_up_and_down(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every migration must be reversible down to base and back."""
    db_path = tmp_path / "updown.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    app_config.get_settings.cache_clear()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    app_config.get_settings.cache_clear()


def test_adopts_partial_create_all_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: pre-Alembic create_all startups created the NEW TABLES
    (credentials, collector_runs) but not the NEW COLUMNS (clusters.site,
    devices.orientation, ...). Startup migration must adopt that mixed state
    without DuplicateTable crashes."""
    import asyncio
    import sqlite3

    from database.migrations import run_migrations

    db_path = tmp_path / "partial.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    app_config.get_settings.cache_clear()

    # 1) Old schema at revision 0001...
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "0001")

    # 2) ...plus the new tables exactly as the pre-Alembic create_all shipped
    #    them at the time (no later columns), and no alembic bookkeeping.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE credentials ("
        "id CHAR(32) PRIMARY KEY, created_at TIMESTAMP, updated_at TIMESTAMP,"
        "name VARCHAR(128) UNIQUE NOT NULL, credential_type VARCHAR(16) NOT NULL,"
        "username VARCHAR(128), password_encrypted VARCHAR(512), description TEXT)"
    )
    conn.execute(
        "CREATE TABLE collector_runs ("
        "id CHAR(32) PRIMARY KEY, created_at TIMESTAMP, updated_at TIMESTAMP,"
        "device_id CHAR(32) NOT NULL REFERENCES devices(id),"
        "success BOOLEAN NOT NULL, duration_ms INTEGER NOT NULL,"
        "snapshot_id CHAR(32) REFERENCES snapshots(id), message TEXT, trigger TEXT)"
    )
    conn.execute("DROP TABLE alembic_version")
    conn.execute(
        "INSERT INTO clusters (id, name, created_at, updated_at) "
        "VALUES ('1111', 'Legacy', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()

    # 3) Startup migration must adopt and upgrade it in place.
    asyncio.run(run_migrations())

    conn = sqlite3.connect(db_path)
    cluster_columns = [r[1] for r in conn.execute("PRAGMA table_info(clusters)")]
    # devices was renamed to rack_device_instances at revision 0006.
    instance_columns = [
        r[1] for r in conn.execute("PRAGMA table_info(rack_device_instances)")
    ]
    revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    preserved = conn.execute("SELECT name FROM clusters").fetchone()[0]
    conn.close()

    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(config).get_current_head()
    assert "site" in cluster_columns
    assert "orientation" in instance_columns
    assert "redfish_credential_id" in instance_columns
    assert "template_id" in instance_columns
    assert revision == head
    assert preserved == "Legacy"

    app_config.get_settings.cache_clear()


def test_adopts_full_create_all_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A create_all database from the last pre-Alembic release (0002 schema)
    must be stamped at 0002 — never head — so later migrations still apply."""
    import asyncio
    import sqlite3

    from alembic.script import ScriptDirectory

    from database.migrations import run_migrations

    db_path = tmp_path / "full_legacy.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    app_config.get_settings.cache_clear()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "0002")

    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE alembic_version")
    conn.commit()
    conn.close()

    asyncio.run(run_migrations())

    conn = sqlite3.connect(db_path)
    run_columns = [r[1] for r in conn.execute("PRAGMA table_info(collector_runs)")]
    revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    conn.close()

    head = ScriptDirectory.from_config(config).get_current_head()
    assert "error_code" in run_columns, "0003 must run on adopted legacy databases"
    assert revision == head

    app_config.get_settings.cache_clear()
