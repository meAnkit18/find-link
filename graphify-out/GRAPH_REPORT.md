# Graph Report - .  (2026-07-03)

## Corpus Check
- Corpus is ~18,561 words - fits in a single context window. You may not need a graph.

## Summary
- 429 nodes · 955 edges · 24 communities (18 shown, 6 thin omitted)
- Extraction: 73% EXTRACTED · 27% INFERRED · 0% AMBIGUOUS · INFERRED: 260 edges (avg confidence: 0.75)
- Token cost: 0 input · 132,822 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Errors & Metadata Overview|Errors & Metadata Overview]]
- [[_COMMUNITY_Connection Pool & Session|Connection Pool & Session]]
- [[_COMMUNITY_Traversal & Result Model|Traversal & Result Model]]
- [[_COMMUNITY_GraphClient Facade|GraphClient Facade]]
- [[_COMMUNITY_Edge Model & Validation|Edge Model & Validation]]
- [[_COMMUNITY_Identifiers & Query Builder|Identifiers & Query Builder]]
- [[_COMMUNITY_FakeValueWrapper Test Double|FakeValueWrapper Test Double]]
- [[_COMMUNITY_Vertex Model|Vertex Model]]
- [[_COMMUNITY_NebulaGraph Serialization|NebulaGraph Serialization]]
- [[_COMMUNITY_Constructor Wiring|Constructor Wiring]]
- [[_COMMUNITY_Package Rationale Notes|Package Rationale Notes]]
- [[_COMMUNITY_nGQL Literal Serialization|nGQL Literal Serialization]]
- [[_COMMUNITY_FakeNode Test Double|FakeNode Test Double]]
- [[_COMMUNITY_FakeRelationship Test Double|FakeRelationship Test Double]]
- [[_COMMUNITY_CLAUDE.md Policies|CLAUDE.md Policies]]
- [[_COMMUNITY_Edge Model Tests|Edge Model Tests]]
- [[_COMMUNITY_FakePath Test Double|FakePath Test Double]]
- [[_COMMUNITY_Integration Test Fixtures|Integration Test Fixtures]]
- [[_COMMUNITY_Package Root|Package Root]]

## God Nodes (most connected - your core abstractions)
1. `FakeValueWrapper` - 36 edges
2. `Metadata` - 35 edges
3. `SchemaRegistry` - 35 edges
4. `QueryResult` - 34 edges
5. `VertexOperations` - 32 edges
6. `graph-core Implementation Plan` - 31 edges
7. `graph-core: Graph Data Layer Design spec` - 30 edges
8. `GraphConfig` - 28 edges
9. `EdgeOperations` - 28 edges
10. `GraphClient` - 26 edges

## Surprising Connections (you probably didn't know these)
- `Git workflow: commit after verified, reviewed changes` --semantically_similar_to--> `graph-core Implementation Plan`  [INFERRED] [semantically similar]
  CLAUDE.md → docs/superpowers/plans/2026-07-02-graph-core-implementation.md
- `Evolutionary architecture: build only what today's requirements justify` --rationale_for--> `Traversal`  [EXTRACTED]
  docs/superpowers/specs/2026-07-02-graph-core-design.md → src/graph_core/repository/traversal.py
- `Composition-based primitives over generic Repository[V] base class` --rationale_for--> `VertexOperations`  [EXTRACTED]
  docs/superpowers/specs/2026-07-02-graph-core-design.md → src/graph_core/repository/vertex_operations.py
- `Result-conversion lives in the storage layer, not a separate query layer` --rationale_for--> `QueryExecutor`  [EXTRACTED]
  docs/superpowers/specs/2026-07-02-graph-core-design.md → src/graph_core/storage/executor.py
- `graph-core Implementation Plan` --references--> `GraphClient`  [EXTRACTED]
  docs/superpowers/plans/2026-07-02-graph-core-implementation.md → src/graph_core/client.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **graph-core layering: repository -> metadata -> schema -> query -> storage** — src_graph_core_client_graphclient, src_graph_core_metadata_metadata, src_graph_core_repository_vertex_operations_vertexoperations, src_graph_core_repository_edge_operations_edgeoperations, src_graph_core_repository_traversal_traversal, src_graph_core_query_builder_functions, src_graph_core_storage_executor_queryexecutor [EXTRACTED 1.00]
