# graph-core: Graph Data Layer Design

Status: Approved
Date: 2026-07-02

## Purpose and Scope

`graph-core` is a standalone, domain-agnostic Graph Data Layer on top of NebulaGraph.
It is the only package permitted to know that NebulaGraph exists. Future packages
(an AML domain package, a REST API, an MCP server, background workers) depend on
`graph-core` without knowing anything about NebulaGraph, nGQL, or the `nebula3-python`
client.

**Explicitly out of scope for this package:** REST APIs, authentication, frontend,
MCP server, AI agents, PostgreSQL, Elasticsearch, Redis, business workflows, AML rules,
and any AML-specific domain models (Person, Account, Transaction, OWNS, etc.). Those
belong in future packages that depend on `graph-core`.

## Guiding Principles

These principles, set by the project owner, shape every design choice below:

- Evolutionary architecture: build only what today's requirements justify. Design
  extension points; do not build out speculative machinery behind them.
- No premature optimization: no async, no thread pools, no distributed-systems
  concerns. Use the official `nebula3-python` client synchronously, as intended.
- Simplicity over cleverness: every abstraction must solve a problem that exists now.
- Domain-agnostic: no AML or other business concepts anywhere in this package.
- NebulaGraph details are fully hidden above the storage layer.
- Correctness and maintainability over architectural perfection.

## Architecture

### Layering

```
Repository layer   VertexOperations, EdgeOperations, Traversal
                    - non-generic primitives; future domain repositories
                      (e.g. PersonRepository) compose these rather than
                      inherit from a generic repository base class
                    v (uses)
Metadata            Metadata — graph administration: spaces, tag/edge/index
                    creation, schema inspection (SHOW/DESCRIBE)
                    v (uses)
Schema layer        SchemaRegistry (Python class <-> tag/edge name mapping,
                    the extension point domain packages call at import time),
                    schema/models.py (PropertyDefinition, TagSchema, EdgeSchema)
                    v (uses)
Query layer         query/builder.py — pure functions building nGQL strings.
                    No I/O, no nebula3-python import.
                    v (calls)
Storage layer        THE ONLY layer importing nebula3-python.
                    - connection.py: ConnectionPool wrapper (start/close)
                    - session.py: session acquire/release context manager
                    - executor.py: execute(ngql) -> QueryResult
                    - serialization.py: centralized bidirectional conversion
                      between NebulaGraph value types and plain Python /
                      RawVertex / RawEdge / RawPath
                    - result.py: QueryResult, RawVertex, RawEdge, RawPath
```

Each layer depends only on the layer(s) below it. Nothing above `storage/` imports
`nebula3-python`.

### Why result-conversion lives in the storage layer

An earlier draft placed query execution and result-conversion in a separate "query"
layer above storage. That's wrong: converting Nebula's `ValueWrapper`/`Vertex`/`Edge`
types requires importing `nebula3-python`, and only `storage/` is allowed to do that.
So `storage/executor.py` executes nGQL and returns already-converted, Nebula-agnostic
`QueryResult` objects; `query/builder.py` only builds nGQL strings and never touches
`nebula3-python`.

### Why composition over a generic repository hierarchy

A generic `Repository[V]` base class with fixed `get`/`create`/`upsert`/`delete`
signatures looks reusable but fights domain-specific needs the moment a future
repository needs something like `find_by_email()`. Instead, `VertexOperations` and
`EdgeOperations` are concrete (non-generic) classes that operate on any object
satisfying the `Vertex`/`Edge` ABC contract (`tag`/`edge_type`, `vid`/`src`+`dst`+`rank`,
`properties`, `validate()`), resolved at runtime via `SchemaRegistry`. Future domain
repositories hold these as a dependency and compose them, rather than inheriting from
a base class.

### Injection safety

nGQL has no general prepared-statement support for identifiers (tag names, edge type
names, property names) — those must be validated, not escaped. `query/builder.py`
validates all identifiers against a strict allowlist pattern
(`^[A-Za-z_][A-Za-z0-9_]*$`) and delegates value-literal escaping to
`storage/serialization.py`'s `to_ngql_literal()`, the single place Python values
become nGQL literals.

## Project Structure

