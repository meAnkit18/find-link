from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedRecord:
    record_id: str
    source_name: str
    source_type: str
    entity_type: str
    raw_payload: dict[str, Any]
    normalized: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
