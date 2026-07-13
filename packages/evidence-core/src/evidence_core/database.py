from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from evidence_core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def init_db() -> None:
    from evidence_core import db_models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """Lightweight, idempotent migrations for columns added after first release.

    create_all() only creates missing *tables*, not missing columns, so an
    existing evidence_store.db needs an ALTER TABLE for new fields.
    """
    from sqlalchemy import inspect, text

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
