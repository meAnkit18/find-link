# Graph Explorer: Phase 1 Design

Status: Approved (automode — owner requested autonomous execution, no interactive
review gate)
Date: 2026-07-06

## Purpose

Build an end-to-end web application on top of `graph-core` that lets a user with no
graph-database knowledge upload a CSV, get an automatically-built graph, and explore it
visually: search, inspect nodes, expand neighborhoods, filter relationships.

`graph-core` remains the only component that knows NebulaGraph exists. This app is a
consumer package, same as the README's "future AML package" example — it depends on
graph-core, never imports `nebula3-python` itself, and never hand-writes nGQL.

## Key architectural problem: dynamic schemas

`graph-core`'s `Vertex`/`Edge` extension model assumes a domain package ships Python
classes for its entity types, registered once at import time (`SchemaRegistry.
register_vertex("person", PersonVertex)`). That fits a package like a future AML domain
with a known, fixed schema.

This app is different: tag and edge-type names, and their properties, are discovered
from whatever CSV a user uploads, at runtime. There is no `PersonVertex` class to write
in advance.

Rather than force dynamic schemas through the typed `Vertex`/`Edge`/`SchemaRegistry`
path (which would mean synthesizing throwaway Python classes at runtime — awkward and
fights the grain of that extension point), the app uses `graph-core`'s already-existing
schema-agnostic path: `RawVertex`/`RawEdge` plus `Metadata` for DDL. `Traversal.
get_neighbors()` already returns `RawVertex` without touching `SchemaRegistry` at all —
the app extends that same pattern to cover fetch, search, and bulk write, so
`VertexOperations`/`EdgeOperations`/`SchemaRegistry` (the typed path) are left completely
untouched for future domain packages that do want them.

## graph-core extensions (additive only, no breaking changes)

Justified by concrete needs below; nothing speculative.

1. **Bulk write** — `VertexOperations.create_many(tag, rows: list[(vid, properties)])`
   and `EdgeOperations.create_many(edge_type, rows: list[(src, dst, rank, properties)])`,
   batching into multi-row `INSERT ... VALUES v1:(...), v2:(...)` statements (one round
   trip per batch, not per row). A CSV import of thousands of rows over one-row-at-a-time
   INSERT would be prohibitively slow.
2. **Schema-agnostic reads** — `VertexOperations.get_many_raw(vids) -> list[RawVertex]`
   via `FETCH PROP ON * "v1","v2",...`, for hydrating many nodes at once (subgraph
   render, neighborhood expansion) without N round trips or a registered Vertex class.
3. **Full scan** — `Traversal.scan_vertices(tag, limit=None) -> list[RawVertex]` via
   `LOOKUP ON tag YIELD id(vertex) AS id | FETCH PROP ON * $-.id YIELD VERTEX AS v`
   (valid without a property index — LOOKUP with no WHERE clause is a full tag scan).
   Used to build the in-process search corpus (see below).
4. **Degree count** — `Traversal.count_neighbors(vid, edge_type=None, direction="out")
   -> int`, for "degree-based expansion" (show fan-out size before the user expands).

All four are new methods added to the existing `VertexOperations`/`EdgeOperations`/
`Traversal` classes plus new pure functions in `query/builder.py`, following the exact
existing pattern (validate identifiers, delegate literals to `serialization.
to_ngql_literal`). No changes to `model/`, `schema/registry.py`, `client.py`'s public
surface (only additive attributes), `config.py`, or `storage/`.

## Search: no full-text engine

