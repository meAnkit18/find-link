# tests/unit/test_client.py
from graph_core.client import GraphClient
from graph_core.config import GraphConfig
from graph_core.repository.edge_operations import EdgeOperations
from graph_core.repository.traversal import Traversal
from graph_core.repository.vertex_operations import VertexOperations
from graph_core.metadata import Metadata


class FakePool:
    def __init__(self):
        self.closed = False
        self.init_args = None

    def init(self, hosts, config):
        self.init_args = (hosts, config)
        return True

    def close(self):
        self.closed = True

    def get_session(self, user, password):
        raise NotImplementedError


def make_config():
    return GraphConfig(
        hosts=[("127.0.0.1", 9669)], user="root", password="nebula", space="test_space"
    )


def test_client_exposes_primitives():
    client = GraphClient(make_config(), pool_factory=FakePool)
    assert isinstance(client.vertices, VertexOperations)
    assert isinstance(client.edges, EdgeOperations)
    assert isinstance(client.traversal, Traversal)
    assert isinstance(client.metadata, Metadata)


def test_connect_starts_pool_and_close_closes_it():
    fake_pool = FakePool()
    client = GraphClient(make_config(), pool_factory=lambda: fake_pool)
    client.connect()
    assert fake_pool.init_args is not None
    client.close()
    assert fake_pool.closed is True


def test_context_manager_connects_and_closes():
    fake_pool = FakePool()
    with GraphClient(make_config(), pool_factory=lambda: fake_pool) as client:
        assert fake_pool.init_args is not None
    assert fake_pool.closed is True
