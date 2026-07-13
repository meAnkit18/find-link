from __future__ import annotations

import json
import time
from typing import Any

from graph_core.client import GraphClient
from intelligence_schema.ingest_schema import ENTITY_TAG, KEY_COLUMN


class GraphWriter:
    """Projects accepted facts into NebulaGraph.

    Idempotent re-projections: INSERT VERTEX overwrites props for an existing VID,
    so re-running a write for the same evidence converges to the same state.
    """

    def __init__(self, client: GraphClient) -> None:
        self._client = client

    # ------------------------------------------------------------- entities

    def upsert_entity(
        self, tag: str, vid: str, name: str,
        attributes: dict[str, Any] | None = None,
        confidence: float = 0.0,
        evidence_id: str | None = None,
    ) -> None:
        entity_type = tag
        tag = ENTITY_TAG.get(tag, tag.lower())

        now = int(time.time())
        attrs = dict(attributes or {})
        aliases = attrs.pop("aliases", [])
        extra_props = attrs.pop("extra_props", {})
        props_bag = {**extra_props, **attrs}

        cols = ["label", "entity_type", "props", "confidence",
                "evidence_ids", "created_at", "updated_at"]
        vals = [
            self._ngql_value(name),
            self._ngql_value(entity_type),
            self._ngql_value(
                json.dumps({"aliases": aliases, **props_bag}, ensure_ascii=False, default=str)
            ),
            self._ngql_value(float(confidence)),
            self._ngql_value(json.dumps([evidence_id] if evidence_id else [])),
            self._ngql_value(now),
            self._ngql_value(now),
        ]

        if tag in KEY_COLUMN:
            key_col = KEY_COLUMN[tag]
            cols.insert(1, key_col)
            vals.insert(1, self._ngql_value(str(attrs.get(key_col, "") or props_bag.get(key_col, ""))))

        ngql = (
            f'INSERT VERTEX {tag}({", ".join(cols)}) '
            f'VALUES {self._ngql_value(str(vid))}:({", ".join(vals)});'
        )
        self._client.execute_raw(ngql)

    def upsert_evidence(self, evidence_id: str, source_name: str, source_type: str) -> None:
        now = int(time.time())
        ngql = (
            f'INSERT VERTEX evidence(label, entity_type, source_name, source_type, created_at) '
            f'VALUES {self._ngql_value(str(evidence_id))}:('
            f'{self._ngql_value(source_name)}, {self._ngql_value("evidence")}, '
            f'{self._ngql_value(source_name)}, {self._ngql_value(source_type)}, {now});'
        )
        self._client.execute_raw(ngql)

    # -------------------------------------------------------- relationships

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
            "relationship_type": relation_label or "",
            "created_at": now,
        }
        cols = ", ".join(props.keys())
        vals = ", ".join(self._ngql_value(v) for v in props.values())
        ngql = (
            f'INSERT EDGE {edge_type}({cols}) VALUES '
            f'{self._ngql_value(str(src_id))}->{self._ngql_value(str(dst_id))}:({vals});'
        )
        self._client.execute_raw(ngql)

    def link_supported_by(self, entity_id: str, evidence_id: str, confidence: float) -> None:
        now = int(time.time())
        ngql = (
            f'INSERT EDGE SUPPORTED_BY(extraction_confidence, created_at) VALUES '
            f'{self._ngql_value(str(entity_id))}->{self._ngql_value(str(evidence_id))}'
            f':({float(confidence)}, {now});'
        )
        self._client.execute_raw(ngql)

    # ------------------------------------------------------------ traversal

    def fetch_neighborhood(self, entity_id: str, depth: int = 2, limit: int = 60) -> list[dict]:
        ngql = (
            f'GO 1 TO {depth} STEPS FROM {self._ngql_value(str(entity_id))} OVER * '
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

    # -------------------------------------------------------------- values

    def _ngql_value(self, v: Any) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if not isinstance(v, str):
            v = str(v)
        escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
