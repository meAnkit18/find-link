"""Session acquisition/release against a NebulaGraph connection pool."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from graph_core.config import GraphConfig
from graph_core.exceptions import GraphConnectionError
from graph_core.storage.connection import GraphConnectionPool


@contextmanager
def session_scope(
    connection_pool: GraphConnectionPool, config: GraphConfig, use_space: bool = True
) -> Iterator[Any]:
    """Acquire a session from the pool for the configured space, releasing it afterward.

    `use_space=False` skips the `USE` statement, for space-administration
    statements (CREATE SPACE, SHOW SPACES, DROP SPACE) that must run before
    the configured space necessarily exists yet.
    """
    session = connection_pool.pool.get_session(config.user, config.password)
    try:
        if use_space:
            use_resp = session.execute(f"USE {config.space}")
            if not use_resp.is_succeeded():
                raise GraphConnectionError(
                    f"Failed to switch to space {config.space!r}: {use_resp.error_msg()}"
                )
        yield session
    finally:
        session.release()
