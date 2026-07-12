from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class EmailVertex(IntelligenceVertex):
    tag: ClassVar[str] = "email"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("address"):
            raise ValueError("email.address is required")
