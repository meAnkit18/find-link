"""Non-generic vertex CRUD primitives.

Future domain repositories (e.g. a PersonRepository in an AML package)
compose this class as a dependency rather than inheriting from a generic
repository base class — that keeps this primitive simple while letting
domain repositories add whatever query methods they actually need.
"""

from __future__ import annotations

from typing import Optional, Type

from graph_core.exceptions import SchemaError
from graph_core.model.vertex import Vertex
from graph_core.query.builder import (
    build_delete_vertex,
    build_fetch_vertex,
    build_insert_vertex,
    build_upsert_vertex,
)
from graph_core.schema.registry import SchemaRegistry
from graph_core.storage.executor import QueryExecutor
from graph_core.storage.result import RawVertex


class VertexOperations:
    """Vertex CRUD primitives, operating on any Vertex subclass via SchemaRegistry."""

    def __init__(self, executor: QueryExecutor, registry: SchemaRegistry) -> None:
        self._executor = executor
        self._registry = registry

    def create(self, vertex: Vertex) -> None:
        vertex.validate()
        ngql = build_insert_vertex(vertex.tag, vertex.vid, vertex.properties)
        self._executor.execute(ngql)

    def upsert(self, vertex: Vertex) -> None:
        vertex.validate()
        ngql = build_upsert_vertex(vertex.tag, vertex.vid, vertex.properties)
        self._executor.execute(ngql)

    def get(self, tag: str, vid: str) -> Optional[Vertex]:
        ngql = build_fetch_vertex(tag, vid)
        result = self._executor.execute(ngql)
        row = result.single_row()
        if row is None:
            return None
        raw = row.get("v")
        if not isinstance(raw, RawVertex):
            return None
        return self._to_domain(raw)

    def delete(self, vid: str) -> None:
        ngql = build_delete_vertex(vid)
        self._executor.execute(ngql)

    def exists(self, tag: str, vid: str) -> bool:
        return self.get(tag, vid) is not None

    def _to_domain(self, raw: RawVertex) -> Vertex:
        vertex_cls: Type[Vertex] | None = None
        properties: dict = {}
        for tag_name, props in raw.tags.items():
            cls = self._registry.get_vertex_class(tag_name)
            if cls is not None:
                vertex_cls = cls
                properties = props
                break
        if vertex_cls is None:
            raise SchemaError(
                f"No Vertex class registered for any tag on vertex {raw.vid!r}: {list(raw.tags)}"
            )
        return vertex_cls(vid=raw.vid, properties=properties)
