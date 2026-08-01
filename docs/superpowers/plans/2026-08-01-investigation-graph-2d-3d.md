# Investigation Graph: 2D Declutter + Reveal-on-Click + 3D View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Investigation page's graph so the 2D view is visually clean (smaller nodes, real spacing, no permanent edge-label clutter), the default view shows only person/company/organization nodes with a click-to-reveal mechanism for each node's own attribute sub-nodes, and add a new 3D view as an alternate renderer for the same data.

**Architecture:** Extract the node/edge styling helpers that already exist inside `GraphCanvas.tsx` into a shared `graphStyle.ts` module so both the 2D (Cytoscape) and new 3D (`react-force-graph-3d` / Three.js) renderers stay visually consistent without duplicating logic. Add a pure `computeVisibleGraph` filter function (independently unit-tested) that implements the reveal-on-click visibility rule, consumed by `InvestigationPage` before data reaches either renderer. Both renderers implement the same `GraphCanvasHandle` imperative interface so `InvestigationPage` and `GraphControls` can operate on whichever is currently mounted without branching logic.

**Tech Stack:** React 18 + TypeScript (Bundler module resolution), Cytoscape.js + cytoscape-fcose (existing 2D), new: `react-force-graph-3d` (Three.js/WebGL) for 3D, Vite, new: Vitest for the one piece of pure, worth-testing logic this feature adds.

## Global Constraints

- Per `CLAUDE.md`: do not run NebulaGraph, the backend, or Docker in this environment. Only the frontend (`npm run dev` in `apps/web`) may be run to visually verify UI. Real end-to-end verification against live investigation data happens on the owner's machine.
- Per the design spec (`docs/superpowers/specs/2026-08-01-investigation-graph-2d-3d-design.md`): all behavior changes are scoped to `apps/web/src/pages/InvestigationPage.tsx` and new files. `apps/web/src/pages/ExplorerPage.tsx` must keep its exact current behavior — do not change `GraphCanvas.tsx`'s public props/interface, only its internal styling/layout constants.
- No frontend test framework exists in this repo today. Do not add broad test scaffolding — the one addition (Vitest, Task 4) is scoped narrowly to the new pure `computeVisibleGraph` function, because it's the one piece of new logic complex enough to regress silently. Every other task's verification gate is `tsc -b` + `eslint .` (both already configured) plus a manual dev-server visual check.
- Keep changes as small as possible; follow existing patterns (imperative-handle canvases, ref-based latest-callback pattern already used in `GraphCanvas.tsx` for `onSelectRef`/`onToggleExpandRef`).

---

### Task 1: Extract shared graph styling/data helpers into `graphStyle.ts`

**Files:**
- Create: `apps/web/src/components/explorer/graphStyle.ts`
- Modify: `apps/web/src/components/explorer/GraphCanvas.tsx:1-43` (remove the now-duplicated local definitions, import from the new module instead)

**Interfaces:**
- Produces: `TAG_PALETTE: string[]`, `colorForTag(tag: string): string`, `edgeId(edge: GraphEdge): string`, `type NodeRole = 'main' | 'sub'`, `roleForNode(node: GraphNode, mainTags: Set<string>): NodeRole`, `edgeLabel(edge: GraphEdge): string` — all pure functions, no React/Cytoscape dependency. Tasks 4 and 6 import these.

This is a pure extraction (no behavior change) so `GraphCanvas.tsx` and `ExplorerPage`/`InvestigationPage` render identically before and after — the only automated gate is the type checker and a smoke check that nothing broke.

- [ ] **Step 1: Create `graphStyle.ts` with the extracted helpers**

```typescript
// apps/web/src/components/explorer/graphStyle.ts
import type { GraphEdge, GraphNode } from '../../api/types'

export const TAG_PALETTE = [
  '#2f6feb',
  '#b5720a',
  '#1e8a5f',
  '#a340c9',
  '#c23b32',
  '#0f9bab',
]

export function colorForTag(tag: string): string {
  let hash = 0
  for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) >>> 0
  return TAG_PALETTE[hash % TAG_PALETTE.length]
}

export function edgeId(edge: GraphEdge): string {
  return `${edge.src}->${edge.dst}@${edge.edge_type}@${edge.rank}`
}

export type NodeRole = 'main' | 'sub'

/** A node is a "main" hub if `mainTags` is empty (no hierarchy configured —
 * every node renders uniformly) or if it carries at least one of the
 * configured main tags; everything else is a "sub"/attribute node. */
export function roleForNode(node: GraphNode, mainTags: Set<string>): NodeRole {
  if (mainTags.size === 0) return 'main'
  return node.tags.some((t) => mainTags.has(t)) ? 'main' : 'sub'
}

/** Prefer the human-readable relationship label captured at ingestion
 * (stored as the `relationship_type` edge property) over the raw edge
 * type code, e.g. "childhood friend" instead of "RELATED_TO". */
export function edgeLabel(edge: GraphEdge): string {
  const relationshipType = edge.properties?.relationship_type
  if (typeof relationshipType === 'string' && relationshipType.trim()) return relationshipType
  return edge.edge_type
}
```

