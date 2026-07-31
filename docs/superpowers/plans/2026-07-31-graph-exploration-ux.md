# Graph Exploration UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix broken graph-canvas navigation and add a person-centric main/sub-node hierarchy with real relationship labels, per `docs/superpowers/specs/2026-07-31-graph-exploration-ux-design.md`.

**Architecture:** Unify the Explorer page's already-working `GraphCanvas`/`GraphControls` (pan/zoom/fit/relayout/fullscreen, resize-observed) as the one canvas both the Explorer and Investigation pages use, replacing Investigation's bare, control-less Cytoscape setup. Layer a main-vs-sub node classification and single-click expand/collapse on top, and extend one backend endpoint so expansion carries real edge data (for relationship labels) instead of synthesizing empty ones.

**Tech Stack:** React 18 + TypeScript + Vite (`apps/web`), Cytoscape + `cytoscape-fcose`, Zustand, `@tanstack/react-query`, FastAPI + `graph-core` (`apps/api`), pytest with a fake `GraphClient`.

## Global Constraints

- Do not run NebulaGraph, the FastAPI backend, or Docker in this environment (`CLAUDE.md`). The frontend dev server (`npm run dev` / `npm run build` in `apps/web`) may be run to verify UI changes. Backend changes are verified by TDD against the existing fake `GraphClient` (`apps/api/tests/unit/fakes.py`); this sandbox has no Python ≥3.10 toolchain installed, so `pytest` itself is not runnable here — write the tests correctly per the existing fake's documented contract and note in the final task that the user runs `pytest tests/unit -v` on their machine.
- Additive backend changes only — no changes to `graph-core`'s public surface beyond calling its existing `Traversal.get_neighbors_with_edges` (already implemented, already used by `graph_service.expand_node`).
- Person-centric hierarchy is fixed (`person`/`company`/`organization`) on the Investigation page and opt-in per-tag on the Explorer page — Explorer's default behavior (no tags marked main) must stay pixel-identical to today.
- Single click on any node selects it and toggles expand/collapse (approved design decision) — applies to every node, not just "main" ones.

---

### Task 1: Backend — `get_neighbors_with_edges` on the fake test double

The new endpoint in Task 2 needs `client.traversal.get_neighbors_with_edges(vid, edge_type, direction)` to exist on the fake `GraphClient` used by tests (`FakeTraversal` currently only has `get_neighbors`/`count_neighbors`/`scan_vertices`). This mirrors the real `graph_core.repository.traversal.Traversal.get_neighbors_with_edges` signature (`packages/graph-core/src/graph_core/repository/traversal.py:41`), which returns `tuple[list[RawVertex], list[RawEdge]]` with real `src`/`dst`/`edge_type`/`rank`/`properties` — not synthesized values.

**Files:**
- Modify: `apps/api/tests/unit/fakes.py`

**Interfaces:**
- Produces: `FakeTraversal.get_neighbors_with_edges(vid: str, edge_type: str | None = None, direction: str = "out") -> tuple[list[RawVertex], list[RawEdge]]`, consumed by Task 2's endpoint test.

- [ ] **Step 1: Add the `RawEdge` import**

In `apps/api/tests/unit/fakes.py`, change:

```python
from graph_core.storage.result import RawVertex
```

to:

```python
from graph_core.storage.result import RawEdge, RawVertex
```

- [ ] **Step 2: Add the method to `FakeTraversal`**

In `apps/api/tests/unit/fakes.py`, inside `class FakeTraversal`, add this method after `get_neighbors` (which ends at the `return [v for v in vertices if v is not None]` line):

```python
    def get_neighbors_with_edges(
        self, vid: str, edge_type: str | None = None, direction: str = "out"
    ) -> tuple[list[RawVertex], list[RawEdge]]:
        edges: list[RawEdge] = []
        neighbor_ids: list[str] = []
        for src, dst, et, rank, props in self.store.edges:
            if edge_type is not None and et != edge_type:
                continue
            if direction in ("out", "both") and src == vid:
                edges.append(RawEdge(src=src, dst=dst, edge_type=et, rank=rank, properties=dict(props)))
                neighbor_ids.append(dst)
            if direction in ("in", "both") and dst == vid:
                edges.append(RawEdge(src=src, dst=dst, edge_type=et, rank=rank, properties=dict(props)))
                neighbor_ids.append(src)
        vertices = [v for v in (self._vertex(n) for n in dict.fromkeys(neighbor_ids)) if v is not None]
        return vertices, edges
```

- [ ] **Step 3: Sanity-check with a throwaway script**

This is a pure data-structure change with no live test yet (Task 2 exercises it through the router). Confirm it at least imports and runs standalone:

```bash
cd /home/ec2-user/ankit_kumar/find-link
python3 -c "
import sys
sys.path.insert(0, 'apps/api')
sys.path.insert(0, 'apps/api/tests')
sys.path.insert(0, 'packages/graph-core/src')
from unit.fakes import FakeGraphClient
c = FakeGraphClient()
c.edges.create_many('FRIEND', [('Alice', 'Bob', 0, {'relationship_type': 'sibling'})])
c.vertices.create_many('entity', [('Alice', {'label': 'Alice'}), ('Bob', {'label': 'Bob'})])
vs, es = c.traversal.get_neighbors_with_edges('Alice', direction='both')
assert [v.vid for v in vs] == ['Bob'], vs
assert es[0].properties['relationship_type'] == 'sibling', es
print('OK')
"
```

Expected: `OK` (if this fails due to missing `graph_core`/`fastapi` imports elsewhere, that's the sandbox's missing Python toolchain per Global Constraints — re-verify this step as part of Task 2's `pytest` run on the user's machine instead).

- [ ] **Step 4: Commit**

```bash
cd /home/ec2-user/ankit_kumar/find-link
git add apps/api/tests/unit/fakes.py
git commit -m "test: add get_neighbors_with_edges to the fake graph client"
```

---

### Task 2: Backend — `GET /nodes/{vid}/neighbors-with-edges` endpoint

`GET /nodes/{vid}/neighbors` only ever returned node data — the frontend has been synthesizing edges with `properties: {}` on every expansion, which is why relationship labels never show real data. Add a sibling endpoint that returns real edges too, following the exact same node/edge filtering pattern `get_overview` already uses in this file (`apps/api/src/graph_explorer_api/routers/explorer.py:170-186`).

**Files:**
- Modify: `apps/api/src/graph_explorer_api/routers/explorer.py`
- Test: `apps/api/tests/unit/test_explorer_router.py`

**Interfaces:**
- Consumes: `FakeTraversal.get_neighbors_with_edges` from Task 1; `SubgraphOut`, `EdgeOut`, `_to_node_out`, `NEIGHBORS_DEFAULT_LIMIT` already defined in `explorer.py`.
- Produces: `GET /api/graphs/{graph_id}/nodes/{vid}/neighbors-with-edges` returning `SubgraphOut` (`{nodes: NodeOut[], edges: EdgeOut[]}`), consumed by Task 3's frontend client method.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/unit/test_explorer_router.py`:

```python
def test_neighbors_with_edges_returns_real_edge_properties(client, fake_clients, graph_with_data):
    fake = fake_clients.for_space(graph_with_data["id"])
    fake.vertices.create_many("entity", [("Dana", {"label": "Dana"})])
    fake.edges.create_many(
        "FRIEND", [("Alice", "Dana", 0, {"relationship_type": "childhood_friend"})]
    )

    resp = client.get(
        f"/api/graphs/{graph_with_data['id']}/nodes/Alice/neighbors-with-edges",
        params={"direction": "both"},
    )
    assert resp.status_code == 200
    body = resp.json()

    labels = {n["label"] for n in body["nodes"]}
    assert labels == {"Bob", "Cara", "Dana"}

    dana_edge = next(e for e in body["edges"] if "Dana" in (e["src"], e["dst"]))
    assert dana_edge["properties"]["relationship_type"] == "childhood_friend"
    assert dana_edge["edge_type"] == "FRIEND"


def test_neighbors_with_edges_respects_limit(client, fake_clients, graph_with_data):
    resp = client.get(
        f"/api/graphs/{graph_with_data['id']}/nodes/Alice/neighbors-with-edges",
        params={"direction": "both", "limit": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) == 1
    # every returned edge must touch only Alice + the one included neighbor
    included = {body["nodes"][0]["vid"], "Alice"}
    for e in body["edges"]:
        assert e["src"] in included and e["dst"] in included
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/api
pytest tests/unit/test_explorer_router.py -k neighbors_with_edges -v
```