```
graph_core/
  config.py                # GraphConfig — plain dataclass (hosts, user, password, space, pool size, timeout)
  exceptions.py             # GraphCoreError, ConnectionError, QueryExecutionError, SchemaError, ValidationError
  client.py                 # GraphClient — single public facade consumers instantiate
  metadata.py                # Metadata — spaces, tag/edge/index admin, schema inspection
  storage/
    connection.py               # ConnectionPool wrapper (start/close)
    session.py                   # session acquire/release context manager
    executor.py                   # execute(ngql) -> QueryResult
    serialization.py                # centralized Nebula <-> Python value conversion (encode + decode)
    result.py                        # QueryResult, RawVertex, RawEdge, RawPath (Nebula-agnostic value objects)
  query/
    builder.py                        # pure nGQL string builders + identifier validation
  schema/
    models.py                           # PropertyDefinition, TagSchema, EdgeSchema
    registry.py                          # SchemaRegistry — register_vertex()/register_edge(), lookup by name
  model/
    vertex.py                             # Vertex ABC — tag, vid, properties, validate()
    edge.py                                 # Edge ABC — edge_type, src, dst, rank, properties, validate()
  repository/
    vertex_operations.py                     # VertexOperations — get/create/upsert/delete/exists
    edge_operations.py                        # EdgeOperations — get/create/delete
    traversal.py                                # Traversal — get_neighbors()
tests/
  unit/            # mirrors package structure; mocks nebula3-python, no infra required
  integration/      # skipped by default unless NEBULA_TEST_HOST env var is set
```

## Component Details

**config.py** — `GraphConfig` is a plain dataclass: `hosts: list[tuple[str, int]]`,
`user`, `password`, `space`, `pool_min_size`, `pool_max_size`, `timeout_ms`. No env-var
loading built in now (trivial to add a `from_env()` classmethod later without breaking
the API — deferred until a consumer actually needs it).

**exceptions.py** — five exceptions, each justified by a concrete failure mode:
`GraphCoreError` (base), `GraphConnectionError` (named to avoid shadowing Python's
builtin `ConnectionError`), `QueryExecutionError`, `SchemaError`,
`ValidationError` (raised from `Vertex.validate()`/`Edge.validate()`). `get()` methods
return `None` on not-found rather than raising, so no `NotFoundError` is needed.

**client.py** — `GraphClient` wires config to the connection pool and exposes what
consumers need: `connect()`, `close()`, factory access to `VertexOperations`,
`EdgeOperations`, `Traversal`, `Metadata`, and an `execute_raw(ngql)` escape hatch for
anything the primitives don't cover (still returns the Nebula-agnostic `QueryResult`).

**identifiers.py** (top-level, dependency-free) — `validate_identifier(name, kind)`
using the strict allowlist regex. `config.py` (space name), `query/builder.py`
(tag/edge/property names), and `metadata.py` (tag/edge/index names) all import this
single copy rather than each maintaining their own regex, since this is a
security-relevant check (identifier injection) that must not drift.

