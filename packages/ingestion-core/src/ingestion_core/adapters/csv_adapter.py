from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from ingestion_core.models import NormalizedRecord


class CSVSourceAdapter:
    def __init__(self, file_path: str, source_name: str) -> None:
        self.file_path = Path(file_path)
        self.source_name = source_name

    def iter_records(self) -> Iterator[NormalizedRecord]:
        with self.file_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                yield NormalizedRecord(
                    record_id=f"{self.source_name}:{idx}",
                    source_name=self.source_name,
                    source_type="csv",
                    entity_type=row.get("entity_type", "unknown").strip().lower(),
                    raw_payload=row,
                )
