"""Rebuild the field-value index over an already-ingested space.

Existing spaces predate the index and their documents predate the generic
`document` tag, so the graph has people and documents but no `field_value`
vertices at all. This walks what is there and emits the index under the
current denylist and normalisation rules.

Re-runnable by construction: INSERT VERTEX overwrites by vid and the value
vid is a pure function of the value, so a second run after retuning the
denylist converges rather than duplicating.

    .venv/bin/python scripts/reindex_field_values.py --dry-run
    .venv/bin/python scripts/reindex_field_values.py --space intel_kg_v2
"""

from __future__ import annotations

import argparse

from graph_core.client import GraphClient
from graph_core.schema.models import EdgeSchema, PropertyDefinition, TagSchema
from graph_explorer_api.config import load_settings
from graph_explorer_api.services.entity_props import merged_properties
from intelligence_schema.field_index import field_values
from intelligence_schema.graph_writer import GraphWriter

PERSON_TAG = "person"

# A space ingested before this change holds passports under HAS_PASSPORT and
# the `passport` tag. Both are read, so a legacy space reindexes without
# needing to be re-ingested first.
DOCUMENT_EDGES = ("HAS_DOCUMENT", "HAS_PASSPORT")
LEGACY_DOCUMENT_TAG = "passport"
DOCUMENT_TAG = "document"


def ensure_index_schema(client: GraphClient) -> None:
    """Create the index's tag and edge if this space predates them.

    Every statement is IF NOT EXISTS, so this is safe on a space that
    already has them.
    """
    client.metadata.create_tag(TagSchema(name="field_value", properties=[
        PropertyDefinition("label", "string"),
        PropertyDefinition("entity_type", "string"),
        PropertyDefinition("value", "string", nullable=True),
        PropertyDefinition("created_at", "int64", nullable=True),
    ]))
    client.metadata.create_edge_type(EdgeSchema(name="HAS_FIELD_VALUE", properties=[
        PropertyDefinition("field_key", "string", nullable=True),
        PropertyDefinition("document_id", "string", nullable=True),
        PropertyDefinition("document_type", "string", nullable=True),
        PropertyDefinition("created_at", "int64", nullable=True),
    ]))


def _person_ids(client: GraphClient) -> list[str]:
    result = client.execute_raw(f"LOOKUP ON {PERSON_TAG} YIELD id(vertex) AS vid;")
    return [str(row["vid"]) for row in (result.rows or [])]


def _document_edges(client: GraphClient) -> list[str]:
    """Whichever document edge types this space actually has — `GO ... OVER
    <unknown>` is a hard nGQL error, not an empty result."""
    available = set(client.metadata.list_edges())
    return [edge for edge in DOCUMENT_EDGES if edge in available]


def _documents_of(client: GraphClient, person_id: str, edges: list[str]) -> list[str]:
    if not edges:
        return []
    result = client.execute_raw(
        f'GO FROM "{person_id}" OVER {", ".join(edges)} YIELD dst(edge) AS vid;'
    )
    return [str(row["vid"]) for row in (result.rows or [])]


def _vertex(client: GraphClient, vid: str):
    return next(iter(client.vertices.get_many_raw([vid])), None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    settings = load_settings()
    parser.add_argument("--space", default=settings.nebula_space)
    parser.add_argument(
        "--dry-run", action="store_true", help="Count what would be indexed, write nothing"
    )
    args = parser.parse_args()

    client = GraphClient(settings.build_config(args.space))
    client.connect()
    writer = GraphWriter(client)
    values_indexed = 0
    documents_seen = 0
    legacy_documents = 0
    people: list[str] = []

    try:
        if not args.dry_run:
            ensure_index_schema(client)
        edges = _document_edges(client)
        people = _person_ids(client)
        for person_id in people:
            vertex = _vertex(client, person_id)
            if vertex is None:
                continue
            own = merged_properties(vertex)
            if args.dry_run:
                values_indexed += len(field_values(own))
            else:
                values_indexed += writer.index_field_values(person_id, own)

            for document_id in _documents_of(client, person_id, edges):
                document = _vertex(client, document_id)
                if document is None:
                    continue
                documents_seen += 1
                props = merged_properties(document)
                is_legacy = LEGACY_DOCUMENT_TAG in document.tags
                if is_legacy:
                    legacy_documents += 1
                # A legacy vertex carries no document_type; it is a passport
                # by virtue of the tag it was stored under.
                document_type = str(
                    props.get("document_type") or (LEGACY_DOCUMENT_TAG if is_legacy else "document")
                )
                if args.dry_run:
                    values_indexed += len(field_values(props))
                else:
                    values_indexed += writer.index_field_values(
                        person_id,
                        props,
                        document_id=document_id,
                        document_type=document_type,
                    )
    finally:
        client.close()

    verb = "would index" if args.dry_run else "indexed"
    legacy_note = (
        f" ({legacy_documents} still on the legacy `{LEGACY_DOCUMENT_TAG}` tag)"
        if legacy_documents
        else ""
    )
    print(
        f"{len(people)} people, {documents_seen} documents{legacy_note}, "
        f"{verb} {values_indexed} values in space {args.space}"
    )


if __name__ == "__main__":
    main()
