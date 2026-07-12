from __future__ import annotations

from graph_core.client import GraphClient
from graph_core.merge import MergePlan


class GraphService:
    def __init__(self, client: GraphClient) -> None:
        self.client = client

    def get_entity(self, entity_id: str):
        query = f'FETCH PROP ON * "{entity_id}" YIELD VERTEX AS v'
        result = self.client.execute_raw(query)
        return result.rows[0] if result.rows else None

    def search_entities(self, entity_type: str, query_str: str) -> list[dict]:
        rows = self.client.traversal.scan_vertices(entity_type, limit=100)
        lowered = query_str.lower()
        return [
            {
                "entity_id": row.vid,
                "label": row.tags.get(entity_type, {}).get("label", row.vid),
                **row.tags.get(entity_type, {}),
            }
            for row in rows
            if lowered in (row.tags.get(entity_type, {}).get("label", "") or "").lower()
        ]

    def expand_node(self, entity_id: str, depth: int = 1) -> dict:
        visited = set()
        frontier = [entity_id]
        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        for _ in range(depth):
            next_frontier = []
            for current in frontier:
                if current in visited:
                    continue
                visited.add(current)
                vertices, raw_edges = self.client.traversal.get_neighbors_with_edges(
                    current, direction="both"
                )
                for vertex in vertices:
                    tags = vertex.tags
                    node_data = {
                        "id": vertex.vid,
                        "label": next(iter(tags.values()), {}).get("label", vertex.vid),
                        "tags": {k: v for k, v in tags.items()},
                    }
                    if vertex.vid not in nodes:
                        nodes[vertex.vid] = node_data
                    next_frontier.append(vertex.vid)

                for raw_edge in raw_edges:
                    edge_data = {
                        "src": raw_edge.src,
                        "dst": raw_edge.dst,
                        "edge_type": raw_edge.edge_type,
                        "rank": raw_edge.rank,
                        "properties": raw_edge.properties,
                    }
                    edge_key = (raw_edge.src, raw_edge.dst, raw_edge.edge_type, raw_edge.rank)
                    if edge_key not in {(e["src"], e["dst"], e["edge_type"], e["rank"]) for e in edges}:
                        edges.append(edge_data)

            frontier = next_frontier

        if entity_id not in nodes:
            nodes[entity_id] = {"id": entity_id, "label": entity_id, "tags": {}}

        return {"nodes": list(nodes.values()), "edges": edges}

    def shortest_path(self, source_id: str, target_id: str, max_steps: int = 5) -> dict:
        paths = self.client.traversal.shortest_path(source_id, target_id, max_steps=max_steps)
        if not paths:
            return {"paths": []}

        result_paths = []
        for path in paths:
            result_paths.append(
                {
                    "vertices": [
                        {"vid": v.vid, "tags": v.tags} for v in path.vertices
                    ],
                    "edges": [
                        {
                            "src": e.src,
                            "dst": e.dst,
                            "edge_type": e.edge_type,
                            "rank": e.rank,
                            "properties": e.properties,
                        }
                        for e in path.edges
                    ],
                }
            )
        return {"paths": result_paths}

    def merge_entities(self, source_entity_id: str, target_entity_id: str) -> dict:
        source = self.get_entity(source_entity_id)
        target = self.get_entity(target_entity_id)
        if source is None or target is None:
            return {"error": "one or both entities not found"}

        merge_plan = MergePlan(
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            merged_properties={},
        )
        return {
            "plan": {
                "source": source_entity_id,
                "target": target_entity_id,
                "redirect_edges": merge_plan.redirect_edges,
            },
            "status": "merge_planned",
        }

    def get_entity_risk_context(self, entity_id: str, depth: int = 2) -> dict:
        """Gather risk-relevant context for an entity via graph traversal."""
        context: dict = {}
        expanded = self.expand_node(entity_id, depth=depth)
        context["neighbors"] = expanded.get("nodes", [])
        context["edges"] = expanded.get("edges", [])
        return context
