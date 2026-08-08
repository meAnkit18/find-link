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
from graph_explorer_api.config import load_settings
from graph_explorer_api.services.entity_props import merged_properties
from intelligence_schema.field_index import field_values
from intelligence_schema.graph_writer import GraphWriter

PERSON_TAG = "person"


def _person_ids(client: GraphClient) -> list[str]:
    result = client.execute_raw(f"LOOKUP ON {PERSON_TAG} YIELD id(vertex) AS vid;")
    return [str(row["vid"]) for row in (result.rows or [])]


def _documents_of(client: GraphClient, person_id: str) -> list[str]:
    result = client.execute_raw(
        f'GO FROM "{person_id}" OVER HAS_DOCUMENT YIELD dst(edge) AS vid;'
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

    try:
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

            for document_id in _documents_of(client, person_id):
                document = _vertex(client, document_id)
                if document is None:
                    continue
                documents_seen += 1
                props = merged_properties(document)
                if args.dry_run:
                    values_indexed += len(field_values(props))
                else:
                    values_indexed += writer.index_field_values(
                        person_id,
                        props,
                        document_id=document_id,
                        document_type=str(props.get("document_type") or "document"),
                    )
    finally:
        client.close()

    verb = "would index" if args.dry_run else "indexed"
    print(
        f"{len(people)} people, {documents_seen} documents, {verb} {values_indexed} values "
        f"in space {args.space}"
    )


if __name__ == "__main__":
    main()