- **Domain extension point mechanism (subclass, register, define schema, compose)** — src_graph_core_model_vertex_vertex, src_graph_core_model_edge_edge, src_graph_core_schema_registry_schemaregistry, src_graph_core_metadata_metadata [EXTRACTED 1.00]
- **Storage layer: the only layer permitted to import nebula3-python** — src_graph_core_storage_connection_graphconnectionpool, src_graph_core_storage_session_session_scope, src_graph_core_storage_executor_queryexecutor, src_graph_core_storage_serialization_to_ngql_literal [EXTRACTED 1.00]

## Communities (24 total, 6 thin omitted)

### Community 0 - "Errors & Metadata Overview"
Cohesion: 0.07
Nodes (35): graph-core Implementation Plan, graph-core: Graph Data Layer Design spec, Exception, graph-core README, GraphConnectionError, GraphCoreError, QueryExecutionError, Base class for all graph_core errors. (+27 more)

### Community 1 - "Connection Pool & Session"
Cohesion: 0.08
Nodes (31): nebula3-python imported lazily via injectable pool_factory, GraphConnectionPool, Wraps a NebulaGraph connection pool's lifecycle (start/close)., Close the underlying connection pool, if started., Any, Acquire a session from the pool for the configured space, releasing it afterward, session_scope(), FakePool (+23 more)