**storage/** — the only package importing `nebula3-python`, and only inside function
bodies (never at module level), via an injectable `pool_factory`. This means every
module in this package — and every unit test in this repo — imports and runs
correctly whether or not `nebula3-python` is installed; tests substitute a fake pool/
session/result-set. Only the real `_default_pool_factory()` codepath (never exercised
by unit tests) requires the real package. `storage/serialization.py` additionally uses
`from __future__ import annotations` with `TYPE_CHECKING`-guarded imports so it never
imports `nebula3-python` even for type hints.
- `connection.py`: wraps `nebula3.gclient.net.ConnectionPool`; `start()`/`close()`.
- `session.py`: context manager acquiring/releasing a session from the pool.
- `executor.py`: `execute(ngql: str) -> QueryResult`; raises `QueryExecutionError` on
  failure.
- `serialization.py`: `to_ngql_literal(value) -> str` (Python -> nGQL literal) and
  `from_value_wrapper(...)` / `from_nebula_vertex(...)` / `from_nebula_edge(...)` /
  `from_nebula_path(...)` (Nebula -> Python / RawVertex / RawEdge / RawPath). The one
  place NebulaGraph value semantics are encoded.
- `result.py`: `QueryResult` (rows as plain dicts), `RawVertex` (vid, tags: dict of
  tag_name -> properties), `RawEdge` (src, dst, edge_type, rank, properties),
  `RawPath` (ordered steps of RawVertex/RawEdge).

**query/builder.py** — pure, side-effect-free functions: `build_insert_vertex()`,
`build_upsert_vertex()`, `build_delete_vertex()`, `build_fetch_vertex()`,
`build_insert_edge()`, `build_delete_edge()`, `build_go_neighbors()`. Trivially unit
testable without mocking anything.

**schema/models.py** — `PropertyDefinition` (name, nebula type, nullable, default),
`TagSchema` (name, properties), `EdgeSchema` (name, properties). Pure data, no
behavior.

**schema/registry.py** — `SchemaRegistry`: `register_vertex(tag: str, cls: Type[Vertex])`,
`register_edge(edge_type: str, cls: Type[Edge])`, `get_vertex_class(tag)`,
`get_edge_class(edge_type)`. This is the extension point future domain packages call
at import time.

**model/vertex.py, model/edge.py** — `Vertex` and `Edge` are the extension-point ABCs.
`Vertex`: `tag: ClassVar[str]`, `vid: str`, `properties: dict`, `validate() -> None`
(no-op by default, override to add rules). `Edge`: `edge_type: ClassVar[str]`, `src`,
`dst`, `rank: int = 0`, `properties: dict`, `validate() -> None`.

**metadata.py** — `Metadata`: space administration (`create_space`, `drop_space`,
`list_spaces`, `space_exists`), schema creation from `TagSchema`/`EdgeSchema`
(`create_tag`, `create_edge_type`, `create_tag_index`, `create_edge_index`), and
inspection (`list_tags`, `list_edges`, `list_indexes`, `describe_tag`, `describe_edge`).
Built now because DDL creation without inspection is unsafe — you cannot tell whether
a `CREATE TAG` succeeded, or avoid re-creating an existing one, without inspection.

**repository/vertex_operations.py, edge_operations.py** — `VertexOperations`:
`get(tag, vid) -> Optional[Vertex]`, `create(vertex)`, `upsert(vertex)`,
`delete(tag, vid)`, `exists(tag, vid)`. Calls `vertex.validate()` before writes.
Deserializes into the `SchemaRegistry`-registered subclass when the tag is registered.
`EdgeOperations` mirrors this for edges.

**repository/traversal.py** — `Traversal.get_neighbors(vid, edge_type=None,
direction="out") -> list[RawVertex]`. The only traversal operation built now; more
advanced graph algorithms (shortest path, subgraph extraction, PageRank, etc.) are
explicitly deferred until a real consumer needs them.

## Testing Strategy

- **Unit tests** (`tests/unit/`): mock `nebula3-python`'s `ConnectionPool`/`Session`
  via `unittest.mock`. Cover query builder (pure functions, no mocking needed),
  serialization (feed synthetic Nebula value types, assert conversion), schema
  registry, and repository primitives (assert correct nGQL built and correct object
  returned/raised). No running NebulaGraph instance or Docker required.
- **Integration tests** (`tests/integration/`): scaffolded now, skipped by default
  unless a `NEBULA_TEST_HOST` environment variable is set. To be exercised later
  against a real NebulaGraph instance on the developer's local machine — not part of
  this development environment.

## Dependencies

Runtime: `nebula3-python` only. Dev: `pytest`, stdlib `unittest.mock`. No pydantic, no
async libraries, no ORMs.

## Extension Points (for future domain packages, e.g. AML)

1. Subclass `Vertex`/`Edge`, optionally override `validate()`.
2. Call `SchemaRegistry.register_vertex("account", AccountVertex)` /
   `register_edge(...)` at import time.
3. Define `TagSchema`/`EdgeSchema` and call `Metadata.create_tag(...)` /
   `create_edge_type(...)` to materialize the schema in NebulaGraph.
4. Compose `VertexOperations`, `EdgeOperations`, `Traversal` inside a
   domain-specific repository (e.g. `PersonRepository`) rather than inheriting from
   them.

No changes to `graph-core` itself are required to add a new domain.

## Decisions Log

| Decision | Alternative considered | Why chosen |
|---|---|---|
| Python | TypeScript, Java | User preference; fits future AI-agent/MCP integration |
| Sync, official `nebula3-python` used directly | Async via thread-pool wrapping | No real concurrency requirement yet; avoid premature optimization |
| Domain-agnostic core with extension points | Bundle initial AML schema now | Keeps this package truly foundational and reusable |
| Composition-based primitives (`VertexOperations`/`EdgeOperations`) | Generic `Repository[V]` base class | Generic base class fights domain-specific query needs later |
| Result-conversion inside `storage/` | Separate query layer converts results | Conversion needs `nebula3-python` types; only storage may import them |
| Centralized `storage/serialization.py` for both encode and decode | Escaping in query builder, decoding in result mapper (separate) | Avoids drift between two independently-evolving conversion paths |
| Mocked unit tests only, integration tests scaffolded but skipped | Docker Compose-based integration tests in CI now | No NebulaGraph instance available in this dev environment |
| `nebula3-python` imported lazily via an injectable `pool_factory`, never at module level | Import it at module level and require it installed to run unit tests | User chose not to `pip install` anything in this sandbox; this lets the full unit test suite run without the package installed or a server running |
| Exact `nebula3-python` method names (`ValueWrapper.is_vertex()`, `Node.tags()`, `Relationship.ranking()`, etc.) used in `serialization.py` are written from documented knowledge of the client, not verified against an installed copy | Verify by installing/inspecting the package now | User declined network/package access in this session; must be verified against a real NebulaGraph instance and installed `nebula3-python` before production use |
