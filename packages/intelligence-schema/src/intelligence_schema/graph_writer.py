from __future__ import annotations

import json
import time
from typing import Any

from graph_core.client import GraphClient


class GraphWriter:
    """Projects accepted facts into NebulaGraph.

    Idempotent re-projections: INSERT VERTEX overwrites props for an existing VID.
    """

    _EXTRA_COLUMN = {
        "country": ("iso2", "iso2"),
        "passport": ("number", "number"),
        "phone": ("number", "number"),
        "email": ("address", "address"),
        "bank_account": ("iban", "iban"),
        "vehicle": ("plate", "plate"),
    }

    def __init__(self, client: GraphClient) -> None:
        self._client = client

    def upsert_entity(
        self, tag: str, vid: str, name: str,
        attributes: dict[str, Any] | None = None,
        confidence: float = 0.0,
        evidence_id: str | None = None,
    ) -> None:
        now = int(time.time())
        attrs = attributes or {}
        aliases = attrs.pop("aliases", [])
        extra_props = attrs.pop("extra_props", {})
        props_bag = {**extra_props, **attrs}

        cols = ["label", "entity_type", "props", "confidence", "created_at", "updated_at"]
        vals = [
            self._ngql_value(name),
            self._ngql_value(tag),
            self._ngql_value(
                json.dumps({"aliases": aliases, **props_bag}, ensure_ascii=False, default=str),
            ),
            self._ngql_value(float(confidence)),
            self._ngql_value(now),
            self._ngql_value(now),
        ]

        if tag in self._EXTRA_COLUMN:
            col, attr_key = self._EXTRA_COLUMN[tag]
            cols.insert(1, col)
            vals.insert(1, self._ngql_value(attrs.get(attr_key, "")))

        if evidence_id:
            cols.append("evidence_ids")
            vals.append(self._ngql_value(json.dumps([evidence_id])))

        ngql = f'INSERT VERTEX {tag}({", ".join(cols)}) VALUES "{vid}":({", ".join(vals)});'
        self._client.execute_raw(ngql)

    def upsert_relationship(
        self, edge_type: str, src_id: str, dst_id: str,
        confidence: float, status: str = "accepted",
        evidence_id: str | None = None,
        attributes: dict[str, Any] | None = None,
        relation_label: str | None = None,
    ) -> None:
        now = int(time.time())
        props = {
            "confidence": float(confidence),
            "status": status,
            "evidence_ids": evidence_id or "",
            "props": json.dumps(attributes or {}, ensure_ascii=False, default=str),
            "created_at": now,
        }
        if edge_type == "RELATED_TO":
            props["relationship_type"] = relation_label or ""

        cols = ", ".join(props.keys())
        vals = ", ".join(self._ngql_value(v) for v in props.values())
        ngql = f'INSERT EDGE {edge_type}({cols}) VALUES "{src_id}"->"{dst_id}":({vals});'
        self._client.execute_raw(ngql)

    def link_supported_by(self, entity_id: str, evidence_id: str, confidence: float) -> None:
        now = int(time.time())
        ngql = (
            f'INSERT EDGE SUPPORTED_BY(extraction_confidence, created_at) '
            f'VALUES "{entity_id}"->"{evidence_id}":({float(confidence)}, {now});'
        )
        self._client.execute_raw(ngql)

    def fetch_neighborhood(self, entity_id: str, depth: int = 2, limit: int = 60) -> list[dict]:
        ngql = (
            f'GO 1 TO {depth} STEPS FROM "{entity_id}" OVER * '
            f"YIELD src(edge) AS src, dst(edge) AS dst, type(edge) AS rel, "
            f"properties(edge).status AS status LIMIT {limit};"
        )
        result = self._client.execute_raw(ngql)
        rows = []
        if result.rows:
            for row in result.rows:
                rows.append({
                    "src": str(row.get("src", "")),
                    "dst": str(row.get("dst", "")),
                    "rel": str(row.get("rel", "")),
                    "status": str(row.get("status", "")),
                })
        return rows

    def _ngql_value(self, v: Any) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
            return f'"{escaped}"'
        return f'"{str(v)}"'