Expected: FAIL — `404 Not Found` (the route doesn't exist yet).

- [ ] **Step 3: Add the endpoint**

In `apps/api/src/graph_explorer_api/routers/explorer.py`, insert this new endpoint immediately after `get_neighbors` (after the line `return [_to_node_out(n) for n in neighbors[:limit]]`, before the `@router.get("/overview"...)` block):

```python
@router.get("/nodes/{vid}/neighbors-with-edges", response_model=SubgraphOut)
def get_neighbors_with_edges(
    graph_id: str,
    vid: str,
    edge_type: str | None = Query(None),
    direction: str = Query("out", pattern="^(out|in|both)$"),
    limit: int = Query(NEIGHBORS_DEFAULT_LIMIT, ge=1, le=1000),
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
) -> SubgraphOut:
    """Like /neighbors, but includes the real connecting edges (type, rank,
    properties) instead of the caller synthesizing empty-properties ones —
    needed so the canvas can show a real relationship label on the line."""
    graph = get_graph_or_404(graph_id, registry)
    client = clients.for_space(graph.space)
    vertices, raw_edges = client.traversal.get_neighbors_with_edges(
        vid, edge_type=edge_type, direction=direction
    )
    limited = vertices[:limit]
    allowed = {v.vid for v in limited} | {vid}
    edges = [
        EdgeOut(src=e.src, dst=e.dst, edge_type=e.edge_type, rank=e.rank, properties=e.properties)
        for e in raw_edges
        if e.src in allowed and e.dst in allowed
    ]
    return SubgraphOut(nodes=[_to_node_out(v) for v in limited], edges=edges)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/api
pytest tests/unit/test_explorer_router.py -v
```

Expected: all tests in the file PASS, including the two new ones.

(If `pytest` isn't runnable in this sandbox per Global Constraints, re-read the diff carefully against `get_overview`'s identical filtering pattern a few lines below it in the same file, and flag this step as pending manual confirmation on the user's machine.)

- [ ] **Step 5: Commit**

```bash
cd /home/ec2-user/ankit_kumar/find-link
git add apps/api/src/graph_explorer_api/routers/explorer.py apps/api/tests/unit/test_explorer_router.py
git commit -m "feat: add /nodes/{vid}/neighbors-with-edges endpoint with real edge data"
```

---

### Task 3: Backend — `/overview` gains an optional `main_tags` filter

So Explorer's initial canvas can show only the user's chosen "main" tag(s) when person-centric mode is on, instead of always sampling every tag.

**Files:**
- Modify: `apps/api/src/graph_explorer_api/routers/explorer.py`
- Test: `apps/api/tests/unit/test_explorer_router.py`

**Interfaces:**
- Produces: `GET /api/graphs/{graph_id}/overview?main_tags=entity,person` restricts sampling to the listed tags (comma-separated); omitting the param keeps today's behavior exactly. Consumed by Task 4's frontend client method.

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/unit/test_explorer_router.py`:

```python
def test_overview_main_tags_restricts_sampling(client, fake_clients, graph_with_data):
    fake = fake_clients.for_space(graph_with_data["id"])
    fake.metadata.create_tag(SimpleNamespace(name="place"))
    fake.vertices.create_many("place", [("NYC", {"label": "NYC"})])

    resp = client.get(
        f"/api/graphs/{graph_with_data['id']}/overview", params={"main_tags": "entity"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert {n["label"] for n in body["nodes"]} == {"Alice", "Bob", "Cara"}
    assert "NYC" not in {n["label"] for n in body["nodes"]}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/api
pytest tests/unit/test_explorer_router.py -k main_tags -v
```

Expected: FAIL — `NYC` is included today because `/overview` samples every known tag.

- [ ] **Step 3: Add the `main_tags` parameter**

In `apps/api/src/graph_explorer_api/routers/explorer.py`, change the `get_overview` signature and body:

```python
@router.get("/overview", response_model=SubgraphOut)
def get_overview(
    graph_id: str,
    limit: int = Query(OVERVIEW_DEFAULT_LIMIT, ge=1, le=500),
    main_tags: str | None = Query(
        None, description="Comma-separated tag names to restrict sampling to"
    ),
    registry: GraphRegistry = Depends(get_registry),
    clients: GraphClientCache = Depends(get_clients),
) -> SubgraphOut:
    """An initial subgraph so the explorer never opens on a blank canvas.

    Phase 1 approximation: sample up to `limit` vertices spread across the
    graph's tags (or, if `main_tags` is set, just those tags), then include
    only the edges between sampled vertices (not every edge touching them)
    so the initial view stays legible.
    """
    graph = get_graph_or_404(graph_id, registry)
    client: GraphClient = clients.for_space(graph.space)
    tags = client.metadata.list_tags()
    if main_tags:
        wanted = {t.strip() for t in main_tags.split(",") if t.strip()}
        tags = [t for t in tags if t in wanted]
    if not tags:
        return SubgraphOut(nodes=[], edges=[])
```

(The rest of the function body — `per_tag_limit` through the final `return` — is unchanged.)

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/api
pytest tests/unit/test_explorer_router.py -v
```

Expected: all tests PASS, including `test_overview_returns_sampled_subgraph` (unchanged behavior when `main_tags` is omitted) and the new `test_overview_main_tags_restricts_sampling`.

- [ ] **Step 5: Commit**

```bash
cd /home/ec2-user/ankit_kumar/find-link
git add apps/api/src/graph_explorer_api/routers/explorer.py apps/api/tests/unit/test_explorer_router.py
git commit -m "feat: let /overview restrict sampling to a set of main tags"
```

---

### Task 4: Frontend — API client methods for the two new backend capabilities

**Files:**
- Modify: `apps/web/src/api/client.ts`

**Interfaces:**
- Consumes: `Subgraph`, `Direction` types already in `apps/web/src/api/types.ts`; `qs()` helper already in `client.ts`.
- Produces: `api.getNeighborsWithEdges(graphId, vid, opts) => Promise<Subgraph>`; `api.getOverview(graphId, limit?, mainTags?) => Promise<Subgraph>` (3rd param added, optional — existing call sites unaffected). Consumed by Task 6 (`ExplorerPage`) and Task 7 (`InvestigationPage`).

- [ ] **Step 1: Add `getNeighborsWithEdges` next to `getNeighbors`**

In `apps/web/src/api/client.ts`, immediately after the existing `getNeighbors` method (ends at the closing `),` before `getOverview`), add:

```ts
  getNeighborsWithEdges: (
    graphId: string,
    vid: string,
    opts: { edgeType?: string; direction?: Direction; limit?: number } = {},
  ) =>
    request<Subgraph>(
      `/api/graphs/${graphId}/nodes/${encodeURIComponent(vid)}/neighbors-with-edges${qs({
        edge_type: opts.edgeType,
        direction: opts.direction,
        limit: opts.limit,
      })}`,
    ),
```

- [ ] **Step 2: Extend `getOverview` with an optional `mainTags` param**

Replace:

```ts
  getOverview: (graphId: string, limit = 40) =>
    request<Subgraph>(`/api/graphs/${graphId}/overview${qs({ limit })}`),
```

with:

```ts
  getOverview: (graphId: string, limit = 40, mainTags?: string[]) =>
    request<Subgraph>(
      `/api/graphs/${graphId}/overview${qs({
        limit,
        main_tags: mainTags && mainTags.length ? mainTags.join(',') : undefined,
      })}`,
    ),
```

- [ ] **Step 3: Type-check**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/web
npm run build
```

Expected: builds clean (existing callers of `api.getOverview(graphId, 40)` still compile since the new param is optional).

- [ ] **Step 4: Commit**

```bash
cd /home/ec2-user/ankit_kumar/find-link
git add apps/web/src/api/client.ts
git commit -m "feat: add API client methods for neighbors-with-edges and main-tags overview"
```

---

### Task 5: Frontend — extract `useGraphCanvasState` hook

`ExplorerPage.tsx` currently keeps node/edge Maps, a "root vids" ref, and an "edges added per expansion" ref inline (`apps/web/src/pages/ExplorerPage.tsx:17-27, 108-160`) so that collapsing a node only removes the edges *that expansion* added. `InvestigationPage.tsx` needs identical bookkeeping once it gains collapse support (it currently has none). Extract it once so both pages share the same, already-correct logic instead of a second hand-rolled copy.

**Files:**
- Create: `apps/web/src/hooks/useGraphCanvasState.ts`

**Interfaces:**
- Consumes: `GraphNode`, `GraphEdge` types from `apps/web/src/api/types.ts`.
- Produces:
  ```ts
  function useGraphCanvasState(): {
    nodes: Map<string, GraphNode>
    edges: Map<string, GraphEdge>
    setOverview: (nodes: GraphNode[], edges: GraphEdge[]) => void
    mergeExpansion: (vid: string, newNodes: GraphNode[], newEdges: GraphEdge[]) => void
    collapse: (vid: string) => void
    addNode: (node: GraphNode) => void
    reset: () => void
  }
  ```
  Consumed by Task 6 (`ExplorerPage`) and Task 7 (`InvestigationPage`).

- [ ] **Step 1: Create the hook**

Create `apps/web/src/hooks/useGraphCanvasState.ts`:

```ts
import { useCallback, useRef, useState } from 'react'
import type { GraphEdge, GraphNode } from '../api/types'

function edgeKey(edge: GraphEdge): string {
  return `${edge.src}->${edge.dst}@${edge.edge_type}@${edge.rank}`
}

interface GraphCanvasState {
  nodes: Map<string, GraphNode>
  edges: Map<string, GraphEdge>
}

const EMPTY_STATE: GraphCanvasState = { nodes: new Map(), edges: new Map() }

/** Shared node/edge bookkeeping for an incrementally-expandable Cytoscape
 * graph: tracks which nodes are "roots" (the initial view — never pruned by
 * collapse) and which edges each expansion added, so collapsing one node
 * only removes *its* edges, not ones another still-expanded node also
 * needs, and never drops a node another expansion still references. */
export function useGraphCanvasState() {
  const rootVidsRef = useRef<Set<string>>(new Set())
  const expansionEdgeKeysRef = useRef<Map<string, Set<string>>>(new Map())
  const [state, setState] = useState<GraphCanvasState>(EMPTY_STATE)

  const setOverview = useCallback((nodes: GraphNode[], edges: GraphEdge[]) => {
    rootVidsRef.current = new Set(nodes.map((n) => n.vid))
    expansionEdgeKeysRef.current = new Map()
    setState({
      nodes: new Map(nodes.map((n) => [n.vid, n])),
      edges: new Map(edges.map((e) => [edgeKey(e), e])),
    })
  }, [])

  const mergeExpansion = useCallback((vid: string, newNodes: GraphNode[], newEdges: GraphEdge[]) => {
    setState((prev) => {
      const nodes = new Map(prev.nodes)
      newNodes.forEach((n) => {
        if (!nodes.has(n.vid)) nodes.set(n.vid, n)
      })
      const edges = new Map(prev.edges)
      const addedKeys = expansionEdgeKeysRef.current.get(vid) ?? new Set<string>()
      newEdges.forEach((e) => {
        const key = edgeKey(e)
        if (!edges.has(key)) addedKeys.add(key)
        edges.set(key, e)
      })
      expansionEdgeKeysRef.current.set(vid, addedKeys)
      return { nodes, edges }
    })
  }, [])

  const collapse = useCallback((vid: string) => {
    const addedKeys = expansionEdgeKeysRef.current.get(vid)
    expansionEdgeKeysRef.current.delete(vid)
    setState((prev) => {
      const edges = new Map(prev.edges)
      if (addedKeys) {
        for (const key of addedKeys) edges.delete(key)
      }
      const stillReferenced = new Set<string>()
      for (const edge of edges.values()) {
        stillReferenced.add(edge.src)
        stillReferenced.add(edge.dst)
      }
      const nodes = new Map(prev.nodes)
      for (const nodeVid of prev.nodes.keys()) {
        if (nodeVid === vid) continue
        if (rootVidsRef.current.has(nodeVid)) continue
        if (stillReferenced.has(nodeVid)) continue
        nodes.delete(nodeVid)
      }
      return { nodes, edges }
    })
  }, [])

  const addNode = useCallback((node: GraphNode) => {
    setState((prev) => {
      if (prev.nodes.has(node.vid)) return prev
      return { nodes: new Map(prev.nodes).set(node.vid, node), edges: prev.edges }
    })
  }, [])

  const reset = useCallback(() => {
    rootVidsRef.current = new Set()
    expansionEdgeKeysRef.current = new Map()
    setState(EMPTY_STATE)
  }, [])

  return { ...state, setOverview, mergeExpansion, collapse, addNode, reset }
}
```

- [ ] **Step 2: Type-check**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/web
npm run build
```

Expected: builds clean (the hook isn't imported anywhere yet, so this only checks it type-checks in isolation).

- [ ] **Step 3: Commit**

```bash
cd /home/ec2-user/ankit_kumar/find-link
git add apps/web/src/hooks/useGraphCanvasState.ts
git commit -m "refactor: extract useGraphCanvasState hook for reuse across explorer pages"
```

---

### Task 6: Frontend — `explorerStore` gains `mainTags`

**Files:**
- Modify: `apps/web/src/store/explorerStore.ts`

**Interfaces:**
- Produces: `useExplorerStore()` now also returns `mainTags: Set<string>` and `toggleMainTag: (tag: string) => void`; `reset()` clears it too. Consumed by Task 8 (`FilterPanel`) and Task 9 (`ExplorerPage`).

- [ ] **Step 1: Add the state and action**

In `apps/web/src/store/explorerStore.ts`, add to the `ExplorerState` interface:

```ts
  mainTags: Set<string>
  toggleMainTag: (tag: string) => void
```

and to the store implementation, add the initial value next to `hiddenEdgeTypes: new Set(),`:

```ts
  mainTags: new Set(),
```

and add the action next to `toggleEdgeType`:

```ts
  toggleMainTag: (tag) =>
    set((state) => {
      const next = new Set(state.mainTags)
      if (next.has(tag)) next.delete(tag)
      else next.add(tag)
      return { mainTags: next }
    }),
```

and add to `reset()`'s returned object:

```ts
      mainTags: new Set(),
```

- [ ] **Step 2: Type-check**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/web
npm run build
```

Expected: builds clean.

- [ ] **Step 3: Commit**

```bash
cd /home/ec2-user/ankit_kumar/find-link
git add apps/web/src/store/explorerStore.ts
git commit -m "feat: track which tags are 'main' nodes in explorerStore"
```

---

### Task 7: Frontend — `GraphCanvas` gains main/sub styling, real edge labels, and click-to-toggle-expand

This is the actual fix for "can't zoom/pan" on Investigation (Task 8 deletes its broken duplicate canvas in favor of this one) and adds the visual hierarchy + click behavior. Because this changes `GraphCanvas`'s prop contract, its one current consumer (`ExplorerPage.tsx`, plus `FilterPanel.tsx` for the new toggle UI) must be updated in the same task so the build stays green.

**Files:**
- Modify: `apps/web/src/components/explorer/GraphCanvas.tsx`
- Modify: `apps/web/src/components/explorer/FilterPanel.tsx`
- Modify: `apps/web/src/pages/ExplorerPage.tsx`

**Interfaces:**
- Consumes: `useGraphCanvasState` (Task 5), `mainTags`/`toggleMainTag` (Task 6), `api.getNeighborsWithEdges`/`api.getOverview` (Task 4).
- Produces: `GraphCanvas` props become `{ nodes, edges, selectedVid, mainTags: Set<string>, onSelect, onToggleExpand, onZoomChange? }` (replacing `onExpand`). `GraphCanvasHandle` is unchanged. Consumed by Task 9 (`InvestigationPage`).

- [ ] **Step 1: Rewrite `GraphCanvas.tsx`**

Replace the full contents of `apps/web/src/components/explorer/GraphCanvas.tsx` with:

```tsx
import { useEffect, useImperativeHandle, useRef, forwardRef, useCallback } from 'react'
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { GraphEdge, GraphNode } from '../../api/types'

cytoscape.use(fcose)

const TAG_PALETTE = [
  '#2f6feb',
  '#b5720a',
  '#1e8a5f',
  '#a340c9',
  '#c23b32',
  '#0f9bab',
]

function colorForTag(tag: string): string {
  let hash = 0
  for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) >>> 0
  return TAG_PALETTE[hash % TAG_PALETTE.length]
}

function edgeId(edge: GraphEdge): string {
  return `${edge.src}->${edge.dst}@${edge.edge_type}@${edge.rank}`
}

/** A node is a "main" hub if `mainTags` is empty (no hierarchy configured —
 * every node renders uniformly, today's behavior) or if it carries at least
 * one of the configured main tags; everything else is a "sub"/attribute
 * node, rendered smaller and muted. */
function roleForNode(node: GraphNode, mainTags: Set<string>): 'main' | 'sub' {
  if (mainTags.size === 0) return 'main'
  return node.tags.some((t) => mainTags.has(t)) ? 'main' : 'sub'
}

/** Prefer the human-readable relationship label captured at ingestion
 * (stored as the `relationship_type` edge property) over the raw edge
 * type code, e.g. "childhood friend" instead of "RELATED_TO". */
function edgeLabel(edge: GraphEdge): string {
  const relationshipType = edge.properties?.relationship_type
  if (typeof relationshipType === 'string' && relationshipType.trim()) return relationshipType
  return edge.edge_type
}

const STYLE: StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      'background-color': (ele: cytoscape.NodeSingular) => colorForTag(ele.data('tag')),
      label: 'data(label)',
      color: '#1a1d24',
      'font-size': 10,
      'text-valign': 'bottom',
      'text-margin-y': 6,
      width: 26,
      height: 26,
      'border-width': 2,
      'border-color': '#ffffff',
      'text-outline-width': 2,
      'text-outline-color': '#f6f7f9',
    },
  },
  {
    // Attribute/sub nodes (phone, email, address, ...) render smaller and
    // muted, so hub-vs-attribute reads at a glance without reading labels.
    selector: 'node[role = "sub"]',
    style: {
      width: 15,
      height: 15,
      'font-size': 8,
      'border-width': 1,
      opacity: 0.8,
    },
  },
  {
    selector: 'node:selected',
    style: { 'border-color': '#2f6feb', 'border-width': 3 },
  },
  {
    selector: 'edge',
    style: {
      width: 1.5,
      'line-color': '#c7ccd6',
      'target-arrow-color': '#c7ccd6',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.8,
      'curve-style': 'bezier',
      label: 'data(edgeType)',
      'font-size': 8,
      color: '#667085',
      'text-background-color': '#ffffff',
      'text-background-opacity': 0.85,
      'text-background-padding': '2px',
    },
  },
]

/** If the graph has drifted entirely outside the viewport (the "black
 * screen"), bring it back into view; otherwise leave the camera alone. */
function ensureGraphVisible(cy: Core) {
  if (cy.nodes().length === 0) return
  const bb = cy.nodes().boundingBox()
  const ext = cy.extent()
  const overlaps = bb.x1 < ext.x2 && bb.x2 > ext.x1 && bb.y1 < ext.y2 && bb.y2 > ext.y1
  if (!overlaps) cy.fit(undefined, 40)
}

export interface GraphCanvasHandle {
  zoomIn: () => void
  zoomOut: () => void
  fit: () => void
  centerSelected: () => void
  relayout: () => void
  exportPng: () => void
}

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedVid: string | null
  /** Tags that count as "main" hub nodes. Empty = no hierarchy — every
   * node renders identically (Explorer's default, unchanged behavior). */
  mainTags: Set<string>
  onSelect: (vid: string | null) => void
  /** Fired on every node tap. The caller decides expand vs. collapse based
   * on its own expanded-state tracking (single click toggles both). */
  onToggleExpand: (vid: string) => void
  onZoomChange?: (zoom: number) => void
}

