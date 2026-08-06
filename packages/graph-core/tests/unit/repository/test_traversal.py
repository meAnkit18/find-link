from graph_core.repository.traversal import Traversal
from graph_core.storage.result import QueryResult, RawEdge, RawVertex


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
        'GO FROM "v1" OVER owns YIELD DISTINCT id($$) AS id '
        '| FETCH PROP ON * $-.id YIELD VERTEX AS v'
    ]


def test_get_neighbors_ignores_non_vertex_rows():
    response = QueryResult(column_names=["v"], rows=[{"v": "not-a-vertex"}])
    executor = FakeExecutor(response)
    traversal = Traversal(executor)
    assert traversal.get_neighbors("v1") == []


def test_count_neighbors_counts_result_rows():
    response = QueryResult(column_names=["id"], rows=[{"id": "a"}, {"id": "b"}])
    executor = FakeExecutor(response)
    traversal = Traversal(executor)
    assert traversal.count_neighbors("v1", edge_type="owns", direction="out") == 2
    assert executor.executed == ['GO FROM "v1" OVER owns YIELD DISTINCT id($$) AS id']


def test_scan_vertices_returns_raw_vertices():
    raw_a = RawVertex(vid="a", tags={"person": {"name": "Alice"}})
    response = QueryResult(column_names=["v"], rows=[{"v": raw_a}])
    executor = FakeExecutor(response)
    traversal = Traversal(executor)
    assert traversal.scan_vertices("person") == [raw_a]
    assert executor.executed == [
        'LOOKUP ON person YIELD id(vertex) AS id | ORDER BY $-.id '
        '| FETCH PROP ON * $-.id YIELD VERTEX AS v'
    ]


def test_scan_vertices_with_limit():
    executor = FakeExecutor(QueryResult(column_names=["v"], rows=[]))
    traversal = Traversal(executor)
    traversal.scan_vertices("person", limit=10)
    assert executor.executed == [
        'LOOKUP ON person YIELD id(vertex) AS id | ORDER BY $-.id | LIMIT 10 '
        '| FETCH PROP ON * $-.id YIELD VERTEX AS v'
    ]


class QueueExecutor:
    """Returns a different response per execute() call, so a chunked
    expansion can be observed one statement at a time."""

    def __init__(self, responses):
        self.executed = []
        self.responses = list(responses)

    def execute(self, ngql):
        self.executed.append(ngql)
        return self.responses.pop(0) if self.responses else QueryResult()


def test_neighbors_batch_returns_edges_and_dedupes():
    edge = RawEdge(src="a", dst="p1", edge_type="HAS_PHONE", rank=0, properties={})
    duplicate = RawEdge(src="a", dst="p1", edge_type="HAS_PHONE", rank=0, properties={})
    other = RawEdge(src="b", dst="p1", edge_type="HAS_PHONE", rank=0, properties={})
    response = QueryResult(
        column_names=["e"], rows=[{"e": edge}, {"e": duplicate}, {"e": other}]
    )
    traversal = Traversal(FakeExecutor(response))
    edges = traversal.neighbors_batch(["a", "b"], ["HAS_PHONE"])
    assert edges == [edge, other]


def test_neighbors_batch_issues_one_query_for_the_whole_frontier():
    executor = FakeExecutor(QueryResult(column_names=["e"], rows=[]))
    traversal = Traversal(executor)
    traversal.neighbors_batch(["a", "b", "c"], ["HAS_PHONE", "HAS_EMAIL"])
    assert executor.executed == [
        'GO FROM "a", "b", "c" OVER HAS_PHONE, HAS_EMAIL BIDIRECT '
        'YIELD DISTINCT edge AS e'
    ]


def test_neighbors_batch_chunks_long_vid_lists():
    executor = QueueExecutor([QueryResult(), QueryResult()])
    traversal = Traversal(executor)
    traversal.neighbors_batch(["a", "b", "c"], None, chunk_size=2)
    assert len(executor.executed) == 2
    assert executor.executed[0].startswith('GO FROM "a", "b" ')
    assert executor.executed[1].startswith('GO FROM "c" ')


def test_neighbors_batch_dedupes_start_vids():
    executor = FakeExecutor(QueryResult())
    traversal = Traversal(executor)
    traversal.neighbors_batch(["a", "a", "b"])
    assert executor.executed == ['GO FROM "a", "b" OVER * BIDIRECT YIELD DISTINCT edge AS e']


def test_neighbors_batch_with_no_vids_runs_nothing():
    executor = FakeExecutor(QueryResult())
    traversal = Traversal(executor)
    assert traversal.neighbors_batch([]) == []
    assert executor.executed == []


def test_neighbors_batch_ignores_non_edge_rows():
    response = QueryResult(column_names=["e"], rows=[{"e": "not-an-edge"}])
    traversal = Traversal(FakeExecutor(response))
    assert traversal.neighbors_batch(["a"]) == []
