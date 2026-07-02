"""Traversal: graph-navigation operations.

get_neighbors() is the only traversal operation built now — more advanced
graph algorithms (shortest path, subgraph extraction, PageRank, etc.) are
explicitly deferred until a real consumer needs them.
"""

from __future__ import annotations

from typing import Optional

from graph_core.query.builder import build_go_neighbors
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
