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

## Tests

Unit tests use a fake `GraphClient`/executor — no NebulaGraph instance
required:

    pytest tests/unit -v
