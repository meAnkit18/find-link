"""Pure schema definitions: tag and edge type property shapes.

Data only; SchemaRegistry and Metadata attach behavior to these.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PropertyDefinition:
    """A single property in a NebulaGraph tag or edge type schema."""

    name: str
    nebula_type: str  # e.g. "string", "int64", "double", "bool", "timestamp"
    nullable: bool = True
    default: object | None = None


@dataclass(frozen=True)
class TagSchema:
    """The NebulaGraph schema for one tag (vertex type)."""

    name: str
    properties: tuple[PropertyDefinition, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EdgeSchema:
    """The NebulaGraph schema for one edge type."""

    name: str
    properties: tuple[PropertyDefinition, ...] = field(default_factory=tuple)
