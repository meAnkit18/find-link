"""Nebula-agnostic result value objects.

These types are what every layer above `storage/` sees. Nothing here
imports nebula3-python.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawVertex:
    """A vertex as returned from NebulaGraph, before any domain mapping.

    `tags` maps tag name -> {property name: value} for every tag attached to
    this vertex in the result.
    """

    vid: str
    tags: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class RawEdge:
    """An edge as returned from NebulaGraph, before any domain mapping."""

    src: str
    dst: str
    edge_type: str
    rank: int
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawPath:
    """An ordered sequence of vertices and the edges connecting them."""

    vertices: list[RawVertex] = field(default_factory=list)
    edges: list[RawEdge] = field(default_factory=list)


@dataclass
class QueryResult:
    """The result of executing an nGQL query.

    `rows` is a list of plain dicts (column name -> decoded Python value);
    values may themselves be RawVertex, RawEdge, RawPath, or plain Python
    scalars/lists/dicts.
    """

    column_names: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return len(self.rows) == 0

    def single_row(self) -> dict[str, Any] | None:
        """Return the first row, or None if the result has no rows."""
        return self.rows[0] if self.rows else None
