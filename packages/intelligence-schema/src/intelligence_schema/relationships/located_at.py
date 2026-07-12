from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from graph_core.model.edge import Edge


@dataclass
class LocatedAtEdge(Edge):
    src: str
    dst: str
    rank: int = 0
    properties: dict[str, Any] = field(default_factory=dict)

    edge_type: ClassVar[str] = "LOCATED_AT"

    def validate(self) -> None:
        if not self.src or not self.dst:
            raise ValueError("src and dst are required")
