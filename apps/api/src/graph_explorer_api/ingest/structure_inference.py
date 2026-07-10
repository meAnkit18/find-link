"""Decide whether an uploaded CSV is an edge list or a node table, and which
columns play which role.

Primary signal: header-name pattern matching against common conventions
(source/target, from/to, ...). Falls back to a cardinality heuristic when
headers don't hint at a pair. This is inherently a best-effort guess, not a
guarantee — the ImportReport surfaces what was inferred so the user can see
(and, in a future iteration, override) the decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from graph_explorer_api.ingest.csv_inspector import ColumnProfile, InspectionResult
from graph_explorer_api.naming import sanitize_identifier

_PAIR_PATTERNS = [
    ("source", "target"),
    ("src", "dst"),
    ("from", "to"),
    ("sender", "receiver"),
    ("start", "end"),
    ("node1", "node2"),
    ("entity1", "entity2"),
    ("person1", "person2"),
]

_TYPE_HEADER_HINTS = ("type", "relationship", "relation", "label", "edge_type", "category")
_ID_HEADER_HINTS = ("id", "name", "key", "uuid", "vid", "identifier")
_NEAR_UNIQUE_RATIO = 0.98


@dataclass
class EdgeListStructure:
    kind: str  # "edge_list"
    source_column: str
    target_column: str
    type_column: str | None
    default_edge_type: str
    node_tag: str
    property_columns: list[str]


@dataclass
class NodeTableStructure:
    kind: str  # "node_table"
    id_column: str
    tag: str
    property_columns: list[str]


def _find_pair(headers: list[str]) -> tuple[str, str] | None:
    lowered = {h.lower(): h for h in headers}
    for left, right in _PAIR_PATTERNS:
        left_matches = [orig for low, orig in lowered.items() if left in low]
        right_matches = [orig for low, orig in lowered.items() if right in low and orig not in left_matches]
        if len(left_matches) == 1 and len(right_matches) == 1:
            return left_matches[0], right_matches[0]
    return None


def _cardinality_fallback_pair(columns: list[ColumnProfile]) -> tuple[str, str] | None:
    candidates = [
        c
        for c in columns
        if c.distinct_ratio < _NEAR_UNIQUE_RATIO
        and c.distinct_ratio > 0
        and not (c.name.lower() in _ID_HEADER_HINTS and c.distinct_ratio > 0.9)
    ]
    candidates.sort(key=lambda c: c.distinct_ratio, reverse=True)
    if len(candidates) < 2:
        return None
    return candidates[0].name, candidates[1].name


def _find_type_column(columns: list[ColumnProfile], exclude: set[str]) -> str | None:
    """A header matching a type/relationship/label hint is trusted as-is —
    an explicit, intentional column name is a stronger signal than any
    cardinality heuristic could be."""
    for c in columns:
        if c.name in exclude:
            continue
        if any(hint in c.name.lower() for hint in _TYPE_HEADER_HINTS):
            return c.name
    return None


def _common_entity_name(a: str, b: str) -> str | None:
    a_low, b_low = a.lower(), b.lower()
    common = ""
    for ca, cb in zip(a_low, b_low):
        if ca != cb:
            break
        common += ca
    common = common.strip("_ ")
    return common if len(common) >= 3 else None


def _find_id_column(columns: list[ColumnProfile]) -> str:
    for c in columns:
        if c.name.lower() in _ID_HEADER_HINTS:
            return c.name
    most_unique = max(columns, key=lambda c: c.distinct_ratio, default=None)
    return most_unique.name if most_unique else columns[0].name


def infer_structure(
    inspection: InspectionResult, filename_stem: str
) -> EdgeListStructure | NodeTableStructure:
    columns = inspection.columns
    pair = _find_pair(inspection.headers) or _cardinality_fallback_pair(columns)

    if pair is not None:
        source_column, target_column = pair
        excluded = {source_column, target_column}
        type_column = _find_type_column(columns, excluded)
        if type_column is not None:
            excluded.add(type_column)
        property_columns = [c.name for c in columns if c.name not in excluded]
        entity_name = _common_entity_name(source_column, target_column)
        node_tag = sanitize_identifier(entity_name or "entity", "entity")
        default_edge_type = sanitize_identifier(filename_stem, "related_to").upper()
        return EdgeListStructure(
            kind="edge_list",
            source_column=source_column,
            target_column=target_column,
            type_column=type_column,
            default_edge_type=default_edge_type,
            node_tag=node_tag,
            property_columns=property_columns,
        )

    id_column = _find_id_column(columns)
    property_columns = [c.name for c in columns if c.name != id_column]
    tag = sanitize_identifier(filename_stem, "entity")
    return NodeTableStructure(
        kind="node_table", id_column=id_column, tag=tag, property_columns=property_columns
    )
