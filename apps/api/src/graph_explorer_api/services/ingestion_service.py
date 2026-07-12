from __future__ import annotations

from graph_explorer_api.services.graph_service import GraphService


class EntityWriter:
    def __init__(self, graph_service: GraphService) -> None:
        self.graph_service = graph_service

    def upsert_entity(self, entity_type: str, normalized: dict, resolution) -> dict:
        existing_id = resolution.entity_id if resolution.action in ("merge",) else None
        if existing_id:
            self.graph_service.client.vertices.upsert(
                self.graph_service.client.vertices._registry.get_vertex_class(entity_type)(
                    vid=existing_id, properties=normalized
                )
            )
            return {"action": "merged", "entity_id": existing_id}
        else:
            import uuid
            entity_id = f"{entity_type}:{uuid.uuid4().hex}"
            ngql = (
                f'INSERT VERTEX {entity_type}({", ".join(normalized.keys())}) '
                f'VALUES "{entity_id}":({", ".join(self._ngql_values(normalized.values()))})'
            )
            self.graph_service.client.execute_raw(ngql)
            return {"action": "created", "entity_id": entity_id}

    def _ngql_values(self, values) -> list[str]:
        result = []
        for v in values:
            if v is None:
                result.append("NULL")
            elif isinstance(v, str):
                result.append(f'"{v}"')
            elif isinstance(v, bool):
                result.append("true" if v else "false")
            else:
                result.append(str(v))
        return result
