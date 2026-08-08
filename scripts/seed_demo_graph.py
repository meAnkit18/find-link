"""Write the demo population into NebulaGraph.

Uses the same GraphWriter calls the ingestion pipeline makes, so what lands
here is what real ingestion would produce — including the field-value index,
which is what the person projection actually walks.

Idempotent: every vid is fixed and INSERT VERTEX overwrites, so re-running
converges rather than duplicating.

    .venv/bin/python scripts/seed_demo_graph.py --dry-run
    .venv/bin/python scripts/seed_demo_graph.py
    .venv/bin/python scripts/seed_demo_graph.py --space demo_graph
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from graph_core.client import GraphClient
from graph_explorer_api.config import load_settings
from graph_explorer_api.ingest.writer import write_with_retry
from intelligence_schema.graph_writer import GraphWriter
from intelligence_schema.ingest_schema import ensure_ingest_schema

sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_graph_data import (  # noqa: E402
    PEOPLE,
    document_by_id,
    holdings,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    settings = load_settings()
    parser.add_argument("--space", default=settings.nebula_space)
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be written, write nothing"
    )
    args = parser.parse_args()

    documents = document_by_id()
    pairs = holdings()

    if args.dry_run:
        print(
            f"would write {len(PEOPLE)} people, {len(documents)} documents, "
            f"{len(pairs)} holdings into space {args.space}"
        )
        return

    client = GraphClient(settings.build_config(args.space))
    client.connect()
    ensure_ingest_schema(client, args.space)
    writer = GraphWriter(client)
    values_indexed = 0

    try:
        # NebulaGraph takes a moment after CREATE TAG before the tag is
        # writable, so on a brand-new space the first write of each kind is
        # retried with backoff. Re-writing is harmless: INSERT overwrites.
        first = PEOPLE[0]
        write_with_retry(lambda: writer.upsert_entity(
            tag="Person", vid=first["id"], name=first["name"],
            attributes=dict(first["attributes"]), confidence=1.0,
        ))
        write_with_retry(lambda: writer.index_field_values(first["id"], first["attributes"]))

        for person in PEOPLE:
            writer.upsert_entity(
                tag="Person", vid=person["id"], name=person["name"],
                attributes=dict(person["attributes"]), confidence=1.0,
            )
            values_indexed += writer.index_field_values(person["id"], person["attributes"])

        first_document = next(iter(documents.values()))
        write_with_retry(lambda: writer.upsert_entity(
            tag="Document", vid=first_document["id"], name=first_document["number"],
            attributes={
                **first_document["attributes"],
                "number": first_document["number"],
                "document_type": first_document["document_type"],
            },
            confidence=1.0,
        ))
        write_with_retry(lambda: writer.upsert_relationship(
            edge_type="HAS_DOCUMENT",
            src_id=pairs[0][0], dst_id=pairs[0][1], confidence=1.0,
        ))

        for document in documents.values():
            props = {
                **document["attributes"],
                "number": document["number"],
                "document_type": document["document_type"],
            }
            writer.upsert_entity(
                tag="Document", vid=document["id"], name=document["number"],
                attributes=dict(props), confidence=1.0,
            )

        for person_id, document_id in pairs:
            document = documents[document_id]
            props = {
                **document["attributes"],
                "number": document["number"],
                "document_type": document["document_type"],
            }
            writer.upsert_relationship(
                edge_type="HAS_DOCUMENT", src_id=person_id, dst_id=document_id,
                confidence=1.0,
            )
            values_indexed += writer.index_field_values(
                person_id, props,
                document_id=document_id, document_type=document["document_type"],
            )
    finally:
        client.close()

    print(
        f"wrote {len(PEOPLE)} people, {len(documents)} documents, {len(pairs)} holdings "
        f"and indexed {values_indexed} values into space {args.space}"
    )


if __name__ == "__main__":
    main()
