"""Non-generic edge CRUD primitives.

Mirrors VertexOperations: future domain repositories compose this rather
than inheriting from a generic repository base class.
"""

from __future__ import annotations

from typing import Any, Optional, Type

from graph_core.exceptions import SchemaError
from graph_core.model.edge import Edge
from graph_core.query.builder import (
    build_delete_edge,
    build_fetch_edge,
    build_insert_edge,
    build_insert_edges,
)
from graph_core.schema.registry import SchemaRegistry
from graph_core.storage.executor import QueryExecutor
from graph_core.storage.result import RawEdge


class EdgeOperations:
    """Edge CRUD primitives, operating on any Edge subclass via SchemaRegistry."""

    def __init__(self, executor: QueryExecutor, registry: SchemaRegistry) -> None:
        self._executor = executor
        self._registry = registry

    def create(self, edge: Edge) -> None:
        edge.validate()
        ngql = build_insert_edge(edge.edge_type, edge.src, edge.dst, edge.rank, edge.properties)
        self._executor.execute(ngql)

    def get(self, edge_type: str, src: str, dst: str, rank: int = 0) -> Optional[Edge]:
        ngql = build_fetch_edge(edge_type, src, dst, rank)
        result = self._executor.execute(ngql)
        row = result.single_row()
        if row is None:
            return None
        raw = row.get("e")
        if not isinstance(raw, RawEdge):
            return None
        return self._to_domain(raw)

    def delete(self, edge_type: str, src: str, dst: str, rank: int = 0) -> None:
        ngql = build_delete_edge(edge_type, src, dst, rank)
        self._executor.execute(ngql)

    def create_many(
        self, edge_type: str, rows: list[tuple[str, str, int, dict[str, Any]]]
    ) -> None:
        """Bulk-insert edges of one edge type in a single round trip.

        Schema-agnostic: operates on raw (src, dst, rank, properties) tuples
        rather than Edge instances, for the same reason as
        VertexOperations.create_many(). All rows must share the same
        property columns. No-op for an empty list.
        """
        if not rows:
            return
        ngql = build_insert_edges(edge_type, rows)
        self._executor.execute(ngql)

    def _to_domain(self, raw: RawEdge) -> Edge:
        edge_cls: Type[Edge] | None = self._registry.get_edge_class(raw.edge_type)
        if edge_cls is None:
            raise SchemaError(f"No Edge class registered for edge type {raw.edge_type!r}")
        return edge_cls(src=raw.src, dst=raw.dst, rank=raw.rank, properties=raw.properties)
