from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from graph_explorer_api.dependencies import (
    get_clients,
    get_graph_service,
    get_registry,
)
from graph_explorer_api.graph_clients import GraphClientCache
from graph_explorer_api.graph_registry import GraphRegistry
from graph_explorer_api.services.graph_service import GraphService

router = APIRouter(prefix="/api/graphs/{graph_id}/entities", tags=["entities"])


@router.get("/search")
def search_entities(
    graph_id: str,
    q: str = Query("", description="Search query"),
    entity_type: str = Query("person", description="Entity type to search"),
    registry: GraphRegistry = Depends(get_registry),
    graph_service: GraphService = Depends(get_graph_service),
):
    return graph_service.search_entities(entity_type, q)


@router.get("/{entity_id}")
def get_entity(
    graph_id: str,
    entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    entity = graph_service.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.get("/{entity_id}/graph")
def expand_entity_graph(
    graph_id: str,
    entity_id: str,
    depth: int = Query(1, ge=1, le=5),
    graph_service: GraphService = Depends(get_graph_service),
):
    return graph_service.expand_node(entity_id=entity_id, depth=depth)


@router.get("/{entity_id}/risk")
def get_entity_risk(
    graph_id: str,
    entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
    clients: GraphClientCache = Depends(get_clients),
):
    from graph_explorer_api.services.risk_service import RiskService

    risk_service = RiskService(graph_service)
    return risk_service.calculate_for_entity(entity_id)


@router.get("/{entity_id}/risk/explain")
def explain_entity_risk(
    graph_id: str,
    entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
    clients: GraphClientCache = Depends(get_clients),
):
    from graph_explorer_api.services.explanation_service import (
        InvestigationExplanationService,
    )
    from graph_explorer_api.services.risk_service import RiskService

    risk_service = RiskService(graph_service)
    risk = risk_service.calculate_for_entity(entity_id)
    explanation_service = InvestigationExplanationService()
    return explanation_service.explain_risk(risk)


@router.get("/shortest-path")
def shortest_path(
    graph_id: str,
    source: str = Query(...),
    target: str = Query(...),
    max_steps: int = Query(5, ge=1, le=10),
    graph_service: GraphService = Depends(get_graph_service),
):
    return graph_service.shortest_path(source, target, max_steps=max_steps)