- [ ] **Step 2: Update `GraphCanvas.tsx` to import from `graphStyle.ts` instead of defining locally**

Remove lines 8–43 of `apps/web/src/components/explorer/GraphCanvas.tsx` (the `TAG_PALETTE` const, `colorForTag`, `edgeId`, `roleForNode`, `edgeLabel` function definitions) and replace the top of the file with:

```typescript
import { useEffect, useImperativeHandle, useRef, forwardRef, useCallback } from 'react'
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { GraphEdge, GraphNode } from '../../api/types'
import { colorForTag, edgeId, edgeLabel, roleForNode } from './graphStyle'

cytoscape.use(fcose)
```

Everything below (the `STYLE` array, `ensureGraphVisible`, the component body) stays exactly as-is — it already calls `colorForTag`, `roleForNode`, `edgeId`, `edgeLabel` by name, which now resolve to the imported versions.

- [ ] **Step 3: Verify the extraction didn't change behavior**

Run: `cd apps/web && npx tsc -b && npx eslint .`
Expected: both commands exit 0 with no errors (no unused imports, no type errors).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/explorer/graphStyle.ts apps/web/src/components/explorer/GraphCanvas.tsx
git commit -m "refactor: extract graph styling helpers from GraphCanvas into graphStyle.ts"
```

---

### Task 2: Declutter the 2D view — smaller nodes, real spacing

**Files:**
- Modify: `apps/web/src/components/explorer/GraphCanvas.tsx` (the `STYLE` array around line 45-96, and the two `fcose` layout option blocks in the imperative `relayout` handle and the data-sync `useEffect`, originally around lines 216-229 and 308-320 pre-Task-1 numbering — re-check exact line numbers after Task 1's edit before editing)

**Interfaces:**
- Consumes: nothing new.
- Produces: a shared `FCOSE_LAYOUT_BASE` constant used by both layout call sites (removes the existing duplication between `relayout()` and the data-sync effect).

- [ ] **Step 1: Shrink node sizes and thin borders in `STYLE`**

In the `node` selector's style block, change:
```typescript
      width: 26,
      height: 26,
      'border-width': 2,
```
to:
```typescript
      width: 18,
      height: 18,
      'border-width': 1.5,
```

In the `node[role = "sub"]` selector's style block, change:
```typescript
      width: 15,
      height: 15,
      'font-size': 8,
      'border-width': 1,
      opacity: 0.8,
```
to:
```typescript
      width: 10,
      height: 10,
      'font-size': 8,
      'border-width': 1,
      opacity: 0.75,
```

- [ ] **Step 2: Add a shared `FCOSE_LAYOUT_BASE` constant and widen spacing**

Above the `GraphCanvas` component definition (after the `ensureGraphVisible` function, before `export interface GraphCanvasHandle`), add:

```typescript
/** Shared fcose tuning for both the initial/incremental layout (data-sync
 * effect) and the manual "re-run layout" control — kept in one place so the
 * two call sites can't drift out of sync. Wider spacing than fcose's
 * defaults so nodes don't visually overlap once there are more than a
 * handful on screen. */
const FCOSE_LAYOUT_BASE = {
  name: 'fcose',
  animate: false,
  quality: 'draft',
  fit: false,
  nodeRepulsion: 12000,
  idealEdgeLength: 130,
} as unknown as cytoscape.LayoutOptions
```

Then in the imperative handle's `relayout`, replace:
```typescript
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
```
with:
```typescript
      relayout: () => {
        const cy = cyRef.current
        if (!cy) return
        cy.layout({ ...FCOSE_LAYOUT_BASE, randomize: false }).run()
      },
```

And in the data-sync `useEffect`'s layout block, replace:
```typescript
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
```
with:
```typescript
      const layout = cy.layout({ ...FCOSE_LAYOUT_BASE, randomize: !hadNodesBefore })
