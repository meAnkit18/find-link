from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class CountryVertex(IntelligenceVertex):
    tag: ClassVar[str] = "country"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("code"):
            raise ValueError("country.code is required")
