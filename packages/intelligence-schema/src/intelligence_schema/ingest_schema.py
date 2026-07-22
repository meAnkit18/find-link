"""Uniform ingest schema + entity-type -> Nebula-tag mapping.

The LLM extraction ontology (ingestion_core.canonical.EntityType /
RELATIONSHIP_TYPES) is the source of truth; this module materializes a
matching NebulaGraph schema and provides the mapping the GraphWriter uses.

Uniform tag columns (all entity tags):
    label        string   -- display name
    entity_type  string   -- original CamelCase type ("Person", "BankAccount")
    props        string   -- JSON: aliases + every extracted attribute
    confidence   double
    evidence_ids string   -- JSON list of supporting evidence ids
    created_at   int64    -- unix seconds
    updated_at   int64
plus one key column for identifier-like types (number/address/iban/plate/iso2).

Uniform edge columns (all relationship edge types):
    confidence, status ("accepted"|"proposed"), evidence_ids, props,
    relationship_type (used by RELATED_TO for the free-form label), created_at.
"""

from __future__ import annotations

import threading
import time

from graph_core.schema.models import EdgeSchema, PropertyDefinition, TagSchema

# Extraction ontology type -> Nebula tag
ENTITY_TAG: dict[str, str] = {
    "Person": "person",
    "Company": "company",
    "Organization": "organization",
    "Address": "address",
    "Country": "country",
    "Passport": "passport",
    "Phone": "phone",
    "Email": "email",
    "BankAccount": "bank_account",
    "Vehicle": "vehicle",
}

# Per-tag identifier column (matches GraphWriter._EXTRA_COLUMN)
KEY_COLUMN: dict[str, str] = {
    "country": "iso2",
    "passport": "number",
    "phone": "number",
    "email": "address",
    "bank_account": "iban",
    "vehicle": "plate",
}

# Every relationship type the extractor can emit (ingestion_core.canonical)
INGEST_EDGE_TYPES: list[str] = [
    "WORKS_AT", "OWNS", "PAYS", "HAS_PASSPORT", "HAS_PHONE", "HAS_EMAIL",
    "HAS_ACCOUNT", "OWNS_VEHICLE", "LOCATED_AT", "CITIZEN_OF", "RELATED_TO",
]

_UNIFORM_TAG_PROPS = [
    PropertyDefinition("label", "string"),
    PropertyDefinition("entity_type", "string"),
    PropertyDefinition("props", "string", nullable=True),
    PropertyDefinition("confidence", "double", nullable=True),
    PropertyDefinition("evidence_ids", "string", nullable=True),
    PropertyDefinition("created_at", "int64", nullable=True),
    PropertyDefinition("updated_at", "int64", nullable=True),
]

_UNIFORM_EDGE_PROPS = [
    PropertyDefinition("confidence", "double", nullable=True),
    PropertyDefinition("status", "string", nullable=True),
    PropertyDefinition("evidence_ids", "string", nullable=True),
    PropertyDefinition("props", "string", nullable=True),
    PropertyDefinition("relationship_type", "string", nullable=True),
    PropertyDefinition("created_at", "int64", nullable=True),
]

_ensured: set[str] = set()
_lock = threading.Lock()


