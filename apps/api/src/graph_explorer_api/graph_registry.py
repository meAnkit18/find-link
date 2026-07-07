"""Persisted registry of Graphs (id, display name, Nebula space, stats).

A Graph's real schema (tags/edge types) lives in NebulaGraph itself and is
read live via Metadata — this registry only stores what NebulaGraph has no
concept of: a human-friendly display name distinct from the space's
identifier-safe technical name, when it was created, and running
vertex/edge counts (so the UI can show graph size without a full scan).

Backed by a single JSON file rather than a second real database: the data
is small (one record per Graph the user has created) and Phase 1 is a
single-process, single-user tool — consistent with graph-core's own
"no premature optimization" stance.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class GraphStats:
    vertex_count: int = 0
    edge_count: int = 0


@dataclass
class Graph:
    id: str
    name: str
    created_at: str
    stats: GraphStats = field(default_factory=GraphStats)

    @property
    def space(self) -> str:
        """The NebulaGraph space name backing this Graph. Same value as id."""
        return self.id


def _new_space_name() -> str:
    # Nebula space/identifier names must match ^[A-Za-z_][A-Za-z0-9_]*$;
    # a uuid4-derived name sidesteps sanitizing arbitrary user-provided
    # display names and guarantees no collision.
    return f"graph_{uuid.uuid4().hex[:12]}"


class GraphRegistry:
    """Thread-safe, JSON-file-backed CRUD for Graph records."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._graphs: dict[str, Graph] = self._load()

    def _load(self) -> dict[str, Graph]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text())
        graphs: dict[str, Graph] = {}
        for item in raw:
            stats = GraphStats(**item.get("stats", {}))
            graphs[item["id"]] = Graph(
                id=item["id"], name=item["name"], created_at=item["created_at"], stats=stats
            )
        return graphs

    def _save(self) -> None:
        """Write via a temp file + atomic rename so a crash mid-write can't
        leave graphs.json truncated/corrupt."""
        payload = [
            {**asdict(g), "stats": asdict(g.stats)} for g in self._graphs.values()
        ]
        tmp_path = self._path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2))
        os.replace(tmp_path, self._path)

    def create(self, name: str) -> Graph:
        with self._lock:
            graph = Graph(
                id=_new_space_name(),
                name=name,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._graphs[graph.id] = graph
            self._save()
            return graph

    def list(self) -> list[Graph]:
        with self._lock:
            return sorted(self._graphs.values(), key=lambda g: g.created_at, reverse=True)

    def get(self, graph_id: str) -> Graph | None:
        with self._lock:
            return self._graphs.get(graph_id)

    def delete(self, graph_id: str) -> None:
        with self._lock:
            self._graphs.pop(graph_id, None)
            self._save()

    def add_stats(self, graph_id: str, vertices: int, edges: int) -> None:
        with self._lock:
            graph = self._graphs.get(graph_id)
            if graph is None:
                return
            graph.stats.vertex_count += vertices
            graph.stats.edge_count += edges
            self._save()
