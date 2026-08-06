# Person-Centric Investigation Graph — Implementation Plan

**Goal:** Rebuild the Investigation graph around people. Persons are the only
primary nodes; 1/2/3-degree person-to-person connections are computed by
projecting through shared attributes; clicking a person fans its own
attributes out radially around it.

> **Status: implemented.** Kept as the design record for the change.
> One deviation from the plan below: persons carry no `attribute_count`.
> Counting a person's details for everyone in the network needs data the
> BFS doesn't collect for nodes discovered at the far end of a level, and a
> number that's right for some people and wrong for others is worse than no
> number — the UI fetches attributes on click instead.

**Scope:** `apps/web/src/pages/InvestigationPage.tsx` and the graph canvases,
a new person-projection service + endpoints in `apps/api`, and one batched
traversal primitive in `graph-core`. Explorer, agent-tools, risk, and
`expand_node` are left untouched.

---

## What exists today (why this needs a real change)

Storage is a **bipartite-ish graph**, not a person-to-person graph:

- Tags (`intelligence_schema/ingest_schema.py:ENTITY_TAG`): `person`,
  `company`, `organization`, `address`, `country`, `passport`, `phone`,
  `email`, `bank_account`, `vehicle`, plus `evidence`.
- Edge types (`INGEST_EDGE_TYPES`): `WORKS_AT`, `OWNS`, `PAYS`,
  `HAS_PASSPORT`, `HAS_PHONE`, `HAS_EMAIL`, `HAS_ACCOUNT`, `OWNS_VEHICLE`,
  `LOCATED_AT`, `CITIZEN_OF`, `RELATED_TO`.

So two people who share a phone are stored as
`A -HAS_PHONE-> phone:+91… <-HAS_PHONE- B` — **two** hops, not one. There is
no `person -> person` edge for it.

The current page (`InvestigationPage.tsx:82`) calls
`api.expandEntityGraph(entityId, depth)` → `GraphService.expand_node`
(`services/graph_service.py:48`), a raw BFS over `*` edges, and then hides
attribute nodes client-side (`graphVisibility.ts`). Consequences:

1. **"Depth" ≠ "degree".** Depth 1 returns only that person's attributes —
   all of which are hidden by `computeVisibleGraph` — so a 1-hop search looks
   empty. The first *other person* only appears at depth 2, the second at
   depth 4. This is exactly the mismatch to fix.
2. **No connection reason.** Person↔person edges never exist, so nothing can
   be labelled "shared phone".
3. **N+1 traversal.** `expand_node` runs `get_neighbors_with_edges` per node
   per level (2 round trips each). Degree 3 with real fan-out is hundreds of
   queries.
4. **No radial layout.** Everything goes through one fcose run
   (`GraphCanvas.tsx:374`), so a revealed attribute lands wherever the force
   simulation puts it.

---

## Design

### Person projection

Define two connector classes over the stored edge types:

```python
DIRECT_EDGES   = {"RELATED_TO", "PAYS", "COMMUNICATED_WITH", "TRANSFERRED_TO"}
SHARED_EDGES   = {"HAS_PHONE", "HAS_EMAIL", "HAS_PASSPORT", "HAS_ACCOUNT",
                  "OWNS_VEHICLE", "LOCATED_AT", "WORKS_AT", "OWNS"}
WEAK_EDGES     = {"CITIZEN_OF"}     # country: excluded by default, opt-in
```

Two persons are **degree-1 connected** when either:
- a `DIRECT_EDGES` edge joins them, or
- both attach to the same non-person vertex via a `SHARED_EDGES` edge
  (shared phone / email / passport / account / vehicle / address / employer).

Degree *n* is BFS over that projected person-person relation. Degree 3 is
additive: it contains the degree-1 and degree-2 sets, each node tagged with
the level at which it was first reached.

**Fan-out guard.** A phone shared by 400 people is a call centre, not a
lead — and it would emit 79,800 links. Any connector whose *true* person
count exceeds `max_shared_fanout` (default 25) is suppressed and reported
back in `suppressed_hubs` so the UI can say so instead of silently lying.
`CITIZEN_OF` is off by default for the same reason.

### BFS algorithm (per level, ~5 round trips instead of hundreds)

