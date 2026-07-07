def _create_graph(client, name="G"):
    return client.post("/api/graphs", json={"name": name}).json()


def test_upload_edge_list_csv_creates_vertices_and_edges(client):
    graph = _create_graph(client)
    csv_bytes = (
        b"source,target,relationship\n"
        b"Alice,Bob,friend\n"
        b"Bob,Cara,coworker\n"
        b"Alice,Cara,friend\n"
    )

    resp = client.post(
        f"/api/graphs/{graph['id']}/imports",
        files={"file": ("friends.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] == "done"
    report = job["report"]
    assert report["structure_kind"] == "edge_list"
    assert report["rows_read"] == 3
    assert report["vertices_created"] == 3  # Alice, Bob, Cara
    assert report["edges_created"] == 3
    assert report["validation_errors"] == []

    # Poll endpoint returns the same job.
    resp = client.get(f"/api/graphs/{graph['id']}/imports/{job['job_id']}")
    assert resp.status_code == 200
    assert resp.json()["report"]["vertices_created"] == 3

    # Graph stats were updated.
    detail = client.get(f"/api/graphs/{graph['id']}").json()
    assert detail["vertex_count"] == 3
    assert detail["edge_count"] == 3
    assert set(detail["edge_types"]) == {"FRIEND", "COWORKER"}


def test_upload_node_table_csv_creates_vertices_only(client):
    graph = _create_graph(client)
    csv_bytes = b"id,name,age\n1,Alice,30\n2,Bob,40\n"

    resp = client.post(
        f"/api/graphs/{graph['id']}/imports",
        files={"file": ("people.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 202
    report = resp.json()["report"]
    assert report["structure_kind"] == "node_table"
    assert report["vertices_created"] == 2
    assert report["edges_created"] == 0


def test_upload_to_unknown_graph_is_404(client):
    resp = client.post(
        "/api/graphs/does_not_exist/imports",
        files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert resp.status_code == 404
