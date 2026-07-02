import pytest

from graph_core.config import GraphConfig
from graph_core.exceptions import GraphConnectionError
from graph_core.storage.connection import GraphConnectionPool
from tests.unit.storage.fakes import FakePool


def make_config():
    return GraphConfig(
        hosts=[("127.0.0.1", 9669)],
        user="root",
        password="nebula",
        space="test_space",
    )


def test_start_initializes_pool_and_exposes_it():
    fake_pool = FakePool(init_result=True)
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    conn.start()
    assert conn.pool is fake_pool
    assert fake_pool.init_args is not None


def test_start_raises_graph_connection_error_on_init_failure():
    fake_pool = FakePool(init_result=False)
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    with pytest.raises(GraphConnectionError):
        conn.start()


def test_pool_property_raises_before_start():
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: FakePool())
    with pytest.raises(GraphConnectionError):
        _ = conn.pool


def test_close_closes_started_pool():
    fake_pool = FakePool(init_result=True)
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    conn.start()
    conn.close()
    assert fake_pool.closed is True


def test_close_before_start_is_a_noop():
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: FakePool())
    conn.close()  # must not raise
