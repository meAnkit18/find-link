from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceRecord:
    evidence_id: str
    source_type: str
    source_name: str
    source_uri: str | None = None
    snippet_text: str | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Citation:
    entity_id: str
    evidence_id: str
    claim: str
    confidence: float = 1.0


@dataclass
class EvidenceReference:
    evidence_id: str
    relationship: str  # e.g. SUPPORTED_BY, EXTRACTED_FROM, MENTIONS
