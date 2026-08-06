from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from graph_explorer_api.dependencies import get_graph_service, get_person_network_service
from graph_explorer_api.services.graph_service import GraphService
from graph_explorer_api.services.person_network_service import (
    DEFAULT_MAX_FANOUT,
    DEFAULT_MAX_PERSONS,
    MAX_DEGREE,
    PersonNetworkService,
)

router = APIRouter(prefix="/api/entities", tags=["entities"])


@router.get("/search")
def search_entities(
    q: str = Query("", description="Search query"),
    entity_type: str | None = Query(
        None, description="Restrict to one tag, e.g. 'person'"
    ),
    graph_service: GraphService = Depends(get_graph_service),
):
    return graph_service.search_entities(q, entity_type=entity_type)


@router.get("/{entity_id}")
def get_entity(
    entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    entity = graph_service.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.get("/{entity_id}/graph")
def expand_entity_graph(
    entity_id: str,
    depth: int = Query(1, ge=1, le=5),
    graph_service: GraphService = Depends(get_graph_service),
):
    return graph_service.expand_node(entity_id=entity_id, depth=depth)


@router.get("/{entity_id}/person-network")
def person_network(
    entity_id: str,
    degree: int = Query(1, ge=1, le=MAX_DEGREE, description="Connection degree, not hops"),
    connectors: str | None = Query(
        None, description="Comma-separated edge types to treat as connections"
    ),
    max_fanout: int = Query(
        DEFAULT_MAX_FANOUT,
        ge=1,
        le=500,
        description="Skip a shared attribute held by more people than this",
    ),
    max_persons: int = Query(DEFAULT_MAX_PERSONS, ge=1, le=2000),
    service: PersonNetworkService = Depends(get_person_network_service),
):
    network = service.person_network(
        root_id=entity_id,
        degree=degree,
        connectors=connectors.split(",") if connectors else None,
        max_fanout=max_fanout,
        max_persons=max_persons,
    )
    if network is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return network


@router.get("/{entity_id}/attributes")
def entity_attributes(
    entity_id: str,
    connectors: str | None = Query(None),
    service: PersonNetworkService = Depends(get_person_network_service),
):
    return service.attributes(
        entity_id, connectors=connectors.split(",") if connectors else None
    )


@router.get("/{entity_id}/risk")
def get_entity_risk(
    entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    from graph_explorer_api.services.risk_service import RiskService

    risk_service = RiskService(graph_service)
    return risk_service.calculate_for_entity(entity_id)


@router.get("/{entity_id}/risk/explain")
def explain_entity_risk(
    entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
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
    source: str = Query(...),
    target: str = Query(...),
    max_steps: int = Query(5, ge=1, le=10),
    graph_service: GraphService = Depends(get_graph_service),
):
    return graph_service.shortest_path(source, target, max_steps=max_steps)