```

- [ ] **Step 3: Verify**

Run: `cd apps/web && npx tsc -b && npx eslint .`
Expected: both exit 0.

Run: `cd apps/web && npm run dev` (leave running), then use the browser to open `http://localhost:5173/` and confirm the app boots with no console errors. Full visual confirmation of node spacing requires real graph data (a running backend), which per the Global Constraints isn't available here — note in the commit/PR description that spacing needs a final visual check on the owner's machine.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/explorer/GraphCanvas.tsx
git commit -m "style: shrink graph nodes and widen fcose spacing to declutter the canvas"
```

---

### Task 3: Hide edge labels except on hover/selection

**Files:**
- Modify: `apps/web/src/components/explorer/GraphCanvas.tsx` (the `edge` selector in `STYLE`, and the Cytoscape init `useEffect` where `tap`/`dragfree` handlers are already registered; the `selectedVid` sync `useEffect`)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new (internal-only Cytoscape classes `edge-hover` / `edge-highlight`).

- [ ] **Step 1: Hide edge label text by default, reveal via two new classes**

Replace the `edge` selector's style block:
```typescript
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
```
with:
```typescript
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
      'text-background-opacity': 0,
      'text-background-padding': '2px',
      'text-opacity': 0,
    },
  },
  {
    // Relationship labels are only shown on demand (hover, or touching the
    // selected node) — permanently-visible edge labels were the biggest
    // source of visual clutter on any graph with more than a few edges.
    selector: 'edge.edge-hover, edge.edge-highlight',
    style: {
      'text-opacity': 1,
      'text-background-opacity': 0.85,
    },
  },
```

- [ ] **Step 2: Wire hover handlers in the Cytoscape init effect**

In `GraphCanvas.tsx`'s main `useEffect` (the one that creates `cy` and registers `cy.on('tap', ...)` / `cy.on('dragfree', ...)`), add, right after the existing `cy.on('dragfree', 'node', ...)` registration:

```typescript
    cy.on('mouseover', 'edge', (evt) => evt.target.addClass('edge-hover'))
    cy.on('mouseout', 'edge', (evt) => evt.target.removeClass('edge-hover'))
```

- [ ] **Step 3: Highlight edges touching the selected node**

In the `useEffect` that syncs `selectedVid` (the one containing `cy.nodes().unselect()` / `cy.getElementById(selectedVid).select()`), extend it to:

```typescript
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes().unselect()
    cy.edges().removeClass('edge-highlight')
    if (selectedVid) {
      const node = cy.getElementById(selectedVid)
      node.select()
      node.connectedEdges().addClass('edge-highlight')
    }
  }, [selectedVid])
```

- [ ] **Step 4: Verify**

Run: `cd apps/web && npx tsc -b && npx eslint .`
Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/explorer/GraphCanvas.tsx
git commit -m "style: hide edge relationship labels until hover or selection"
```

---

### Task 4: Reveal-on-click visibility logic (`computeVisibleGraph`) + Vitest setup

**Files:**
- Create: `apps/web/src/components/explorer/graphVisibility.ts`
- Create: `apps/web/src/components/explorer/graphVisibility.test.ts`
- Modify: `apps/web/package.json` (add `vitest` devDependency + `test` script)
- Modify: `apps/web/vite.config.ts` (add a `test` block for Vitest)

**Interfaces:**
- Consumes: `GraphNode`, `GraphEdge` (from `../../api/types`), `roleForNode` (from `./graphStyle`, Task 1).
- Produces: `computeVisibleGraph(nodes: GraphNode[], edges: GraphEdge[], mainTags: Set<string>, revealedVids: Set<string>): { visibleNodes: GraphNode[]; visibleEdges: GraphEdge[] }` — consumed by Task 5 (`InvestigationPage.tsx`).

- [ ] **Step 1: Add Vitest to the project**

Modify `apps/web/package.json`: add to `"scripts"`:
```json
    "test": "vitest run",
```
and to `"devDependencies"`:
```json
    "vitest": "^2.1.4",
```