const GraphCanvas = forwardRef<GraphCanvasHandle, Props>(function GraphCanvas(
  { nodes, edges, selectedVid, mainTags, onSelect, onToggleExpand, onZoomChange },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)
  // Last known position of every node that has ever been shown, so filter
  // toggles restore nodes where they were instead of dropping them at (0,0)
  // off-screen and re-running the layout.
  const positionsRef = useRef<Map<string, cytoscape.Position>>(new Map())
  const onSelectRef = useRef(onSelect)
  const onToggleExpandRef = useRef(onToggleExpand)
  onSelectRef.current = onSelect
  onToggleExpandRef.current = onToggleExpand

  useEffect(() => {
    if (!containerRef.current) return
    const cy = cytoscape({
      container: containerRef.current,
      style: STYLE,
      wheelSensitivity: 0.2,
      pixelRatio: 1,
      // NOTE: textureOnViewport was removed on purpose — it causes blank /
      // black frames during pan+zoom on some GPUs and isn't needed here.
      hideEdgesOnViewport: true,
      motionBlur: false,
    })
    cyRef.current = cy

    // Single click both selects (opens the detail panel) and toggles
    // expand/collapse — approved interaction model, applies to any node.
    cy.on('tap', 'node', (evt) => {
      const vid = evt.target.id()
      onSelectRef.current(vid)
      onToggleExpandRef.current(vid)
    })
    cy.on('tap', (evt) => {
      if (evt.target === cy) onSelectRef.current(null)
    })
    // Keep the position cache fresh when the user drags nodes around.
    cy.on('dragfree', 'node', (evt) => {
      positionsRef.current.set(evt.target.id(), { ...evt.target.position() })
    })

    // Cytoscape caches its container's size and offset. The container
    // changes size whenever the detail panel opens/closes, the filter panel
    // mounts, or the window resizes — without this, rendering goes stale
    // (blank areas) and clicks hit the wrong coordinates.
    const resizeObserver = new ResizeObserver(() => cy.resize())
    resizeObserver.observe(containerRef.current)

    return () => {
      resizeObserver.disconnect()
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  const handleZoomChange = useCallback(() => {
    const cy = cyRef.current
    if (cy) onZoomChange?.(cy.zoom())
  }, [onZoomChange])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !onZoomChange) return
    cy.on('zoom', handleZoomChange)
    return () => { cy.off('zoom', handleZoomChange) }
  }, [onZoomChange, handleZoomChange])

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => (cyRef.current as any)?.zoomIn(),
      zoomOut: () => (cyRef.current as any)?.zoomOut(),
      fit: () => cyRef.current?.fit(undefined, 40),
      centerSelected: () => cyRef.current?.fit(cyRef.current.$('node:selected'), 40),
      relayout: () => {
        const cy = cyRef.current
        if (!cy) return
        const fcoseOptions = {
          name: 'fcose',
          animate: false,
          quality: 'draft',
          randomize: false,
          fit: false,
          nodeRepulsion: 8000,
          idealEdgeLength: 90,
        } as unknown as cytoscape.LayoutOptions
        cy.layout(fcoseOptions).run()
      },
      exportPng: () => {
        const cy = cyRef.current
        if (!cy) return
        const blob = cy.png({ output: 'blob', bg: '#ffffff', full: true })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'graph.png'
        a.click()
        URL.revokeObjectURL(url)
      },
    }),
    [],
  )

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    const hadNodesBefore = cy.nodes().length > 0
    const desiredNodeIds = new Set(nodes.map((n) => n.vid))
    const desiredEdgeIds = new Set(edges.map(edgeId))

    cy.edges().forEach((ele) => {
      if (!desiredEdgeIds.has(ele.id())) ele.remove()
    })
    cy.nodes().forEach((ele) => {
      if (!desiredNodeIds.has(ele.id())) {
        // Remember where the node was so re-showing it restores the spot.
        positionsRef.current.set(ele.id(), { ...ele.position() })
        ele.remove()
      }
    })

    let brandNewCount = 0
    const newNodeEles: ElementDefinition[] = []
    for (const n of nodes) {
      if (!cy.getElementById(n.vid).empty()) continue
      const saved = positionsRef.current.get(n.vid)
      if (!saved) brandNewCount++
      newNodeEles.push({
        data: { id: n.vid, label: n.label, tag: n.tags[0] ?? 'entity', role: roleForNode(n, mainTags) },
        ...(saved ? { position: { ...saved } } : {}),
      })
    }

    const newEdgeEles: ElementDefinition[] = edges
      .filter((e) => cy.getElementById(edgeId(e)).empty())
      .map((e) => ({
        data: { id: edgeId(e), source: e.src, target: e.dst, edgeType: edgeLabel(e) },
      }))

    cy.add([...newNodeEles, ...newEdgeEles])

    // Keep already-visible nodes' main/sub role in sync when mainTags
    // changes (e.g. the user just marked a tag as main) without touching
    // anything else about them.
    for (const n of nodes) {
      const ele = cy.getElementById(n.vid)
      if (!ele.empty()) ele.data('role', roleForNode(n, mainTags))
    }

    // Only run the layout when nodes appear that have never had a position
    // (initial load, an expansion, a search hit). Re-showing filtered nodes
    // and toggling edge types keep the existing layout untouched, so the
    // graph no longer reshuffles on every filter click.
    if (brandNewCount > 0) {
      // fcose's options (animate/randomize/nodeRepulsion/...) aren't part of
      // @types/cytoscape's built-in layout typings, hence the cast.
      const fcoseOptions = {
        name: 'fcose',
        animate: false,
        quality: 'draft',
        randomize: !hadNodesBefore,
        fit: false,
        nodeRepulsion: 8000,
        idealEdgeLength: 90,
      } as unknown as cytoscape.LayoutOptions
      const layout = cy.layout(fcoseOptions)
      layout.one('layoutstop', () => {
        // Cache the settled positions of everything, then make sure the
        // result is actually on screen.
        cy.nodes().forEach((ele) => { positionsRef.current.set(ele.id(), { ...ele.position() }) })
        if (!hadNodesBefore) cy.fit(undefined, 40)
        else ensureGraphVisible(cy)
      })
      layout.run()
    } else if (newNodeEles.length > 0 || newEdgeEles.length > 0) {
      ensureGraphVisible(cy)
    }
  }, [nodes, edges, mainTags])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes().unselect()
    if (selectedVid) cy.getElementById(selectedVid).select()
  }, [selectedVid])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
})

