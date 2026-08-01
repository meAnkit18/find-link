import threading
import time

from graph_core.config import GraphConfig
from graph_core.storage.connection import GraphConnectionPool
from graph_core.storage.session import session_scope
from tests.unit.storage.fakes import FakePool, FakeSession


def make_config():
    return GraphConfig(
        hosts=[("127.0.0.1", 9669)], user="root", password="nebula", space="test_space"
    )


def test_session_scope_serializes_session_usage_under_concurrency():
    """nebula3-python's ConnectionPool races when sessions are acquired and
    released concurrently (graphd kills one session's query with
    'Execution had been killed'). session_scope must therefore guarantee at
    most one session is checked out of the pool at a time."""
    max_concurrent = 0
    active = 0
    active_lock = threading.Lock()

    class TrackingSession(FakeSession):
        pass

    def make_session(user, password):
        nonlocal max_concurrent, active
        with active_lock:
            active += 1
            max_concurrent = max(max_concurrent, active)
        time.sleep(0.01)
        try:
            return TrackingSession(use_succeeds=True)
        finally:
            with active_lock:
                active -= 1

    fake_pool = FakePool(init_result=True)
    fake_pool.get_session = make_session
    conn = GraphConnectionPool(make_config(), pool_factory=lambda: fake_pool)
    conn.start()

    def worker():
        with session_scope(conn, make_config()):
            time.sleep(0.01)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_concurrent == 1
