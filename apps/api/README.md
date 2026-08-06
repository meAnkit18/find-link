# graph-explorer-api

FastAPI backend for the Graph Explorer app. Depends on `graph-core` (this
repo's data access layer) as a plain Python import — it never touches
NebulaGraph or nGQL directly.

## Install

`graph-core` isn't declared as a packaging dependency here (a relative
path dependency between two `pyproject.toml`s isn't reliably resolved by
pip); install both into the same environment, graph-core first:

    pip install -e ".[dev]"          # from the repo root — installs graph-core
    pip install -e "apps/api[dev]"   # this package

## Run

Requires a reachable NebulaGraph cluster (see the repo root README for
`docker compose up -d`). Configure via environment variables (defaults
match `docker-compose.yml`):

    NEBULA_HOST=127.0.0.1
    NEBULA_PORT=9669
    NEBULA_USER=root
    NEBULA_PASSWORD=nebula
    NEBULA_USE_SSL=false
    GRAPH_EXPLORER_DATA_DIR=./data   # uploaded CSVs + graph registry

Then:

    uvicorn graph_explorer_api.main:app --reload --port 8000

## The person-network projection

`services/person_network_service.py` serves the Investigation page. The
graph stores a person's phone, email, passport, address and employer as
separate vertices joined by `HAS_*`/`LOCATED_AT`/`WORKS_AT` edges, so two
people who share a phone are two stored hops apart with no edge between
them. The service projects that onto a **person-only** graph in which an
edge means "these two share something", carrying the shared vertex along as
the reason. Degree 1/2/3 is breadth-first search over that projection, not
over raw hops.

- `GET /api/entities/{id}/person-network?degree=1..3` — persons, links
  (each with a `via` list explaining the connection), `truncated`, and
  `suppressed_hubs`.
- `GET /api/entities/{id}/attributes` — one person's own attribute
  vertices, each with `shared_with` (the other people holding it).

Two things to know before changing it:

- **Fan-out is the failure mode.** A phone shared by 400 people would emit
  ~80k links. Connectors held by more than `max_fanout` (default 25) people
  are skipped and reported in `suppressed_hubs` rather than silently
  dropped; `CITIZEN_OF` is off by default for the same reason, and is
  available via the `connectors` parameter.
- **Edge types are checked against the space first.** A space built from a
  partial import won't have every edge type, and `GO ... OVER <unknown>` is
  a hard nGQL error, not an empty result.

Traversal cost is ~5 batched queries per BFS level (via graph-core's
`Traversal.neighbors_batch`), not two per vertex as `expand_node` does.
`expand_node` and `/api/entities/{id}/graph` are unchanged and still back
Explorer, the risk context, and the agent toolbox.

## Tests

Unit tests use a fake `GraphClient`/executor — no NebulaGraph instance
required:

    pytest tests/unit -v
