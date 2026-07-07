def test_create_list_get_delete_graph(client):
    resp = client.post("/api/graphs", json={"name": "My Graph"})
    assert resp.status_code == 201
    graph = resp.json()
    assert graph["name"] == "My Graph"
    assert graph["vertex_count"] == 0

    resp = client.get("/api/graphs")
    assert resp.status_code == 200
    assert [g["id"] for g in resp.json()] == [graph["id"]]

    resp = client.get(f"/api/graphs/{graph['id']}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["tags"] == []
    assert detail["edge_types"] == []

    resp = client.delete(f"/api/graphs/{graph['id']}")
    assert resp.status_code == 204

    resp = client.get(f"/api/graphs/{graph['id']}")
    assert resp.status_code == 404


def test_create_graph_rejects_empty_name(client):
    resp = client.post("/api/graphs", json={"name": "   "})
    assert resp.status_code == 422


def test_get_unknown_graph_is_404(client):
    resp = client.get("/api/graphs/does_not_exist")
    assert resp.status_code == 404
