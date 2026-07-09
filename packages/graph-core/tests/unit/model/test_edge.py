import pytest

from graph_core.model.edge import Edge


def test_edge_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Edge("a", "b")


class DummyEdge(Edge):
    edge_type = "dummy_edge"


def test_subclass_with_edge_type_can_be_instantiated():
    e = DummyEdge("a", "b", rank=2, properties={"weight": 1.0})
    assert e.src == "a"
    assert e.dst == "b"
    assert e.rank == 2
    assert e.properties == {"weight": 1.0}
    assert e.edge_type == "dummy_edge"


def test_rank_and_properties_default():
    e = DummyEdge("a", "b")
    assert e.rank == 0
    assert e.properties == {}


def test_default_validate_is_noop():
    e = DummyEdge("a", "b")
    e.validate()
