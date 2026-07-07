"""Graph (= one NebulaGraph space) CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from graph_explorer_api.dependencies import get_clients, get_graph_or_404, get_registry
from graph_explorer_api.graph_clients import GraphClientCache
from graph_explorer_api.graph_registry import Graph, GraphRegistry

router = APIRouter(prefix="/api/graphs", tags=["graphs"])


class GraphCreate(BaseModel):
    name: str


class GraphOut(BaseModel):
    id: str
    name: str
    created_at: str
    vertex_count: int
    edge_count: int

    @classmethod
    def from_graph(cls, graph: Graph) -> "GraphOut":
        return cls(
            id=graph.id,
            name=graph.name,
            created_at=graph.created_at,
            vertex_count=graph.stats.vertex_count,
            edge_count=graph.stats.edge_count,
        )


class GraphDetailOut(GraphOut):
    tags: list[str]
    edge_types: list[str]


@router.post("", response_model=GraphOut, status_code=201)
def create_graph(
    body: GraphCreate,
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
) -> GraphOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name must not be empty")
    graph = registry.create(name)
    clients.admin().metadata.create_space(graph.space)
    return GraphOut.from_graph(graph)


@router.get("", response_model=list[GraphOut])
def list_graphs(registry: GraphRegistry = Depends(get_registry)) -> list[GraphOut]:
    return [GraphOut.from_graph(g) for g in registry.list()]


@router.get("/{graph_id}", response_model=GraphDetailOut)
def get_graph(
    graph_id: str,
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
) -> GraphDetailOut:
    graph = get_graph_or_404(graph_id, registry)
    client = clients.for_space(graph.space)
    return GraphDetailOut(
        **GraphOut.from_graph(graph).model_dump(),
        tags=client.metadata.list_tags(),
        edge_types=client.metadata.list_edges(),
    )


@router.delete("/{graph_id}", status_code=204)
def delete_graph(
    graph_id: str,
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
) -> None:
    graph = get_graph_or_404(graph_id, registry)
    clients.admin().metadata.drop_space(graph.space)
    clients.drop(graph.space)
    registry.delete(graph_id)
