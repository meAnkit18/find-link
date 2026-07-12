from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_tools.toolbox import GraphToolbox, ToolResult
from graph_explorer_api.dependencies import (
    get_graph_service,
)
from graph_explorer_api.services.graph_service import GraphService
from graph_explorer_api.services.investigation_service import InvestigationService
from graph_explorer_api.services.risk_service import RiskService

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _get_toolbox(
    graph_service: GraphService,
    investigation_service: InvestigationService | None = None,
) -> GraphToolbox:
    risk_service = RiskService(graph_service)
    return GraphToolbox(
        graph_service=graph_service,
        investigation_service=investigation_service,
        risk_service=risk_service,
        ingestion_service=None,
    )


@router.post("/search-person", response_model=ToolResult)
def agent_search_person(
    query: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    toolbox = _get_toolbox(graph_service)
    return toolbox.search_person(query)


@router.post("/expand-node", response_model=ToolResult)
def agent_expand_node(
    entity_id: str,
    depth: int = 1,
    graph_service: GraphService = Depends(get_graph_service),
):
    toolbox = _get_toolbox(graph_service)
    return toolbox.expand_node(entity_id, depth)


@router.post("/shortest-path", response_model=ToolResult)
def agent_shortest_path(
    source_id: str,
    target_id: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    toolbox = _get_toolbox(graph_service)
    return toolbox.shortest_path(source_id, target_id)


@router.post("/merge-entities", response_model=ToolResult)
def agent_merge_entities(
    source_entity_id: str,
    target_entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    toolbox = _get_toolbox(graph_service)
    return toolbox.merge_entities(source_entity_id, target_entity_id)


@router.post("/calculate-risk", response_model=ToolResult)
def agent_calculate_risk(
    entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    toolbox = _get_toolbox(graph_service)
    return toolbox.calculate_risk(entity_id)
