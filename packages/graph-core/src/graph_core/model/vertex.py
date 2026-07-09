"""Vertex extension point.

Domain packages subclass Vertex to define their own vertex types (e.g. a
future AML package's Person, Account). graph_core never defines any concrete
Vertex subclass itself.
"""

from abc import ABC, abstractmethod
from typing import Any


class Vertex(ABC):
    """Base contract every vertex type must satisfy.

    Subclasses must implement the `tag` property to return the NebulaGraph
    tag name this vertex type maps to — commonly a plain class attribute,
    e.g. `tag = "person"`, which satisfies this abstract property.

    Subclasses should not change this constructor's signature if they rely
    on generic deserialization (VertexOperations.get()).
    """

    def __init__(self, vid: str, properties: dict[str, Any] | None = None) -> None:
        self.vid = vid
        self.properties: dict[str, Any] = properties or {}

    @property
    @abstractmethod
    def tag(self) -> str:
        ...

    def validate(self) -> None:
        """Raise ValidationError if this instance is invalid. No-op by default."""
