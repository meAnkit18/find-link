from __future__ import annotations

from fastapi import APIRouter, Depends

from graph_explorer_api.dependencies import get_graph_service
from graph_explorer_api.services.explanation_service import (
    InvestigationExplanationService,
)
from graph_explorer_api.services.graph_service import GraphService
from graph_explorer_api.services.risk_service import RiskService

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/{entity_id}")
def calculate_risk(
    entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    risk_service = RiskService(graph_service)
    return risk_service.calculate_for_entity(entity_id)


@router.get("/{entity_id}/explain")
def explain_risk(
    entity_id: str,
    graph_service: GraphService = Depends(get_graph_service),
):
    risk_service = RiskService(graph_service)
    risk = risk_service.calculate_for_entity(entity_id)
    explanation_service = InvestigationExplanationService()
    return explanation_service.explain_risk(risk)
