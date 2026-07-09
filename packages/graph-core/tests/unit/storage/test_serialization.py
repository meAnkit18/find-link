from datetime import date, datetime

from graph_core.storage.result import RawEdge, RawPath, RawVertex
from graph_core.storage.serialization import (
    from_nebula_edge,
    from_nebula_path,
    from_nebula_vertex,
    from_value_wrapper,
    to_ngql_literal,
)
from tests.unit.storage.fakes import FakeNode, FakeRelationship, FakePath, FakeValueWrapper


def test_to_ngql_literal_none():
    assert to_ngql_literal(None) == "NULL"


def test_to_ngql_literal_bool():
    assert to_ngql_literal(True) == "true"
    assert to_ngql_literal(False) == "false"


def test_to_ngql_literal_number():
    assert to_ngql_literal(42) == "42"
    assert to_ngql_literal(3.14) == "3.14"


def test_to_ngql_literal_string_escapes_quotes_and_backslashes():
    assert to_ngql_literal('He said "hi"') == '"He said \\"hi\\""'
    assert to_ngql_literal("back\\slash") == '"back\\\\slash"'


def test_to_ngql_literal_datetime_and_date():
    assert to_ngql_literal(datetime(2024, 1, 2, 3, 4, 5)) == 'datetime("2024-01-02T03:04:05")'
    assert to_ngql_literal(date(2024, 1, 2)) == 'date("2024-01-02")'


def test_to_ngql_literal_list_and_dict():
    assert to_ngql_literal([1, "a"]) == '[1, "a"]'
    assert to_ngql_literal({"x": 1}) == "{x: 1}"


def test_to_ngql_literal_unsupported_type_raises():
    import pytest

    with pytest.raises(TypeError):
        to_ngql_literal(object())


def test_from_value_wrapper_scalars():
    assert from_value_wrapper(FakeValueWrapper(null=True)) is None
    assert from_value_wrapper(FakeValueWrapper(bool_=True)) is True
    assert from_value_wrapper(FakeValueWrapper(int_=7)) == 7
    assert from_value_wrapper(FakeValueWrapper(double_=1.5)) == 1.5
    assert from_value_wrapper(FakeValueWrapper(string_="hi")) == "hi"


def test_from_value_wrapper_list_and_map():
    wrapped_list = FakeValueWrapper(list_=[FakeValueWrapper(int_=1), FakeValueWrapper(int_=2)])
    assert from_value_wrapper(wrapped_list) == [1, 2]

    wrapped_map = FakeValueWrapper(map_={"a": FakeValueWrapper(int_=1)})
    assert from_value_wrapper(wrapped_map) == {"a": 1}


def test_from_nebula_vertex_decodes_tags_and_properties():
    node = FakeNode(
        vid="v1",
        tags={"person": {"name": FakeValueWrapper(string_="Alice")}},
    )
    raw = from_nebula_vertex(node)
    assert isinstance(raw, RawVertex)
    assert raw.vid == "v1"
    assert raw.tags == {"person": {"name": "Alice"}}


def test_from_nebula_edge_decodes_fields():
    relationship = FakeRelationship(
        src="a",
        dst="b",
        edge_type="owns",
        rank=1,
        properties={"since": FakeValueWrapper(int_=2020)},
    )
    raw = from_nebula_edge(relationship)
    assert isinstance(raw, RawEdge)
    assert raw.src == "a"
    assert raw.dst == "b"
    assert raw.edge_type == "owns"
    assert raw.rank == 1
    assert raw.properties == {"since": 2020}


def test_from_nebula_path_decodes_vertices_and_edges():
    node_a = FakeNode(vid="a", tags={})
    node_b = FakeNode(vid="b", tags={})
    relationship = FakeRelationship(src="a", dst="b", edge_type="owns", rank=0, properties={})
    path = FakePath(nodes=[node_a, node_b], relationships=[relationship])
    raw = from_nebula_path(path)
    assert isinstance(raw, RawPath)
    assert [v.vid for v in raw.vertices] == ["a", "b"]
    assert len(raw.edges) == 1
    assert raw.edges[0].edge_type == "owns"


def test_from_value_wrapper_vertex_and_edge():
    node = FakeNode(vid="v1", tags={})
    assert from_value_wrapper(FakeValueWrapper(vertex=node)) == RawVertex(vid="v1", tags={})

    relationship = FakeRelationship(src="a", dst="b", edge_type="owns", rank=0, properties={})
    assert from_value_wrapper(FakeValueWrapper(edge=relationship)) == RawEdge(
        src="a", dst="b", edge_type="owns", rank=0, properties={}
    )
