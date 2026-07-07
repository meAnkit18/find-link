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

### Local development with Docker

`docker-compose.yml` brings up a single-node NebulaGraph cluster
(metad/storaged/graphd) for local dev, sized to run comfortably on a small
machine (~1.3GB RAM combined across all services).

Start it:

    docker compose up -d
    docker compose ps          # wait until all services show "healthy"

The `console` service is a one-shot job that registers the storage host
with the meta service (`ADD HOSTS`) — required once per fresh cluster
before any space can be created. It exits after running; check its log if
space creation fails:

    docker compose logs console

Then point graph-core / the integration tests at it (these are already the
defaults in `tests/integration/test_smoke.py`, so plain `NEBULA_TEST_HOST`
is enough):

    NEBULA_TEST_HOST=127.0.0.1 pytest tests/integration -v

Shut down, keeping data:

    docker compose down

Reset the database (wipe all data/volumes and start clean):

    docker compose down -v
    docker compose up -d

Troubleshooting:

- **A service never becomes healthy** — `docker compose logs metad0` (or
  `storaged0`/`graphd`). Most often this is a stale volume from an
  incompatible previous version; `docker compose down -v` and retry.
- **`ADD HOSTS` / space creation fails** — the `console` job runs once,
  5 seconds after `graphd` reports healthy. If `graphd` was slow to elect
  a leader, that timing may be tight; check `docker compose logs console`
  and re-run manually if needed:
  `docker exec -it $(docker compose ps -q graphd) nebula-console -addr 127.0.0.1 -port 9669 -u root -p nebula -e 'ADD HOSTS "storaged0":9779;'`
- **Out of memory / containers killed** — the per-service `mem_limit`
  values in `docker-compose.yml` are tuned for ~2GB-RAM machines; lower
  them further (or free up RAM from other processes) if containers get
  OOM-killed, or raise them if you have more headroom.

To run against a NebulaGraph Cloud (cloud.nebula-graph.io) cluster, copy
`example.env` to `.env`, fill in your cluster's host/port/user/password
(keep `NEBULA_TEST_USE_SSL=true`, which Cloud requires), then:

    set -a; source .env; set +a
    pytest tests/integration -v

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

## Graph Explorer (Phase 1 app)

`apps/` contains an end-to-end web app built on top of `graph-core`: upload
a CSV, get an automatically-inferred graph, and explore it visually
(search, expand neighborhoods, inspect nodes, filter by type) — no nGQL
required. See
`docs/superpowers/specs/2026-07-06-graph-explorer-design.md` for the full
architecture and rationale.

- `apps/api/` — FastAPI backend (CSV import pipeline + exploration API).
  See `apps/api/README.md` to install and run it against
  the NebulaGraph cluster from `docker-compose.yml`.
- `apps/web/` — Vite + React + TypeScript frontend (Cytoscape.js graph
  canvas). See `apps/web/README.md`.

Quick start once NebulaGraph is up (`docker compose up -d`):

    pip install -e ".[dev]"                 # graph-core
    pip install -e "apps/api[dev]"          # backend
    uvicorn graph_explorer_api.main:app --reload --port 8000 \
      --app-dir apps/api/src

    cd apps/web && npm install && npm run dev   # frontend, in another shell
