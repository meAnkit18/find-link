"""Materializes inferred schema in NebulaGraph and bulk-writes rows.

Handles two operational realities that don't show up in a happy-path demo:
- NebulaGraph has a short propagation delay after CREATE TAG/EDGE before
  the new schema is reliably writable; the first write batch after schema
  creation is retried with backoff rather than failing immediately.
- The same entity (e.g. a person's name used as its own vid) legitimately
  repeats across many CSV rows; only the first occurrence per batch is
  sent, the rest counted as duplicates for the report. Cross-import
  reuse of the same vid is handled by NebulaGraph itself: INSERT VERTEX
  overwrites an existing vertex's properties rather than erroring.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from graph_core.client import GraphClient
from graph_core.exceptions import QueryExecutionError
from graph_core.schema.models import EdgeSchema, PropertyDefinition, TagSchema

from graph_explorer_api.import_pipeline.csv_inspector import ColumnProfile

BATCH_SIZE = 200
LABEL_PROPERTY = "label"
_NEBULA_TYPE = {"int": "int64", "float": "double", "bool": "bool", "string": "string"}
_LABEL_HINTS = ("name", "label", "title")


def nebula_type_for(inferred_type: str) -> str:
    return _NEBULA_TYPE.get(inferred_type, "string")


def pick_label_column(columns: list[ColumnProfile], candidate_names: list[str]) -> str | None:
    """Best string column to display as a node's label, or None (falls back to vid)."""
    by_name = {c.name: c for c in columns if c.name in candidate_names}
    for hint in _LABEL_HINTS:
        for name, col in by_name.items():
            if hint in name.lower() and col.inferred_type == "string":
                return name
    for name, col in by_name.items():
        if col.inferred_type == "string":
            return name
    return None


def coerce_value(raw: str, inferred_type: str) -> tuple[Any, bool]:
    """Parse `raw` per the column's inferred type. Returns (value, ok);
    ok=False means the value didn't fit and the caller should log + null it,
    not abort the batch."""
    if raw == "":
        return None, True
    if inferred_type == "int":
        try:
            return int(raw), True
        except ValueError:
            return None, False
    if inferred_type == "float":
        try:
            return float(raw), True
        except ValueError:
            return None, False
    if inferred_type == "bool":
        return raw.strip().lower() in ("true", "yes"), True
    return raw, True


def ensure_tag(client: GraphClient, tag: str, columns: list[ColumnProfile]) -> None:
    properties = tuple(
        PropertyDefinition(name=c.name, nebula_type=nebula_type_for(c.inferred_type))
        for c in columns
    ) + (PropertyDefinition(name=LABEL_PROPERTY, nebula_type="string"),)
    client.metadata.create_tag(TagSchema(name=tag, properties=properties))
    write_with_retry(
        lambda: client.metadata.create_tag_index(
            f"{tag}_label_idx", tag, [f"{LABEL_PROPERTY}(256)"]
        )
    )


def ensure_edge_type(client: GraphClient, edge_type: str, columns: list[ColumnProfile]) -> None:
    properties = tuple(
        PropertyDefinition(name=c.name, nebula_type=nebula_type_for(c.inferred_type))
        for c in columns
    )
    client.metadata.create_edge_type(EdgeSchema(name=edge_type, properties=properties))


def write_with_retry(fn: Callable[[], None], max_wait_seconds: float = 15.0) -> None:
    """Retry `fn` with backoff, covering NebulaGraph's schema-propagation
    delay right after CREATE TAG/EDGE — not a general transient-failure
    retry policy."""
    delays = [0.0, 1.0, 2.0, 4.0, 8.0]
    waited = 0.0
    last_error: QueryExecutionError | None = None
    for delay in delays:
        if delay:
            time.sleep(delay)
            waited += delay
        try:
            fn()
            return
        except QueryExecutionError as exc:
            last_error = exc
            if waited >= max_wait_seconds:
                break
    assert last_error is not None
    raise last_error


def _write_batches(rows: list, create_many: Callable[[list], None]) -> None:
    first_batch = True
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        if first_batch:
            write_with_retry(lambda b=batch: create_many(b))
            first_batch = False
        else:
            create_many(batch)


def write_vertices(
    client: GraphClient, tag: str, rows: list[tuple[str, dict[str, Any]]]
) -> tuple[int, int]:
    """Dedupe by vid and bulk-write. Returns (unique_count, duplicates_skipped)."""
    seen: set[str] = set()
    unique: list[tuple[str, dict[str, Any]]] = []
    duplicates = 0
    for vid, properties in rows:
        if vid in seen:
            duplicates += 1
            continue
        seen.add(vid)
        unique.append((vid, properties))
    _write_batches(unique, lambda batch: client.vertices.create_many(tag, batch))
    return len(unique), duplicates


def write_edges(
    client: GraphClient, edge_type: str, rows: list[tuple[str, str, int, dict[str, Any]]]
) -> tuple[int, int]:
    """Dedupe by (src, dst, rank) and bulk-write. Returns (unique_count, duplicates_skipped)."""
    seen: set[tuple[str, str, int]] = set()
    unique: list[tuple[str, str, int, dict[str, Any]]] = []
    duplicates = 0
    for src, dst, rank, properties in rows:
        key = (src, dst, rank)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append((src, dst, rank, properties))
    _write_batches(unique, lambda batch: client.edges.create_many(edge_type, batch))
    return len(unique), duplicates
