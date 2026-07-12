from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class PhoneVertex(IntelligenceVertex):
    tag: ClassVar[str] = "phone"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("number"):
            raise ValueError("phone.number is required")
