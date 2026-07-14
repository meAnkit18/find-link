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

    class OtherPerson(Vertex):
        tag = "other"

    registry.register_vertex("person", Person)
    with pytest.raises(SchemaError):
        registry.register_vertex("person", OtherPerson)


def test_register_and_get_edge_class():
    registry = SchemaRegistry()
    registry.register_edge("owns", Owns)
    assert registry.get_edge_class("owns") is Owns


def test_get_edge_class_returns_none_when_unregistered():
    registry = SchemaRegistry()
    assert registry.get_edge_class("unknown") is None


def test_register_edge_twice_raises_schema_error():
    registry = SchemaRegistry()

    class OwnsOther(Edge):
        edge_type = "owns_other"

    registry.register_edge("owns", Owns)
    with pytest.raises(SchemaError):
        registry.register_edge("owns", OwnsOther)


def test_reregister_same_class_vertex_is_noop():
    registry = SchemaRegistry()
    registry.register_vertex("person", Person)
    registry.register_vertex("person", Person)  # should not raise
    assert registry.get_vertex_class("person") is Person


def test_reregister_same_class_edge_is_noop():
    registry = SchemaRegistry()
    registry.register_edge("owns", Owns)
    registry.register_edge("owns", Owns)  # should not raise
    assert registry.get_edge_class("owns") is Owns


def test_global_fallback_on_instance():
    registry = SchemaRegistry()
    SchemaRegistry.register_global_vertex("person", Person)
    assert registry.get_vertex_class("person") is Person


def test_instance_overrides_global():
    registry = SchemaRegistry()

    class CustomPerson(Vertex):
        tag = "custom"

    SchemaRegistry.register_global_vertex("custom", Person)
    registry.register_vertex("custom", CustomPerson)
    assert registry.get_vertex_class("custom") is CustomPerson
