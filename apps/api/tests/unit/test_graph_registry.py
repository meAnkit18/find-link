from graph_explorer_api.graph_registry import GraphRegistry


def test_create_list_get_delete_roundtrip(tmp_path):
    registry = GraphRegistry(tmp_path / "graphs.json")

    graph = registry.create("My Graph")
    assert graph.name == "My Graph"
    assert graph.space == graph.id

    assert [g.id for g in registry.list()] == [graph.id]
    assert registry.get(graph.id).name == "My Graph"

    registry.delete(graph.id)
    assert registry.get(graph.id) is None


def test_stats_persist_across_reload(tmp_path):
    path = tmp_path / "graphs.json"
    registry = GraphRegistry(path)
    graph = registry.create("G")
    registry.add_stats(graph.id, vertices=5, edges=3)
    registry.add_stats(graph.id, vertices=2, edges=1)

    reloaded = GraphRegistry(path)
    stored = reloaded.get(graph.id)
    assert stored.stats.vertex_count == 7
    assert stored.stats.edge_count == 4


def test_two_graphs_get_distinct_valid_space_names(tmp_path):
    registry = GraphRegistry(tmp_path / "graphs.json")
    a = registry.create("A")
    b = registry.create("B")
    assert a.id != b.id
    import re

    assert re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", a.id)
