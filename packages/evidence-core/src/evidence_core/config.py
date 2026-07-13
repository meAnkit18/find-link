from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    evidence_dir: str
    conf_auto_accept: float
    conf_review_min: float


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings(
            database_url=os.environ.get(
                "EVIDENCE_DATABASE_URL",
                "sqlite:///./evidence_store.db",
            ),
            evidence_dir=os.environ.get("EVIDENCE_DIR", "./evidence_store"),
            conf_auto_accept=float(os.environ.get("CONF_AUTO_ACCEPT", "0.85")),
            conf_review_min=float(os.environ.get("CONF_REVIEW_MIN", "0.50")),
        )
    return _settings
