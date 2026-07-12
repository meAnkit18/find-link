"""GraphClient: the single public entry point for graph-core consumers.

Wires GraphConfig to the connection pool and exposes the repository
primitives, Metadata, and an execute_raw() escape hatch. Nothing outside
this file (and storage/) needs to know NebulaGraph exists.
"""

from __future__ import annotations

from graph_core.config import GraphConfig
from graph_core.metadata import Metadata
from graph_core.repository.edge_operations import EdgeOperations
from graph_core.repository.traversal import Traversal
from graph_core.repository.vertex_operations import VertexOperations
from graph_core.schema.registry import SchemaRegistry
from graph_core.storage.connection import GraphConnectionPool, PoolFactory
from graph_core.storage.executor import QueryExecutor
from graph_core.storage.result import QueryResult


class GraphClient:
    """Single public facade wiring config to storage, schema, and repository primitives."""

    def __init__(
        self,
        config: GraphConfig,
        registry: SchemaRegistry | None = None,
        pool_factory: PoolFactory | None = None,
    ) -> None:
        self._config = config
        self._registry = registry or SchemaRegistry()
        self._connection_pool = GraphConnectionPool(config, pool_factory=pool_factory)
        self._executor = QueryExecutor(self._connection_pool, config)
        self.vertices = VertexOperations(self._executor, self._registry)
        self.edges = EdgeOperations(self._executor, self._registry)
        self.traversal = Traversal(self._executor)
        self.metadata = Metadata(self._executor)

    def connect(self) -> None:
        self._connection_pool.start()

    def close(self) -> None:
        self._connection_pool.close()

    def execute_raw(self, ngql: str) -> QueryResult:
        """Escape hatch for operations not covered by the primitives above."""
        return self._executor.execute(ngql)

    def __enter__(self) -> GraphClient:
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
