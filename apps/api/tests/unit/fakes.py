"""In-memory stand-ins for graph_clients.GraphClientCache / graph-core's
GraphClient, exercising this app's routers and import pipeline without a
real NebulaGraph instance.

Mirrors the *behavior* graph-core documents (INSERT VERTEX overwrites,
LOOKUP-with-no-WHERE is a full scan, etc.) rather than graph-core's
internals, so these tests validate this app's logic against that
contract — whether NebulaGraph itself actually honors the contract is
covered by graph-core's own tests plus the owner's manual verification.
"""

from __future__ import annotations

from graph_core.storage.result import RawVertex


class FakeGraphStore:
    def __init__(self) -> None:
        self.tags: dict[str, object] = {}
        self.edge_types: dict[str, object] = {}
        self.vertices: dict[str, dict[str, dict]] = {}  # vid -> {tag: {prop: val}}
        self.edges: list[tuple[str, str, str, int, dict]] = []


class FakeMetadata:
    def __init__(self, store: FakeGraphStore) -> None:
        self.store = store

    def create_tag(self, schema) -> None:
        self.store.tags[schema.name] = schema

    def create_edge_type(self, schema) -> None:
        self.store.edge_types[schema.name] = schema

    def create_tag_index(self, index_name: str, tag: str, property_names: list[str]) -> None:
        pass

    def list_tags(self) -> list[str]:
        return list(self.store.tags)

    def list_edges(self) -> list[str]:
        return list(self.store.edge_types)


class FakeVertexOperations:
    def __init__(self, store: FakeGraphStore) -> None:
        self.store = store

    def create_many(self, tag: str, rows) -> None:
        for vid, properties in rows:
            self.store.vertices.setdefault(vid, {})[tag] = properties

    def get_many_raw(self, vids: list[str]) -> list[RawVertex]:
        result = []
        for vid in vids:
            tags = self.store.vertices.get(vid)
            if tags:
                result.append(RawVertex(vid=vid, tags=dict(tags)))
        return result


class FakeEdgeOperations:
    def __init__(self, store: FakeGraphStore) -> None:
        self.store = store

    def create_many(self, edge_type: str, rows) -> None:
        for src, dst, rank, properties in rows:
            self.store.edges.append((src, dst, edge_type, rank, properties))


class FakeTraversal:
    def __init__(self, store: FakeGraphStore) -> None:
        self.store = store

    def _vertex(self, vid: str) -> RawVertex | None:
        tags = self.store.vertices.get(vid)
        return RawVertex(vid=vid, tags=dict(tags)) if tags else None

    def get_neighbors(self, vid: str, edge_type: str | None = None, direction: str = "out"):
        found = []
        for src, dst, et, _rank, _props in self.store.edges:
            if edge_type is not None and et != edge_type:
                continue
            if direction in ("out", "both") and src == vid:
                found.append(dst)
            if direction in ("in", "both") and dst == vid:
                found.append(src)
        vertices = (self._vertex(v) for v in dict.fromkeys(found))
        return [v for v in vertices if v is not None]

    def count_neighbors(self, vid: str, edge_type: str | None = None, direction: str = "out") -> int:
        return len(self.get_neighbors(vid, edge_type, direction))

    def scan_vertices(self, tag: str, limit: int | None = None):
        result = [
            RawVertex(vid=vid, tags={tag: tags[tag]})
            for vid, tags in self.store.vertices.items()
            if tag in tags
        ]
        return result[:limit] if limit is not None else result


class FakeGraphClient:
    def __init__(self) -> None:
        self.store = FakeGraphStore()
        self.metadata = FakeMetadata(self.store)
        self.vertices = FakeVertexOperations(self.store)
        self.edges = FakeEdgeOperations(self.store)
        self.traversal = FakeTraversal(self.store)

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass


class _FakeAdminMetadata:
    def __init__(self, spaces: set) -> None:
        self.spaces = spaces

    def create_space(self, name: str, vid_type: str = "FIXED_STRING(32)") -> None:
        self.spaces.add(name)

    def drop_space(self, name: str) -> None:
        self.spaces.discard(name)

    def list_spaces(self) -> list[str]:
        return list(self.spaces)


class _FakeAdminClient:
    def __init__(self, spaces: set) -> None:
        self.metadata = _FakeAdminMetadata(spaces)


class FakeGraphClientCache:
    """Drop-in replacement for graph_clients.GraphClientCache."""

    def __init__(self) -> None:
        self._spaces: set = set()
        self._admin = _FakeAdminClient(self._spaces)
        self._clients: dict[str, FakeGraphClient] = {}

    def admin(self) -> _FakeAdminClient:
        return self._admin

    def for_space(self, space: str) -> FakeGraphClient:
        if space not in self._clients:
            self._clients[space] = FakeGraphClient()
        return self._clients[space]

    def drop(self, space: str) -> None:
        self._clients.pop(space, None)

    def close_all(self) -> None:
        self._clients.clear()


class SyncImportJobRunner:
    """Runs the import pipeline synchronously (no thread), so tests don't
    need to poll for background-job completion."""

    def __init__(self) -> None:
        self._jobs: dict = {}

    def start(self, graph_id, filename, path, client, on_complete=None):
        from graph_explorer_api.ingest.pipeline import run_import
        from graph_explorer_api.ingest.jobs import ImportJob

        job = ImportJob(id=f"job-{len(self._jobs)}", graph_id=graph_id, filename=filename)
        try:
            report = run_import(client, path, filename)
            job.report = report
            job.status = "done"
            if on_complete:
                on_complete(report)
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = str(exc)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str):
        return self._jobs.get(job_id)

    def list_for_graph(self, graph_id: str):
        return [j for j in self._jobs.values() if j.graph_id == graph_id]
