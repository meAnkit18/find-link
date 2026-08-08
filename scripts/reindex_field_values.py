"""Rebuild the field-value index over an already-ingested space.

Ingestion indexes as it writes, so this exists for the case ingestion can't
cover: the matching rules themselves changed. Retune a field weight, add a
key to the denylist, or change how values normalise, and the index on disk
is stale — this rebuilds it from the people and documents already there.

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
DOCUMENT_EDGE = "HAS_DOCUMENT"


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


def _has_document_edge(client: GraphClient) -> bool:
    """`GO ... OVER <unknown>` is a hard nGQL error, not an empty result, so
    a space with nothing ingested yet has to be checked rather than walked."""
    return DOCUMENT_EDGE in set(client.metadata.list_edges())


def _documents_of(client: GraphClient, person_id: str) -> list[str]:
    result = client.execute_raw(
        f'GO FROM "{person_id}" OVER {DOCUMENT_EDGE} YIELD dst(edge) AS vid;'
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
    people: list[str] = []

    try:
        if not args.dry_run:
            ensure_index_schema(client)
        has_documents = _has_document_edge(client)
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

            if not has_documents:
                continue
            for document_id in _documents_of(client, person_id):
                document = _vertex(client, document_id)
                if document is None:
                    continue
                documents_seen += 1
                props = merged_properties(document)
                document_type = str(props.get("document_type") or "document")
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
    print(
        f"{len(people)} people, {documents_seen} documents, "
        f"{verb} {values_indexed} values in space {args.space}"
    )


if __name__ == "__main__":
    main()
