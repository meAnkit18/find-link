import { useEffect, useImperativeHandle, useMemo, useRef, useState, forwardRef, useCallback } from 'react'
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { GraphEdge, GraphNode } from '../../api/types'
import { EDGE_COLOR, SELECT_COLOR, colorForTag, edgeId, edgeLabel, edgeWeight, roleForNode } from './graphStyle'
import GraphPopup, { type GraphPopupInfo } from './GraphPopup'

cytoscape.use(fcose)

// Same gradient stops as kindred-main's SVG `bgGlow` radial gradient, ported
// to a plain CSS background since cytoscape's canvas itself stays transparent.
const CANVAS_BG = 'radial-gradient(65% 65% at 50% 45%, #0b1220 0%, #020617 100%)'

const STYLE: StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      'background-color': (ele: cytoscape.NodeSingular) => colorForTag(ele.data('tag')),
      label: 'data(label)',
      color: '#cbd5e1',
      'font-size': 10,
      'text-valign': 'bottom',
      'text-margin-y': 6,
      width: 18,
      height: 18,
      'border-width': 1.5,
      'border-color': 'rgba(255, 255, 255, 0.35)',
      'text-outline-width': 2,
      'text-outline-color': '#05070d',
    },
  },
  {
    // Attribute/sub nodes (phone, email, address, ...) render smaller and
    // muted, so hub-vs-attribute reads at a glance without reading labels.
    selector: 'node[role = "sub"]',
    style: {
      width: 10,
      height: 10,
      'font-size': 8,
      'border-width': 1,
      opacity: 0.75,
    },
  },
  {
    // Hub nodes carry a soft tag-colored halo (cytoscape's built-in overlay,
    // standing in for kindred's SVG blur filter glow).
    selector: 'node[role = "main"]',
    style: {
      'overlay-color': (ele) => colorForTag(ele.data('tag')),
      'overlay-opacity': 0.22,
      'overlay-padding': 10,
    },
  },
  {
    selector: 'node:selected',
    style: {
      'border-color': SELECT_COLOR,
      'border-width': 3,
      'overlay-color': SELECT_COLOR,
      'overlay-opacity': 0.38,
      'overlay-padding': 12,
    },
  },
  {
    selector: 'edge',
    style: {
      // Investigation's person links carry a `weight` (how many separate
      // things two people share), so an overlap of three details reads as
      // visibly stronger than a single shared email. Everything else has
      // weight 1 and renders exactly as it always did.
      width: (ele: cytoscape.EdgeSingular) => 1.5 + Math.min(Number(ele.data('weight')) || 1, 5) - 1,
      'line-color': 'rgba(148, 163, 184, 0.45)',
      'target-arrow-color': 'rgba(148, 163, 184, 0.6)',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.8,
      'curve-style': 'bezier',
      label: 'data(edgeType)',
      'font-size': 8,
      color: '#94a3b8',
      'text-background-color': '#0a0e16',
      'text-background-opacity': 0,
      'text-background-padding': '2px',
      'text-opacity': 0,
    },
  },
  {
    // A person-to-attribute spoke is structure, not a finding: it should
    // recede so the person-to-person links stay the thing you read first.
    selector: 'edge.edge-spoke',
    style: {
      width: 1,
      'line-color': 'rgba(148, 163, 184, 0.22)',
      'line-style': 'dashed',
      'target-arrow-shape': 'none',
    },
  },
  {
    // Relationship labels are only shown on demand (hover, or touching the
    // selected node) — permanently-visible edge labels were the biggest
    // source of visual clutter on any graph with more than a few edges.
    selector: 'edge.edge-hover, edge.edge-highlight',
    style: {
      'line-color': SELECT_COLOR,
      'target-arrow-color': SELECT_COLOR,
      width: 2,
      'text-opacity': 1,
      'text-background-opacity': 0.85,
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

/** Shared fcose tuning for both the initial/incremental layout (data-sync
 * effect) and the manual "re-run layout" control — kept in one place so the
 * two call sites can't drift out of sync. Wider spacing than fcose's
 * defaults so nodes don't visually overlap once there are more than a
 * handful on screen.
 *
 * quality must track randomize: fcose only supports `randomize: false` with
 * quality "default"/"proof" (see its own README and the console warning it
 * logs for this exact combination) — pairing "draft" quality with
 * `randomize: false` makes it throw inside relocateComponent(), because
 * spectralResult is never populated when randomize is off. "draft" is fine,
 * and fast, for the initial full-graph layout (randomize: true); incremental
 * layouts that keep already-placed nodes fixed (every reveal/expand click
 * after the first render) need "default" instead. */
function fcoseLayoutOptions(randomize: boolean) {
  return {
    name: 'fcose',
    animate: false,
    quality: randomize ? 'draft' : 'default',
    fit: false,
    nodeRepulsion: 12000,
    idealEdgeLength: 130,
    randomize,
  }
}

/** Run the force layout over the nodes that are free to move, leaving
 * pinned ones (Investigation's radially-placed attribute rings) exactly
 * where the caller put them. With nothing pinned this is the whole graph,
 * i.e. identical to `cy.layout(...)`. */
function layoutFreeNodes(cy: Core, pinned: Map<string, cytoscape.Position>, randomize: boolean) {
  const free = pinned.size === 0 ? cy.nodes() : cy.nodes().filter((ele) => !pinned.has(ele.id()))
  const elements = free.union(free.edgesWith(free))
  // fcose's options (animate/randomize/nodeRepulsion/...) aren't part of
  // @types/cytoscape's built-in layout typings, hence the cast.
  return elements.layout(fcoseLayoutOptions(randomize) as unknown as cytoscape.LayoutOptions)
}

/** Move pinned nodes onto their given positions and lock them, so neither
 * the force layout nor a stray drag can pull an attribute out of its ring. */
function applyPinnedPositions(cy: Core, pinned: Map<string, cytoscape.Position>) {
  cy.batch(() => {
    for (const [id, position] of pinned) {
      const ele = cy.getElementById(id)
      if (ele.empty()) continue
      ele.unlock()
      ele.position({ ...position })
      ele.lock()
    }
  })
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
  /** Nodes the caller places itself — Investigation's radial attribute
   * rings. These are excluded from the force layout and locked in place.
   * Omit for the default behavior: everything is laid out by fcose. */
  pinnedPositions?: Map<string, cytoscape.Position>
  /** Fired while a hub node is dragged, so a caller pinning children
   * around it can keep the ring centred on its parent. */
  onParentMoved?: (vid: string, position: cytoscape.Position) => void
  /** Fired once the force layout settles, with where every node landed —
   * what a caller needs before it can place anything relative to them. */
  onPositionsSettled?: (positions: Map<string, cytoscape.Position>) => void
}

const GraphCanvas = forwardRef<GraphCanvasHandle, Props>(function GraphCanvas(
  {
    nodes,
    edges,
    selectedVid,
    mainTags,
    onSelect,
    onToggleExpand,
    onZoomChange,
    pinnedPositions,
    onParentMoved,
    onPositionsSettled,
  },
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
  const onParentMovedRef = useRef(onParentMoved)
  const onPositionsSettledRef = useRef(onPositionsSettled)
  onPositionsSettledRef.current = onPositionsSettled
  onSelectRef.current = onSelect
  onToggleExpandRef.current = onToggleExpand
  onParentMovedRef.current = onParentMoved

  const emptyPinned = useMemo(() => new Map<string, cytoscape.Position>(), [])
  const pinnedNodes = pinnedPositions ?? emptyPinned
  // Read by the mount-time event handlers and the imperative relayout(),
  // which both outlive any single render.
  const pinnedPositionsRef = useRef(pinnedNodes)
  pinnedPositionsRef.current = pinnedNodes

  const [popupInfo, setPopupInfo] = useState<GraphPopupInfo | null>(null)
  const [pinned, setPinned] = useState(false)
  const pinnedRef = useRef(pinned)
  pinnedRef.current = pinned
  const closePopup = () => {
    setPinned(false)
    setPopupInfo(null)
  }

  const nodePopupInfo = (ele: cytoscape.NodeSingular): GraphPopupInfo => ({
    kind: 'node',
    label: ele.data('label'),
    tag: ele.data('tag'),
    color: colorForTag(ele.data('tag')),
    role: ele.data('role'),
  })
  const edgePopupInfo = (ele: cytoscape.EdgeSingular): GraphPopupInfo => ({
    kind: 'edge',
    label: ele.data('edgeType'),
    source: ele.source().data('label') ?? ele.data('source'),
    target: ele.target().data('label') ?? ele.data('target'),
    color: EDGE_COLOR,
  })

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
    // It also pins the hover popup, matching kindred's click-to-pin.
    cy.on('tap', 'node', (evt) => {
      const vid = evt.target.id()
      onSelectRef.current(vid)
      onToggleExpandRef.current(vid)
      setPopupInfo(nodePopupInfo(evt.target))
      setPinned(true)
    })
    cy.on('tap', 'edge', (evt) => {
      setPopupInfo(edgePopupInfo(evt.target))
      setPinned(true)
    })
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        onSelectRef.current(null)
        closePopup()
      }
    })
    // Keep the position cache fresh when the user drags nodes around.
    cy.on('dragfree', 'node', (evt) => {
      positionsRef.current.set(evt.target.id(), { ...evt.target.position() })
    })
    // A dragged hub carries its pinned children with it, so an attribute
    // ring stays centred on the person it belongs to.
    cy.on('drag', 'node', (evt) => {
      const notify = onParentMovedRef.current
      if (!notify) return
      const vid = evt.target.id()
      if (pinnedPositionsRef.current.has(vid)) return
      notify(vid, { ...evt.target.position() })
    })
    cy.on('mouseover', 'node', (evt) => {
      if (!pinnedRef.current) setPopupInfo(nodePopupInfo(evt.target))
    })
    cy.on('mouseout', 'node', () => {
      if (!pinnedRef.current) setPopupInfo(null)
    })
    cy.on('mouseover', 'edge', (evt) => {
      evt.target.addClass('edge-hover')
      if (!pinnedRef.current) setPopupInfo(edgePopupInfo(evt.target))
    })
    cy.on('mouseout', 'edge', (evt) => {
      evt.target.removeClass('edge-hover')
      if (!pinnedRef.current) setPopupInfo(null)
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
      zoomIn: () => {
        const cy = cyRef.current
        if (!cy) return
        cy.zoom({ level: cy.zoom() * 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
      },
      zoomOut: () => {
        const cy = cyRef.current
        if (!cy) return
        cy.zoom({ level: cy.zoom() / 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
      },
      fit: () => cyRef.current?.fit(undefined, 40),
      centerSelected: () => cyRef.current?.fit(cyRef.current.$('node:selected'), 40),
      relayout: () => {
        const cy = cyRef.current
        if (!cy) return
        layoutFreeNodes(cy, pinnedPositionsRef.current, false).run()
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
      // A pinned node already has the position the caller wants; it must not
      // count as "brand new", or adding one attribute would re-run the force
      // layout and reshuffle every person on the canvas.
      const placed = pinnedNodes.get(n.vid) ?? positionsRef.current.get(n.vid)
      if (!placed) brandNewCount++
      newNodeEles.push({
        data: { id: n.vid, label: n.label, tag: n.tags[0] ?? 'entity', role: roleForNode(n, mainTags) },
        ...(placed ? { position: { ...placed } } : {}),
      })
    }

    const newEdgeEles: ElementDefinition[] = edges
      .filter((e) => cy.getElementById(edgeId(e)).empty())
      .map((e) => ({
        data: {
          id: edgeId(e),
          source: e.src,
          target: e.dst,
          edgeType: edgeLabel(e),
          weight: edgeWeight(e),
        },
        ...(pinnedNodes.has(e.src) || pinnedNodes.has(e.dst) ? { classes: 'edge-spoke' } : {}),
      }))

    cy.add([...newNodeEles, ...newEdgeEles])

    // Keep already-visible nodes' main/sub role in sync when mainTags
    // changes (e.g. the user just marked a tag as main), and already-visible
    // edges' labels in sync when a later expansion brings back the real
    // relationship_type for an edge that was first added without one (e.g.
    // from /overview) — without touching anything else about them, and
    // without writing when the value hasn't actually changed (Cytoscape's
    // data setter forces a style recalculation on every call).
    for (const n of nodes) {
      const ele = cy.getElementById(n.vid)
      if (ele.empty()) continue
      const role = roleForNode(n, mainTags)
      if (ele.data('role') !== role) ele.data('role', role)
    }
    for (const e of edges) {
      const ele = cy.getElementById(edgeId(e))
      if (ele.empty()) continue
      const label = edgeLabel(e)
      if (ele.data('edgeType') !== label) ele.data('edgeType', label)
      const weight = edgeWeight(e)
      if (ele.data('weight') !== weight) ele.data('weight', weight)
      // An edge can gain a pinned endpoint after it was added (the user just
      // expanded one of its people), which turns it into an attribute spoke.
      const isSpoke = pinnedNodes.has(e.src) || pinnedNodes.has(e.dst)
      if (isSpoke !== ele.hasClass('edge-spoke')) ele.toggleClass('edge-spoke', isSpoke)
    }

    // Only run the layout when nodes appear that have never had a position
    // (initial load, an expansion, a search hit). Re-showing filtered nodes
    // and toggling edge types keep the existing layout untouched, so the
    // graph no longer reshuffles on every filter click.
    if (brandNewCount > 0) {
      const layout = layoutFreeNodes(cy, pinnedNodes, !hadNodesBefore)
      layout.one('layoutstop', () => {
        // Cache the settled positions of everything, then make sure the
        // result is actually on screen.
        cy.nodes().forEach((ele) => { positionsRef.current.set(ele.id(), { ...ele.position() }) })
        applyPinnedPositions(cy, pinnedNodes)
        onPositionsSettledRef.current?.(new Map(positionsRef.current))
        if (!hadNodesBefore) cy.fit(undefined, 40)
        else ensureGraphVisible(cy)
      })
      layout.run()
    } else {
      applyPinnedPositions(cy, pinnedNodes)
      if (newNodeEles.length > 0 || newEdgeEles.length > 0) ensureGraphVisible(cy)
    }
  }, [nodes, edges, mainTags, pinnedNodes])

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

  // Tag breakdown for the bottom legend bar, mirroring kindred's persistent
  // node-kind legend (there it's a fixed 4-kind list; here tags are
  // schema-driven, so this is the top tags actually present, by count).
  const legend = useMemo(() => {
    const counts = new Map<string, number>()
    for (const n of nodes) {
      const tag = n.tags[0] ?? 'entity'
      counts.set(tag, (counts.get(tag) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8)
  }, [nodes])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%' }}>
      <div style={{ position: 'relative', flex: 1, minHeight: 0, background: CANVAS_BG }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        <GraphPopup info={popupInfo} pinned={pinned} onClose={closePopup} />
      </div>
      <div className="graph-legend">
        {legend.map(([tag, count]) => (
          <span key={tag} className="graph-legend__item">
            <span className="graph-legend__dot" style={{ background: colorForTag(tag) }} />
            {tag} ({count})
          </span>
        ))}
        <span className="graph-legend__spacer" />
        <span>
          {nodes.length} node{nodes.length === 1 ? '' : 's'} · {edges.length} link{edges.length === 1 ? '' : 's'}
        </span>
      </div>
    </div>
  )
})

export default GraphCanvas
