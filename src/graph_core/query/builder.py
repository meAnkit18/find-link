"""Pure nGQL string construction. No I/O, no NebulaGraph client import."""

from __future__ import annotations

from typing import Any

from graph_core.identifiers import validate_identifier
from graph_core.storage.serialization import to_ngql_literal


def _format_vid(vid: str) -> str:
    return to_ngql_literal(str(vid))


def _format_insert_properties(properties: dict[str, Any]) -> tuple[str, str]:
    names = list(properties.keys())
    for name in names:
        validate_identifier(name, "property")
    columns = ", ".join(names)
    values = ", ".join(to_ngql_literal(properties[name]) for name in names)
    return columns, values


def build_insert_vertex(tag: str, vid: str, properties: dict[str, Any]) -> str:
    validate_identifier(tag, "tag")
    columns, values = _format_insert_properties(properties)
    return f"INSERT VERTEX {tag}({columns}) VALUES {_format_vid(vid)}:({values})"


def build_upsert_vertex(tag: str, vid: str, properties: dict[str, Any]) -> str:
    validate_identifier(tag, "tag")
    for name in properties:
        validate_identifier(name, "property")
    assignments = ", ".join(
        f"{tag}.{name} = {to_ngql_literal(value)}" for name, value in properties.items()
    )
    return f"UPSERT VERTEX ON {tag} {_format_vid(vid)} SET {assignments}"


def build_fetch_vertex(tag: str, vid: str) -> str:
    validate_identifier(tag, "tag")
    return f"FETCH PROP ON {tag} {_format_vid(vid)} YIELD VERTEX AS v"


def build_delete_vertex(vid: str) -> str:
    return f"DELETE VERTEX {_format_vid(vid)}"


def build_insert_edge(
    edge_type: str, src: str, dst: str, rank: int, properties: dict[str, Any]
) -> str:
    validate_identifier(edge_type, "edge type")
    columns, values = _format_insert_properties(properties)
    return (
        f"INSERT EDGE {edge_type}({columns}) VALUES "
        f"{_format_vid(src)}->{_format_vid(dst)}@{rank}:({values})"
    )


def build_fetch_edge(edge_type: str, src: str, dst: str, rank: int) -> str:
    validate_identifier(edge_type, "edge type")
    return (
        f"FETCH PROP ON {edge_type} {_format_vid(src)}->{_format_vid(dst)}@{rank} "
        f"YIELD EDGE AS e"
    )


def build_delete_edge(edge_type: str, src: str, dst: str, rank: int) -> str:
    validate_identifier(edge_type, "edge type")
    return f"DELETE EDGE {edge_type} {_format_vid(src)}->{_format_vid(dst)}@{rank}"


def build_go_neighbors(vid: str, edge_type: str | None, direction: str) -> str:
    if direction not in ("out", "in", "both"):
        raise ValueError(f"direction must be 'out', 'in', or 'both', got {direction!r}")

    edge_clause = "*"
    if edge_type is not None:
        validate_identifier(edge_type, "edge type")
        edge_clause = edge_type

    if direction == "out":
        over_clause = f"OVER {edge_clause}"
    elif direction == "in":
        over_clause = f"OVER {edge_clause} REVERSELY"
    else:
        over_clause = f"OVER {edge_clause} BIDIRECT"

    return (
        f"GO FROM {_format_vid(vid)} {over_clause} YIELD DISTINCT dst(edge) AS id "
        f"| FETCH PROP ON * $-.id YIELD VERTEX AS v"
    )
