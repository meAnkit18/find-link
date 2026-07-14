"""SchemaRegistry: the extension point mapping tag/edge-type names to Python classes.

Domain packages call register_global_vertex()/register_global_edge() at import
time to make their Vertex/Edge subclasses resolvable across the process.

Each SchemaRegistry instance has its own isolated registries but falls back
to the process-wide global registry on lookup, so bootstrap-registered
classes remain visible everywhere.
"""

from __future__ import annotations

from graph_core.exceptions import SchemaError
from graph_core.model.edge import Edge
from graph_core.model.vertex import Vertex


class SchemaRegistry:
    _global_vertex: dict[str, type[Vertex]] = {}
    _global_edge: dict[str, type[Edge]] = {}

    def __init__(self) -> None:
        self._vertex_classes: dict[str, type[Vertex]] = {}
        self._edge_classes: dict[str, type[Edge]] = {}

    @classmethod
    def register_global_vertex(cls, tag: str, vertex_cls: type[Vertex]) -> None:
        existing = cls._global_vertex.get(tag)
        if existing is vertex_cls:
            return
        if existing is not None:
            raise SchemaError(f"Vertex tag {tag!r} is already registered")
        cls._global_vertex[tag] = vertex_cls

    @classmethod
    def register_global_edge(cls, edge_type: str, edge_cls: type[Edge]) -> None:
        existing = cls._global_edge.get(edge_type)
        if existing is edge_cls:
            return
        if existing is not None:
            raise SchemaError(f"Edge type {edge_type!r} is already registered")
        cls._global_edge[edge_type] = edge_cls

    def register_vertex(self, tag: str, vertex_cls: type[Vertex]) -> None:
        existing = self._vertex_classes.get(tag)
        if existing is vertex_cls:
            return
        if existing is not None:
            raise SchemaError(f"Vertex tag {tag!r} is already registered")
        self._vertex_classes[tag] = vertex_cls

    def register_edge(self, edge_type: str, edge_cls: type[Edge]) -> None:
        existing = self._edge_classes.get(edge_type)
        if existing is edge_cls:
            return
        if existing is not None:
            raise SchemaError(f"Edge type {edge_type!r} is already registered")
        self._edge_classes[edge_type] = edge_cls

    def get_vertex_class(self, tag: str) -> type[Vertex] | None:
        cls = self._vertex_classes.get(tag)
        if cls is not None:
            return cls
        return self._global_vertex.get(tag)

    def get_edge_class(self, edge_type: str) -> type[Edge] | None:
        cls = self._edge_classes.get(edge_type)
        if cls is not None:
            return cls
        return self._global_edge.get(edge_type)
