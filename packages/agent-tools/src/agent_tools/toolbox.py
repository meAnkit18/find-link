from __future__ import annotations

from agent_tools.models import ToolResult


class GraphToolbox:
    def __init__(self, graph_service, investigation_service, risk_service, ingestion_service):
        self.graph_service = graph_service
        self.investigation_service = investigation_service
        self.risk_service = risk_service
        self.ingestion_service = ingestion_service

    def search_person(self, query: str) -> ToolResult:
        rows = self.graph_service.search_entities("person", query)
        return ToolResult(ok=True, data={"results": rows}, message=f"found {len(rows)} people")

    def expand_node(self, entity_id: str, depth: int = 1) -> ToolResult:
        graph = self.graph_service.expand_node(entity_id=entity_id, depth=depth)
        return ToolResult(ok=True, data=graph, message="graph expansion complete")

    def shortest_path(self, source_id: str, target_id: str) -> ToolResult:
        path = self.graph_service.shortest_path(source_id, target_id)
        return ToolResult(ok=True, data={"path": path}, message="shortest path computed")

    def merge_entities(self, source_entity_id: str, target_entity_id: str) -> ToolResult:
        result = self.graph_service.merge_entities(source_entity_id, target_entity_id)
        return ToolResult(ok=True, data=result, message="entities merged")

    def calculate_risk(self, entity_id: str) -> ToolResult:
        risk = self.risk_service.calculate_for_entity(entity_id)
        return ToolResult(ok=True, data={"risk": risk}, message="risk calculated")

    def ingest_csv(self, file_path: str, source_name: str) -> ToolResult:
        result = self.ingestion_service.ingest_csv(file_path, source_name)
        return ToolResult(ok=True, data=result, message="csv ingestion complete")