### Community 2 - "Traversal & Result Model"
Cohesion: 0.09
Nodes (32): Traversal: graph-navigation operations.  get_neighbors() is the only traversal o, Traversal, Vertex CRUD primitives, operating on any Vertex subclass via SchemaRegistry., VertexOperations, Any, QueryResult, Nebula-agnostic result value objects.  These types are what every layer above `s, A vertex as returned from NebulaGraph, before any domain mapping.      `tags` ma (+24 more)

### Community 3 - "GraphClient Facade"
Cohesion: 0.07
Nodes (30): Sync-only, official nebula3-python client, no async/thread pools, GraphClient, GraphClient: the single public entry point for graph-core consumers.  Wires Grap, Single public facade wiring config to storage, schema, and repository primitives, Escape hatch for operations not covered by the primitives above., GraphConfig, Connection configuration for graph_core., Configuration required to connect to a NebulaGraph cluster.      `hosts` is a li (+22 more)

### Community 4 - "Edge Model & Validation"
Cohesion: 0.11
Nodes (32): Composition-based primitives over generic Repository[V] base class, Domain-agnostic core with extension points, Raised for schema administration failures (tag/edge/index/space, registry)., Raised when a Vertex or Edge fails its validate() check before a write., SchemaError, ValidationError, Edge, Any (+24 more)

### Community 5 - "Identifiers & Query Builder"
Cohesion: 0.09
Nodes (31): Identifier injection safety via allowlist validation, not escaping, Shared identifier validation.  NebulaGraph's nGQL has no parameterization for id, Raise ValueError if `name` is not a safe NebulaGraph identifier., validate_identifier(), build_delete_edge(), build_delete_vertex(), build_fetch_edge(), build_fetch_vertex() (+23 more)

### Community 7 - "Vertex Model"
Cohesion: 0.13
Nodes (12): ABC, Edge extension point.  Domain packages subclass Edge to define their own edge ty, Any, Vertex extension point.  Domain packages subclass Vertex to define their own ver, Base contract every vertex type must satisfy.      Subclasses must implement the, Raise ValidationError if this instance is invalid. No-op by default., Vertex, DummyVertex (+4 more)

### Community 8 - "NebulaGraph Serialization"
Cohesion: 0.17
Nodes (15): from_nebula_edge(), from_nebula_path(), from_nebula_vertex(), from_value_wrapper(), Any, Centralized NebulaGraph <-> Python value conversion.  This is the only module th, Decode a NebulaGraph PathWrapper into a RawPath., Decode a single NebulaGraph ValueWrapper into a plain Python value. (+7 more)

### Community 9 - "Constructor Wiring"
Cohesion: 0.15
Nodes (6): PoolFactory, _build_query_result(), Any, QueryExecutor, nGQL execution against NebulaGraph, producing Nebula-agnostic results., Executes nGQL statements and returns Nebula-agnostic QueryResult objects.

### Community 10 - "Package Rationale Notes"
Cohesion: 0.14
Nodes (5): Exception hierarchy for graph_core.  All NebulaGraph-specific errors are transla, Non-generic edge CRUD primitives.  Mirrors VertexOperations: future domain repos, Non-generic vertex CRUD primitives.  Future domain repositories (e.g. a PersonRe, SchemaRegistry: the extension point mapping tag/edge-type names to Python classe, Session acquisition/release against a NebulaGraph connection pool.

### Community 11 - "nGQL Literal Serialization"
Cohesion: 0.23
Nodes (12): Centralized storage/serialization.py for both encode and decode, Result-conversion lives in the storage layer, not a separate query layer, nebula3-python method names used in serialization.py are unverified against an installed copy, Render a plain Python value as an nGQL literal.      The single place Python val, to_ngql_literal(), test_to_ngql_literal_bool(), test_to_ngql_literal_datetime_and_date(), test_to_ngql_literal_list_and_dict() (+4 more)

### Community 14 - "CLAUDE.md Policies"
Cohesion: 0.33
Nodes (6): Git workflow: commit after verified, reviewed changes, Prefer Graphify for architecture understanding, Investigation Mode: diagnose without modifying code, CLAUDE.md project instructions, Scope policy: only implement what was requested, Evolutionary architecture: build only what today's requirements justify

### Community 15 - "Edge Model Tests"
Cohesion: 0.53
Nodes (5): DummyEdge, test_default_validate_is_noop(), test_edge_cannot_be_instantiated_directly(), test_rank_and_properties_default(), test_subclass_with_edge_type_can_be_instantiated()

## Knowledge Gaps
- **1 isolated node(s):** `graph-core`
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `graph-core Implementation Plan` connect `Errors & Metadata Overview` to `Connection Pool & Session`, `Traversal & Result Model`, `GraphClient Facade`, `Edge Model & Validation`, `Identifiers & Query Builder`, `Vertex Model`, `NebulaGraph Serialization`, `Constructor Wiring`, `nGQL Literal Serialization`, `CLAUDE.md Policies`?**
  _High betweenness centrality (0.178) - this node is a cross-community bridge._
- **Why does `graph-core: Graph Data Layer Design spec` connect `Errors & Metadata Overview` to `Connection Pool & Session`, `Traversal & Result Model`, `GraphClient Facade`, `Edge Model & Validation`, `Identifiers & Query Builder`, `Vertex Model`, `NebulaGraph Serialization`, `Constructor Wiring`, `nGQL Literal Serialization`?**
  _High betweenness centrality (0.160) - this node is a cross-community bridge._
- **Why does `FakeValueWrapper` connect `FakeValueWrapper Test Double` to `Connection Pool & Session`, `NebulaGraph Serialization`, `nGQL Literal Serialization`, `FakeNode Test Double`, `FakeRelationship Test Double`?**
  _High betweenness centrality (0.122) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `Metadata` (e.g. with `GraphClient` and `.__init__()`) actually correct?**
  _`Metadata` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `SchemaRegistry` (e.g. with `GraphClient` and `EdgeOperations`) actually correct?**
  _`SchemaRegistry` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 25 inferred relationships involving `QueryResult` (e.g. with `GraphClient` and `QueryExecutor`) actually correct?**
  _`QueryResult` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `VertexOperations` (e.g. with `GraphClient` and `.__init__()`) actually correct?**
  _`VertexOperations` has 18 INFERRED edges - model-reasoned connections that need verification._