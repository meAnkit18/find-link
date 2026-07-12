from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class IPAddressVertex(IntelligenceVertex):
    tag: ClassVar[str] = "ip_address"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("ip"):
            raise ValueError("ip_address.ip is required")
