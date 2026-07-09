"""SchemaRegistry: the extension point mapping tag/edge-type names to Python classes.

Future domain packages call register_vertex()/register_edge() at import
time to make their Vertex/Edge subclasses resolvable during
deserialization.
"""

from __future__ import annotations

from typing import Type

from graph_core.exceptions import SchemaError
from graph_core.model.edge import Edge
from graph_core.model.vertex import Vertex


class SchemaRegistry:
    def __init__(self) -> None:
        self._vertex_classes: dict[str, Type[Vertex]] = {}
        self._edge_classes: dict[str, Type[Edge]] = {}

    def register_vertex(self, tag: str, vertex_cls: Type[Vertex]) -> None:
        if tag in self._vertex_classes:
            raise SchemaError(f"Vertex tag {tag!r} is already registered")
        self._vertex_classes[tag] = vertex_cls

    def register_edge(self, edge_type: str, edge_cls: Type[Edge]) -> None:
        if edge_type in self._edge_classes:
            raise SchemaError(f"Edge type {edge_type!r} is already registered")
        self._edge_classes[edge_type] = edge_cls

    def get_vertex_class(self, tag: str) -> Type[Vertex] | None:
        return self._vertex_classes.get(tag)

    def get_edge_class(self, edge_type: str) -> Type[Edge] | None:
        return self._edge_classes.get(edge_type)
