from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class WebsiteVertex(IntelligenceVertex):
    tag: ClassVar[str] = "website"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("url"):
            raise ValueError("website.url is required")
