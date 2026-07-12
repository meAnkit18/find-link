from __future__ import annotations

from graph_core.client import GraphClient


class SearchGateway:
    """Bridges entity resolution to the graph for candidate lookup."""

    def __init__(self, client: GraphClient) -> None:
        self.client = client

    def find_by_unique_field(
        self, entity_type: str, field: str, value: str
    ) -> str | None:
        ngql = (
            f'LOOKUP ON {entity_type} '
            f'WHERE {entity_type}.{field} == "{value}" '
            f'YIELD id(vertex) AS id'
        )
        result = self.client.execute_raw(ngql)
        if result.rows:
            return str(result.rows[0].get("id", ""))
        return None

    def search_similar(self, entity_type: str, label: str) -> list[dict]:
        ngql = (
            f"LOOKUP ON {entity_type} "
            f"YIELD id(vertex) AS id, properties(vertex) AS props"
        )
        result = self.client.execute_raw(ngql)
        entries = []
        for row in result.rows:
            props = row.get("props", {})
            entries.append(
                {
                    "entity_id": str(row.get("id", "")),
                    "label": props.get("label", ""),
                    "date_of_birth": props.get("date_of_birth"),
                    "nationality": props.get("nationality"),
                }
            )
        return entries
