from __future__ import annotations

from ingestion_core.adapters.csv_adapter import CSVSourceAdapter
from ingestion_core.normalizers.person import normalize_person


class IngestionService:
    def __init__(self, resolver, writer) -> None:
        self.resolver = resolver
        self.writer = writer

    def ingest_csv(self, file_path: str, source_name: str) -> dict:
        adapter = CSVSourceAdapter(file_path=file_path, source_name=source_name)

        created = 0
        merged = 0
        for record in adapter.iter_records():
            if record.entity_type == "person":
                normalized = normalize_person(record.raw_payload)
            else:
                continue

            resolution = self.resolver.resolve(record.entity_type, normalized)
            result = self.writer.upsert_entity(record.entity_type, normalized, resolution)
            if result["action"] == "created":
                created += 1
            else:
                merged += 1

        return {"created": created, "merged": merged}
