"""Edge extension point.

Domain packages subclass Edge to define their own edge types (e.g. a future
AML package's OWNS, TRANSFERS). graph_core never defines any concrete Edge
subclass itself.
"""

from abc import ABC, abstractmethod
from typing import Any


class Edge(ABC):
    """Base contract every edge type must satisfy.

    Subclasses must implement the `edge_type` property to return the
    NebulaGraph edge type name — commonly a plain class attribute, e.g.
    `edge_type = "owns"`, which satisfies this abstract property.

    Subclasses should not change this constructor's signature if they rely
    on generic deserialization (EdgeOperations.get()).
    """

    def __init__(
        self,
        src: str,
        dst: str,
        rank: int = 0,
        properties: dict[str, Any] | None = None,
    ) -> None:
        self.src = src
        self.dst = dst
        self.rank = rank
        self.properties: dict[str, Any] = properties or {}

    @property
    @abstractmethod
    def edge_type(self) -> str:
        ...

    def validate(self) -> None:
        """Raise ValidationError if this instance is invalid. No-op by default."""
