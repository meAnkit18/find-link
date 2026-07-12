"""Centralized NebulaGraph <-> Python value conversion.

This is the only module that understands NebulaGraph's wire-level value
representations (ValueWrapper, Node, Relationship, PathWrapper from
nebula3-python). Every other module works with plain Python values plus
RawVertex/RawEdge/RawPath.

Uses `from __future__ import annotations` with TYPE_CHECKING-guarded
imports so this module never imports nebula3-python at runtime — every
function here operates on its argument via duck typing (calling
is_vertex()/as_node()/etc.), so it works identically against the real
nebula3-python types or the test fakes in tests/unit/storage/fakes.py.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from graph_core.storage.result import RawEdge, RawPath, RawVertex

if TYPE_CHECKING:
    from nebula3.data.DataObject import Node, PathWrapper, Relationship, ValueWrapper


def to_ngql_literal(value: Any) -> str:
    """Render a plain Python value as an nGQL literal.

    The single place Python values become nGQL literals; query/builder.py
    must never build literals by hand.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, datetime):
        return f'datetime("{value.isoformat()}")'
    if isinstance(value, date):
        return f'date("{value.isoformat()}")'
    if isinstance(value, time):
        return f'time("{value.isoformat()}")'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(to_ngql_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{k}: {to_ngql_literal(v)}" for k, v in value.items())
        return "{" + pairs + "}"
    raise TypeError(f"Cannot render value of type {type(value)!r} as an nGQL literal")


def from_value_wrapper(value: ValueWrapper) -> Any:
    """Decode a single NebulaGraph ValueWrapper into a plain Python value."""
    if value.is_null():
        return None
    if value.is_bool():
        return value.as_bool()
    if value.is_int():
        return value.as_int()
    if value.is_double():
        return value.as_double()
    if value.is_string():
        return value.as_string()
    if value.is_list():
        return [from_value_wrapper(item) for item in value.as_list()]
    if value.is_map():
        return {key: from_value_wrapper(val) for key, val in value.as_map().items()}
    if value.is_vertex():
        return from_nebula_vertex(value.as_node())
    if value.is_edge():
        return from_nebula_edge(value.as_relationship())
    if value.is_path():
        return from_nebula_path(value.as_path())
    if hasattr(value, "is_datetime") and value.is_datetime():
        dt = value.as_datetime()
        return datetime(dt.get_year(), dt.get_month(), dt.get_day(),
                        dt.get_hour(), dt.get_minute(), dt.get_sec(), dt.get_microsec())
    if hasattr(value, "is_date") and value.is_date():
        d = value.as_date()
        from nebula3.data.DataObject import DateWrapper
        if isinstance(d, DateWrapper):
            return date(d.get_year(), d.get_month(), d.get_day())
        return date(d.year, d.month, d.day)
    if hasattr(value, "is_time") and value.is_time():
        t = value.as_time()
        from nebula3.data.DataObject import TimeWrapper
        if isinstance(t, TimeWrapper):
            return time(t.get_hour(), t.get_minute(), t.get_sec(), t.get_microsec())
        return time(t.hour, t.minute, t.sec, t.microsec)
    raise TypeError(f"Unsupported NebulaGraph value type: {value!r}")


def from_nebula_vertex(node: Node) -> RawVertex:
    """Decode a NebulaGraph Node into a RawVertex."""
    vid = from_value_wrapper(node.get_id())
    tags: dict[str, dict[str, Any]] = {}
    for tag_name in node.tags():
        props = node.properties(tag_name)
        tags[tag_name] = {name: from_value_wrapper(val) for name, val in props.items()}
    return RawVertex(vid=str(vid), tags=tags)


def from_nebula_edge(relationship: Relationship) -> RawEdge:
    """Decode a NebulaGraph Relationship into a RawEdge."""
    src = from_value_wrapper(relationship.start_vertex_id())
    dst = from_value_wrapper(relationship.end_vertex_id())
    props = relationship.properties()
    return RawEdge(
        src=str(src),
        dst=str(dst),
        edge_type=relationship.edge_name(),
        rank=relationship.ranking(),
        properties={name: from_value_wrapper(val) for name, val in props.items()},
    )


def from_nebula_path(path: PathWrapper) -> RawPath:
    """Decode a NebulaGraph PathWrapper into a RawPath."""
    vertices = [from_nebula_vertex(node) for node in path.nodes()]
    edges = [from_nebula_edge(rel) for rel in path.relationships()]
    return RawPath(vertices=vertices, edges=edges)
