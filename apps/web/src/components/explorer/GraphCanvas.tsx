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
