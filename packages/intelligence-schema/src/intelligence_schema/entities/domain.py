from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class DomainVertex(IntelligenceVertex):
    tag: ClassVar[str] = "domain"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("domain_name"):
            raise ValueError("domain.domain_name is required")