```
frontier = {root}; persons = {root: degree 0}
for level in 1..degree:
    A. direct  = GO FROM <frontier> OVER <DIRECT_EDGES>  BIDIRECT YIELD DISTINCT edge AS e
    B. out     = GO FROM <frontier> OVER <SHARED_EDGES>  BIDIRECT YIELD DISTINCT edge AS e
    C. FETCH PROP ON * <all new vids>        -> tags, so person vs connector is known
    D. back    = GO FROM <connector vids>    OVER <SHARED_EDGES> BIDIRECT YIELD DISTINCT edge AS e
    E. FETCH PROP ON * <new person vids>

    for each connector c with owner set O (all persons attached to c, from D):
        if len(O) > max_shared_fanout: record in suppressed_hubs; skip
        for every pair (p, q) in O where p or q is already in the graph:
            link p-q, via = {kind: shared_attribute, connector: c}
    new persons get degree = level;  frontier = new persons
    if len(persons) >= max_persons: truncated = True; break
```

Pairs among *already-known* persons are kept, not just frontier pairs — that
closes triangles inside the subgraph, which is the thing an analyst actually
looks for.

Two guards before any query: intersect the requested edge types with
`client.metadata.list_edge_types()` and confirm `person` is in
`list_tags()`. A space created from a partial import will not have every edge
type, and `GO ... OVER <unknown>` is a hard nGQL error.

### API contract

`GET /api/entities/{id}/person-network?degree=1..3&connectors=…&max_fanout=25`

```jsonc
{
  "root_id": "person:1",
  "degree": 2,
  "persons": [
    { "id": "person:1", "label": "A. Kumar", "degree": 0,
      "entity_type": "Person", "properties": {…} }
  ],
  "links": [
    { "source": "person:1", "target": "person:2", "degree": 1,
      "label": "shared phone",
      "via": [ { "kind": "shared_attribute", "connector_id": "phone:+91…",
                 "connector_tag": "phone", "connector_label": "+91…",
                 "edge_types": ["HAS_PHONE"] } ] }
  ],
  "truncated": false,
  "suppressed_hubs": [ { "id": "country:IN", "label": "India",
                         "tag": "country", "person_count": 412 } ]
}
```

`GET /api/entities/{id}/attributes`

```jsonc
{ "entity_id": "person:1",
  "attributes": [ { "id": "phone:+91…", "tag": "phone", "label": "+91…",
                    "edge_type": "HAS_PHONE", "properties": {…},
                    "shared_with": ["person:2"] } ] }
```

`shared_with` is what lets the UI highlight *"this is the node that links A
and B"* when a person is expanded.

### Radial expansion

Persons keep the existing fcose force layout. Attribute nodes are **pinned**,
never fed to fcose:

- One expanded parent → evenly spaced on a circle around it. Radius grows
  with child count (`r = max(baseR, n * nodeSpacing / (2π))`) so 15 attributes
  don't overlap. Start angle is seeded from a hash of the parent id so two
  adjacent people's rings don't align and collide.
- A **shared** attribute with two expanded parents sits at their centroid —
  visually reinforcing that it is the link — instead of being duplicated.
- Ordering is deterministic (by tag, then label) so collapse→re-expand puts
  everything back where it was.

In `GraphCanvas`, fcose runs on the person subgraph only
(`persons.union(persons.edgesWith(persons)).layout(...)`), then pinned
positions are applied. Dragging a person re-centres its ring live.

---

## Global constraints

- Do **not** change `GraphService.expand_node`, `/api/entities/{id}/graph`,
  or `agent_tools.toolbox.expand_node` — Explorer, EntitiesRiskPage,
  `get_entity_risk_context`, and the agent toolbox all depend on them.
- Do **not** change `useGraphCanvasState` — ExplorerPage shares it.
  Investigation gets its own state hook.
- New nGQL goes through `query/builder.py` and `to_ngql_literal()`; no ad-hoc
  literal building.
- graph-core stays domain-agnostic: no `person`, no AML concept in it. The
  new primitive takes a generic vid list + edge type list.
- Frontend verification only (`npm run dev` / `npm run test` in `apps/web`);
  never start NebulaGraph, the API, or Docker on this machine.
- Commit per task with explicit `git add <files>`.

---

### Task 1 — Batched traversal primitive (graph-core)

**Files:** `packages/graph-core/src/graph_core/query/builder.py`,
`repository/traversal.py`, `tests/unit/query/test_builder.py`

