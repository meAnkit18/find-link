from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class SanctionEntryVertex(IntelligenceVertex):
    tag: ClassVar[str] = "sanction_entry"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("sanction_list"):
            raise ValueError("sanction_entry.sanction_list is required")
