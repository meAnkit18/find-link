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


def _build_over_clause(edge_type: str | None, direction: str) -> str:
    if direction not in ("out", "in", "both"):
        raise ValueError(f"direction must be 'out', 'in', or 'both', got {direction!r}")

    edge_clause = "*"
    if edge_type is not None:
        validate_identifier(edge_type, "edge type")
        edge_clause = edge_type

    if direction == "out":
        return f"OVER {edge_clause}"
    if direction == "in":
        return f"OVER {edge_clause} REVERSELY"
    return f"OVER {edge_clause} BIDIRECT"


def build_go_neighbors(vid: str, edge_type: str | None, direction: str) -> str:
    over_clause = _build_over_clause(edge_type, direction)
    return (
        f"GO FROM {_format_vid(vid)} {over_clause} YIELD DISTINCT dst(edge) AS id "
        f"| FETCH PROP ON * $-.id YIELD VERTEX AS v"
    )


def build_count_neighbors(vid: str, edge_type: str | None, direction: str) -> str:
    """Count distinct neighbor ids without hydrating full vertices."""
    over_clause = _build_over_clause(edge_type, direction)
    return f"GO FROM {_format_vid(vid)} {over_clause} YIELD DISTINCT dst(edge) AS id"


def build_insert_vertices(tag: str, rows: list[tuple[str, dict[str, Any]]]) -> str:
    """Build a single multi-row INSERT VERTEX statement.

    All rows must share the same property columns (same keys, any order) so
    they can be declared once in the column list, as nGQL requires.
    """
    validate_identifier(tag, "tag")
    if not rows:
        raise ValueError("build_insert_vertices requires at least one row")
    columns = list(rows[0][1].keys())
    for name in columns:
        validate_identifier(name, "property")
    columns_str = ", ".join(columns)
    value_groups = []
    for vid, properties in rows:
        if set(properties.keys()) != set(columns):
            raise ValueError("All rows in a batch must share the same property columns")
        values = ", ".join(to_ngql_literal(properties[name]) for name in columns)
        value_groups.append(f"{_format_vid(vid)}:({values})")
    return f"INSERT VERTEX {tag}({columns_str}) VALUES {', '.join(value_groups)}"


def build_insert_edges(
    edge_type: str, rows: list[tuple[str, str, int, dict[str, Any]]]
) -> str:
    """Build a single multi-row INSERT EDGE statement (see build_insert_vertices)."""
    validate_identifier(edge_type, "edge type")
    if not rows:
        raise ValueError("build_insert_edges requires at least one row")
    columns = list(rows[0][3].keys())
    for name in columns:
        validate_identifier(name, "property")
    columns_str = ", ".join(columns)
    value_groups = []
    for src, dst, rank, properties in rows:
        if set(properties.keys()) != set(columns):
            raise ValueError("All rows in a batch must share the same property columns")
        values = ", ".join(to_ngql_literal(properties[name]) for name in columns)
        value_groups.append(f"{_format_vid(src)}->{_format_vid(dst)}@{rank}:({values})")
    return f"INSERT EDGE {edge_type}({columns_str}) VALUES {', '.join(value_groups)}"


def build_fetch_vertices(vids: list[str]) -> str:
    """Fetch many vertices (any tag) in one round trip."""
    if not vids:
        raise ValueError("build_fetch_vertices requires at least one vid")
    vid_list = ", ".join(_format_vid(vid) for vid in vids)
    return f"FETCH PROP ON * {vid_list} YIELD VERTEX AS v"


def build_scan_vertices(tag: str, limit: int | None = None) -> str:
    """Scan all vertices of a tag via LOOKUP.

    NOTE: LOOKUP ON <tag> REQUIRES a tag index on <tag> (an empty index
    `ON tag()` is sufficient). Schema-setup code must create one per tag.
    """
    validate_identifier(tag, "tag")
    ngql = f"LOOKUP ON {tag} YIELD id(vertex) AS id"
    if limit is not None:
        ngql += f" | LIMIT {int(limit)}"
    return ngql + " | FETCH PROP ON * $-.id YIELD VERTEX AS v"


def build_find_shortest_path(
    source_vid: str, target_vid: str, max_steps: int = 5, edge_type: str | None = None
) -> str:
    over_clause = f"OVER {edge_type}" if edge_type else "OVER *"
    return (
        f'FIND SHORTEST PATH FROM {_format_vid(source_vid)} '
        f'TO {_format_vid(target_vid)} '
        f'{over_clause} UPTO {max_steps} STEPS YIELD path AS p'
    )


def build_go_neighbors_with_edges(
    vid: str, edge_type: str | None = None, direction: str = "out"
) -> str:
    over_clause = _build_over_clause(edge_type, direction)
    return (
        f"GO FROM {_format_vid(vid)} {over_clause} "
        f"YIELD DISTINCT dst(edge) AS id, edge AS e"
    )


def build_edge_existence_check(edge_type: str, src: str, dst: str, rank: int = 0) -> str:
    validate_identifier(edge_type, "edge type")
    return (
        f"FETCH PROP ON {edge_type} "
        f"{_format_vid(src)}->{_format_vid(dst)}@{rank} "
        f"YIELD EDGE AS e"
    )


def build_upsert_edge(
    edge_type: str, src: str, dst: str, rank: int, properties: dict[str, Any]
) -> str:
    validate_identifier(edge_type, "edge type")
    for name in properties:
        validate_identifier(name, "property")
    assignments = ", ".join(
        f"{edge_type}.{name} = {to_ngql_literal(value)}" for name, value in properties.items()
    )
    return (
        f"UPSERT EDGE ON {edge_type} "
        f"{_format_vid(src)}->{_format_vid(dst)}@{rank} "
        f"SET {assignments}"
    )