NebulaGraph OSS (the `v3.6.0` images already in `docker-compose.yml`) only accelerates
equality/range LOOKUP through native tag indexes; real substring/fuzzy text search
requires an external Elasticsearch listener, which is out of scope (unnecessary
complexity for a CSV-scale tool; the product vision is "upload a CSV," not "index a
billion rows").

Decision: search is a thin app-layer concern, not a graph-core concern. On each import,
the API rebuilds an in-memory search corpus per space (vid, tag, label, lowercased
searchable text) via `scan_vertices`, then does substring matching in Python. This is
simple, always-correct, needs no ES, and is fast enough for the tens-of-thousands-of-rows
scale a CSV upload implies. Documented as a Phase 2 item if a consumer ever needs
million-row full-text search.

Every imported tag gets a synthesized `label` string property (best string column, or
row id as fallback) — this is what search matches against and what the UI displays on
nodes, so the user never has to know a tag's real property names.

## Data model: one Nebula space per "Graph"

Each upload creates or appends to a named **Graph**, backed 1:1 by a NebulaGraph space
(`Metadata.create_space`/`drop_space` already exist for this). Rationale: spaces are
NebulaGraph's natural isolation unit, mapping directly onto "a dataset the user is
exploring"; a user can create several independent Graphs over time and switch between
them, and deleting a Graph is one `DROP SPACE`.

## Import pipeline

`apps/api/import_pipeline/`:

1. **inspect** (`csv_inspector.py`) — sniff dialect/encoding, read header + a sample of
   rows, compute per-column stats: null ratio, uniqueness ratio, inferred type (int /
   float / bool / date / string) by trial-parsing the sample.
2. **infer structure** (`structure_inference.py`) — decide whether the file is an
   **edge list** (two columns look like paired entity references — detected by header
   name patterns like `from/to`, `source/target`, `*_a/*_b`, or, failing that, the two
   highest-cardinality non-numeric columns) or a **node table** (one clear id/name
   column, no plausible pair). Edge lists: remaining columns become edge properties; a
   `type`/`relationship`/`label` column (if present) is used as the edge type per row,
   grouped, else a single edge type is inferred from the filename or defaults to
   `RELATED_TO`. Node tables: tag name is inferred from the filename or a `type` column.
3. **validate** — required columns present, type-consistency per column against the
   inferred type, row-level errors collected (not fatal — bad rows are skipped and
   counted, not silently dropped and not aborting the whole import).
4. **materialize schema** — `Metadata.create_tag`/`create_edge_type` for newly-seen
   tags/edge types (idempotent, `IF NOT EXISTS`). NebulaGraph has a short schema-
   propagation delay after DDL before it's reliably writable; the writer retries the
   first batch with backoff (bounded, ~15s) rather than failing immediately — an
   operational quirk specific to this app, out of scope for graph-core itself.
5. **write** — dedupe within the import (seen-vid / seen-edge-tuple set, so re-uploading
   the same file or overlapping files doesn't create duplicate INSERTs), then bulk write
   via the new `create_many` primitives.
6. **report** — `ImportReport`: rows read, vertices created, edges created, duplicates
   skipped, validation errors (with row numbers), elapsed time.

Runs as a background job (in-process thread + job-id keyed status dict — no Redis/
Celery; single-process dev-scale tool, consistent with graph-core's own "no premature
optimization" stance). Upload endpoint returns a job id immediately; frontend polls
job status until done, then shows the report.

## Backend: FastAPI (`apps/api/`)

New Python package, own `pyproject.toml`, depends on `graph-core` via a local path
dependency (`graph-core @ file://../..`) — keeps graph-core an independently
installable/reusable package, exactly per its own README's extension contract.

Endpoints (all under `/api`):
- `POST /graphs` — create a Graph (space).
- `GET /graphs`, `GET /graphs/{id}` — list/inspect Graphs.
- `DELETE /graphs/{id}` — drop a Graph.
- `POST /graphs/{id}/imports` — upload a CSV, starts a background import job, returns
  `job_id`.
- `GET /graphs/{id}/imports/{job_id}` — job status/progress/report.
- `GET /graphs/{id}/search?q=` — substring search over the in-memory corpus.
- `GET /graphs/{id}/nodes/{vid}` — node detail (all tags/properties) + degree per edge
  type/direction.
- `GET /graphs/{id}/nodes/{vid}/neighbors?edge_type=&direction=&limit=` — one hop of
  expansion.
- `GET /graphs/{id}/overview?limit=` — an initial subgraph to render on first load
  (highest-degree nodes, capped) so the explorer isn't a blank canvas before any search.
- `GET /graphs/{id}/schema` — tags/edge types discovered, for the filter panel.

Endpoints are regular (non-`async def`) FastAPI handlers, since `graph-core` is
synchronous — FastAPI runs `def` endpoints in its worker thread pool automatically, so
no async wrapping is needed anywhere.

## Frontend: Vite + React + TypeScript (`apps/web/`)

- **Visualization**: `cytoscape` (core, not a React wrapper) driven imperatively from a
  thin React component via `useRef`/`useEffect` — gives full control over incremental
  add/remove of elements on expand/collapse, which a declarative wrapper fights. Layout:
  `cytoscape-fcose` (fast, good-quality force-directed layout, handles incremental
  re-layout on expand well).
- **Server state**: `@tanstack/react-query` for search/detail/neighbor fetches
  (caching, request dedup, polling for import jobs).
- **Canvas/UI state**: `zustand` — small, focused store for selection, expanded-node
  set, active filters; avoids prop-drilling between the search bar, canvas, detail
  panel, and filter panel, which are siblings.
- **Routing**: `react-router-dom` — Graphs list → Upload → Explorer.
- **Styling**: plain CSS (CSS Modules + a small set of CSS-variable design tokens for
  color/spacing/type) — no Tailwind toolchain, keeps the build minimal.

### Interaction model

- Landing on a Graph shows the `/overview` subgraph immediately (never a blank canvas).
- Search bar filters/highlights matches on the current canvas and can pull a match onto
  canvas if it isn't already there.
- Click a node → detail panel (properties, degree per relationship type).
- Double-click / "Expand" action on a node → fetch neighbors, add to canvas, re-layout
  incrementally (existing node positions preserved where possible).
- Right-click / "Collapse" → remove nodes that would become orphaned (not referenced by
  any other visible node) back off canvas.
- Filter panel: toggle visibility per edge type / per tag; hidden types are removed from
  canvas, not just dimmed, to keep large graphs legible.
- Degree badges on nodes hint at fan-out before expanding.

## Assumptions and risks

- NebulaGraph `v3.6.0` (matching `docker-compose.yml`) is the deployment target; nGQL
  syntax assumed (`LOOKUP` without `WHERE`, multi-row `INSERT ... VALUES`) is written
  from documented behavior, consistent with graph-core's own existing disclaimer that
  exact client/server behavior needs verification against a running instance — the
  owner is running Docker/the app manually, so that verification happens outside this
  session.
- Single-process job tracking (in-memory dict) means import job status is lost on API
  process restart. Acceptable for Phase 1 (single-user local tool); flagged as a Phase 2
  durability gap, not fixed now.
- Schema-propagation delay after `CREATE TAG`/`CREATE EDGE` is handled with a bounded
  retry, not a guaranteed wait — under unusual load this could still occasionally need a
  retry of the import.
- No auth/multi-tenancy in Phase 1 — matches "no knowledge of graph databases" personal-
  exploration-tool framing, not a multi-user deployment.

## Testing strategy

- `graph-core` extensions: unit tests mirroring existing style (mocked
  `nebula3-python`), plus builder-function tests (pure, no mocking).
- Import pipeline: unit tests for `csv_inspector`/`structure_inference` against sample
  CSVs (pure functions, no DB).
- API: FastAPI `TestClient` tests against a fake `GraphClient` (dependency-injected),
  no live NebulaGraph required.
- Frontend: component tests for the non-canvas pieces (upload flow, search, detail
  panel); Cytoscape canvas verified manually (owner runs the app).
- End-to-end/manual verification against a real NebulaGraph instance is the owner's
  responsibility per their instruction not to run Docker/the app in this session.
