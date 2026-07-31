# Graph exploration: unified navigation + person-centric hierarchy

## Goal

Two problems, one root cause worth fixing together:

1. **Navigation is broken/hard to use.** Panning, zooming, and general canvas
   navigation don't work reliably. The Investigation page (`/investigation`)
   has a bare-bones Cytoscape setup with no zoom/pan/fit controls and no
   resize handling at all — unlike the Explorer page, which already has a
   working `GraphCanvas` + `GraphControls` pair. The fix is to stop
   duplicating canvas logic: extract one shared, already-solid canvas
   component and use it on both pages.
2. **The canvas shows everything at once with no hierarchy.** The user wants
   a "main node → connected sub-node" model: person (and company/
   organization) nodes are the primary hubs; things like phone, email,
   address, passport, bank account are satellite information nodes that
   only appear once their owning node is expanded. Connections between two
   hub nodes (e.g. two people) should show their relationship as a label on
   the connecting line — the standard link-chart / investigation-tool
   pattern (Palantir/Maltego-style).

## Scope

- `apps/web/src/pages/InvestigationPage.tsx` — replace its bespoke Cytoscape
  init with the shared canvas component; adopt person-centric hierarchy
  (fixed to the canonical schema: `person`, `company`, `organization` are
  main; everything else is a sub-node).
- `apps/web/src/components/explorer/GraphCanvas.tsx` /
  `GraphControls.tsx` — generalize (already Explorer-specific) into a
  shared pair both pages import; add main/sub visual styling and
  click-to-expand/collapse.
- `apps/web/src/components/explorer/FilterPanel.tsx` — add an opt-in
  "mark tag(s) as main" control so Explorer (arbitrary, schema-agnostic CSV
  data) can turn the same hierarchy on for its own data, off by default.
- `apps/api/src/graph_explorer_api/routers/explorer.py` — extend the
  neighbor-fetch endpoint to return real edge data (type, rank, properties)
  instead of the frontend synthesizing empty-properties edges, reusing the
  already-existing `graph_core Traversal.get_neighbors_with_edges` (already
  used internally by the Investigation/entities backend).
- Out of scope: risk scoring, shortest-path, CSV import pipeline, the
  Explorer's search/filter panel beyond the one new toggle, backend schema
  storage changes. No changes to `graph-core`'s public surface beyond what
  `get_neighbors_with_edges` already provides.

## Shared canvas component

`GraphCanvas` (Cytoscape core, imperative via `useRef`/`useEffect`,
`cytoscape-fcose` layout) and `GraphControls` (zoom in/out, fit, center-
selected, relayout, export PNG, fullscreen, zoom-percent indicator) move
from Explorer-only to a shared pair both pages import unchanged. This is
the actual fix for "can't pan/zoom" on Investigation: it inherits working
wheel-zoom, drag-pan, `ResizeObserver`-driven resize (so panel open/close
doesn't desync click coordinates), and position caching (dragged/expanded
nodes keep their spot across re-renders) for free, instead of a second,
incomplete implementation.

No changes to the underlying interaction primitives (wheel sensitivity,
`hideEdgesOnViewport`, `motionBlur: false`, the `ensureGraphVisible`
recovery for a graph that's drifted off-screen) — they already work
correctly on Explorer.

## Person-centric node model

**Main vs. sub-node classification:**
- Investigation page: fixed constant `MAIN_TAGS = ['person', 'company',
  'organization']`, matching `ingestion_core/canonical.py`'s existing
  taxonomy. Not configurable — Investigation's data always comes through
  that canonical schema.
- Explorer page: schema-agnostic CSV uploads have no fixed taxonomy, so
  this is an opt-in per-tag toggle in `FilterPanel` ("Set as main"),
  starting empty. With no tags marked main, Explorer's behavior is
  unchanged from today (flat view, all tags visible). Marking one or more
  tags main switches the canvas into the same hierarchy using those tags.

**Initial view:** only main-tagged nodes are fetched/shown
(`/overview` on Explorer already samples per-tag — when main tags are set,
sample only those; Investigation's initial state is empty until a search
picks a starting node, unchanged).

**Expand/collapse — applies to any node, not just main ones:**
Clicking a node selects it *and* expands it in place: fetch its
connections (both other main nodes and attribute/sub nodes), add them as
satellites, incremental re-layout preserving existing node positions
(same approach as Explorer's current `expandNode`/fcose incremental-add
behavior). Clicking an already-expanded node again collapses it — removes
satellites that would become orphaned (not referenced by any other visible
node), reusing Explorer's existing collapse logic
(`ExplorerPage.collapseNode`'s reference-counting approach), moved into
the shared canvas/hook layer so Investigation gets it too.

Deliberately *not* restricted to person nodes: expanding a shared
attribute (e.g. a phone number two people both have) is often the most
useful signal in this kind of tool, and it's the same mechanism either
way — only the *initial* visible set is main-only.

**Visual distinction:** main nodes render larger with a bold border (the
existing per-tag color palette, `colorForTag`, stays); sub nodes render
smaller and visually muted (lighter border, reduced opacity), so hub vs.
attribute nodes are distinguishable at a glance without reading labels.

## Relationship labels on edges

Edge labels already render (`label: 'data(edgeType)'` in `GraphCanvas`'s
Cytoscape style), but expansion currently fabricates edges with
`properties: {}` and `rank: 0` client-side, because `GET
/nodes/{vid}/neighbors` returns only nodes, no edge data.

Extend that endpoint's response to include edges (type, rank, properties),
using `Traversal.get_neighbors_with_edges` from `graph-core` — already
implemented and already used server-side by
`graph_service.expand_node` for the Investigation/entities router, just
not exposed through Explorer's neighbor-fetch path. Response shape becomes
`{ nodes, edges }` (matching the existing `SubgraphOut` model already used
by `/overview`), rather than a bare node list.

Edge label text prefers `properties.relation_label` (a human-readable
label captured at ingestion time, e.g. "childhood friend" instead of
`RELATED_TO`) when present, falling back to `edge_type` — no style changes
needed, the existing text-background/legibility treatment stays as-is.

Both `ExplorerPage.expandNode` and the Investigation page's expand logic
switch to consuming real edges from this endpoint instead of synthesizing
them.

## Error handling / edge cases

- Expanding a node with zero connections: no-op past the fetch (nothing
  added), same as today — no special-case UI needed.
- Collapsing a node whose satellites are also referenced by another
  visible expanded node: those satellites stay (existing reference-
  counting collapse logic already handles this correctly on Explorer).
- Explorer with no tags marked "main": behaves exactly as it does today —
  this is strictly additive, not a breaking change to existing workflows.
- Backend neighbor-with-edges call failing mid-expand: same error-surface
  pattern Explorer already uses (`actionError` status strip with a retry-
  friendly message), ported to Investigation.

## Testing

Per `CLAUDE.md`, the full stack (NebulaGraph/backend/Docker) is not run in
this environment — verification against a live graph is the owner's
responsibility on their own machine.

- Backend: extend the existing FastAPI `TestClient` tests (fake
  `GraphClient`, matching current style in `apps/api/tests`) to cover the
  neighbors-with-edges response shape.
- Frontend: the Vite dev server is run standalone in this environment to
  visually confirm rendering, pan/zoom/click/expand/collapse interactions,
  using the page's existing error/loading states (no live backend
  available here) — real end-to-end confirmation against imported data
  happens on the owner's machine.
