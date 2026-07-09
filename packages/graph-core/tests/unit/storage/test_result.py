from graph_core.storage.result import QueryResult, RawEdge, RawPath, RawVertex


def test_raw_vertex_defaults():
    v = RawVertex(vid="v1")
    assert v.tags == {}


def test_raw_edge_holds_fields():
    e = RawEdge(src="a", dst="b", edge_type="owns", rank=0, properties={"since": 2020})
    assert e.src == "a"
    assert e.dst == "b"
    assert e.edge_type == "owns"
    assert e.rank == 0
    assert e.properties == {"since": 2020}


def test_raw_path_defaults():
    p = RawPath()
    assert p.vertices == []
    assert p.edges == []


def test_query_result_is_empty_true_when_no_rows():
    result = QueryResult(column_names=["id"], rows=[])
    assert result.is_empty() is True
    assert result.single_row() is None


def test_query_result_is_empty_false_and_single_row():
    result = QueryResult(column_names=["id"], rows=[{"id": 1}, {"id": 2}])
    assert result.is_empty() is False
    assert result.single_row() == {"id": 1}
