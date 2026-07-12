from __future__ import annotations

from evidence_core.models import EvidenceRecord


class EvidenceStore:
    """In-memory evidence store for MVP. Will be backed by NebulaGraph in production."""

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    def put(self, record: EvidenceRecord) -> None:
        self._records[record.evidence_id] = record

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return self._records.get(evidence_id)

    def get_many(self, evidence_ids: list[str]) -> list[EvidenceRecord]:
        return [self._records[eid] for eid in evidence_ids if eid in self._records]
