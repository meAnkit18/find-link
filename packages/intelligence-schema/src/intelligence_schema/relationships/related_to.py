from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from graph_core.model.edge import Edge


@dataclass
class RelatedToEdge(Edge):
    src: str
    dst: str
    rank: int = 0
    properties: dict[str, Any] = field(default_factory=dict)

    edge_type: ClassVar[str] = "RELATED_TO"

    def validate(self) -> None:
        if not self.src or not self.dst:
            raise ValueError("src and dst are required")
        confidence = self.properties.get("confidence")
        if confidence is not None and not (0.0 <= float(confidence) <= 1.0):
            raise ValueError("confidence must be between 0 and 1")
