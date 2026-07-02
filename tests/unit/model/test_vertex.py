import pytest

from graph_core.model.vertex import Vertex


def test_vertex_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Vertex("v1")


class DummyVertex(Vertex):
    tag = "dummy"


def test_subclass_with_tag_can_be_instantiated():
    v = DummyVertex("v1", {"name": "Alice"})
    assert v.vid == "v1"
    assert v.properties == {"name": "Alice"}
    assert v.tag == "dummy"


def test_properties_default_to_empty_dict():
    v = DummyVertex("v1")
    assert v.properties == {}


def test_default_validate_is_noop():
    v = DummyVertex("v1")
    v.validate()
