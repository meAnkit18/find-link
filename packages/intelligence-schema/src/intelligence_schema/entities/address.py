from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class AddressVertex(IntelligenceVertex):
    tag: ClassVar[str] = "address"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("full_address"):
            raise ValueError("address.full_address is required")
