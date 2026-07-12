from __future__ import annotations

from datetime import datetime, timezone

from graph_core.client import GraphClient


class ReviewQueueRepository:
    def __init__(self, client: GraphClient) -> None:
        self.client = client

    def list_pending(self, queue_type: str | None = None) -> list[dict]:
        type_filter = (
            f'WHERE review_item.queue_type == "{queue_type}"' if queue_type else ""
        )
        ngql = (
            f"LOOKUP ON review_item {type_filter} "
            f"YIELD id(vertex) AS id, properties(vertex) AS props"
        )
        result = self.client.execute_raw(ngql)
        return [
            {"review_id": row["id"], **row.get("props", {})}
            for row in result.rows
        ]

    def approve(self, review_id: str, reviewed_by: str, reason: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        reason_str = reason or "approved"
        self.client.execute_raw(
            f'UPDATE vertex ON review_item "{review_id}" '
            f'SET review_item.status = "approved", '
            f'review_item.reviewed_at = datetime("{now}"), '
            f'review_item.reviewed_by = "{reviewed_by}", '
            f'review_item.decision_reason = "{reason_str}"'
        )

    def reject(self, review_id: str, reviewed_by: str, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.client.execute_raw(
            f'UPDATE vertex ON review_item "{review_id}" '
            f'SET review_item.status = "rejected", '
            f'review_item.reviewed_at = datetime("{now}"), '
            f'review_item.reviewed_by = "{reviewed_by}", '
            f'review_item.decision_reason = "{reason}"'
        )
