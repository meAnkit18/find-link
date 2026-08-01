# Investigation graph: decluttered 2D view, reveal-on-click hierarchy, new 3D view

## Goal

The Investigation page's graph is visually messy and expands too much at
once. Three changes, scoped to Investigation only (Explorer keeps its
current behavior unchanged):

1. **Declutter the existing 2D (Cytoscape) view** — smaller nodes, more
   breathing room between them, and edge-label text (the main source of
   visual noise today) hidden unless relevant.
2. **Reveal-on-click hierarchy** — by default, show only person/company/
   organization ("main") nodes and the edges between them. Clicking a main
   node reveals *that node's own* attribute/sub-nodes (phone, email,
   address, ...) in place. Today, expanding a node dumps every neighbor —
   main and sub — onto the canvas at once, which is the biggest contributor
   to clutter.
3. **New 3D view** — an alternate renderer for the same graph, toggled
   alongside the existing 2D view, useful for visually untangling dense
   clusters that read as a flat hairball in 2D.

## Scope

- `apps/web/src/components/explorer/GraphCanvas.tsx` — restyle only
  (smaller nodes, layout spacing, conditional edge labels). No prop/
  interface changes, so Explorer is unaffected.
- `apps/web/src/pages/InvestigationPage.tsx` — new `revealedVids` state and
  updated click handling; renderer toggle wired to `GraphControls`.
- `apps/web/src/components/explorer/GraphCanvas3D.tsx` — **new**, wraps
  `react-force-graph-3d`, matching `GraphCanvas`'s existing prop contract
  (`nodes`, `edges`, `selectedVid`, `mainTags`, `onSelect`,
  `onToggleExpand`) so `InvestigationPage` can swap between the two without
  branching its own state logic.
- `apps/web/src/components/explorer/GraphControls.tsx` — add a 2D/3D
  toggle button.
- `apps/web/package.json` — new dependency: `react-force-graph-3d`
  (Three.js/WebGL, actively maintained, ~vasturiano/force-graph family —
  the standard choice for React force-directed 3D graphs).
- Out of scope: Explorer page, backend API changes (existing
  `expand_entity_graph`/`expandEntityGraph` already returns everything
  needed — mixed main+sub nodes per hop — no new endpoint required), risk
  scoring, shortest-path, CSV import.

## 1. Decluttering the 2D view

- Node size: main nodes 26px → 18px, sub nodes 15px → 10px; thinner
  borders (2px → 1.5px main, 1px → 1px sub).
- Layout spacing: increase `fcose`'s `nodeRepulsion` and
  `idealEdgeLength` (both the initial-layout and `relayout()` call sites in
  `GraphCanvas.tsx`) so nodes settle further apart instead of overlapping.
- Edge labels are the dominant source of clutter today — every edge
  permanently renders a text box (`label: 'data(edgeType)'` plus a solid
  background). Change: edge label text is hidden by default
  (`'text-opacity': 0` via a base style) and shown only for edges touching
  the selected node, or on hover of that specific edge (a `mouseover`/
  `mouseout` handler setting a `hover` class, mirroring the existing
  `node:selected` selector pattern already in `STYLE`). This keeps
  relationship-label information available on demand without permanently
  cluttering the canvas.
- No changes to interaction primitives (wheel/pan/resize, `pixelRatio`,
  `hideEdgesOnViewport`) — those already work correctly per the prior
  graph-exploration-ux work.

## 2. Reveal-on-click hierarchy (Investigation only)

**New state in `InvestigationPage`:** `revealedVids: Set<string>` —
purely a rendering filter, independent of `expandedVids` (which continues
to track network-fetch state exactly as it does today, unchanged).

**Visibility rule**, computed in the existing `canvasNodes`/`canvasEdges`
`useMemo`s:
- Main nodes (`person`/`company`/`organization`) and edges between two
  main nodes: always visible.
- Sub nodes: visible only if at least one edge connects them to a main
  node that is in `revealedVids`.
