import { useEffect, useImperativeHandle, useRef, forwardRef, useCallback } from 'react'
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { GraphEdge, GraphNode } from '../../api/types'
import { colorForTag, edgeId, edgeLabel, roleForNode } from './graphStyle'

cytoscape.use(fcose)

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
      width: 18,
      height: 18,
      'border-width': 1.5,
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
      width: 10,
      height: 10,
      'font-size': 8,
      'border-width': 1,
      opacity: 0.75,
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
 * handful on screen. */
const FCOSE_LAYOUT_BASE = {
  name: 'fcose',
  animate: false,
  quality: 'draft',
  fit: false,
  nodeRepulsion: 12000,
  idealEdgeLength: 130,
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
    cy.on('mouseover', 'edge', (evt) => evt.target.addClass('edge-hover'))
    cy.on('mouseout', 'edge', (evt) => evt.target.removeClass('edge-hover'))

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
        // fcose's options (animate/randomize/nodeRepulsion/...) aren't part of
        // @types/cytoscape's built-in layout typings, hence the cast.
        cy.layout({ ...FCOSE_LAYOUT_BASE, randomize: false } as unknown as cytoscape.LayoutOptions).run()
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
    }

    // Only run the layout when nodes appear that have never had a position
    // (initial load, an expansion, a search hit). Re-showing filtered nodes
    // and toggling edge types keep the existing layout untouched, so the
    // graph no longer reshuffles on every filter click.
    if (brandNewCount > 0) {
      // fcose's options (animate/randomize/nodeRepulsion/...) aren't part of
      // @types/cytoscape's built-in layout typings, hence the cast.
      const layout = cy.layout(
        { ...FCOSE_LAYOUT_BASE, randomize: !hadNodesBefore } as unknown as cytoscape.LayoutOptions,
      )
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
    cy.edges().removeClass('edge-highlight')
    if (selectedVid) {
      const node = cy.getElementById(selectedVid)
      node.select()
      node.connectedEdges().addClass('edge-highlight')
    }
  }, [selectedVid])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
})

export default GraphCanvas
