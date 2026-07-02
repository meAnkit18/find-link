import pytest

from graph_core.query.builder import (
    build_delete_edge,
    build_delete_vertex,
    build_fetch_edge,
    build_fetch_vertex,
    build_go_neighbors,
    build_insert_edge,
    build_insert_vertex,
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