- [ ] `build_go_neighbors_batch(vids: list[str], edge_types: list[str] | None, direction: str) -> str`
  → `GO FROM "a","b" OVER T1,T2 BIDIRECT YIELD DISTINCT edge AS e`.
  Reuse `_build_over_clause` for direction; extend it (or add a sibling) to
  accept a list, validating each name with `validate_identifier`. Empty
  `vids` raises, mirroring `build_fetch_vertices`.
- [ ] `Traversal.neighbors_batch(vids, edge_types=None, direction="both", chunk_size=200) -> list[RawEdge]`
  — chunks vids, executes, dedupes on `(edge_type, src, dst, rank)`.
  `edge AS e` decodes to `RawEdge` through the existing path already used by
  `get_neighbors_with_edges`, so no serialization work is needed.
- [ ] Unit tests: multi-vid + multi-edge-type string, `OVER *` when
  `edge_types is None`, direction variants, invalid identifier rejected,
  chunking splits at the boundary. Must pass without NebulaGraph.

### Task 2 — Person projection service

**Files:** create `apps/api/src/graph_explorer_api/services/person_network_service.py`;
tests `apps/api/tests/unit/test_person_network_service.py`

- [ ] Module constants `DIRECT_EDGES` / `SHARED_EDGES` / `WEAK_EDGES`,
  `PERSON_TAG = "person"`, `DEFAULT_MAX_FANOUT = 25`,
  `DEFAULT_MAX_PERSONS = 300`.
- [ ] `PersonNetworkService(clients, space)` with the same lazy
  `client` property as `GraphService` (a drop/recreate must not leave a dead
  pool).
- [ ] `available_edge_types()` — intersect the requested set with
  `metadata.list_edge_types()`, cached per space.
- [ ] `person_network(root_id, degree, connectors=None, max_fanout=…, max_persons=…) -> dict`
  implementing the BFS above and returning the contract shape.
- [ ] `attributes(entity_id) -> dict` — one `neighbors_batch([id], SHARED_EDGES)`,
  one `FETCH PROP ON *` for the connectors, one `neighbors_batch(connector_ids)`
  to fill `shared_with` (persons only, self excluded).
- [ ] Link labels: direct → `properties.relationship_type` or a humanized
  edge type; shared → `"shared {tag}"`; >1 connector → `"{n} shared details"`,
  with every connector kept in `via`.
- [ ] Unit tests against a fake client (follow `apps/api/tests/unit/fakes.py`):
  degree-1 shared phone, degree-2 chain A–B–C, degree-3 chain A–B–C–D,
  additive degrees, triangle closure between already-known persons, fan-out
  suppression, `max_persons` truncation, missing edge type in space,
  root with no connections, cycle safety.

### Task 3 — Endpoints

**Files:** `apps/api/src/graph_explorer_api/routers/entities.py`,
`dependencies.py`, tests `apps/api/tests/unit/test_person_network_router.py`

- [ ] `get_person_network_service` dependency mirroring `get_graph_service`.
- [ ] `GET /api/entities/{entity_id}/person-network`
  (`degree: int = Query(1, ge=1, le=3)`, `connectors: str | None`,
  `max_fanout: int = Query(25, ge=1, le=500)`), 404 when the root is absent
  or not tagged `person`.
- [ ] `GET /api/entities/{entity_id}/attributes`.
- [ ] Add `entity_type: str | None = None` to `GET /api/entities/search` and
  forward it — `GraphService.search_entities` already accepts the parameter
  (`graph_service.py:25`), the router just never exposed it. Default `None`
  keeps every existing caller unchanged.

### Task 4 — Frontend types + client

**Files:** `apps/web/src/api/types.ts`, `apps/web/src/api/client.ts`

- [ ] `PersonNode`, `PersonLinkVia`, `PersonLink`, `SuppressedHub`,
  `PersonNetwork`, `EntityAttribute`, `EntityAttributes`, mirroring Task 3
  exactly (the file header notes both sides must move together).
- [ ] `api.getPersonNetwork(entityId, degree, opts?)`,
  `api.getEntityAttributes(entityId)`, and an optional `entityType` argument
  on `api.searchEntities`.

### Task 5 — Radial layout module

**Files:** create `apps/web/src/components/explorer/radialLayout.ts` and
`radialLayout.test.ts`

- [ ] `computeRadialPositions(parents: Map<string, Position>, children: RadialChild[], opts): Map<string, Position>`
  where `RadialChild = { id: string; parentIds: string[]; sortKey: string }`.
