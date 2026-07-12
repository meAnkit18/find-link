from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class CompanyVertex(IntelligenceVertex):
    tag: ClassVar[str] = "company"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("name"):
            raise ValueError("company.name is required")
