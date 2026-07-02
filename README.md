# graph-core

A domain-agnostic Graph Data Layer over NebulaGraph. See
`docs/superpowers/specs/2026-07-02-graph-core-design.md` for the full
architecture and design rationale.

## Installation

    pip install -e ".[dev]"

## Running tests

Unit tests require no NebulaGraph instance or installed `nebula3-python`:

    pytest tests/unit -v

Integration tests require a real NebulaGraph instance and the
`nebula3-python` package installed. They are skipped unless `NEBULA_TEST_HOST`
is set:

    NEBULA_TEST_HOST=127.0.0.1 pytest tests/integration -v

## Usage

    from graph_core import GraphClient
    from graph_core.config import GraphConfig

    config = GraphConfig(
        hosts=[("127.0.0.1", 9669)],
        user="root",
        password="nebula",
        space="my_space",
    )

    with GraphClient(config) as client:
        client.metadata.create_space("my_space")
        # ... create tags/edges, then use client.vertices / client.edges / client.traversal

## Extending with a new domain (e.g. a future AML package)

1. Subclass `graph_core.model.vertex.Vertex` / `graph_core.model.edge.Edge`,
   optionally overriding `validate()`.
2. Call `SchemaRegistry.register_vertex("account", AccountVertex)` /
   `register_edge(...)` at import time.
3. Define `TagSchema`/`EdgeSchema` and call `Metadata.create_tag(...)` /
   `create_edge_type(...)` to materialize the schema in NebulaGraph.
4. Compose `VertexOperations`, `EdgeOperations`, `Traversal` inside your own
   domain-specific repository rather than inheriting from them.

No changes to `graph-core` itself are required to add a new domain.
