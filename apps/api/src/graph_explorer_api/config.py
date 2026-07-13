from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from graph_core.config import GraphConfig

ADMIN_SPACE = "graph_explorer_admin"


@dataclass(frozen=True)
class Settings:
    nebula_host: str
    nebula_port: int
    nebula_user: str
    nebula_password: str
    nebula_use_ssl: bool
    data_dir: Path
    database_url: str
    evidence_dir: str

    def build_config(self, space: str) -> GraphConfig:
        return GraphConfig(
            hosts=[(self.nebula_host, self.nebula_port)],
            user=self.nebula_user,
            password=self.nebula_password,
            space=space,
            use_ssl=self.nebula_use_ssl,
        )

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def registry_path(self) -> Path:
        return self.data_dir / "graphs.json"


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("GRAPH_EXPLORER_DATA_DIR", "./data")).resolve()
    settings = Settings(
        nebula_host=os.environ.get("NEBULA_HOST", "127.0.0.1"),
        nebula_port=int(os.environ.get("NEBULA_PORT", "9669")),
        nebula_user=os.environ.get("NEBULA_USER", "root"),
        nebula_password=os.environ.get("NEBULA_PASSWORD", "nebula"),
        nebula_use_ssl=os.environ.get("NEBULA_USE_SSL", "false").lower() == "true",
        data_dir=data_dir,
        database_url=os.environ.get("EVIDENCE_DATABASE_URL", "sqlite:///./evidence_store.db"),
        evidence_dir=os.environ.get("EVIDENCE_DIR", "./evidence_store"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    Path(settings.evidence_dir).mkdir(parents=True, exist_ok=True)
    return settings
