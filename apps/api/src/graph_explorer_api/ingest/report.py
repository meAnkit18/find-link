"""ImportReport: the statistics surfaced to the user after an import job finishes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportReport:
    filename: str
    structure_kind: str  # "edge_list" | "node_table"
    tag: str | None = None
    edge_type: str | None = None
    rows_read: int = 0
    vertices_created: int = 0
    edges_created: int = 0
    duplicates_skipped: int = 0
    validation_errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
