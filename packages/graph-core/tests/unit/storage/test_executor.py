import pytest

from graph_core.config import GraphConfig
from graph_core.exceptions import QueryExecutionError
from graph_core.storage.connection import GraphConnectionPool
from graph_core.storage.executor import QueryExecutor
from tests.unit.storage.fakes import FakePool, FakeQuerySession, FakeResultSet, FakeValueWrapper


def make_config():
    return GraphConfig(
        hosts=[("127.0.0.1", 9669)], user="root", password="nebula", space="test_space"
    )


def _executor_with(query_result):
    session = FakeQuerySession(query_result=query_result)
    fake_pool = FakePool(init_result=True)
    fake_pool.get_session = lambda user, password: session
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    conn.start()
    return QueryExecutor(conn, make_config()), session


def test_execute_returns_decoded_rows():
    result_set = FakeResultSet(
        succeeded=True,
        column_names=["name", "age"],
        rows=[[FakeValueWrapper(string_="Alice"), FakeValueWrapper(int_=30)]],
    )
    executor, _ = _executor_with(result_set)
    result = executor.execute("FETCH PROP ON person \"v1\" YIELD VERTEX AS v")
    assert result.column_names == ["name", "age"]
    assert result.rows == [{"name": "Alice", "age": 30}]


def test_execute_raises_query_execution_error_on_failure():
    result_set = FakeResultSet(succeeded=False, error_msg="syntax error")
    executor, _ = _executor_with(result_set)
    with pytest.raises(QueryExecutionError, match="syntax error"):
        executor.execute("BAD QUERY")


def test_execute_releases_session():
    result_set = FakeResultSet(succeeded=True, column_names=[], rows=[])
    executor, session = _executor_with(result_set)
    executor.execute("SHOW TAGS")
    assert session.released is True


def test_execute_with_use_space_false_skips_use_statement():
    result_set = FakeResultSet(succeeded=True, column_names=[], rows=[])
    executor, session = _executor_with(result_set)
    executor.execute("SHOW SPACES", use_space=False)
    assert session.executed == ["SHOW SPACES"]
