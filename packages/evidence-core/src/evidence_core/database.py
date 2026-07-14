from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from evidence_core.config import get_settings

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    future=True,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and a 30 s busy timeout on every new SQLite connection.

    WAL allows concurrent readers without blocking on the writing pipeline
    thread, and the busy timeout prevents spurious "database is locked"
    errors when the ingest thread pool + API request threads hit SQLite at
    the same time.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def init_db() -> None:
    from evidence_core import db_models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """Lightweight, idempotent migrations for columns added after first release.

    create_all() only creates missing *tables*, not missing columns, so an
    existing evidence_store.db needs an ALTER TABLE for new fields.
    """
    from sqlalchemy import inspect

    inspector = inspect(engine)
    if "evidence" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("evidence")}
    if "cancel_requested" not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE evidence "
                "ADD COLUMN cancel_requested BOOLEAN NOT NULL DEFAULT 0"
            ))