Modify `apps/web/vite.config.ts` to add a `test` block (Vitest reads its config from the same file):

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Dev-only convenience: talk to the FastAPI backend (run separately,
      // e.g. `uvicorn graph_explorer_api.main:app --port 8000`) without CORS
      // friction. Production deploys serve web + api behind the same origin
      // or set VITE_API_BASE_URL instead.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'node',
  },
})
```

Run: `cd apps/web && npm install`
Expected: installs `vitest` with no errors.

- [ ] **Step 2: Write the failing test**

```typescript
// apps/web/src/components/explorer/graphVisibility.test.ts
import { describe, expect, it } from 'vitest'
import type { GraphEdge, GraphNode } from '../../api/types'
import { computeVisibleGraph } from './graphVisibility'

const mainTags = new Set(['person'])

function node(vid: string, tags: string[]): GraphNode {
  return { vid, tags, label: vid, properties: {} }
}

function edge(src: string, dst: string): GraphEdge {
  return { src, dst, edge_type: 'HAS_PHONE', rank: 0, properties: {} }
}

describe('computeVisibleGraph', () => {
  it('shows only main nodes and main-to-main edges by default', () => {
    const nodes = [node('alice', ['person']), node('bob', ['person']), node('alice-phone', ['phone'])]
    const edges = [edge('alice', 'bob'), edge('alice', 'alice-phone')]

    const { visibleNodes, visibleEdges } = computeVisibleGraph(nodes, edges, mainTags, new Set())

    expect(visibleNodes.map((n) => n.vid).sort()).toEqual(['alice', 'bob'])
    expect(visibleEdges).toHaveLength(1)
    expect(visibleEdges[0]).toMatchObject({ src: 'alice', dst: 'bob' })
  })

  it("reveals a main node's own sub nodes once that node is revealed", () => {
    const nodes = [node('alice', ['person']), node('bob', ['person']), node('alice-phone', ['phone'])]
    const edges = [edge('alice', 'bob'), edge('alice', 'alice-phone')]

    const { visibleNodes, visibleEdges } = computeVisibleGraph(nodes, edges, mainTags, new Set(['alice']))

    expect(visibleNodes.map((n) => n.vid).sort()).toEqual(['alice', 'alice-phone', 'bob'])
    expect(visibleEdges).toHaveLength(2)
  })

  it("does not reveal a different main node's sub nodes", () => {
    const nodes = [node('alice', ['person']), node('bob', ['person']), node('bob-email', ['email'])]
    const edges = [edge('alice', 'bob'), edge('bob', 'bob-email')]

    const { visibleNodes } = computeVisibleGraph(nodes, edges, mainTags, new Set(['alice']))

    expect(visibleNodes.map((n) => n.vid).sort()).toEqual(['alice', 'bob'])
  })

  it('keeps a sub node shared by two main nodes visible if either is revealed', () => {
    const nodes = [node('alice', ['person']), node('bob', ['person']), node('shared-phone', ['phone'])]
    const edges = [edge('alice', 'bob'), edge('alice', 'shared-phone'), edge('bob', 'shared-phone')]

    const { visibleNodes } = computeVisibleGraph(nodes, edges, mainTags, new Set(['bob']))

    expect(visibleNodes.map((n) => n.vid).sort()).toEqual(['alice', 'bob', 'shared-phone'])
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd apps/web && npx vitest run graphVisibility`
Expected: FAIL — `graphVisibility.ts` doesn't exist yet (`Cannot find module './graphVisibility'` or similar).

- [ ] **Step 4: Implement `computeVisibleGraph`**

```typescript
// apps/web/src/components/explorer/graphVisibility.ts
import type { GraphEdge, GraphNode } from '../../api/types'
import { roleForNode } from './graphStyle'

export interface VisibleGraph {
  visibleNodes: GraphNode[]
  visibleEdges: GraphEdge[]
}

/** Investigation's reveal-on-click hierarchy: main nodes (person/company/
 * organization) and edges between two main nodes are always visible. A
 * sub/attribute node (phone, email, address, ...) is visible only once at
 * least one main node it's directly connected to has been "revealed" —
 * every main node, including the initially searched one, starts collapsed,
 * so attribute clutter never appears until the user asks for it. */
export function computeVisibleGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  mainTags: Set<string>,
  revealedVids: Set<string>,
): VisibleGraph {
  const roleByVid = new Map(nodes.map((n) => [n.vid, roleForNode(n, mainTags)]))

  const subVisible = new Set<string>()
  for (const edge of edges) {
    const srcRole = roleByVid.get(edge.src)
    const dstRole = roleByVid.get(edge.dst)
    if (srcRole === 'sub' && dstRole === 'main' && revealedVids.has(edge.dst)) {
      subVisible.add(edge.src)
    }
    if (dstRole === 'sub' && srcRole === 'main' && revealedVids.has(edge.src)) {
      subVisible.add(edge.dst)
    }
  }

  const visibleNodes = nodes.filter((n) => roleByVid.get(n.vid) === 'main' || subVisible.has(n.vid))
  const visibleVids = new Set(visibleNodes.map((n) => n.vid))
  const visibleEdges = edges.filter((e) => visibleVids.has(e.src) && visibleVids.has(e.dst))

  return { visibleNodes, visibleEdges }
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd apps/web && npx vitest run graphVisibility`
Expected: PASS — 4 tests passing.

- [ ] **Step 6: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/vite.config.ts apps/web/src/components/explorer/graphVisibility.ts apps/web/src/components/explorer/graphVisibility.test.ts
git commit -m "feat: add computeVisibleGraph reveal-on-click filter with Vitest coverage"
```

---

### Task 5: Wire reveal-on-click into `InvestigationPage`

**Files:**
- Modify: `apps/web/src/pages/InvestigationPage.tsx`

**Interfaces:**
- Consumes: `computeVisibleGraph` (Task 4), `roleForNode` (Task 1).
- Produces: `toggleReveal(vid: string): void` (replaces the page's current `toggleExpand`; passed as `onToggleExpand` to whichever canvas is mounted in Task 7).

- [ ] **Step 1: Add the `revealedVids` state and imports**

At the top of `InvestigationPage.tsx`, add to the existing imports:
```typescript
import { roleForNode } from '../components/explorer/graphStyle'
import { computeVisibleGraph } from '../components/explorer/graphVisibility'
```

Add alongside the existing `expandedVids`/`expandingVids` state declarations:
```typescript
  const [revealedVids, setRevealedVids] = useState<Set<string>>(new Set())
```

- [ ] **Step 2: Replace `collapseEntity` + `toggleExpand` with `toggleReveal`**

Remove the existing `collapseEntity` and `toggleExpand` functions:
```typescript
  function collapseEntity(entityId: string) {
    graphState.collapse(entityId)
    setExpandedVids((prev) => {
      const next = new Set(prev)
      next.delete(entityId)
      return next
    })
  }

  function toggleExpand(vid: string) {
    if (expandingVids.has(vid)) return
    if (expandedVids.has(vid)) collapseEntity(vid)
    else void loadEntity(vid, false)
  }
```

Replace with:
```typescript
  function nodeRole(vid: string): 'main' | 'sub' {
    const node = graphState.nodes.get(vid)
    if (!node) return 'sub'
    return roleForNode(node, MAIN_TAGS)
  }

  /** Reveal (or hide) a main node's own already-loaded sub-nodes — a pure,
   * instant visibility toggle, decoupled from network fetching. The first
   * time a main node is revealed, if we've never fetched its neighborhood
   * (true for any main node discovered only as someone else's neighbor),
   * also fetch it so there's something to reveal. Hiding never discards
   * fetched data — re-revealing is instant, no spinner. Sub nodes have no
   * expand affordance; clicking one is select-only. */
  function toggleReveal(vid: string) {
    if (nodeRole(vid) !== 'main') return
    const alreadyRevealed = revealedVids.has(vid)
    setRevealedVids((prev) => {
      const next = new Set(prev)
      if (alreadyRevealed) next.delete(vid)
      else next.add(vid)
      return next
    })
    if (!alreadyRevealed && !expandedVids.has(vid)) {
      void loadEntity(vid, false)
    }
  }
```

- [ ] **Step 3: Filter canvas data through `computeVisibleGraph`**

Replace:
```typescript
  const selectedNode = selectedVid ? graphState.nodes.get(selectedVid) ?? null : null
  const canvasNodes = useMemo(() => Array.from(graphState.nodes.values()), [graphState.nodes])
  const canvasEdges = useMemo(() => Array.from(graphState.edges.values()), [graphState.edges])
```
with:
```typescript
  const selectedNode = selectedVid ? graphState.nodes.get(selectedVid) ?? null : null
  const { visibleNodes: canvasNodes, visibleEdges: canvasEdges } = useMemo(
    () =>
      computeVisibleGraph(
        Array.from(graphState.nodes.values()),
        Array.from(graphState.edges.values()),
        MAIN_TAGS,
        revealedVids,
      ),
    [graphState.nodes, graphState.edges, revealedVids],
  )
```

- [ ] **Step 4: Update `GraphCanvas`'s `onToggleExpand` prop and the right-panel button**

In the JSX, change:
```typescript
            onToggleExpand={toggleExpand}
```
to:
```typescript
            onToggleExpand={toggleReveal}
```

Replace the right-panel Expand/Collapse button block:
```typescript
                <button
                  className="btn btn--primary"
                  onClick={() => toggleExpand(selectedNode.vid)}
                  disabled={expandingVids.has(selectedNode.vid)}
                >
                  {expandingVids.has(selectedNode.vid)
                    ? 'Expanding…'
                    : expandedVids.has(selectedNode.vid)
                      ? 'Collapse'
                      : 'Expand'}
                </button>
                <InfoTooltip text="Load everyone and everything directly connected to this node onto the graph, or collapse it back." />
```
with:
```typescript
                {nodeRole(selectedNode.vid) === 'main' && (
                  <>
                    <button
                      className="btn btn--primary"
                      onClick={() => toggleReveal(selectedNode.vid)}
                      disabled={expandingVids.has(selectedNode.vid)}
                    >
                      {expandingVids.has(selectedNode.vid)
                        ? 'Loading…'
                        : revealedVids.has(selectedNode.vid)
                          ? 'Hide details'
                          : 'Show details'}
                    </button>
                    <InfoTooltip text="Reveal or hide this person's or company's own attribute nodes (phone, email, address, ...) on the canvas." />
                  </>
                )}
```

- [ ] **Step 5: Verify**

Run: `cd apps/web && npx tsc -b && npx eslint .`
Expected: both exit 0 — this also confirms nothing else in the file still references the removed `toggleExpand`/`collapseEntity`.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/pages/InvestigationPage.tsx
git commit -m "feat: default Investigation graph to main nodes only, reveal sub-nodes on click"
```

---

### Task 6: New 3D view (`GraphCanvas3D`)

**Files:**
- Modify: `apps/web/package.json` (add `react-force-graph-3d` + `three` dependencies)
- Create: `apps/web/src/components/explorer/GraphCanvas3D.tsx`

**Interfaces:**
- Consumes: `GraphCanvasHandle` (type, from `./GraphCanvas`, Task 1 unaffected), `colorForTag`, `edgeLabel`, `roleForNode` (from `./graphStyle`, Task 1).
- Produces: default export `GraphCanvas3D`, a `forwardRef<GraphCanvasHandle, Props>` component with the same `Props` shape as `GraphCanvas` (minus `onZoomChange`, which 3D has no equivalent event for) — consumed by Task 7 (`InvestigationPage.tsx`).

- [ ] **Step 1: Add dependencies**

Modify `apps/web/package.json`, add to `"dependencies"`:
```json
    "react-force-graph-3d": "^1.29.1",
    "three": "^0.179.0",
```

Run: `cd apps/web && npm install`
Expected: installs with no errors.

- [ ] **Step 2: Write `GraphCanvas3D.tsx`**

```typescript
// apps/web/src/components/explorer/GraphCanvas3D.tsx
import { forwardRef, useImperativeHandle, useMemo, useRef } from 'react'
import ForceGraph3D, { type ForceGraphMethods } from 'react-force-graph-3d'
import type { GraphEdge, GraphNode } from '../../api/types'
import { colorForTag, edgeLabel, roleForNode } from './graphStyle'
import type { GraphCanvasHandle } from './GraphCanvas'

interface Node3D {
  id: string
  label: string
  color: string
  val: number
}

interface Link3D {
  source: string
  target: string
  label: string
}

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedVid: string | null
  mainTags: Set<string>
  onSelect: (vid: string | null) => void
  onToggleExpand: (vid: string) => void
}

const GraphCanvas3D = forwardRef<GraphCanvasHandle, Props>(function GraphCanvas3D(
  { nodes, edges, selectedVid, mainTags, onSelect, onToggleExpand },
  ref,
) {
  const fgRef = useRef<ForceGraphMethods<Node3D, Link3D>>()
  const selectedVidRef = useRef(selectedVid)
  selectedVidRef.current = selectedVid

  const graphData = useMemo(() => {
    const graphNodes: Node3D[] = nodes.map((n) => ({
      id: n.vid,
      label: n.label,
      color: colorForTag(n.tags[0] ?? 'entity'),
      val: roleForNode(n, mainTags) === 'main' ? 6 : 2,
    }))
    const graphLinks: Link3D[] = edges.map((e) => ({
      source: e.src,
      target: e.dst,
      label: edgeLabel(e),
    }))
    return { nodes: graphNodes, links: graphLinks }
  }, [nodes, edges, mainTags])

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => {
        const fg = fgRef.current
        if (!fg) return
        const { x, y, z } = fg.camera().position
        fg.cameraPosition({ x: x * 0.8, y: y * 0.8, z: z * 0.8 }, undefined, 300)
      },
      zoomOut: () => {
        const fg = fgRef.current
        if (!fg) return
        const { x, y, z } = fg.camera().position
        fg.cameraPosition({ x: x * 1.25, y: y * 1.25, z: z * 1.25 }, undefined, 300)
      },
      fit: () => {
        fgRef.current?.zoomToFit(400, 40)
      },
      centerSelected: () => {
        const vid = selectedVidRef.current
        if (!vid) return
        fgRef.current?.zoomToFit(400, 80, (node) => node.id === vid)
      },
      relayout: () => {
        fgRef.current?.d3ReheatSimulation()
      },
      exportPng: () => {
        const fg = fgRef.current
        if (!fg) return
        const url = fg.renderer().domElement.toDataURL('image/png')
        const a = document.createElement('a')
        a.href = url
        a.download = 'graph-3d.png'
        a.click()
      },
    }),
    [],
  )

  return (
    <ForceGraph3D<Node3D, Link3D>
      ref={fgRef}
      graphData={graphData}
      backgroundColor="#11141a"
      rendererConfig={{ preserveDrawingBuffer: true }}
      nodeId="id"
      nodeLabel="label"
      nodeColor={(node) => (node.id === selectedVid ? '#ffffff' : node.color)}
      nodeVal="val"
      nodeRelSize={4}
      linkColor={() => '#5b6472'}
      linkLabel="label"
      linkDirectionalArrowLength={3}
      linkDirectionalArrowRelPos={1}
      onNodeClick={(node) => {
        if (typeof node.id !== 'string') return
        onSelect(node.id)
        onToggleExpand(node.id)
      }}
      onBackgroundClick={() => onSelect(null)}
    />
  )
})

export default GraphCanvas3D
```

- [ ] **Step 3: Verify**

Run: `cd apps/web && npx tsc -b && npx eslint .`
Expected: both exit 0. If `tsc` reports it cannot find type declarations for `three/examples/jsm/postprocessing/EffectComposer.js` (pulled in transitively by `react-force-graph-3d`'s own `.d.ts`), this is expected to be suppressed by the project's existing `skipLibCheck: true` (`tsconfig.app.json`) — if it still surfaces, it means `skipLibCheck` isn't covering a top-level import in *our* file specifically, in which case double check `GraphCanvas3D.tsx` only imports `ForceGraph3D` and the `ForceGraphMethods` type from `react-force-graph-3d` (not from `three` directly), matching the code above.

- [ ] **Step 4: Commit**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/src/components/explorer/GraphCanvas3D.tsx
git commit -m "feat: add GraphCanvas3D, a Three.js-based 3D renderer for the graph canvas"
```

---

### Task 7: 2D/3D toggle in `GraphControls`, wired into `InvestigationPage`

**Files:**
- Modify: `apps/web/src/components/explorer/GraphControls.tsx`
- Modify: `apps/web/src/index.css` (button active-state styling, ~line 766-789 `.graph-controls__btn` block)
- Modify: `apps/web/src/pages/InvestigationPage.tsx`

**Interfaces:**
- Consumes: `GraphCanvas3D` (Task 6), `computeVisibleGraph`/`toggleReveal` (Task 5, unchanged).
- Produces: nothing consumed by later tasks (this is the last integration point).

- [ ] **Step 1: Add the view toggle to `GraphControls`**

In `apps/web/src/components/explorer/GraphControls.tsx`, add to `Props`:
```typescript
  view: '2d' | '3d'
  onToggleView: () => void
```
and destructure them in the function signature alongside the existing props.

Add a new button right after the opening `<div className="graph-controls" ...>` info-tooltip row and its divider (i.e. as the first button in the toolbar):
```tsx
        <button
          className="graph-controls__btn"
          title={view === '2d' ? 'Switch to 3D view' : 'Switch to 2D view'}
          onClick={onToggleView}
        >
          {view === '2d' ? '3D' : '2D'}
        </button>
        <div className="graph-controls__divider" />
```

Change the zoom indicator to only render in 2D (3D has no equivalent live zoom-percent signal):
```tsx
      {view === '2d' && (
        <div className="graph-zoom-indicator" aria-live="polite">
          {Math.round(zoom * 100)}%
        </div>
      )}
```

- [ ] **Step 2: Add a text-button style variant so "3D"/"2D" reads clearly next to the icon buttons**

In `apps/web/src/index.css`, after the existing `.graph-controls__btn` block, add:
```css
.graph-controls__btn--label {
  width: auto;
  padding: 0 var(--space-2);
  font-size: 11px;
  font-weight: 600;
}
```
Then in `GraphControls.tsx`, give the new toggle button both classes:
```tsx
          className="graph-controls__btn graph-controls__btn--label"
```

- [ ] **Step 3: Wire the toggle into `InvestigationPage`**

Add the necessary imports at the top of `InvestigationPage.tsx`:
```typescript
import GraphCanvas3D from '../components/explorer/GraphCanvas3D'
```

Add view state and a second ref alongside the existing `canvasRef`:
```typescript
  const [view, setView] = useState<'2d' | '3d'>('2d')
  const canvas2DRef = useRef<GraphCanvasHandle>(null)
  const canvas3DRef = useRef<GraphCanvasHandle>(null)

  function activeCanvas(): GraphCanvasHandle | null {
    return view === '2d' ? canvas2DRef.current : canvas3DRef.current
  }
```
(remove the old single `const canvasRef = useRef<GraphCanvasHandle>(null)` declaration — it's replaced by the two above.)

Replace the `<GraphCanvas ... />` element and the `<GraphControls ... />` element with:
```tsx
          {view === '2d' ? (
            <GraphCanvas
              ref={canvas2DRef}
              nodes={canvasNodes}
              edges={canvasEdges}
              selectedVid={selectedVid}
              mainTags={MAIN_TAGS}
              onSelect={setSelectedVid}
              onToggleExpand={toggleReveal}
              onZoomChange={setZoom}
            />
          ) : (
            <GraphCanvas3D
              ref={canvas3DRef}
              nodes={canvasNodes}
              edges={canvasEdges}
              selectedVid={selectedVid}
              mainTags={MAIN_TAGS}
              onSelect={setSelectedVid}
              onToggleExpand={toggleReveal}
            />
          )}
          <GraphControls
            view={view}
            onToggleView={() => setView((v) => (v === '2d' ? '3d' : '2d'))}
            onZoomIn={() => activeCanvas()?.zoomIn()}
            onZoomOut={() => activeCanvas()?.zoomOut()}
            onFit={() => activeCanvas()?.fit()}
            onCenterSelected={() => activeCanvas()?.centerSelected()}
            onRelayout={() => activeCanvas()?.relayout()}
            onExportPng={() => activeCanvas()?.exportPng()}
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
```

- [ ] **Step 4: Verify**

Run: `cd apps/web && npx tsc -b && npx eslint .`
Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/explorer/GraphControls.tsx apps/web/src/index.css apps/web/src/pages/InvestigationPage.tsx
git commit -m "feat: add 2D/3D toggle to the Investigation graph controls"
```

---

### Task 8: Full-repo verification pass

**Files:** none (verification only).

- [ ] **Step 1: Type-check and lint the whole frontend**

Run: `cd apps/web && npx tsc -b && npx eslint .`
Expected: both exit 0.

- [ ] **Step 2: Run the new unit tests**

Run: `cd apps/web && npx vitest run`
Expected: all `graphVisibility.test.ts` tests pass.

- [ ] **Step 3: Production build**

Run: `cd apps/web && npm run build`
Expected: exits 0, produces `dist/`.

- [ ] **Step 4: Manual dev-server smoke test**

Run: `cd apps/web && npm run dev`, open the Investigation page in a browser. Since no backend is available in this environment, confirm structurally rather than with real data:
- The page loads with no console errors.
- The 2D/3D toggle button renders in the graph controls and clicking it swaps the rendered canvas (Cytoscape ↔ WebGL) without a crash — with no data loaded yet, both should just show an empty canvas.
- The zoom-percent indicator is visible in 2D and hidden in 3D.

Note in the final summary to the user: interactive verification of the reveal-on-click hierarchy, real 2D spacing/label behavior, and 3D rendering with actual investigation data all require the owner's machine (backend + NebulaGraph), per `CLAUDE.md`.

- [ ] **Step 5: Push the branch**

Do not push automatically — confirm with the user first, per this project's established git workflow (`origin` needs the SSH deploy key noted in `CLAUDE.md`).
