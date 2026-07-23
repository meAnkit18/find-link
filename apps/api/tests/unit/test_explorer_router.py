from types import SimpleNamespace

import pytest


@pytest.fixture
def graph_with_data(client, fake_clients):
    """Seed the fake graph store directly (the CSV import route was removed
    in text-only mode, so tests no longer go through it)."""
    graph = client.post("/api/graphs", json={"name": "G"}).json()
    fake = fake_clients.for_space(graph["id"])
    fake.metadata.create_tag(SimpleNamespace(name="entity"))
    fake.metadata.create_edge_type(SimpleNamespace(name="FRIEND"))
    fake.metadata.create_edge_type(SimpleNamespace(name="COWORKER"))
    fake.vertices.create_many(
        "entity", [(n, {"label": n}) for n in ("Alice", "Bob", "Cara")]
    )
    fake.edges.create_many("FRIEND", [("Alice", "Bob", 0, {}), ("Alice", "Cara", 0, {})])
    fake.edges.create_many("COWORKER", [("Bob", "Cara", 0, {})])
    return graph


def test_schema_lists_tags_and_edge_types(client, graph_with_data):
    resp = client.get(f"/api/graphs/{graph_with_data['id']}/schema")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tags"] == ["entity"]
    assert set(body["edge_types"]) == {"FRIEND", "COWORKER"}


def test_search_finds_by_label_substring(client, graph_with_data):
    resp = client.get(f"/api/graphs/{graph_with_data['id']}/search", params={"q": "ali"})
    assert resp.status_code == 200
    results = resp.json()
    assert [r["label"] for r in results] == ["Alice"]


def test_search_empty_query_returns_everything_up_to_limit(client, graph_with_data):
    resp = client.get(f"/api/graphs/{graph_with_data['id']}/search", params={"q": ""})
    labels = {r["label"] for r in resp.json()}
    assert labels == {"Alice", "Bob", "Cara"}


def test_node_detail_includes_degree_per_edge_type(client, graph_with_data):
    resp = client.get(f"/api/graphs/{graph_with_data['id']}/nodes/Alice")
    assert resp.status_code == 200
    body = resp.json()
    assert body["vid"] == "Alice"
    assert body["label"] == "Alice"
    degree_by_type = {(d["edge_type"], d["direction"]): d["count"] for d in body["degree"]}
    assert degree_by_type[("FRIEND", "out")] == 2  # Bob and Cara


def test_node_detail_404_for_unknown_vid(client, graph_with_data):
    resp = client.get(f"/api/graphs/{graph_with_data['id']}/nodes/Nobody")
    assert resp.status_code == 404


def test_neighbors_returns_connected_nodes(client, graph_with_data):
    resp = client.get(
        f"/api/graphs/{graph_with_data['id']}/nodes/Alice/neighbors",
        params={"edge_type": "FRIEND", "direction": "out"},
    )
    assert resp.status_code == 200
    labels = {n["label"] for n in resp.json()}
    assert labels == {"Bob", "Cara"}


def test_overview_returns_sampled_subgraph(client, graph_with_data):
    resp = client.get(f"/api/graphs/{graph_with_data['id']}/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert {n["label"] for n in body["nodes"]} == {"Alice", "Bob", "Cara"}
    assert len(body["edges"]) == 3