- Edges touching a hidden sub node are filtered out along with it (same
  `visibleVids`-based edge filter Explorer already uses in
  `ExplorerPage.visibleEdges`, reused here).

**Click behavior**, replacing `toggleExpand`:
- Click a main node not yet in `revealedVids`: add it to `revealedVids`
  (instant reveal of whatever sub-nodes are already loaded for it — no
  spinner). If it's also not yet in `expandedVids` (i.e. we've never
  fetched its neighborhood — true for any main node reached only as a
  same-hop neighbor, e.g. a second person discovered at depth 2), also
  call the existing `loadEntity(vid, false)` to fetch its neighbors
  (more mains + its subs), same as today's expand.
- Click a main node already in `revealedVids`: remove it from
  `revealedVids` (hide its subs again). Network data already fetched for
  it is *not* discarded — collapsing here is a pure visibility toggle, not
  a data-eviction. This trades a small amount of retained memory for a
  snappier, spinner-free toggle, and matches the "keep expanded nodes
  spatially/data-stable" pattern that avoids the edge-clutter-on-re-expand
  problem.
- Click a sub node: select it only (opens the existing detail panel).
  Sub-nodes are leaves — no expand affordance.
- The root node (the one just searched for) starts **not** revealed —
  its own attributes stay hidden until explicitly clicked, consistent
  with every other main node.
- The right-panel "Expand"/"Collapse" button (`InvestigationPage.tsx`
  lines 241–251) is relabeled "Show details"/"Hide details" for a selected
  main node, and calls the same reveal toggle; hidden entirely when the
  selected node is a sub-node (nothing to expand).

## 3. New 3D view

`GraphCanvas3D` wraps `react-force-graph-3d`:
- Same node/edge data mapped from the same `GraphNode`/`GraphEdge` types —
  no data-layer duplication, only a rendering adapter.
- Node size and color follow the same `mainTags`-derived role and
  `colorForTag` palette as 2D, so switching views doesn't change what
  colors/sizes mean.
- Click handling maps to the same `onSelect`/`onToggleExpand` callbacks —
  reveal-on-click behavior from section 2 is identical in 3D, since it
  lives in `InvestigationPage`, not the canvas component.
- Camera: orbit controls (drag to rotate, scroll to zoom) — the library's
  default, no custom camera logic needed.
- `GraphControls` gets a "2D"/"3D" toggle button; `InvestigationPage` holds
  a `view: '2d' | '3d'` state and renders `GraphCanvas` or `GraphCanvas3D`
  conditionally. Existing controls that don't make sense in 3D (export
  PNG, fullscreen still applies) are left as-is for 2D and a reduced set
  wired for 3D (zoom in/out/fit map to the library's camera API; relayout
  re-runs its force simulation).
- No position caching needed for 3D (the library's own simulation handles
  stable layout across data updates internally, unlike the current 2D
  approach which needs `positionsRef` because Cytoscape has no built-in
  incremental-layout memory).

## Error handling / edge cases

- Switching 2D → 3D → 2D preserves `revealedVids`/`expandedVids`/selection
  — both canvases read from the same `InvestigationPage` state, so nothing
  needs re-fetching or re-computing on toggle.
- A main node with zero sub-nodes in the currently-loaded data: reveal is
  a no-op past adding it to `revealedVids` (nothing renders differently) —
  same "no special-case UI" precedent as the existing empty-expand case.
- 3D view on a machine/browser without WebGL: `react-force-graph-3d` will
  fail to mount; out of scope to add a fallback/detection UI for this pass
  — acceptable given this is an internal investigation tool.

## Testing

Per `CLAUDE.md`, the full stack (NebulaGraph/backend/Docker) is not run in
this environment.

- Frontend only, no backend changes in this pass.
- Vite dev server run standalone in this environment to visually confirm:
  2D node sizing/spacing, edge labels appearing only on hover/selection,
  reveal-on-click showing only the clicked node's own sub-nodes, hide
  toggling back correctly, and the 2D/3D switch rendering the same data
  correctly in both views.
- Real end-to-end confirmation against imported investigation data happens
  on the owner's machine, per existing project convention.