- [ ] Single parent → circle slots, radius `max(baseRadius, n * spacing / (2π))`,
  start angle from a hash of the parent id, children ordered by `sortKey`.
- [ ] Multiple expanded parents → centroid, with a deterministic perpendicular
  nudge when two shared children would land on the same point.
- [ ] Parent not in `parents` (collapsed) → omitted from the result.
- [ ] Vitest cases: even angular spacing, radius growth with n, stable output
  across repeated calls, centroid placement, collision nudge.

### Task 6 — GraphCanvas: pinned nodes + person-only layout

**Files:** `apps/web/src/components/explorer/GraphCanvas.tsx`

- [ ] New optional prop `pinnedPositions?: Map<string, Position>`. Absent →
  today's behavior byte-for-byte (Explorer must not shift).
- [ ] In the data-sync effect, pinned nodes are added at their given position
  and `.lock()`ed; fcose runs on
  `persons.union(persons.edgesWith(persons))` instead of the whole graph, so
  attribute rings are never disturbed by the force simulation.
- [ ] Re-apply pinned positions after `layoutstop` and whenever
  `pinnedPositions` changes.
- [ ] `cy.on('drag', 'node[role="main"]')` → notify via a new optional
  `onParentMoved(vid, position)` so the page recomputes that ring live.
- [ ] Style: pinned/attribute edges thinner and dimmer than person links;
  person links get width scaled by `via.length` so a 3-way overlap reads as
  stronger than a single shared email.

### Task 7 — InvestigationPage rebuild

**Files:** `apps/web/src/pages/InvestigationPage.tsx`; create
`apps/web/src/hooks/usePersonNetworkState.ts`; delete
`apps/web/src/components/explorer/graphVisibility.ts` and
`graphVisibility.test.ts` (only this page uses them)

- [ ] `usePersonNetworkState` holds `network`, `expandedPersons: Set<string>`,
  `attributesByPerson: Map<string, EntityAttribute[]>`, and derives canvas
  nodes/edges = persons + attributes of expanded persons.
- [ ] Search restricted to `entity_type='person'`; selecting a hit sets the
  root and loads the network at the current degree.
- [ ] "Depth" control → **"Degree"** (1/2/3), tooltip rewritten to describe
  connection degree, not hops. Changing it refetches around the same root.
- [ ] Person click → toggle attribute expansion (fetch once, cache, instant
  re-expand). Attribute nodes are select-only, as sub nodes are today.
- [ ] Detail panel: `Show/Hide details` drives the same toggle; add a
  **"Why connected"** section listing `via` entries for the selected person's
  links — this is the payoff of the whole projection.
- [ ] Surface `truncated` and `suppressed_hubs` in the status strip
  ("2 shared details skipped — connected to 400+ people").
- [ ] Keep risk and shortest-path exactly as they are.

### Task 8 — 3D parity

**Files:** `apps/web/src/components/explorer/GraphCanvas3D.tsx`

- [ ] Accept the same `pinnedPositions`. On `onEngineTick`, hard-set each
  attribute node's `fx/fy/fz` to a ring around its parent in the plane facing
  the camera, so the 2D and 3D views tell the same story.
- [ ] Ships after Task 7; the 2D path must not depend on it.

### Task 9 — Docs

**Files:** `docs/specs/2026-07-06-graph-explorer-design.md`,
`apps/api/README.md`, `apps/web/README.md`

- [ ] Document the projection model, the connector classes, the fan-out
  guard, and the two new endpoints.

---

## Risks

| Risk | Mitigation |
|---|---|
| Fan-out explosion (shared country/city) | `max_shared_fanout` + `CITIZEN_OF` off by default + `suppressed_hubs` reported, not hidden |
| Degree-3 latency on a dense graph | ~5 batched queries per level (vs. hundreds today); `max_persons` truncation; degree capped at 3 |
| Space missing an edge type | Intersect with `list_edge_types()` before querying |
| Explorer regressions | New endpoints and a new state hook; `pinnedPositions` optional; `expand_node` untouched |
| Ring overlap between close persons | Radius scales with child count; per-parent angle seed; shared children at centroid |

## Verification

- `pytest packages/graph-core/tests/unit -v`
- `pytest apps/api/tests/unit -v`
- `cd apps/web && npm run test && npm run build`
- Frontend-only smoke on this box; full-stack check happens on your machine.
