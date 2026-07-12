from __future__ import annotations

import uuid
from datetime import datetime, timezone


class InvestigationService:
    def __init__(self, client) -> None:
        self.client = client

    def create_case(self, title: str, created_by: str, priority: str = "medium") -> dict:
        case_id = f"case:{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()
        self.client.execute_raw(
            f'INSERT VERTEX investigation_case(title, status, priority, created_by, created_at, updated_at) '
            f'VALUES "{case_id}":('
            f'"{title}", "open", "{priority}", "{created_by}", '
            f'datetime("{now}"), datetime("{now}")'
            f')'
        )
        return {"case_id": case_id, "title": title, "status": "open"}

    def get_case(self, case_id: str) -> dict | None:
        result = self.client.execute_raw(
            f'FETCH PROP ON investigation_case "{case_id}" YIELD VERTEX AS v'
        )
        return result.rows[0] if result.rows else None

    def add_subject(self, case_id: str, entity_id: str, subject_role: str, added_by: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        self.client.execute_raw(
            f'INSERT EDGE HAS_SUBJECT(subject_role, added_at, added_by) '
            f'VALUES "{case_id}"->"{entity_id}":('
            f'"{subject_role}", datetime("{now}"), "{added_by}"'
            f')'
        )
        return {"case_id": case_id, "entity_id": entity_id, "role": subject_role}

    def add_note(self, case_id: str, body: str, author_id: str) -> dict:
        note_id = f"note:{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()
        self.client.execute_raw(
            f'INSERT VERTEX case_note(body, author_id, created_at, updated_at) '
            f'VALUES "{note_id}":('
            f'"{body}", "{author_id}", datetime("{now}"), datetime("{now}")'
            f')'
        )
        self.client.execute_raw(
            f'INSERT EDGE HAS_NOTE(created_at) '
            f'VALUES "{case_id}"->"{note_id}":(datetime("{now}"))'
        )
        return {"note_id": note_id, "case_id": case_id}

    def list_cases(self) -> list[dict]:
        result = self.client.execute_raw(
            'LOOKUP ON investigation_case YIELD id(vertex) AS id, properties(vertex) AS props'
        )
        return [
            {"case_id": row["id"], **row.get("props", {})}
            for row in result.rows
        ]
