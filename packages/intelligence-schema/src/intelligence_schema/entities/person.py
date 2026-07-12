from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class PersonVertex(IntelligenceVertex):
    tag: ClassVar[str] = "person"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("full_name"):
            raise ValueError("person.full_name is required")
