import pytest

from graph_core.query.builder import (
    build_count_neighbors,
    build_delete_edge,
    build_delete_vertex,
    build_fetch_edge,
    build_fetch_vertex,
    build_fetch_vertices,
    build_go_neighbors,
    build_insert_edge,
    build_insert_edges,
    build_insert_vertex,
    build_insert_vertices,
    build_scan_vertices,
    build_upsert_vertex,
)


def test_build_insert_vertex():
    ngql = build_insert_vertex("person", "v1", {"name": "Alice", "age": 30})
    assert ngql == 'INSERT VERTEX person(name, age) VALUES "v1":("Alice", 30)'


def test_build_insert_vertex_rejects_bad_tag():
    with pytest.raises(ValueError):
        build_insert_vertex("bad-tag", "v1", {"name": "Alice"})


def test_build_upsert_vertex():
    ngql = build_upsert_vertex("person", "v1", {"age": 31})
    assert ngql == 'UPSERT VERTEX ON person "v1" SET person.age = 31'


def test_build_fetch_vertex():
    ngql = build_fetch_vertex("person", "v1")
    assert ngql == 'FETCH PROP ON person "v1" YIELD VERTEX AS v'


def test_build_delete_vertex():
    ngql = build_delete_vertex("v1")
    assert ngql == 'DELETE VERTEX "v1"'


def test_build_insert_edge():
    ngql = build_insert_edge("owns", "a", "b", 0, {"since": 2020})
    assert ngql == 'INSERT EDGE owns(since) VALUES "a"->"b"@0:(2020)'


def test_build_fetch_edge():
    ngql = build_fetch_edge("owns", "a", "b", 0)
    assert ngql == 'FETCH PROP ON owns "a"->"b"@0 YIELD EDGE AS e'


def test_build_delete_edge():
    ngql = build_delete_edge("owns", "a", "b", 0)
    assert ngql == 'DELETE EDGE owns "a"->"b"@0'


def test_build_go_neighbors_out():
    ngql = build_go_neighbors("v1", "owns", "out")
    assert ngql == (
        'GO FROM "v1" OVER owns YIELD DISTINCT dst(edge) AS id '
        '| FETCH PROP ON * $-.id YIELD VERTEX AS v'
    )


def test_build_go_neighbors_in():
    ngql = build_go_neighbors("v1", "owns", "in")
    assert "REVERSELY" in ngql


def test_build_go_neighbors_both_any_edge_type():
    ngql = build_go_neighbors("v1", None, "both")
    assert "OVER * BIDIRECT" in ngql


def test_build_go_neighbors_rejects_bad_direction():
    with pytest.raises(ValueError):
        build_go_neighbors("v1", "owns", "sideways")


def test_build_count_neighbors():
    ngql = build_count_neighbors("v1", "owns", "out")
    assert ngql == 'GO FROM "v1" OVER owns YIELD DISTINCT dst(edge) AS id'


def test_build_count_neighbors_any_edge_type_reverse():
    ngql = build_count_neighbors("v1", None, "in")
    assert ngql == 'GO FROM "v1" OVER * REVERSELY YIELD DISTINCT dst(edge) AS id'


def test_build_insert_vertices_multi_row():
    ngql = build_insert_vertices(
        "person",
        [("v1", {"name": "Alice", "age": 30}), ("v2", {"name": "Bob", "age": 40})],
    )
    assert ngql == (
        'INSERT VERTEX person(name, age) VALUES '
        '"v1":("Alice", 30), "v2":("Bob", 40)'
    )


def test_build_insert_vertices_requires_rows():
    with pytest.raises(ValueError):
        build_insert_vertices("person", [])


def test_build_insert_vertices_rejects_mismatched_columns():
    with pytest.raises(ValueError):
        build_insert_vertices(
            "person", [("v1", {"name": "Alice"}), ("v2", {"age": 40})]
        )


def test_build_insert_edges_multi_row():
    ngql = build_insert_edges(
        "owns", [("a", "b", 0, {"since": 2020}), ("c", "d", 1, {"since": 2021})]
    )
    assert ngql == (
        'INSERT EDGE owns(since) VALUES "a"->"b"@0:(2020), "c"->"d"@1:(2021)'
    )


def test_build_insert_edges_requires_rows():
    with pytest.raises(ValueError):
        build_insert_edges("owns", [])


def test_build_fetch_vertices():
    ngql = build_fetch_vertices(["v1", "v2"])
    assert ngql == 'FETCH PROP ON * "v1", "v2" YIELD VERTEX AS v'


def test_build_fetch_vertices_requires_vids():
    with pytest.raises(ValueError):
        build_fetch_vertices([])


def test_build_scan_vertices():
    ngql = build_scan_vertices("person")
    assert ngql == (
        'LOOKUP ON person YIELD id(vertex) AS id | FETCH PROP ON * $-.id YIELD VERTEX AS v'
    )


def test_build_scan_vertices_with_limit():
    ngql = build_scan_vertices("person", limit=50)
    assert ngql == (
        'LOOKUP ON person YIELD id(vertex) AS id | LIMIT 50 '
        '| FETCH PROP ON * $-.id YIELD VERTEX AS v'
    )
