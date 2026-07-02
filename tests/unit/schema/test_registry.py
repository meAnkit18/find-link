import pytest

from graph_core.exceptions import SchemaError
from graph_core.model.edge import Edge
from graph_core.model.vertex import Vertex
from graph_core.schema.registry import SchemaRegistry


class Person(Vertex):
    tag = "person"


class Owns(Edge):
    edge_type = "owns"


def test_register_and_get_vertex_class():
    registry = SchemaRegistry()
    registry.register_vertex("person", Person)
    assert registry.get_vertex_class("person") is Person


def test_get_vertex_class_returns_none_when_unregistered():
    registry = SchemaRegistry()
    assert registry.get_vertex_class("unknown") is None


def test_register_vertex_twice_raises_schema_error():
    registry = SchemaRegistry()
    registry.register_vertex("person", Person)
    with pytest.raises(SchemaError):
        registry.register_vertex("person", Person)


def test_register_and_get_edge_class():
    registry = SchemaRegistry()
    registry.register_edge("owns", Owns)
    assert registry.get_edge_class("owns") is Owns


def test_get_edge_class_returns_none_when_unregistered():
    registry = SchemaRegistry()
    assert registry.get_edge_class("unknown") is None


def test_register_edge_twice_raises_schema_error():
    registry = SchemaRegistry()
    registry.register_edge("owns", Owns)
    with pytest.raises(SchemaError):
        registry.register_edge("owns", Owns)
