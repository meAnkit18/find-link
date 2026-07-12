from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class DocumentVertex(IntelligenceVertex):
    tag: ClassVar[str] = "document"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("title"):
            raise ValueError("document.title is required")
