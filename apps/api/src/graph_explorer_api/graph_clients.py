"""Lazily-created, reused GraphClient instances, one per NebulaGraph space.

Opening a connection pool per request would be wasteful; a Graph (space) is
typically hit repeatedly across a session, so clients are cached and closed
only when a Graph is deleted or the app shuts down.
"""

from __future__ import annotations

import threading

from graph_core.client import GraphClient
from graph_explorer_api.config import ADMIN_SPACE, Settings


class GraphClientCache:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients: dict[str, GraphClient] = {}
        self._lock = threading.Lock()

    def admin(self) -> GraphClient:
        """A client for space-administration only (create/list/drop spaces)."""
        return self.for_space(ADMIN_SPACE)

    def for_space(self, space: str) -> GraphClient:
        with self._lock:
            client = self._clients.get(space)
            if client is None:
                client = GraphClient(self._settings.build_config(space))
                client.connect()
                self._clients[space] = client
            return client

    def drop(self, space: str) -> None:
        with self._lock:
            client = self._clients.pop(space, None)
        if client is not None:
            client.close()

    def close_all(self) -> None:
        with self._lock:
            clients, self._clients = list(self._clients.values()), {}
        for client in clients:
            client.close()