export default GraphCanvas
```

- [ ] **Step 2: Add the "set as main" toggle to `FilterPanel.tsx`**

Replace the full contents of `apps/web/src/components/explorer/FilterPanel.tsx` with:

```tsx
import type { SchemaInfo } from '../../api/types'
import InfoTooltip from '../common/InfoTooltip'

interface Props {
  schema: SchemaInfo
  hiddenTags: Set<string>
  hiddenEdgeTypes: Set<string>
  mainTags: Set<string>
  onToggleTag: (tag: string) => void
  onToggleEdgeType: (edgeType: string) => void
  onToggleMainTag: (tag: string) => void
}

export default function FilterPanel({
  schema,
  hiddenTags,
  hiddenEdgeTypes,
  mainTags,
  onToggleTag,
  onToggleEdgeType,
  onToggleMainTag,
}: Props) {
  return (
    <div className="card stack" style={{ width: '100%' }}>
      <div>
        <h4 style={{ marginBottom: 'var(--space-2)' }}>
          Node types
          <InfoTooltip text="Untick a type to hide those items from the graph. Star a type to treat it as a main node: the graph will show only starred types at first, and clicking one reveals everything connected to it." />
        </h4>
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          {schema.tags.map((tag) => (
            <div key={tag} className="row" style={{ gap: 'var(--space-2)', justifyContent: 'space-between' }}>
              <label className="row" style={{ gap: 'var(--space-2)' }}>
                <input
                  type="checkbox"
                  checked={!hiddenTags.has(tag)}
                  onChange={() => onToggleTag(tag)}
                />
                {tag}
              </label>
              <button
                type="button"
                className="btn btn-sm"
                aria-pressed={mainTags.has(tag)}
                title={mainTags.has(tag) ? 'Main node type — click to unset' : 'Set as a main node type'}
                onClick={() => onToggleMainTag(tag)}
                style={{ color: mainTags.has(tag) ? 'var(--color-primary)' : undefined }}
              >
                ★
              </button>
            </div>
          ))}
        </div>
      </div>
      <div>
        <h4 style={{ marginBottom: 'var(--space-2)' }}>
          Relationship types
          <InfoTooltip text="Untick a type to hide those connections from the graph. Doesn't delete anything — just hides them from view." />
        </h4>
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          {schema.edge_types.map((edgeType) => (
            <label key={edgeType} className="row" style={{ gap: 'var(--space-2)' }}>
              <input
                type="checkbox"
                checked={!hiddenEdgeTypes.has(edgeType)}
                onChange={() => onToggleEdgeType(edgeType)}
              />
              {edgeType}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Rewrite `ExplorerPage.tsx` to use the hook, the new endpoint, and the new `GraphCanvas` contract**

Replace the full contents of `apps/web/src/pages/ExplorerPage.tsx` with:

```tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { SearchResult } from '../api/types'
import { useExplorerStore } from '../store/explorerStore'
import { useGraphCanvasState } from '../hooks/useGraphCanvasState'
import GraphCanvas, { type GraphCanvasHandle } from '../components/explorer/GraphCanvas'
import GraphControls from '../components/explorer/GraphControls'
import SearchBar from '../components/explorer/SearchBar'
import FilterPanel from '../components/explorer/FilterPanel'
import NodeDetailPanel from '../components/explorer/NodeDetailPanel'

export default function ExplorerPage() {
  const { graphId } = useParams<{ graphId: string }>()
  const graphState = useGraphCanvasState()
  const [expandingVids, setExpandingVids] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const canvasRef = useRef<GraphCanvasHandle>(null)

  const {
    selectedVid,
    expandedVids,
    hiddenTags,
    hiddenEdgeTypes,
    mainTags,
    select,
    markExpanded,
    markCollapsed,
    toggleTag,
    toggleEdgeType,
    toggleMainTag,
    reset,
  } = useExplorerStore()

  const graphQuery = useQuery({ queryKey: ['graph', graphId], queryFn: () => api.getGraph(graphId!) })
  const schemaQuery = useQuery({ queryKey: ['schema', graphId], queryFn: () => api.getSchema(graphId!) })
  const mainTagsKey = useMemo(() => Array.from(mainTags).sort().join(','), [mainTags])
  const overviewQuery = useQuery({
    queryKey: ['overview', graphId, mainTagsKey],
    queryFn: () => api.getOverview(graphId!, 40, mainTags.size > 0 ? Array.from(mainTags) : undefined),
  })

  // Reset canvas + selection state when navigating to a different graph.
  useEffect(() => {
    reset()
    graphState.reset()
    setExpandingVids(new Set())
    setActionError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphId])

  useEffect(() => {
    if (!overviewQuery.data) return
    graphState.setOverview(overviewQuery.data.nodes, overviewQuery.data.edges)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overviewQuery.data])

  async function expandNode(vid: string) {
    if (expandingVids.has(vid)) return // an expansion for this node is already in flight
    setExpandingVids((prev) => new Set(prev).add(vid))
    setActionError(null)

    try {
      const subgraph = await api.getNeighborsWithEdges(graphId!, vid, { direction: 'both', limit: 200 })
      graphState.mergeExpansion(vid, subgraph.nodes, subgraph.edges)
      markExpanded(vid)
    } catch (err) {
      setActionError(
        err instanceof Error ? `Could not expand this node: ${err.message}` : 'Could not expand this node.',
      )
    } finally {
      setExpandingVids((prev) => {
        const next = new Set(prev)
        next.delete(vid)
        return next
      })
    }
  }

  function collapseNode(vid: string) {
    graphState.collapse(vid)
    markCollapsed(vid)
  }

  function toggleExpand(vid: string) {
    if (expandedVids.has(vid)) collapseNode(vid)
    else void expandNode(vid)
  }

  async function handleSearchResult(result: SearchResult) {
    try {
      if (!graphState.nodes.has(result.vid)) {
        const node = await api.getNode(graphId!, result.vid)
        graphState.addNode(node)
      }
      select(result.vid)
      setActionError(null)
    } catch {
      setActionError(
        `Could not load "${result.label}" — the search index may be stale. Re-import the data or restart the API to rebuild it.`,
      )
    }
  }

  const visibleNodes = useMemo(
    () => Array.from(graphState.nodes.values()).filter((n) => !n.tags.some((t) => hiddenTags.has(t))),
    [graphState.nodes, hiddenTags],
  )
  const visibleVids = useMemo(() => new Set(visibleNodes.map((n) => n.vid)), [visibleNodes])
  const visibleEdges = useMemo(
    () =>
      Array.from(graphState.edges.values()).filter(
        (e) => !hiddenEdgeTypes.has(e.edge_type) && visibleVids.has(e.src) && visibleVids.has(e.dst),
      ),
    [graphState.edges, hiddenEdgeTypes, visibleVids],
  )

  const graphIsEmpty = overviewQuery.data != null && graphState.nodes.size === 0
  const allFilteredOut = graphState.nodes.size > 0 && visibleNodes.length === 0

  if (graphQuery.isError) {
    return (
      <main className="page">
        <p style={{ color: 'var(--color-danger)' }}>This graph could not be found.</p>
        <Link to="/">← All graphs</Link>
      </main>
    )
  }

  return (
    <main className="page page--flush explorer">
      <div className="explorer-topbar">
        <div className="row">
          <Link to="/">← All graphs</Link>
          <strong>{graphQuery.data?.name}</strong>
        </div>
        <div className="explorer-topbar__search">
          {graphId && <SearchBar graphId={graphId} onResultClick={handleSearchResult} />}
        </div>
      </div>

      {actionError && <div className="status-strip">{actionError}</div>}

      <div className="explorer-layout">
        {schemaQuery.data && (
          <div className="explorer-filter-panel">
            <FilterPanel
              schema={schemaQuery.data}
              hiddenTags={hiddenTags}
              hiddenEdgeTypes={hiddenEdgeTypes}
              mainTags={mainTags}
              onToggleTag={toggleTag}
              onToggleEdgeType={toggleEdgeType}
              onToggleMainTag={toggleMainTag}
            />
          </div>
        )}

        <div className="card explorer-canvas">
          {overviewQuery.isLoading ? (
            <div className="row" style={{ height: '100%', justifyContent: 'center' }}>
              <span className="spinner" /> Loading graph…
            </div>
          ) : overviewQuery.isError ? (
            <div
              className="stack"
              style={{ height: '100%', alignItems: 'center', justifyContent: 'center' }}
            >
              <p className="error-text">
                Could not load the graph overview:{' '}
                {overviewQuery.error instanceof Error ? overviewQuery.error.message : 'unknown error'}
              </p>
              <button className="btn btn-sm" onClick={() => overviewQuery.refetch()}>
                Retry
              </button>
            </div>
          ) : (
            <>
              {graphId && (
                <GraphCanvas
                  ref={canvasRef}
                  key={graphId}
                  nodes={visibleNodes}
                  edges={visibleEdges}
                  selectedVid={selectedVid}
                  mainTags={mainTags}
                  onSelect={select}
                  onToggleExpand={toggleExpand}
                  onZoomChange={setZoom}
                />
              )}
              {graphId && (
                <GraphControls
                  onZoomIn={() => canvasRef.current?.zoomIn()}
                  onZoomOut={() => canvasRef.current?.zoomOut()}
                  onFit={() => canvasRef.current?.fit()}
                  onCenterSelected={() => canvasRef.current?.centerSelected()}
                  onRelayout={() => canvasRef.current?.relayout()}
                  onExportPng={() => canvasRef.current?.exportPng()}
                  onToggleFullscreen={() => {
                    if (!document.fullscreenElement) {
                      document.documentElement.requestFullscreen()
                      setIsFullscreen(true)
                    } else {
                      document.exitFullscreen()
                      setIsFullscreen(false)
                    }
                  }}
                  isFullscreen={isFullscreen}
                  hasSelection={selectedVid != null}
                  zoom={zoom}
                />
              )}
              {graphIsEmpty && (
                <div className="explorer-canvas__overlay">
                  <p className="muted">This graph is empty — import a CSV to get started.</p>
                </div>
              )}
              {allFilteredOut && (
                <div className="explorer-canvas__overlay">
                  <p className="muted">All nodes are hidden by the current filters.</p>
                </div>
              )}
            </>
          )}
        </div>

        {graphId && selectedVid && (
          <div className="explorer-detail-panel">
            <NodeDetailPanel
              graphId={graphId}
              vid={selectedVid}
              isExpanded={expandedVids.has(selectedVid)}
              isExpanding={expandingVids.has(selectedVid)}
              onExpand={() => void expandNode(selectedVid)}
              onCollapse={() => collapseNode(selectedVid)}
              onClose={() => select(null)}
            />
          </div>
        )}
      </div>
    </main>
  )
}
```

- [ ] **Step 4: Type-check and lint**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/web
npm run build
npm run lint
```

Expected: both clean.

- [ ] **Step 5: Manual verification (dev server, no backend available in this sandbox)**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/web
npm run dev
```

Open the printed local URL. Without a backend, the Graphs list will show a fetch error — that's expected here (per Global Constraints, the full stack isn't run in this sandbox). Confirm there are no console errors on load and that the page renders (topbar, sidebar) without a blank screen or React error boundary. Full interactive verification (pan/zoom/click-to-expand/main-tag toggle against real data) happens on the user's machine once the backend is running — call this out explicitly when reporting this task done.

- [ ] **Step 6: Commit**

```bash
cd /home/ec2-user/ankit_kumar/find-link
git add apps/web/src/components/explorer/GraphCanvas.tsx apps/web/src/components/explorer/FilterPanel.tsx apps/web/src/pages/ExplorerPage.tsx
git commit -m "feat: main/sub node hierarchy, real edge labels, and click-to-toggle-expand on the Explorer canvas"
```

---

### Task 8: Frontend — rebuild `InvestigationPage` on the shared canvas

Deletes the bare, control-less Cytoscape setup (`apps/web/src/pages/InvestigationPage.tsx:45-130`) in favor of the same `GraphCanvas`/`GraphControls`/`useGraphCanvasState` the Explorer page uses — this is what actually fixes "can't pan/zoom" here. Adds collapse (previously missing entirely) and the fixed `person`/`company`/`organization` main-tag hierarchy.

**Files:**
- Modify: `apps/web/src/pages/InvestigationPage.tsx`
- Modify: `apps/web/src/index.css`

**Interfaces:**
- Consumes: `GraphCanvas`/`GraphCanvasHandle`/`GraphControls` (Task 7), `useGraphCanvasState` (Task 5), `EntityGraphNode`/`GraphNode`/`EntitySearchHit`/`RiskResult` types already in `apps/web/src/api/types.ts`.

- [ ] **Step 1: Give `.explorer-center` a positioned, clipped box for `GraphControls` to anchor in**

In `apps/web/src/index.css`, change:

```css
.explorer-center {
  flex: 1;
  min-width: 0;
}
```

to:

```css
.explorer-center {
  flex: 1;
  min-width: 0;
  position: relative;
  overflow: hidden;
}
```

- [ ] **Step 2: Rewrite `InvestigationPage.tsx`**

Replace the full contents of `apps/web/src/pages/InvestigationPage.tsx` with:

```tsx
import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { EntityGraphNode, EntitySearchHit, GraphNode, RiskResult } from '../api/types'
import GraphPicker from '../components/common/GraphPicker'
import JsonView from '../components/common/JsonView'
import InfoTooltip from '../components/common/InfoTooltip'
import GraphCanvas, { type GraphCanvasHandle } from '../components/explorer/GraphCanvas'
import GraphControls from '../components/explorer/GraphControls'
import { useGraphCanvasState } from '../hooks/useGraphCanvasState'

// Fixed to the canonical schema (packages/ingestion-core/src/ingestion_core/canonical.py):
// person/company/organization are the hub entities everything else attaches to.
const MAIN_TAGS = new Set(['person', 'company', 'organization'])

export function riskColor(level: string): string {
  switch (level) {
    case 'high':
      return '#c23b32'
    case 'medium':
      return '#b5720a'
    default:
      return '#1e8a5f'
  }
}

function toGraphNode(n: EntityGraphNode): GraphNode {
  const properties: Record<string, unknown> = {}
  for (const props of Object.values(n.tags)) Object.assign(properties, props)
  return { vid: n.id, tags: Object.keys(n.tags), label: n.label || n.id, properties }
}

/** Investigation canvas: search people, load their neighborhood into the
 * shared graph canvas, inspect nodes, see risk scores, expand deeper by
 * clicking a node (click again to collapse it), and run shortest-path
 * between two picked nodes. */
export function InvestigationGraphPage() {
  const graphState = useGraphCanvasState()
  const canvasRef = useRef<GraphCanvasHandle>(null)

  const [graphId, setGraphId] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [entityType, setEntityType] = useState('person')
  const [searchResults, setSearchResults] = useState<EntitySearchHit[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)

  const [selectedVid, setSelectedVid] = useState<string | null>(null)
  const [expandedVids, setExpandedVids] = useState<Set<string>>(new Set())
  const [zoom, setZoom] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [risk, setRisk] = useState<RiskResult | null>(null)
  const [depth, setDepth] = useState(1)
  const [pathSource, setPathSource] = useState<string | null>(null)
  const [pathResult, setPathResult] = useState<unknown>(null)
  const [status, setStatus] = useState<string | null>(null)

  // Reset canvas + selection state when the user picks a different graph.
  useEffect(() => {
    graphState.reset()
    setSelectedVid(null)
    setExpandedVids(new Set())
    setRisk(null)
    setPathSource(null)
    setPathResult(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphId])

  async function handleSearch() {
    if (!graphId || !searchQuery.trim()) return
    setSearchError(null)
    try {
      const results = await api.searchEntities(graphId, searchQuery.trim(), entityType.trim() || 'person')
      setSearchResults(results)
      if (results.length === 0) setSearchError('No matches.')
    } catch (err) {
      setSearchResults([])
      setSearchError((err as Error).message)
    }
  }

  async function loadEntity(entityId: string, replace: boolean) {
    if (!graphId) return
    setStatus(`Expanding ${entityId} (depth ${depth})…`)
    try {
      const data = await api.expandEntityGraph(graphId, entityId, depth)
      const nodes = data.nodes.map(toGraphNode)
      if (replace) graphState.setOverview(nodes, data.edges)
      else graphState.mergeExpansion(entityId, nodes, data.edges)
      setExpandedVids((prev) => new Set(prev).add(entityId))
      setStatus(null)
    } catch (err) {
      setStatus(`✗ ${(err as Error).message}`)
    }
  }

  function collapseEntity(entityId: string) {
    graphState.collapse(entityId)
    setExpandedVids((prev) => {
      const next = new Set(prev)
      next.delete(entityId)
      return next
    })
  }

  function toggleExpand(vid: string) {
    if (expandedVids.has(vid)) collapseEntity(vid)
    else void loadEntity(vid, false)
  }

  async function handleSelectResult(hit: EntitySearchHit) {
    setSearchResults([])
    setSearchQuery('')
    setSelectedVid(hit.entity_id)
    await loadEntity(hit.entity_id, true)
  }

  async function fetchRisk(entityId: string) {
    setRisk(null)
    try {
      setRisk(await api.getEntityRisk(graphId, entityId))
    } catch (err) {
      setStatus(`✗ risk: ${(err as Error).message}`)
    }
  }

  async function runShortestPath(targetId: string) {
    if (!pathSource || !graphId) return
    setStatus(`Path ${pathSource} → ${targetId}…`)
    try {
      setPathResult(await api.shortestPath(graphId, pathSource, targetId))
      setStatus(null)
    } catch (err) {
      setStatus(`✗ ${(err as Error).message}`)
    } finally {
      setPathSource(null)
    }
  }

  const selectedNode = selectedVid ? graphState.nodes.get(selectedVid) ?? null : null

  return (
    <main className="page page--flush explorer">
      <div className="explorer-topbar">
        <div className="row" style={{ flex: '0 0 auto' }}>
          <strong>Investigation</strong>
          <div style={{ width: 220 }}>
            <GraphPicker
              value={graphId}
              onChange={setGraphId}
              label=""
              info="Choose which graph to search and explore."
            />
          </div>
        </div>
        <div className="explorer-topbar__search" style={{ position: 'relative' }}>
          <div className="row">
            <input
              className="input"
              style={{ width: 110 }}
              value={entityType}
              onChange={(e) => setEntityType(e.target.value)}
              title="Entity type (tag)"
            />
            <InfoTooltip text="What kind of thing to search for, e.g. person, company, or address." />
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder={graphId ? 'Search entities by name…' : 'Pick a graph first'}
              disabled={!graphId}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button className="btn btn--primary" disabled={!graphId} onClick={handleSearch}>
              Search
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="card search-dropdown">
              {searchResults.map((hit) => (
                <button
                  key={hit.entity_id}
                  className="list-item"
                  onClick={() => handleSelectResult(hit)}
                >
                  <strong>{hit.label || hit.entity_id}</strong>
                  <div className="mono muted">{hit.entity_id}</div>
                </button>
              ))}
            </div>
          )}
        </div>
        <label className="row" style={{ gap: 'var(--space-2)' }}>
          <span className="muted">Depth</span>
          <InfoTooltip text="How many steps out from a person or company to load onto the graph at once." />
          <select className="select" style={{ width: 90 }} value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            <option value={1}>1 hop</option>
            <option value={2}>2 hops</option>
            <option value={3}>3 hops</option>
          </select>
        </label>
      </div>

      {(status || searchError) && (
        <div className="status-strip">{status ?? searchError}</div>
      )}

      <div className="explorer-body">
        <div className="explorer-center">
          <GraphCanvas
            ref={canvasRef}
            key={graphId}
            nodes={Array.from(graphState.nodes.values())}
            edges={Array.from(graphState.edges.values())}
            selectedVid={selectedVid}
            mainTags={MAIN_TAGS}
            onSelect={setSelectedVid}
            onToggleExpand={toggleExpand}
            onZoomChange={setZoom}
          />
          <GraphControls
            onZoomIn={() => canvasRef.current?.zoomIn()}
            onZoomOut={() => canvasRef.current?.zoomOut()}
            onFit={() => canvasRef.current?.fit()}
            onCenterSelected={() => canvasRef.current?.centerSelected()}
            onRelayout={() => canvasRef.current?.relayout()}
            onExportPng={() => canvasRef.current?.exportPng()}
            onToggleFullscreen={() => {
              if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen()
                setIsFullscreen(true)
              } else {
                document.exitFullscreen()
                setIsFullscreen(false)
              }
            }}
            isFullscreen={isFullscreen}
            hasSelection={selectedVid != null}
            zoom={zoom}
          />
        </div>

        <div className="explorer-right">
          {selectedNode ? (
            <div className="panel stack">
              <h3>{selectedNode.label}</h3>
              <p className="text-secondary mono">{selectedNode.vid}</p>

              <div className="row" style={{ flexWrap: 'wrap' }}>
                <button className="btn btn--primary" onClick={() => toggleExpand(selectedNode.vid)}>
                  {expandedVids.has(selectedNode.vid) ? 'Collapse' : 'Expand'}
                </button>
                <InfoTooltip text="Load everyone and everything directly connected to this node onto the graph, or collapse it back." />
                <button className="btn" onClick={() => fetchRisk(selectedNode.vid)}>
                  Risk
                </button>
                <InfoTooltip text="Calculate a risk score for this person or company based on their connections and known flags." />
                {pathSource && pathSource !== selectedNode.vid ? (
                  <button className="btn" onClick={() => runShortestPath(selectedNode.vid)}>
                    Path from {pathSource.slice(0, 12)}… → here
                  </button>
                ) : (
                  <button className="btn" onClick={() => setPathSource(selectedNode.vid)}>
                    Path: set as source
                  </button>
                )}
                <InfoTooltip text="Find the shortest chain of connections between two people or companies. Pick a starting point here, then click another node to find the path to it." />
              </div>

              {risk && risk.entity_id === selectedNode.vid && (
                <div className="risk-section">
                  <h4>Risk assessment</h4>
                  <div className="risk-badge" style={{ background: riskColor(risk.level), color: '#fff' }}>
                    {risk.level.toUpperCase()} · {risk.score.toFixed(2)}
                  </div>
                  {risk.factors.length > 0 && (
                    <ul className="risk-factors">
                      {risk.factors.map((f, i) => (
                        <li key={i}>{f.explanation}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <h4>Properties</h4>
              <JsonView data={selectedNode.properties} title="properties" initiallyOpen />
            </div>
          ) : (
            <div className="panel">
              <h3>Investigation tools</h3>
              <p className="text-secondary">
                Pick a graph, search a person or company, then click it on the canvas to
                inspect, expand its connections, score risk, or run a shortest path. Only
                people, companies, and organizations show up front — click one to reveal
                everything connected to it, and click an expanded node again to collapse
                it.
              </p>
            </div>
          )}

          {pathResult !== null && (
            <div className="panel">
              <JsonView data={pathResult} title="shortest-path result" />
              <button className="btn" onClick={() => setPathResult(null)}>
                Clear
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  )
}
```

- [ ] **Step 3: Type-check and lint**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/web
npm run build
npm run lint
```

Expected: both clean. This is the primary signal for this task since `cytoscape`/`fcose` are no longer imported directly here (confirm the build doesn't complain about now-unused former imports — there should be none left, they were fully removed in the rewrite above).

- [ ] **Step 4: Manual verification (dev server, no backend available in this sandbox)**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/web
npm run dev
```

Navigate to `/investigation`. Without a backend, `GraphPicker` will show empty/error state — expected here. Confirm the page renders without a blank screen or console error, and that the canvas area + zoom/fit/relayout/fullscreen toolbar mount (they'll just show an empty canvas). Full interactive verification (search → select → auto-expand → click to collapse → pan/zoom) happens on the user's machine against a real graph — call this out explicitly when reporting this task done.

- [ ] **Step 5: Commit**

```bash
cd /home/ec2-user/ankit_kumar/find-link
git add apps/web/src/pages/InvestigationPage.tsx apps/web/src/index.css
git commit -m "feat: rebuild Investigation page on the shared graph canvas (fixes broken pan/zoom, adds collapse)"
```

---

### Task 9: Final verification pass

**Files:** none (verification only).

- [ ] **Step 1: Full frontend build + lint**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/web
npm run build
npm run lint
```

Expected: both clean, zero errors/warnings introduced by this feature.

- [ ] **Step 2: Backend test suite (on the user's machine, or here if the Python ≥3.10 toolchain turns out to be available)**

```bash
cd /home/ec2-user/ankit_kumar/find-link/apps/api
pytest tests/unit -v
```

Expected: full suite passes, including the four new tests from Tasks 1–3.

- [ ] **Step 3: Manual end-to-end check (owner's machine, per `CLAUDE.md`)**

With NebulaGraph/backend/frontend all running:

- Explorer page: confirm scroll-to-zoom, drag-to-pan, the zoom/fit/relayout/fullscreen toolbar, and clicking a node both selects it and expands its neighbors (click again collapses). Star a tag in the filter panel and confirm the canvas narrows to that tag's nodes on next load, with clicking one revealing its connections.
- Investigation page: confirm the same pan/zoom/toolbar now works (previously completely non-functional), search finds only person/company/organization results, clicking a result loads its neighborhood with people/companies shown large and attributes (phone/email/address/...) shown small, and connections between two people show a real relationship label (not just the raw edge-type code) when the source data has one.

- [ ] **Step 4: Report results**

Summarize which checks passed, which are still pending the owner's manual pass, and any deviations from this plan discovered during implementation.
