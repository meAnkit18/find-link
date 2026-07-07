"""In-process substring search corpus, rebuilt per Graph after each import.

NebulaGraph OSS has no native substring/full-text search without an
external Elasticsearch listener — out of scope as unnecessary complexity
for a CSV-scale tool (see design doc). Search is instead a plain Python
substring match over a corpus built once per Graph via
Traversal.scan_vertices() and cached until the next import invalidates it.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from graph_core.client import GraphClient

LABEL_PROPERTY = "label"


@dataclass
class SearchEntry:
    vid: str
    tag: str
    label: str


class SearchIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, list[SearchEntry]] = {}

    def invalidate(self, graph_id: str) -> None:
        with self._lock:
            self._entries.pop(graph_id, None)

    def _build(self, client: GraphClient, tags: list[str]) -> list[SearchEntry]:
        entries: list[SearchEntry] = []
        for tag in tags:
            for raw in client.traversal.scan_vertices(tag):
                properties = raw.tags.get(tag, {})
                label = str(properties.get(LABEL_PROPERTY) or raw.vid)
                entries.append(SearchEntry(vid=raw.vid, tag=tag, label=label))
        return entries

    def search(
        self, graph_id: str, client: GraphClient, tags: list[str], query: str, limit: int = 50
    ) -> list[SearchEntry]:
        with self._lock:
            entries = self._entries.get(graph_id)
        if entries is None:
            entries = self._build(client, tags)
            with self._lock:
                self._entries[graph_id] = entries

        needle = query.strip().lower()
        if not needle:
            return entries[:limit]
        matches = [entry for entry in entries if needle in entry.label.lower()]
        return matches[:limit]