def ensure_ingest_schema(client, space: str) -> None:
    """Idempotently create space + uniform tags/edges. Safe to call often.

    The `_ensured` cache is only a fast path: we still verify the space
    actually exists, because it can be dropped out from under us (graph
    deleted via the UI, `DROP SPACE` in a console, or a Nebula data reset)
    while this process keeps running.
    """
    with _lock:
        if space in _ensured:
            try:
                if client.metadata.space_exists(space):
                    return
            except Exception:
                pass  # can't verify — fall through and re-ensure from scratch
            _ensured.discard(space)  # space vanished; rebuild it below

        client.metadata.create_space(space, vid_type="FIXED_STRING(64)")
        _wait_for_space(client, space)

        _retry_ddl(client, lambda: client.metadata.create_tag(
            TagSchema(name="person", properties=_tag_props("person"))
        ))

        for tag in ENTITY_TAG.values():
            if tag == "person":
                continue
            client.metadata.create_tag(TagSchema(name=tag, properties=_tag_props(tag)))

        client.metadata.create_tag(TagSchema(name="evidence", properties=[
            PropertyDefinition("label", "string"),
            PropertyDefinition("entity_type", "string"),
            PropertyDefinition("source_name", "string", nullable=True),
            PropertyDefinition("source_type", "string", nullable=True),
            PropertyDefinition("created_at", "int64", nullable=True),
        ]))

        for edge in INGEST_EDGE_TYPES:
            client.metadata.create_edge_type(
                EdgeSchema(name=edge, properties=list(_UNIFORM_EDGE_PROPS))
            )
        client.metadata.create_edge_type(EdgeSchema(name="SUPPORTED_BY", properties=[
            PropertyDefinition("extraction_confidence", "double", nullable=True),
            PropertyDefinition("created_at", "int64", nullable=True),
        ]))

        # Additional schemas for investigations and review queue
        client.metadata.create_tag(TagSchema(name="review_item", properties=[
            PropertyDefinition("queue_type", "string", nullable=True),
            PropertyDefinition("status", "string", nullable=True),
            PropertyDefinition("reviewed_at", "datetime", nullable=True),
            PropertyDefinition("reviewed_by", "string", nullable=True),
            PropertyDefinition("decision_reason", "string", nullable=True),
        ]))
        client.metadata.create_tag(TagSchema(name="investigation_case", properties=[
            PropertyDefinition("title", "string", nullable=True),
            PropertyDefinition("status", "string", nullable=True),
            PropertyDefinition("priority", "string", nullable=True),
            PropertyDefinition("created_by", "string", nullable=True),
            PropertyDefinition("created_at", "datetime", nullable=True),
            PropertyDefinition("updated_at", "datetime", nullable=True),
        ]))
        client.metadata.create_tag(TagSchema(name="case_note", properties=[
            PropertyDefinition("body", "string", nullable=True),
            PropertyDefinition("author_id", "string", nullable=True),
            PropertyDefinition("created_at", "datetime", nullable=True),
            PropertyDefinition("updated_at", "datetime", nullable=True),
        ]))
        client.metadata.create_edge_type(EdgeSchema(name="HAS_SUBJECT", properties=[
            PropertyDefinition("subject_role", "string", nullable=True),
            PropertyDefinition("added_at", "datetime", nullable=True),
            PropertyDefinition("added_by", "string", nullable=True),
        ]))
        client.metadata.create_edge_type(EdgeSchema(name="HAS_NOTE", properties=[
            PropertyDefinition("created_at", "datetime", nullable=True),
        ]))

        _verify_uniform(client, space)
        _ensured.add(space)


def _tag_props(tag: str) -> list[PropertyDefinition]:
    props = list(_UNIFORM_TAG_PROPS)
    if tag in KEY_COLUMN:
        props.insert(1, PropertyDefinition(KEY_COLUMN[tag], "string", nullable=True))
    return props


def _retry_ddl(client, fn, attempts: int = 12, delay: float = 2.0) -> None:
    last: Exception | None = None
    for _ in range(attempts):
        try:
            fn()
            return
        except Exception as exc:
            last = exc
            time.sleep(delay)
    raise RuntimeError(f"NebulaGraph DDL kept failing for space setup: {last}")


def _wait_for_space(client, space: str, attempts: int = 30, delay: float = 2.0) -> None:
    """Block until the (asynchronously created) space accepts `USE <space>`.

    NebulaGraph makes a new space usable only after the meta info propagates
    (~2 heartbeat cycles). `execute_raw` runs `USE <space>` first, so a
    successful SHOW TAGS proves the space is ready for DDL.
    """
    last: Exception | None = None
    for _ in range(attempts):
        try:
            client.execute_raw("SHOW TAGS")
            return
        except Exception as exc:
            last = exc
            time.sleep(delay)
    raise RuntimeError(
        f"space '{space}' was created but never became usable "
        f"(is storaged registered via ADD HOSTS?): {last}"
    )


def invalidate_ensured(space: str) -> None:
    """Forget a space so the next ensure_ingest_schema() rebuilds it.

    Call this whenever a space is dropped (graph deletion) so a stale
    in-process cache can't cause instant SpaceNotFound failures later.
    """
    with _lock:
        _ensured.discard(space)


def _verify_uniform(client, space: str) -> None:
    result = client.execute_raw("DESCRIBE TAG person")
    fields = {row.get("Field") for row in result.rows}
    if "props" not in fields:
        raise RuntimeError(
            f"Space '{space}' contains a legacy 'person' tag without the uniform "
            f"'props' column. Either drop the space (DROP SPACE {space}; -- this "
            f"deletes its data) or point NEBULA_SPACE at a fresh space name, "
            f"then restart the API."
        )
