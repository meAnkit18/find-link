from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from graph_core.model.vertex import Vertex


@dataclass
class IntelligenceVertex(Vertex):
    vid: str
    properties: dict[str, Any] = field(default_factory=dict)

    tag: ClassVar[str] = "entity"

    def validate(self) -> None:
        if not self.vid:
            raise ValueError("vid is required")
        if "label" not in self.properties:
            raise ValueError("label is required")
        if "entity_type" not in self.properties:
            self.properties["entity_type"] = self.tag
        if "confidence" in self.properties:
            confidence = self.properties["confidence"]
            if confidence is not None and not (0.0 <= float(confidence) <= 1.0):
                raise ValueError("confidence must be between 0 and 1")
