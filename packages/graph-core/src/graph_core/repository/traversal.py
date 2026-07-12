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

from graph_core.query.builder import (
    build_count_neighbors,
    build_find_shortest_path,
    build_go_neighbors,
    build_go_neighbors_with_edges,
    build_scan_vertices,
)
from graph_core.storage.executor import QueryExecutor
from graph_core.storage.result import RawEdge, RawPath, RawVertex


class Traversal:
    def __init__(self, executor: QueryExecutor) -> None:
        self._executor = executor

    def get_neighbors(
        self, vid: str, edge_type: str | None = None, direction: str = "out"
    ) -> list[RawVertex]:
        ngql = build_go_neighbors(vid, edge_type, direction)
        result = self._executor.execute(ngql)
        neighbors: list[RawVertex] = []
        for row in result.rows:
            vertex = row.get("v")
            if isinstance(vertex, RawVertex):
                neighbors.append(vertex)
        return neighbors

    def get_neighbors_with_edges(
        self, vid: str, edge_type: str | None = None, direction: str = "out"
    ) -> tuple[list[RawVertex], list[RawEdge]]:
        """Fetch neighbors and the edges connecting to them."""
        ngql = build_go_neighbors_with_edges(vid, edge_type, direction)
        result = self._executor.execute(ngql)
        neighbor_ids: list[str] = []
        edges: list[RawEdge] = []
        seen_edges: set[tuple[str, str, str, int]] = set()
        for row in result.rows:
            neighbor_id = row.get("id")
            if neighbor_id is not None and isinstance(neighbor_id, str):
                if neighbor_id not in neighbor_ids:
                    neighbor_ids.append(neighbor_id)
            raw_edge = row.get("e")
            if isinstance(raw_edge, RawEdge):
                key = (raw_edge.edge_type, raw_edge.src, raw_edge.dst, raw_edge.rank)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append(raw_edge)
        # Fetch full vertex data for all neighbors
        vertices: list[RawVertex] = []
        from graph_core.query.builder import build_fetch_vertices
        if neighbor_ids:
            fetch_ngql = build_fetch_vertices(neighbor_ids)
            fetch_result = self._executor.execute(fetch_ngql)
            for fetch_row in fetch_result.rows:
                raw_v = fetch_row.get("v")
                if isinstance(raw_v, RawVertex):
                    vertices.append(raw_v)
        return vertices, edges

    def count_neighbors(
        self, vid: str, edge_type: str | None = None, direction: str = "out"
    ) -> int:
        """Count distinct neighbors without hydrating full vertex data."""
        ngql = build_count_neighbors(vid, edge_type, direction)
        result = self._executor.execute(ngql)
        return len(result.rows)

    def scan_vertices(self, tag: str, limit: int | None = None) -> list[RawVertex]:
        """Fetch every vertex of a tag. No index required (full tag scan)."""
        ngql = build_scan_vertices(tag, limit)
        result = self._executor.execute(ngql)
        return [row["v"] for row in result.rows if isinstance(row.get("v"), RawVertex)]

    def shortest_path(
        self, source_vid: str, target_vid: str, max_steps: int = 5, edge_type: str | None = None
    ) -> list[RawPath]:
        ngql = build_find_shortest_path(source_vid, target_vid, max_steps, edge_type)
        result = self._executor.execute(ngql)
        paths: list[RawPath] = []
        for row in result.rows:
            path = row.get("p")
            if isinstance(path, RawPath):
                paths.append(path)
        return paths
