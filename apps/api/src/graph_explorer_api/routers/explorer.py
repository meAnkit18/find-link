"""Read-only exploration endpoints: schema, search, node detail, neighbors, overview."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from graph_core.client import GraphClient
from graph_core.storage.result import RawVertex

from graph_explorer_api.dependencies import get_clients, get_graph_or_404, get_registry, get_search_index
from graph_explorer_api.graph_clients import GraphClientCache
from graph_explorer_api.graph_registry import GraphRegistry
from graph_explorer_api.search.index import SearchIndex

router = APIRouter(prefix="/api/graphs/{graph_id}", tags=["explorer"])

OVERVIEW_DEFAULT_LIMIT = 40
NEIGHBORS_DEFAULT_LIMIT = 100


class SchemaOut(BaseModel):
    tags: list[str]
    edge_types: list[str]


class NodeOut(BaseModel):
    vid: str
    tags: list[str]
    label: str
    properties: dict


def _to_node_out(raw: RawVertex) -> NodeOut:
    properties: dict = {}
    for props in raw.tags.values():
        properties.update(props)
    label = str(properties.get("label") or raw.vid)
    return NodeOut(vid=raw.vid, tags=list(raw.tags.keys()), label=label, properties=properties)


class SearchResultOut(BaseModel):
    vid: str
    tag: str
    label: str


class DegreeOut(BaseModel):
    edge_type: str
    direction: str
    count: int


class NodeDetailOut(NodeOut):
    degree: list[DegreeOut]


class EdgeOut(BaseModel):
    src: str
    dst: str
    edge_type: str
    rank: int
    properties: dict


class SubgraphOut(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut]


@router.get("/schema", response_model=SchemaOut)
def get_schema(
    graph_id: str,
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
) -> SchemaOut:
    graph = get_graph_or_404(graph_id, registry)
    client = clients.for_space(graph.space)
    return SchemaOut(tags=client.metadata.list_tags(), edge_types=client.metadata.list_edges())


@router.get("/search", response_model=list[SearchResultOut])
def search(
    graph_id: str,
    q: str = Query("", description="Substring to match against node labels"),
    limit: int = Query(50, ge=1, le=500),
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
    search_index: SearchIndex = Depends(get_search_index),
) -> list[SearchResultOut]:
    graph = get_graph_or_404(graph_id, registry)
    client = clients.for_space(graph.space)
    tags = client.metadata.list_tags()
    entries = search_index.search(graph_id, client, tags, q, limit=limit)
    return [SearchResultOut(vid=e.vid, tag=e.tag, label=e.label) for e in entries]


@router.get("/nodes/{vid}", response_model=NodeDetailOut)
def get_node(
    graph_id: str,
    vid: str,
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
) -> NodeDetailOut:
    graph = get_graph_or_404(graph_id, registry)
    client = clients.for_space(graph.space)
    matches = client.vertices.get_many_raw([vid])
    if not matches:
        raise HTTPException(status_code=404, detail=f"Node {vid!r} not found")
    node = _to_node_out(matches[0])

    degree = []
    for edge_type in client.metadata.list_edges():
        for direction in ("out", "in"):
            count = client.traversal.count_neighbors(vid, edge_type=edge_type, direction=direction)
            if count:
                degree.append(DegreeOut(edge_type=edge_type, direction=direction, count=count))

    return NodeDetailOut(**node.model_dump(), degree=degree)


@router.get("/nodes/{vid}/neighbors", response_model=list[NodeOut])
def get_neighbors(
    graph_id: str,
    vid: str,
    edge_type: str | None = Query(None),
    direction: str = Query("out", pattern="^(out|in|both)$"),
    limit: int = Query(NEIGHBORS_DEFAULT_LIMIT, ge=1, le=1000),
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
) -> list[NodeOut]:
    graph = get_graph_or_404(graph_id, registry)
    client = clients.for_space(graph.space)
    neighbors = client.traversal.get_neighbors(vid, edge_type=edge_type, direction=direction)
    return [_to_node_out(n) for n in neighbors[:limit]]


@router.get("/overview", response_model=SubgraphOut)
def get_overview(
    graph_id: str,
    limit: int = Query(OVERVIEW_DEFAULT_LIMIT, ge=1, le=500),
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
) -> SubgraphOut:
    """An initial subgraph so the explorer never opens on a blank canvas.

    Phase 1 approximation: sample up to `limit` vertices spread across the
    graph's tags, then include only the edges between sampled vertices
    (not every edge touching them) so the initial view stays legible.
    """
    graph = get_graph_or_404(graph_id, registry)
    client: GraphClient = clients.for_space(graph.space)
    tags = client.metadata.list_tags()
    if not tags:
        return SubgraphOut(nodes=[], edges=[])

    per_tag_limit = max(1, math.ceil(limit / len(tags)))
    sampled: list[RawVertex] = []
    for tag in tags:
        sampled.extend(client.traversal.scan_vertices(tag, limit=per_tag_limit))
    sampled = sampled[:limit]
    sampled_vids = {v.vid for v in sampled}

    edges: list[EdgeOut] = []
    seen_edges: set[tuple[str, str, str, int]] = set()
    edge_types = client.metadata.list_edges()
    for vertex in sampled:
        for edge_type in edge_types:
            for neighbor_vid in (
                n.vid for n in client.traversal.get_neighbors(vertex.vid, edge_type=edge_type, direction="out")
            ):
                if neighbor_vid not in sampled_vids:
                    continue
                key = (vertex.vid, neighbor_vid, edge_type, 0)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append(
                    EdgeOut(src=vertex.vid, dst=neighbor_vid, edge_type=edge_type, rank=0, properties={})
                )

    return SubgraphOut(nodes=[_to_node_out(v) for v in sampled], edges=edges)
