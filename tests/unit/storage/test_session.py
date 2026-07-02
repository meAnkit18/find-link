import pytest

from graph_core.config import GraphConfig
from graph_core.exceptions import GraphConnectionError
from graph_core.storage.connection import GraphConnectionPool
from graph_core.storage.session import session_scope
from tests.unit.storage.fakes import FakePool, FakeSession


def make_config():
    return GraphConfig(
        hosts=[("127.0.0.1", 9669)], user="root", password="nebula", space="test_space"
    )


def _pool_with_session(session):
    fake_pool = FakePool(init_result=True)
    fake_pool.get_session = lambda user, password: session
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    conn.start()
    return conn


def test_session_scope_yields_session_and_switches_space():
    session = FakeSession(use_succeeds=True)
    conn = _pool_with_session(session)
    with session_scope(conn, make_config()) as s:
        assert s is session
    assert session.executed == ["USE test_space"]


def test_session_scope_releases_session_on_success():
    session = FakeSession(use_succeeds=True)
    conn = _pool_with_session(session)
    with session_scope(conn, make_config()):
        pass
    assert session.released is True


def test_session_scope_releases_session_even_on_exception():
    session = FakeSession(use_succeeds=True)
    conn = _pool_with_session(session)
    with pytest.raises(RuntimeError):
        with session_scope(conn, make_config()):
            raise RuntimeError("boom")
    assert session.released is True


def test_session_scope_raises_graph_connection_error_when_use_fails():
    session = FakeSession(use_succeeds=False)
    conn = _pool_with_session(session)
    with pytest.raises(GraphConnectionError):
        with session_scope(conn, make_config()):
            pass
    assert session.released is True
