"""SchemaRegistry: the extension point mapping tag/edge-type names to Python classes.

Future domain packages call register_vertex()/register_edge() at import
time to make their Vertex/Edge subclasses resolvable during
deserialization.
"""

from __future__ import annotations

from graph_core.exceptions import SchemaError
from graph_core.model.edge import Edge
from graph_core.model.vertex import Vertex


class SchemaRegistry:
    _vertex_classes: dict[str, type[Vertex]] = {}
    _edge_classes: dict[str, type[Edge]] = {}

    @classmethod
    def register_vertex(cls, tag: str, vertex_cls: type[Vertex]) -> None:
        if tag in cls._vertex_classes:
            raise SchemaError(f"Vertex tag {tag!r} is already registered")
        cls._vertex_classes[tag] = vertex_cls

    @classmethod
    def register_edge(cls, edge_type: str, edge_cls: type[Edge]) -> None:
        if edge_type in cls._edge_classes:
            raise SchemaError(f"Edge type {edge_type!r} is already registered")
        cls._edge_classes[edge_type] = edge_cls

    @classmethod
    def get_vertex_class(cls, tag: str) -> type[Vertex] | None:
        return cls._vertex_classes.get(tag)

    @classmethod
    def get_edge_class(cls, edge_type: str) -> type[Edge] | None:
        return cls._edge_classes.get(edge_type)
