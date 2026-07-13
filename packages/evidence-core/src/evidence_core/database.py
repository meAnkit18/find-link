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
