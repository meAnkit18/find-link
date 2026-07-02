from graph_core.repository.traversal import Traversal
from graph_core.storage.result import QueryResult, RawVertex


class FakeExecutor:
    def __init__(self, response):
        self.executed = []
        self.response = response

    def execute(self, ngql):
        self.executed.append(ngql)
        return self.response


def test_get_neighbors_returns_raw_vertices():
    raw_a = RawVertex(vid="a", tags={"person": {"name": "Alice"}})
    raw_b = RawVertex(vid="b", tags={"person": {"name": "Bob"}})
    response = QueryResult(column_names=["v"], rows=[{"v": raw_a}, {"v": raw_b}])
    executor = FakeExecutor(response)
    traversal = Traversal(executor)
    neighbors = traversal.get_neighbors("v1", edge_type="owns", direction="out")
    assert neighbors == [raw_a, raw_b]
    assert executor.executed == [
        'GO FROM "v1" OVER owns YIELD DISTINCT dst(edge) AS id '
        '| FETCH PROP ON * $-.id YIELD VERTEX AS v'
    ]


def test_get_neighbors_ignores_non_vertex_rows():
    response = QueryResult(column_names=["v"], rows=[{"v": "not-a-vertex"}])
    executor = FakeExecutor(response)
    traversal = Traversal(executor)
    assert traversal.get_neighbors("v1") == []
