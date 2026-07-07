"""Traversal: graph-navigation operations.

get_neighbors() was the only traversal operation built at first — more
advanced graph algorithms (shortest path, subgraph extraction, PageRank,
etc.) remain explicitly deferred until a real consumer needs them.
count_neighbors() (degree, for "expand this node?" UX) and scan_vertices()
(full tag scan, for building an app-level search corpus without a
NebulaGraph full-text/ES dependency) were added for the Graph Explorer
consumer.
"""

from __future__ import annotations

from typing import Optional

from graph_core.query.builder import (
    build_count_neighbors,
    build_go_neighbors,
    build_scan_vertices,
)
from graph_core.storage.executor import QueryExecutor
from graph_core.storage.result import RawVertex


class Traversal:
    def __init__(self, executor: QueryExecutor) -> None:
        self._executor = executor

    def get_neighbors(
        self, vid: str, edge_type: Optional[str] = None, direction: str = "out"
    ) -> list[RawVertex]:
        ngql = build_go_neighbors(vid, edge_type, direction)
        result = self._executor.execute(ngql)
        neighbors: list[RawVertex] = []
        for row in result.rows:
            vertex = row.get("v")
            if isinstance(vertex, RawVertex):
                neighbors.append(vertex)
        return neighbors

    def count_neighbors(
        self, vid: str, edge_type: Optional[str] = None, direction: str = "out"
    ) -> int:
        """Count distinct neighbors without hydrating full vertex data."""
        ngql = build_count_neighbors(vid, edge_type, direction)
        result = self._executor.execute(ngql)
        return len(result.rows)

    def scan_vertices(self, tag: str, limit: Optional[int] = None) -> list[RawVertex]:
        """Fetch every vertex of a tag. No index required (full tag scan)."""
        ngql = build_scan_vertices(tag, limit)
        result = self._executor.execute(ngql)
        return [row["v"] for row in result.rows if isinstance(row.get("v"), RawVertex)]
