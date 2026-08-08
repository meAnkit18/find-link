"""Turning stored vertex columns into usable entity properties.

Every entity tag keeps its extracted attributes in a single JSON `props`
string column (see intelligence_schema.ingest_schema), so a caller reading a
vertex straight from the graph gets one opaque blob rather than the fields it
holds. Both the investigator-facing projection and risk scoring need the
fields, so the unpacking lives here rather than in either of them.
"""

from __future__ import annotations

import json

from graph_core.storage.result import RawVertex

# Storage plumbing rather than facts about the entity. `props` is unpacked
# into real fields below; the rest (`label` is already the display name, the
# timestamps are unix ints) would only be noise to a reader or a scorer.
INTERNAL_PROPS = frozenset({"props", "evidence_ids", "label", "created_at", "updated_at"})


def unpack_props(value) -> dict:
    """The JSON `props` blob as a dict, empty for anything unparseable."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except ValueError:
        return {}
    # Empty aliases/attributes are written for every entity; surfacing them
    # would put a row reading "Not recorded" on every single panel.
    return (
        {k: v for k, v in parsed.items() if v not in (None, "", [], {})}
        if isinstance(parsed, dict)
        else {}
    )


def merged_properties(vertex: RawVertex) -> dict:
    """Flatten every tag on a vertex into one property dict."""
    merged: dict = {}
    for props in vertex.tags.values():
        merged.update(properties_of_tag(props))
    return merged


def properties_of_tag(props: dict) -> dict:
    """One tag's stored columns, with `props` unpacked and plumbing dropped."""
    flattened: dict = {}
    for key, value in props.items():
        if key == "props":
            flattened.update(unpack_props(value))
        elif key not in INTERNAL_PROPS:
            flattened[key] = value
    return flattened
