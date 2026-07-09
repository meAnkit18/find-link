"""NebulaGraph connection pool lifecycle.

This module never imports nebula3-python at module load time — the real
pool implementation is only constructed inside `_default_pool_factory()`,
which is never called by unit tests (they always inject a fake
`pool_factory`). This means the module — and every consumer of it — is
importable and testable without nebula3-python installed.
"""

from __future__ import annotations

from typing import Any, Callable

from graph_core.config import GraphConfig
from graph_core.exceptions import GraphConnectionError

PoolFactory = Callable[[], Any]


def _default_pool_factory() -> Any:
    from nebula3.gclient.net import ConnectionPool

    return ConnectionPool()


def _build_nebula_config(config: GraphConfig) -> Any:
    from nebula3.Config import Config as NebulaConfig

    nebula_config = NebulaConfig()
    nebula_config.min_connection_pool_size = config.pool_min_size
    nebula_config.max_connection_pool_size = config.pool_max_size
    nebula_config.timeout = config.timeout_ms
    return nebula_config


def _build_ssl_config(config: GraphConfig) -> Any:
    import ssl as ssl_module

    from nebula3.Config import SSL_config

    ssl_config = SSL_config()
    ssl_config.cert_reqs = ssl_module.CERT_REQUIRED
    ssl_config.ca_certs = config.ssl_ca_certs or ssl_module.get_default_verify_paths().cafile
    ssl_config.verify_name = True
    return ssl_config


class GraphConnectionPool:
    """Wraps a NebulaGraph connection pool's lifecycle (start/close)."""

    def __init__(self, config: GraphConfig, pool_factory: PoolFactory | None = None) -> None:
        self._config = config
        self._pool_factory = pool_factory or _default_pool_factory
        self._pool: Any | None = None

    def start(self) -> None:
        """Initialize the underlying connection pool. Raises GraphConnectionError on failure."""
        pool = self._pool_factory()
        if self._pool_factory is _default_pool_factory:
            nebula_config = _build_nebula_config(self._config)
            ssl_config = _build_ssl_config(self._config) if self._config.use_ssl else None
            ok = pool.init(self._config.hosts, nebula_config, ssl_config)
        else:
            nebula_config = self._config
            ok = pool.init(self._config.hosts, nebula_config)
        if not ok:
            raise GraphConnectionError(
                f"Failed to initialize NebulaGraph connection pool for hosts {self._config.hosts}"
            )
        self._pool = pool

    def close(self) -> None:
        """Close the underlying connection pool, if started."""
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    @property
    def pool(self) -> Any:
        """The underlying nebula3-python ConnectionPool. Raises GraphConnectionError if not started."""
        if self._pool is None:
            raise GraphConnectionError("Connection pool has not been started; call start() first")
        return self._pool
