from __future__ import annotations

from graph_explorer_api.services.graph_service import GraphService
from risk_engine.models import RiskResult
from risk_engine.scorer import RiskScorer


class RiskService:
    def __init__(self, graph_service: GraphService, scorer: RiskScorer | None = None) -> None:
        self.graph_service = graph_service
        self.scorer = scorer or RiskScorer()

    def calculate_for_entity(self, entity_id: str) -> RiskResult:
        context = self.graph_service.get_entity_risk_context(entity_id)
        risk_context = self._build_risk_context(entity_id, context)
        return self.scorer.calculate(entity_id, risk_context)

    def _build_risk_context(self, entity_id: str, context: dict) -> dict:
        risk_context: dict = {}
        neighbors = context.get("neighbors", [])

        sanctioned_neighbors = [
            n for n in neighbors
            if n.get("tags", {}).get("sanction_entry") or n.get("tags", {}).get("watchlist_entry")
        ]
        if sanctioned_neighbors:
            risk_context["is_direct_sanction_match"] = True
            risk_context["sanction_evidence_ids"] = [n["id"] for n in sanctioned_neighbors]

        for edge_data in context.get("edges", []):
            if edge_data["edge_type"] == "TRANSFERRED_TO":
                risk_context["shared_bank_account_count"] = (
                    risk_context.get("shared_bank_account_count", 0) + 1
                )

        return risk_context
